"""
Reusable data and extraction pipeline for the coursework system.

The pipeline intentionally copies the useful corpus from INFO_RETRIEVE into this
project's own data directory. After that conversion, INFO_RETRIEVE is no longer
needed for running the information extraction system.
"""
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config import (
    DEFAULT_BASIC_RESULTS_FILE,
    DEFAULT_CORPUS_FILE,
    DEFAULT_NLP_RESULTS_CSV,
    DEFAULT_NLP_RESULTS_FILE,
    DEFAULT_OPEN_NLP_RESULTS_CSV,
    DEFAULT_OPEN_NLP_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
    DEFAULT_REGEX_RESULTS_FILE,
    EXTRACTION_FIELDS,
    INFO_RETRIEVE_DOCUMENTS_FILE,
    RAW_NEWS_DIR,
)
from extractor.regex_extractor import BasicRegexExtractor, RegexExtractor
from extractor.opensource_nlp_extractor import OpenSourceNLPExtractor
from utils.helpers import load_json, save_json


def _stable_article_id(doc: Dict[str, Any], fallback_idx: int) -> str:
    raw_id = doc.get("id")
    if raw_id is not None and str(raw_id) != "":
        return f"ir_{raw_id}"
    seed = f"{doc.get('url', '')}|{doc.get('title', '')}|{fallback_idx}"
    return "ir_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]


def _pick_text(doc: Dict[str, Any]) -> str:
    for key in ("content", "text", "body", "summary"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def convert_retrieve_documents(
    source_file: str = INFO_RETRIEVE_DOCUMENTS_FILE,
    output_file: str = DEFAULT_CORPUS_FILE,
) -> Dict[str, Any]:
    """Convert INFO_RETRIEVE documents to the event extraction corpus format."""
    if not os.path.exists(source_file):
        raise FileNotFoundError(
            f"未找到作业2语料文件: {source_file}. "
            f"如果 INFO_RETRIEVE 已删除，请直接使用已生成的 {output_file}。"
        )

    docs = load_json(source_file)
    if not isinstance(docs, list):
        raise ValueError("作业2 documents.json 应为文档列表")

    articles: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        if not isinstance(doc, dict):
            continue
        content = _pick_text(doc)
        title = str(doc.get("title") or "").strip()
        if not title and not content:
            continue

        summary = content[:300] + "..." if len(content) > 300 else content
        article = {
            "id": _stable_article_id(doc, idx),
            "source_doc_id": doc.get("id", idx),
            "title": title or content[:80],
            "summary": summary,
            "content": content,
            "url": str(doc.get("url") or ""),
            "source": str(doc.get("source") or "未知来源"),
            "source_key": str(doc.get("source") or "未知来源"),
            "publish_time": str(doc.get("date") or ""),
            "crawled_at": doc.get("crawled_at"),
        }
        articles.append(article)

    output = {
        "metadata": {
            "total": len(articles),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_file": source_file,
            "domain": "中文科技新闻中的核心技术产品发布与升级事件",
            "fields": EXTRACTION_FIELDS,
            "note": "由作业2本地语料转换生成，作业3运行不再依赖 INFO_RETRIEVE 目录。",
        },
        "articles": articles,
    }
    save_json(output, output_file)
    return output


def load_corpus(corpus_file: str = DEFAULT_CORPUS_FILE) -> Dict[str, Any]:
    if not os.path.exists(corpus_file):
        if os.path.exists(INFO_RETRIEVE_DOCUMENTS_FILE):
            return convert_retrieve_documents(output_file=corpus_file)
        if corpus_file == DEFAULT_CORPUS_FILE:
            candidates = [
                os.path.join(RAW_NEWS_DIR, name)
                for name in os.listdir(RAW_NEWS_DIR)
                if name.endswith(".json")
            ]
            if candidates:
                latest = max(candidates, key=os.path.getmtime)
                data = load_json(latest)
                if isinstance(data, dict) and isinstance(data.get("articles"), list):
                    return data
        raise FileNotFoundError(f"未找到作业3语料文件: {corpus_file}")
    data = load_json(corpus_file)
    if isinstance(data, dict) and isinstance(data.get("articles"), list):
        return data
    raise ValueError(f"语料文件格式错误: {corpus_file}")


def corpus_stats(corpus: Dict[str, Any]) -> Dict[str, Any]:
    articles = corpus.get("articles", [])
    sources = Counter(a.get("source") or a.get("source_key") or "未知来源" for a in articles)
    return {
        "total_articles": len(articles),
        "source_count": len(sources),
        "sources": dict(sources.most_common()),
        "fields": EXTRACTION_FIELDS,
    }


def _result_row(
    article: Dict[str, Any],
    extraction: Dict[str, Optional[str]],
    extractor_name: str,
) -> Dict[str, Any]:
    row = {
        "article_id": article.get("id", ""),
        "title": article.get("title", ""),
        "source": article.get("source") or article.get("source_key") or "",
        "url": article.get("url", ""),
        "publish_time": article.get("publish_time", ""),
        "extractor": extractor_name,
    }
    for field in EXTRACTION_FIELDS:
        row[field] = extraction.get(field)
    for key in ("llm_used", "api_failed", "llm_error", "llm_model", "llm_postprocessed"):
        if key in extraction:
            row[key] = extraction.get(key)
    row["event_complete_fields"] = sum(1 for field in EXTRACTION_FIELDS if row.get(field))
    return row


def run_extraction(
    corpus_file: str = DEFAULT_CORPUS_FILE,
    output_file: str = DEFAULT_REGEX_RESULTS_FILE,
    output_csv: Optional[str] = DEFAULT_REGEX_RESULTS_CSV,
    extractor_name: str = "optimized",
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Run batch extraction and persist JSON/CSV outputs."""
    corpus = load_corpus(corpus_file)
    articles = corpus.get("articles", [])
    if limit is not None and limit > 0:
        articles = articles[:limit]

    if extractor_name == "basic":
        extractor = BasicRegexExtractor()
    elif extractor_name in ("open_nlp", "opensource_nlp", "jieba"):
        extractor = OpenSourceNLPExtractor()
    elif extractor_name in ("nlp", "llm", "api"):
        from extractor.nlp_extractor import NLPExtractor

        extractor = NLPExtractor()
    else:
        extractor = RegexExtractor()

    rows = [_result_row(article, extractor.extract(article), extractor.name) for article in articles]
    output = {
        "metadata": {
            "total": len(rows),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "corpus_file": corpus_file,
            "extractor": extractor.name,
            "requested_extractor": extractor_name,
            "limit": limit,
            "fields": EXTRACTION_FIELDS,
        },
        "results": rows,
    }
    save_json(output, output_file)

    if output_csv:
        save_results_csv(rows, output_csv)
    return output


def run_algorithm_comparison(
    corpus_file: str = DEFAULT_CORPUS_FILE,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Generate baseline and optimized outputs for report comparison."""
    basic = run_extraction(
        corpus_file=corpus_file,
        output_file=DEFAULT_BASIC_RESULTS_FILE,
        output_csv=None,
        extractor_name="basic",
    )
    optimized = run_extraction(
        corpus_file=corpus_file,
        output_file=DEFAULT_REGEX_RESULTS_FILE,
        output_csv=DEFAULT_REGEX_RESULTS_CSV,
        extractor_name="optimized",
    )
    return basic, optimized


def run_selectable_extraction(
    extractor_name: str,
    corpus_file: str = DEFAULT_CORPUS_FILE,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one selected extractor and save it to the matching output path."""
    normalized = extractor_name.lower()
    if normalized in ("nlp", "llm", "api"):
        return run_extraction(
            corpus_file=corpus_file,
            output_file=DEFAULT_NLP_RESULTS_FILE,
            output_csv=DEFAULT_NLP_RESULTS_CSV,
            extractor_name="nlp",
            limit=limit,
        )
    if normalized in ("open_nlp", "opensource_nlp", "jieba"):
        return run_extraction(
            corpus_file=corpus_file,
            output_file=DEFAULT_OPEN_NLP_RESULTS_FILE,
            output_csv=DEFAULT_OPEN_NLP_RESULTS_CSV,
            extractor_name="open_nlp",
            limit=limit,
        )
    if normalized == "basic":
        return run_extraction(
            corpus_file=corpus_file,
            output_file=DEFAULT_BASIC_RESULTS_FILE,
            output_csv=None,
            extractor_name="basic",
            limit=limit,
        )
    return run_extraction(
        corpus_file=corpus_file,
        output_file=DEFAULT_REGEX_RESULTS_FILE,
        output_csv=DEFAULT_REGEX_RESULTS_CSV,
        extractor_name="optimized",
        limit=limit,
    )


def save_results_csv(rows: Iterable[Dict[str, Any]], output_csv: str) -> None:
    rows = list(rows)
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    fieldnames = [
        "article_id",
        "title",
        "source",
        "url",
        "publish_time",
        *EXTRACTION_FIELDS,
        "event_complete_fields",
        "extractor",
    ]
    for key in ("llm_used", "api_failed", "llm_error", "llm_model", "llm_postprocessed"):
        if any(key in row for row in rows):
            fieldnames.append(key)
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def extraction_stats(results_data: Dict[str, Any]) -> Dict[str, Any]:
    rows = results_data.get("results", [])
    by_field = {
        field: sum(1 for row in rows if row.get(field))
        for field in EXTRACTION_FIELDS
    }
    complete_events = sum(
        1 for row in rows if sum(1 for field in EXTRACTION_FIELDS if row.get(field)) >= 4
    )
    action_counts = Counter(row.get("action_type") or "未抽取" for row in rows)
    return {
        "total_results": len(rows),
        "by_field": by_field,
        "complete_events": complete_events,
        "top_actions": dict(action_counts.most_common(10)),
    }


def is_good_demo_event(row: Dict[str, Any]) -> bool:
    """Pick readable examples for CLI demos and screenshots."""
    product = str(row.get("tech_product") or "")
    return (
        bool(row.get("developer"))
        and bool(product)
        and bool(row.get("action_type"))
        and bool(row.get("date"))
        and len(product) <= 24
        and not any(mark in product for mark in ("证据", "目前关于", "阿视亚经济", "脑干", "脊椎"))
    )


def select_demo_rows(rows: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    selected = [row for row in rows if is_good_demo_event(row)]
    if len(selected) < limit:
        selected.extend(row for row in rows if row not in selected)
    return selected[:limit]
