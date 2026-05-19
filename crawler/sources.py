"""
新闻源配置模块 —— 定义各平台的搜索 URL 模板与解析规则
"""
import re
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any


@dataclass
class NewsSource:
    name: str
    base_url: str
    search_url: str
    keywords: List[str] = field(default_factory=list)
    article_link_selector: str = ""
    title_selector: str = ""
    content_selector: str = ""
    date_selector: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

    def build_search_url(self, keyword: str, page: int = 1) -> str:
        return self.search_url.format(keyword=keyword, page=page)


def _36kr_parse_articles(html: str) -> List[Dict[str, Any]]:
    """36氪 搜索结果解析"""
    import json
    articles = []
    try:
        data = json.loads(html)
        items = data.get("data", {}).get("items", [])
        for item in items:
            articles.append({
                "title": item.get("title", ""),
                "url": f"https://36kr.com/p/{item.get('id', '')}",
                "summary": item.get("summary", ""),
                "publish_time": item.get("published_at", ""),
                "source": "36氪",
            })
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return articles


def _pedaily_parse_articles(html: str) -> List[Dict[str, Any]]:
    """投资界 搜索结果解析"""
    from bs4 import BeautifulSoup
    articles = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".news-list .news-item")
        if not items:
            items = soup.select(".list-ul li")
        for item in items:
            link_tag = item.find("a")
            title = link_tag.get_text(strip=True) if link_tag else ""
            url = link_tag.get("href", "") if link_tag else ""
            if url and not url.startswith("http"):
                url = "https://www.pedaily.cn" + url
            date_tag = item.find("span", class_=re.compile("time|date"))
            publish_time = date_tag.get_text(strip=True) if date_tag else ""
            articles.append({
                "title": title,
                "url": url,
                "summary": "",
                "publish_time": publish_time,
                "source": "投资界",
            })
    except Exception:
        pass
    return articles


def _itjuzi_parse_search(html: str) -> List[Dict[str, Any]]:
    """IT桔子 搜索结果解析"""
    from bs4 import BeautifulSoup
    articles = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".list-item, .search-item, .block-item")
        for item in items:
            link_tag = item.find("a")
            title = link_tag.get_text(strip=True) if link_tag else ""
            url = link_tag.get("href", "") if link_tag else ""
            if url and not url.startswith("http"):
                url = "https://www.itjuzi.com" + url
            articles.append({
                "title": title,
                "url": url,
                "summary": item.get_text(strip=True)[:200] if title else "",
                "publish_time": "",
                "source": "IT桔子",
            })
    except Exception:
        pass
    return articles


ALL_SOURCES: Dict[str, tuple] = {
    "36kr": (NewsSource(
        name="36氪",
        base_url="https://36kr.com",
        search_url="https://36kr.com/api/search/article?q={keyword}&page={page}&per_page=20",
        keywords=["融资", "投资", "A轮", "B轮", "C轮", "D轮", "天使轮"],
        headers={
            "Referer": "https://36kr.com/",
            "Accept": "application/json",
        },
    ), _36kr_parse_articles),
    "pedaily": (NewsSource(
        name="投资界",
        base_url="https://www.pedaily.cn",
        search_url="https://www.pedaily.cn/search?k={keyword}&p={page}",
        keywords=["融资", "投资", "VC", "PE"],
        headers={
            "Referer": "https://www.pedaily.cn/",
        },
    ), _pedaily_parse_articles),
    "itjuzi": (NewsSource(
        name="IT桔子",
        base_url="https://www.itjuzi.com",
        search_url="https://www.itjuzi.com/search?key={keyword}&page={page}",
        keywords=["融资"],
        headers={
            "Referer": "https://www.itjuzi.com/",
        },
    ), _itjuzi_parse_search),
}
