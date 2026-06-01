"""
High-Performance Asynchronous Web Crawler
Using asyncio + aiohttp for concurrent I/O operations.

Performance comparison:
- Traditional synchronous crawler: ~1-2 pages/second
- Async crawler: ~50-100 pages/second (limited by politeness)

References:
[1] asyncio - Asynchronous I/O. Python Documentation.
[2] aiohttp - Async HTTP client/server. https://docs.aiohttp.org/
"""

import asyncio
import aiohttp
import aiofiles
from aiohttp import ClientTimeout, TCPConnector
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import json
import os
import random
from datetime import datetime

from config import (
    CRAWL_MIN_DOCS, CRAWL_TIMEOUT, CRAWL_MAX_DOCS,
    DOCUMENTS_FILE, CRAWL_SOURCES
)
from crawler.data_cleaner import clean_documents, clean_text

MAX_CONCURRENT = 20
CONNECTION_TIMEOUT = ClientTimeout(total=CRAWL_TIMEOUT, connect=5)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def extract_text_from_html(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "noscript", "iframe", "form", "button", "input", "textarea",
                     "select", "option", "svg", "canvas"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text


def resolve_url(href, list_url):
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    parsed = urlparse(list_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if href.startswith("/"):
        return base + href
    dir_path = parsed.path.rsplit("/", 1)[0] if "/" in parsed.path else ""
    return f"{base}{dir_path}/{href}"


class AsyncWebCrawler:

    def __init__(self, max_concurrent=MAX_CONCURRENT, sources=None):
        self.documents = []
        self.seen_urls = set()
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.sources = sources or [s for s in CRAWL_SOURCES if s.get("enabled", True)]
        self.stats = {
            "fetched": 0,
            "failed": 0,
            "skipped": 0,
            "cleaned_removed": 0,
        }
        self.source_contributions = {}

        if os.path.exists(DOCUMENTS_FILE):
            try:
                with open(DOCUMENTS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if existing:
                    self.documents = existing
                    self.seen_urls = {d["url"] for d in existing}
                    print(f"[AsyncCrawler] Loaded {len(self.documents)} existing documents.")
            except Exception as e:
                print(f"[AsyncCrawler] Warning: Could not load existing docs: {e}")

    async def _fetch_with_retry(self, session, url, retries=3):
        for attempt in range(retries):
            try:
                async with self.semaphore:
                    async with session.get(
                        url,
                        headers=get_random_headers(),
                        timeout=CONNECTION_TIMEOUT,
                        allow_redirects=True,
                        ssl=False,
                    ) as response:
                        if response.status == 200:
                            content_type = response.headers.get("Content-Type", "")
                            if "text/html" not in content_type and "text/plain" not in content_type:
                                return None
                            html = await response.text()
                            return html
                        elif response.status in (301, 302, 307, 308):
                            return None
                        elif response.status in (429, 503):
                            wait = 2 ** attempt + random.uniform(0, 1)
                            await asyncio.sleep(wait)
                        else:
                            return None
            except (asyncio.TimeoutError, aiohttp.ClientError,
                    aiohttp.ServerDisconnectedError, aiohttp.ClientConnectorError):
                if attempt < retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
        return None

    async def _extract_article_urls(self, session, list_url, source_config):
        html = await self._fetch_with_retry(session, list_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        urls = []
        patterns = source_config.get("article_url_patterns", [])

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(pattern in href for pattern in patterns):
                resolved = resolve_url(href, list_url)
                if resolved and resolved not in self.seen_urls:
                    urls.append(resolved)

        return list(set(urls))

    async def _parse_article(self, session, url, source_config):
        html = await self._fetch_with_retry(session, url)
        if not html:
            self.stats["failed"] += 1
            return None

        soup = BeautifulSoup(html, "lxml")

        # --- Title ---
        title_tag = (
            soup.find("h1") or
            soup.find("h2", class_=re.compile(r"title", re.I)) or
            soup.find("title")
        )
        title = title_tag.get_text(strip=True) if title_tag else "无标题"
        # Remove site name suffix
        title = re.sub(r'[-_|].*$', '', title).strip()
        if len(title) > 200:
            title = title[:200]

        # --- Date ---
        date_str = ""
        date_format = source_config.get("date_format", r"(\d{4}-\d{2}-\d{2})")
        # Try configured patterns first
        for pat in date_format.split("|"):
            pat = pat.strip("() ")
            m = re.search(pat, html)
            if m:
                date_str = m.group(0)
                # Normalize to ISO
                date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "")
                date_str = date_str.replace("/", "-")
                break
        # Fallback: scan for any date-like pattern in the HTML
        if not date_str:
            m = re.search(r'(202[0-9]-\d{2}-\d{2})', html)
            if m:
                date_str = m.group(1)

        # --- Content ---
        content_selectors = source_config.get("content_selectors", [])
        content_div = None
        for selector in content_selectors:
            tag = selector.get("tag", "div")
            find_kwargs = {}
            for k, v in selector.items():
                if k == "tag":
                    continue
                if k == "id":
                    find_kwargs["id"] = v
                elif k == "class_":
                    find_kwargs["class_"] = re.compile(v, re.I)
            try:
                content_div = soup.find(tag, **find_kwargs) if find_kwargs else soup.find(tag)
            except Exception:
                content_div = None
            if content_div:
                break

        # Generic fallback: try common article containers
        if not content_div:
            for cls in ["article", "content", "post", "entry", "detail", "main", "body", "text"]:
                content_div = soup.find(class_=re.compile(cls, re.I))
                if content_div:
                    break
        if not content_div:
            content_div = soup.find("article") or soup.find("main")

        if content_div:
            text = extract_text_from_html(str(content_div))
        else:
            text = extract_text_from_html(html)

        text = clean_text(text)
        title = clean_text(title)

        if len(text.strip()) < 100:
            self.stats["skipped"] += 1
            return None

        self.stats["fetched"] += 1
        return {
            "url": url,
            "title": title,
            "text": text,
            "date": date_str,
        }

    async def _worker(self, session, url_queue, results_queue, source_config):
        while True:
            try:
                url = await asyncio.wait_for(url_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
            if url is None:
                break
            article = await self._parse_article(session, url, source_config)
            if article:
                await results_queue.put(article)
            await asyncio.sleep(random.uniform(0.08, 0.2))

    async def _results_collector(self, results_queue):
        while len(self.documents) < CRAWL_MAX_DOCS:
            try:
                article = await asyncio.wait_for(results_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                if results_queue.empty():
                    break
                continue
            if article is None:
                break
            if article["url"] not in self.seen_urls:
                doc_id = len(self.documents)
                self.documents.append({
                    **article,
                    "id": doc_id,
                    "crawled_at": datetime.now().isoformat(),
                })
                self.seen_urls.add(article["url"])
                print(f"  [{len(self.documents)}] {article['title'][:50]}")
                if len(self.documents) % 20 == 0:
                    await self._async_save()

    async def _async_save(self):
        os.makedirs(os.path.dirname(DOCUMENTS_FILE), exist_ok=True)
        try:
            async with aiofiles.open(DOCUMENTS_FILE, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self.documents, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[AsyncCrawler] Save error: {e}")

    async def _crawl_one_source(self, source_config):
        name = source_config.get("name", "Unknown")
        print(f"\n  [{name}] Getting article URLs...")
        list_urls = source_config.get("list_urls", [])

        connector = TCPConnector(
            limit=self.max_concurrent,
            limit_per_host=5,
            enable_cleanup_closed=True,
            force_close=True,
        )

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=CONNECTION_TIMEOUT,
        ) as session:
            # Extract article URLs from all list pages
            all_article_urls = []
            for list_url in list_urls:
                urls = await self._extract_article_urls(session, list_url, source_config)
                all_article_urls.extend(urls)
                print(f"    List page [{list_url[-30:]}]: {len(urls)} candidates")

                if len(self.documents) >= CRAWL_MAX_DOCS:
                    break
            all_article_urls = list(set(all_article_urls))
            random.shuffle(all_article_urls)
            print(f"  [{name}] Total unique candidates: {len(all_article_urls)}")

            if not all_article_urls:
                print(f"  [{name}] WARNING: No article URLs found. Site structure may have changed.")
                return 0

            # Fetch articles concurrently
            queue = asyncio.Queue()
            results = asyncio.Queue()

            for url in all_article_urls[:CRAWL_MAX_DOCS]:
                await queue.put(url)

            workers = [
                asyncio.create_task(self._worker(session, queue, results, source_config))
                for _ in range(min(8, len(all_article_urls)))
            ]
            collector = asyncio.create_task(self._results_collector(results))

            await asyncio.gather(*workers)
            await results.put(None)
            await collector

        return self.stats["fetched"]

    async def crawl_all(self):
        print(f"[AsyncCrawler] Target: {CRAWL_MIN_DOCS}-{CRAWL_MAX_DOCS} docs")
        print(f"[AsyncCrawler] Max concurrent: {self.max_concurrent}")
        print(f"[AsyncCrawler] Sources: {len(self.sources)}")

        for i, source in enumerate(self.sources):
            if len(self.documents) >= CRAWL_MAX_DOCS:
                break
            before = len(self.documents)
            try:
                await self._crawl_one_source(source)
            except Exception as e:
                print(f"  Source error [{source.get('name')}]: {e}")
            after = len(self.documents)
            gained = after - before
            self.source_contributions[source["name"]] = gained
            print(f"  [{source['name']}] +{gained} docs (total: {after})")

        # Clean
        before_clean = len(self.documents)
        self.documents = clean_documents(self.documents)
        self.stats["cleaned_removed"] = before_clean - len(self.documents)

        await self._async_save()

        print(f"\n[AsyncCrawler] Complete!")
        print(f"  Final count: {len(self.documents)}")
        print(f"  Fetched: {self.stats['fetched']}")
        print(f"  Failed: {self.stats['failed']}")
        print(f"  Skipped: {self.stats['skipped']}")
        print(f"  Cleaned: {self.stats['cleaned_removed']}")
        if self.source_contributions:
            print(f"  By source: {json.dumps(self.source_contributions, ensure_ascii=False)}")

        if len(self.documents) < CRAWL_MIN_DOCS:
            print(f"  WARNING: Only got {len(self.documents)} docs, target is {CRAWL_MIN_DOCS}.")
            print(f"  Try running again or check network connectivity.")

        return self.documents


def run_async_crawl():
    crawler = AsyncWebCrawler(max_concurrent=MAX_CONCURRENT)
    try:
        return asyncio.run(crawler.crawl_all())
    except KeyboardInterrupt:
        print("\n[AsyncCrawler] Interrupted. Saving partial results...")
        asyncio.run(crawler._async_save())
        return crawler.documents


def get_document_count():
    if os.path.exists(DOCUMENTS_FILE):
        try:
            with open(DOCUMENTS_FILE, "r") as f:
                return len(json.load(f))
        except Exception:
            pass
    return 0


def needs_crawling():
    return get_document_count() < CRAWL_MIN_DOCS


if __name__ == "__main__":
    docs = run_async_crawl()
    print(f"Done. {len(docs)} documents collected.")
