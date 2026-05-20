"""
科技技术新闻源配置模块 - 超级高容错通用解析 + 分页支持
配置反爬极宽松、纯静态、量极大的国内顶级科技开源媒体
"""
import re
import logging
from urllib.parse import urljoin
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class NewsSource:
    name: str
    base_url: str
    news_list_url: str  # 注意：这里我们让它支持 format 传入页码
    keywords: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    parser_func: Optional[Callable] = None

    def build_url(self, page: int = 1) -> str:
        # 支持传入页码动态生成，比如 `https://www.oschina.net/news?p=2`
        try:
            return self.news_list_url.format(page=page)
        except Exception:
            return self.news_list_url


def _generic_list_parser(html: str, base_url: str, source_name: str) -> List[Dict[str, Any]]:
    """
    超级高容错通用列表页解析器：
    1. 找所有 a 标签
    2. 任何 URL 都提取（包含相对路径、绝对路径）
    3. urljoin 智能补全
    4. 去重，每个标签文本长度大于 5
    """
    articles = []
    seen_hrefs = set()
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. 遍历所有 a 标签
        all_links = soup.find_all("a", href=True)
        logger.debug(f"[{source_name}] 找到 {len(all_links)} 个 a 标签")
        
        for a_tag in all_links:
            href = a_tag.get("href", "")
            if not href:
                continue
                
            title = a_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue
                
            # 2. URL 智能化补全
            full_url = urljoin(base_url, href)
            
            # 3. 任何看起来像文章的链接都要
            # 排除明显不是文章的
            exclude_patterns = [
                "#", "javascript:", "mailto:", "tel:",
                "login", "register", "signup", "logout",
                ".jpg", ".png", ".gif", ".pdf", ".zip"
            ]
            
            is_valid = True
            for pat in exclude_patterns:
                if pat in full_url.lower():
                    is_valid = False
                    break
                    
            # 必须是 HTTP
            if not (full_url.startswith("http://") or full_url.startswith("https://")):
                is_valid = False
                
            if is_valid:
                if full_url not in seen_hrefs:
                    seen_hrefs.add(full_url)
                    articles.append({
                        "title": title,
                        "url": full_url,
                        "summary": "",
                        "publish_time": "",
                        "source": source_name,
                    })
                    if len(articles) >= 80:
                        break
                        
    except Exception as e:
        logger.error(f"[{source_name}] 列表页解析异常: {e}")
    
    logger.info(f"[{source_name}] 解析出 {len(articles)} 条新闻链接")
    return articles


def _oschina_parse(html: str) -> List[Dict[str, Any]]:
    """开源中国高容错解析器"""
    return _generic_list_parser(html, "https://www.oschina.net", "开源中国")


def _51cto_parse(html: str) -> List[Dict[str, Any]]:
    """51CTO高容错解析器"""
    return _generic_list_parser(html, "https://www.51cto.com", "51CTO")


def _infoq_parse(html: str) -> List[Dict[str, Any]]:
    """InfoQ高容错解析器"""
    return _generic_list_parser(html, "https://www.infoq.cn", "InfoQ")


def _segmentfault_parse(html: str) -> List[Dict[str, Any]]:
    """思否高容错解析器"""
    return _generic_list_parser(html, "https://segmentfault.com", "思否")


def _csdn_parse(html: str) -> List[Dict[str, Any]]:
    """CSDN高容错解析器"""
    return _generic_list_parser(html, "https://blog.csdn.net", "CSDN")


ALL_SOURCES: Dict[str, NewsSource] = {
    "oschina": NewsSource(
        name="开源中国",
        base_url="https://www.oschina.net",
        # 增加页码控制占位符
        news_list_url="https://www.oschina.net/news?p={page}",
        keywords=["开源", "架构", "发布", "升级"],
        parser_func=_oschina_parse,
        headers={
            "Referer": "https://www.oschina.net/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ),
    "51cto": NewsSource(
        name="51CTO",
        base_url="https://www.51cto.com",
        news_list_url="https://www.51cto.com/",
        keywords=["开源", "架构", "发布", "升级"],
        parser_func=_51cto_parse,
        headers={
            "Referer": "https://www.51cto.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ),
    "infoq": NewsSource(
        name="InfoQ",
        base_url="https://www.infoq.cn",
        news_list_url="https://www.infoq.cn/news",
        keywords=["开源", "架构", "发布", "升级"],
        parser_func=_infoq_parse,
        headers={
            "Referer": "https://www.infoq.cn/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ),
    "segmentfault": NewsSource(
        name="思否",
        base_url="https://segmentfault.com",
        # 思否是通过 offset 来控制分页的，一页30条
        news_list_url="https://segmentfault.com/news?offset={page}0",
        keywords=["开源", "架构", "发布", "升级"],
        parser_func=_segmentfault_parse,
        headers={
            "Referer": "https://segmentfault.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ),
    "csdn": NewsSource(
        name="CSDN",
        base_url="https://blog.csdn.net",
        news_list_url="https://blog.csdn.net/rank/list/page/{page}",
        keywords=["开源", "架构", "发布", "升级"],
        parser_func=_csdn_parse,
        headers={
            "Referer": "https://blog.csdn.net/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ),
}
