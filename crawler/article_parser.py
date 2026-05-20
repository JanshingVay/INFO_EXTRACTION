"""
高质量文章详情页解析器 —— 基于真实 HTML 结构

针对 36氪 文章详情页设计，提取：
- 标题 (article-title)
- 发布时间 (item-time)
- 摘要 (summary)
- 正文 (articleDetailContent 下的所有 <p>)
"""
import re
import logging
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


def parse_36kr_article(html: str) -> Dict[str, Any]:
    """
    解析 36氪 文章详情页

    HTML 结构特征（基于真实页面分析）：
      <h1 class="article-title">一向擅长赢的马斯克，这次输了</h1>
      <span class="title-icon-item item-time">·2026年05月19日 19:33</span>
      <div class="summary">真正的厮杀才刚刚开始。</div>
      <div class="content articleDetailContent kr-rich-text-wrapper">
        <p>一向擅长赢的埃隆·马斯克，输了。</p>
        <p>2026年5月18日，...</p>
        ...
      </div>
    """
    result = {
        "title": "",
        "publish_time": "",
        "summary": "",
        "content": "",
        "source": "36氪",
    }

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. 提取标题
        title_tag = soup.find("h1", class_="article-title")
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)

        # 2. 提取发布时间
        time_tag = soup.find("span", class_="item-time")
        if time_tag:
            time_text = time_tag.get_text(strip=True)
            # 去除前缀 "·"
            result["publish_time"] = time_text.lstrip("·").strip()

        # 3. 提取摘要
        summary_tag = soup.find("div", class_="summary")
        if summary_tag:
            result["summary"] = summary_tag.get_text(strip=True)

        # 4. 提取正文
        content_div = soup.find("div", class_="articleDetailContent")
        if content_div:
            # 提取所有 <p> 标签的文本
            paragraphs = content_div.find_all("p")
            content_lines = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    content_lines.append(text)
            result["content"] = "\n".join(content_lines)

        # 5. 备用：从 meta 标签提取
        if not result["title"]:
            meta_title = soup.find("meta", property="og:title")
            if meta_title:
                result["title"] = meta_title.get("content", "")

        if not result["publish_time"]:
            meta_time = soup.find("meta", property="article:published_time")
            if meta_time:
                result["publish_time"] = meta_time.get("content", "")

        if not result["summary"]:
            meta_desc = soup.find("meta", property="og:description")
            if meta_desc:
                result["summary"] = meta_desc.get("content", "")

    except Exception as e:
        logger.warning("36氪文章解析失败: %s", e)

    return result


def parse_generic_article(html: str, source_name: str = "") -> Dict[str, Any]:
    """
    通用文章解析器 —— 自动识别常见文章结构
    """
    result = {
        "title": "",
        "publish_time": "",
        "summary": "",
        "content": "",
        "source": source_name,
    }

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 删除干扰元素
        for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # 1. 标题（多种策略）
        title_selectors = [
            "h1.article-title",
            "h1.title",
            "h1.post-title",
            "h1.entry-title",
            "h1",
            ".article-title",
            ".post-title",
            ".entry-title",
        ]
        for sel in title_selectors:
            tag = soup.select_one(sel)
            if tag:
                result["title"] = tag.get_text(strip=True)
                break

        # 2. 发布时间
        time_patterns = [
            re.compile(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?"),
            re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
        ]
        time_tags = soup.find_all(class_=re.compile(r"time|date|publish", re.I))
        for t in time_tags:
            text = t.get_text(strip=True)
            for pat in time_patterns:
                m = pat.search(text)
                if m:
                    result["publish_time"] = m.group(0)
                    break
            if result["publish_time"]:
                break

        # 3. 摘要
        summary_selectors = [
            ".summary",
            ".abstract",
            ".description",
            ".excerpt",
        ]
        for sel in summary_selectors:
            tag = soup.select_one(sel)
            if tag:
                result["summary"] = tag.get_text(strip=True)
                break

        # 4. 正文（最长候选策略）
        content_selectors = [
            ".articleDetailContent",
            ".article-content",
            ".post-content",
            ".entry-content",
            ".content",
            "article",
        ]
        best_content = ""
        for sel in content_selectors:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(separator="\n", strip=True)
                if len(text) > len(best_content):
                    best_content = text
        result["content"] = best_content

    except Exception as e:
        logger.warning("通用文章解析失败: %s", e)

    return result
