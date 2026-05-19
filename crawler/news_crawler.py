"""
异步高并发新闻爬虫模块

特性:
- 基于 asyncio + aiohttp 的异步高并发架构
- 信号量控制并发上限，避免被封 IP
- 自动重试 + 指数退避
- 支持多源多关键词联合爬取
- 结果本地 JSON 持久化
"""
import asyncio
import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

import aiohttp
from aiohttp import ClientTimeout, ClientError

from config import CRAWLER_CONFIG, RAW_NEWS_DIR, NEWS_SOURCES
from crawler.sources import ALL_SOURCES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawler")


class AsyncNewsCrawler:
    """异步高并发新闻爬虫"""

    def __init__(
        self,
        max_concurrency: int = None,
        timeout: int = None,
        retry_times: int = None,
        rate_limit: float = None,
    ):
        self.max_concurrency = max_concurrency or CRAWLER_CONFIG["max_concurrency"]
        self.timeout = ClientTimeout(total=timeout or CRAWLER_CONFIG["request_timeout"])
        self.retry_times = retry_times or CRAWLER_CONFIG["retry_times"]
        self.rate_limit = rate_limit or CRAWLER_CONFIG["rate_limit"]
        self.user_agent = CRAWLER_CONFIG["user_agent"]

        self._semaphore: Optional[asyncio.Semaphore] = None
        self._last_request_time: float = 0.0
        self._seen_urls: Set[str] = set()
        self._results: List[Dict[str, Any]] = []
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def results(self) -> List[Dict[str, Any]]:
        return self._results

    async def _init_session(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrency + 5,
            limit_per_host=self.max_concurrency,
            ttl_dns_cache=300,
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        return self._session

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _rate_limit_wait(self):
        """速率控制：确保两次请求之间有足够间隔"""
        if self.rate_limit <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit:
            await asyncio.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.monotonic()

    def _build_url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    async def _fetch(
        self, url: str, headers: Dict[str, str] = None
    ) -> Optional[str]:
        """带重试机制的异步页面抓取"""
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)

        for attempt in range(1, self.retry_times + 1):
            try:
                await self._rate_limit_wait()
                async with self._session.get(
                    url, headers=req_headers, ssl=False
                ) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    elif resp.status == 429:
                        wait = 2 ** attempt + random.uniform(0, 1)
                        logger.warning(
                            "Rate limited on %s, retry %d/%d after %.1fs",
                            url[:80], attempt, self.retry_times, wait,
                        )
                        await asyncio.sleep(wait)
                    elif resp.status >= 500:
                        logger.warning(
                            "Server error %d on %s, retry %d/%d",
                            resp.status, url[:80], attempt, self.retry_times,
                        )
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.debug("HTTP %d for %s", resp.status, url[:80])
                        return None
            except (ClientError, asyncio.TimeoutError) as e:
                wait = 2 ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Request failed for %s: %s, retry %d/%d after %.1fs",
                    url[:80], type(e).__name__, attempt, self.retry_times, wait,
                )
                if attempt < self.retry_times:
                    await asyncio.sleep(wait)
        return None

    async def _crawl_source_keyword(
        self,
        source_key: str,
        keyword: str,
        max_pages: int = 3,
    ) -> List[Dict[str, Any]]:
        """爬取单个源 + 单个关键词的多页结果"""
        if source_key not in ALL_SOURCES:
            logger.error("Unknown source: %s", source_key)
            return []

        source, parser = ALL_SOURCES[source_key]
        articles: List[Dict[str, Any]] = []
        extra_headers = dict(source.headers) if source.headers else {}

        for page in range(1, max_pages + 1):
            url = source.build_search_url(keyword, page)
            logger.info("Crawling [%s] keyword=%s page=%d", source_key, keyword, page)

            async with self._semaphore:
                html = await self._fetch(url, headers=extra_headers)

            if html is None:
                logger.warning("Empty response for %s page=%d", source_key, page)
                continue

            try:
                page_articles = parser(html)
            except Exception as e:
                logger.error("Parse error for %s page=%d: %s", source_key, page, e)
                continue

            if not page_articles:
                logger.info("No more results for %s keyword=%s page=%d", source_key, keyword, page)
                break

            for art in page_articles:
                url_hash = self._build_url_hash(art.get("url", ""))
                if url_hash in self._seen_urls:
                    continue
                self._seen_urls.add(url_hash)
                art["source_key"] = source_key
                art["search_keyword"] = keyword
                art["crawled_at"] = datetime.now().isoformat()
                art["id"] = url_hash
                articles.append(art)

            logger.info("Got %d articles from %s page=%d", len(page_articles), source_key, page)
            await asyncio.sleep(0.5)

        return articles

    async def crawl_all(
        self,
        sources: List[str] = None,
        keywords: List[str] = None,
        max_pages_per_keyword: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        主入口：多源多关键词并发爬取

        Args:
            sources: 要爬取的源列表，None 表示全部
            keywords: 自定义关键词列表，None 则使用源默认关键词
            max_pages_per_keyword: 每个关键词最大翻页数

        Returns:
            所有去重后的新闻文章列表
        """
        await self._init_session()

        try:
            source_keys = sources or list(ALL_SOURCES.keys())
            tasks: List[asyncio.Task] = []

            for sk in source_keys:
                if sk not in ALL_SOURCES:
                    logger.warning("Skipping unknown source: %s", sk)
                    continue
                source, _ = ALL_SOURCES[sk]
                kws = keywords or source.keywords
                for kw in kws:
                    task = asyncio.create_task(
                        self._crawl_source_keyword(sk, kw, max_pages_per_keyword)
                    )
                    tasks.append(task)

            logger.info(
                "Starting crawl: %d sources × keywords = %d tasks, concurrency=%d",
                len(source_keys), len(tasks), self.max_concurrency,
            )

            all_results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(all_results):
                if isinstance(result, Exception):
                    logger.error("Task %d failed: %s", i, result)
                else:
                    self._results.extend(result)

            logger.info("Crawl completed: %d unique articles total", len(self._results))
            return self._results

        finally:
            await self._close_session()

    def save_results(self, filename: str = None) -> str:
        """将爬取结果保存为本地 JSON"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tech_investment_news_{timestamp}.json"

        filepath = os.path.join(RAW_NEWS_DIR, filename)

        output = {
            "metadata": {
                "total": len(self._results),
                "crawled_at": datetime.now().isoformat(),
                "sources": list(set(r.get("source_key", "") for r in self._results)),
                "version": "1.0",
            },
            "articles": self._results,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info("Saved %d articles to %s", len(self._results), filepath)
        return filepath

    @staticmethod
    def load_results(filepath: str) -> List[Dict[str, Any]]:
        """从 JSON 文件加载爬取结果"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("articles", data if isinstance(data, list) else [])


async def demo_crawl():
    """演示爬虫：自定义网页抓取 + 模拟数据生成（用于测试全流程）"""

    crawler = AsyncNewsCrawler(max_concurrency=5)

    articles = []
    now = datetime.now().isoformat()

    demo_data = [
        {
            "title": "字节跳动完成15亿美元D轮融资，红杉资本领投",
            "url": "https://example.com/news/1",
            "summary": "据知情人士透露，字节跳动已完成15亿美元D轮融资，本轮由红杉资本领投，腾讯、软银跟投。公司估值超过750亿美元。",
            "publish_time": "2026-01-15 10:30:00",
            "source_key": "36kr",
            "source": "36氪",
        },
        {
            "title": "AI芯片初创公司寒武纪获得中金公司10亿元B轮投资",
            "url": "https://example.com/news/2",
            "summary": "寒武纪科技宣布完成10亿元人民币B轮融资，投资方为中金公司、国投创业。资金将用于新一代AI芯片研发。",
            "publish_time": "2026-02-20 14:00:00",
            "source_key": "pedaily",
            "source": "投资界",
        },
        {
            "title": "智能驾驶公司小马智行完成3亿美元C轮融资",
            "url": "https://example.com/news/3",
            "summary": "小马智行（Pony.ai）宣布完成3亿美元C轮融资，由IDG资本领投，红杉中国、五源资本等跟投。",
            "publish_time": "2026-03-10 09:15:00",
            "source_key": "36kr",
            "source": "36氪",
        },
        {
            "title": "商汤科技获阿里巴巴领投的5亿美元Pre-IPO轮融资",
            "url": "https://example.com/news/4",
            "summary": "商汤科技今日宣布获得由阿里巴巴集团领投的5亿美元Pre-IPO轮融资，投后估值约120亿美元。",
            "publish_time": "2026-01-28 16:45:00",
            "source_key": "pedaily",
            "source": "投资界",
        },
        {
            "title": "生物科技公司华大智造完成2.5亿美元A+轮融资，高瓴资本投资",
            "url": "https://example.com/news/5",
            "summary": "华大智造宣布完成2.5亿美元A+轮融资，投资方包括高瓴资本、淡马锡等知名机构。",
            "publish_time": "2026-04-05 11:00:00",
            "source_key": "itjuzi",
            "source": "IT桔子",
        },
        {
            "title": "钉钉完成新一轮战略融资，投资方尚未披露",
            "url": "https://example.com/news/6",
            "summary": "阿里巴巴旗下钉钉据传已完成新一轮战略融资，具体金额和投资方尚未公开。",
            "publish_time": "2026-04-18 08:30:00",
            "source_key": "36kr",
            "source": "36氪",
        },
        {
            "title": "美团旗下龙珠资本投资新茶饮品牌'茶颜悦色'，金额达5000万美元",
            "url": "https://example.com/news/7",
            "summary": "茶颜悦色获得美团龙珠资本5000万美元（约合3.6亿人民币）战略投资，用于门店扩张和供应链建设。",
            "publish_time": "2026-02-14 17:20:00",
            "source_key": "pedaily",
            "source": "投资界",
        },
        {
            "title": "大疆创新完成1亿美元天使轮后续融资",
            "url": "https://example.com/news/8",
            "summary": "大疆创新近日完成1亿美元天使轮后续融资，本轮由深圳创新投资集团领投。这是今年无人机领域最大的一笔融资。",
            "publish_time": "2026-03-25 13:00:00",
            "source_key": "36kr",
            "source": "36氪",
        },
        {
            "title": "云从科技获中国互联网投资基金领投的8000万美元B+轮融资",
            "url": "https://example.com/news/9",
            "summary": "AI公司云从科技宣布完成8000万美元B+轮融资，由中国互联网投资基金领投，广州基金跟投。",
            "publish_time": "2026-05-01 10:00:00",
            "source_key": "pedaily",
            "source": "投资界",
        },
        {
            "title": "小米集团战略投资蔚来汽车，金额约2亿美元",
            "url": "https://example.com/news/10",
            "summary": "小米集团宣布战略投资蔚来汽车约2亿美元，双方将在智能电动汽车领域展开深度合作。",
            "publish_time": "2026-05-12 15:30:00",
            "source_key": "36kr",
            "source": "36氪",
        },
    ]

    for item in demo_data:
        url_hash = hashlib.md5(item["url"].encode()).hexdigest()
        item["id"] = url_hash
        item["search_keyword"] = "融资"
        item["crawled_at"] = now
        articles.append(item)

    crawler._results = articles

    filepath = crawler.save_results()
    print(f"\n✅ Demo crawl finished! {len(articles)} articles saved to:\n   {filepath}")
    return crawler


if __name__ == "__main__":
    asyncio.run(demo_crawl())
