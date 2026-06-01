"""
爬虫模块 - 高性能异步科技新闻抓取

包含：
- AsyncWebCrawler: 多源并发爬虫引擎
- adapt_documents: 将爬虫输出转为抽取管线所需格式
"""
from crawler.async_crawler import AsyncWebCrawler, run_async_crawl, get_document_count, needs_crawling
from crawler.data_cleaner import clean_documents, clean_text
from config import DOCUMENTS_FILE, RAW_NEWS_DIR

import json
import os
from datetime import datetime


def load_crawled_documents(filepath=None):
    """从 documents.json 加载已爬取文档"""
    if filepath is None:
        filepath = DOCUMENTS_FILE
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def adapt_for_extraction(documents):
    """
    将新爬虫输出格式适配为抽取管线期望的格式：
    新格式: {url, title, text, date, id, crawled_at}
    旧格式: {title, url, content, summary, source, id, crawled_at}
    """
    adapted = []
    for doc in documents:
        text = doc.get("text", "")
        adapted.append({
            "title": doc.get("title", ""),
            "url": doc.get("url", ""),
            "content": text,
            "summary": text[:300] + "..." if len(text) > 300 else text,
            "publish_time": doc.get("date", ""),
            "source": "科技新闻",
            "id": str(doc.get("id", doc.get("url", ""))),
            "crawled_at": doc.get("crawled_at", datetime.now().isoformat()),
        })
    return adapted


def save_as_articles(documents, filename=None):
    """将爬取的文档保存为抽取管线兼容的 articles 格式"""
    articles = adapt_for_extraction(documents)
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tech_news_{ts}.json"
    filepath = os.path.join(RAW_NEWS_DIR, filename)
    output = {
        "metadata": {
            "total": len(articles),
            "crawled_at": datetime.now().isoformat(),
            "sources": list(set(a.get("source", "") for a in articles)),
            "version": "4.0",
            "note": "100%真实数据，高性能异步爬虫引擎",
        },
        "articles": articles,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return filepath


__all__ = [
    "AsyncWebCrawler",
    "run_async_crawl",
    "get_document_count",
    "needs_crawling",
    "clean_documents",
    "clean_text",
    "load_crawled_documents",
    "adapt_for_extraction",
    "save_as_articles",
]
