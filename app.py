"""
科技事件信息抽取系统 — Streamlit 前端

自有爬虫直接采集 → 事件抽取 → 人工评价 → OCR 多媒体
"""
import asyncio
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    DEFAULT_EVAL_ANNOTATIONS_FILE,
    DEFAULT_EVAL_METRICS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
    DEFAULT_REGEX_RESULTS_FILE,
    DOCUMENTS_FILE,
    EXTRACTION_FIELDS,
    IMAGES_DIR,
    RAW_NEWS_DIR,
)
from evaluator.metrics import calculate_extraction_metrics
from extractor.regex_extractor import BasicRegexExtractor, RegexExtractor
from multimodal import MultimodalExtractor
from utils.helpers import load_json, save_json


st.set_page_config(page_title="科技事件信息抽取系统", layout="wide")
st.markdown(
    """<style>
    .block-container { padding-top: 1.3rem; padding-bottom: 2rem; }
    .event-panel { border:1px solid #e5e7eb; border-radius:8px; padding:14px 16px; background:#fff; }
    .crawl-log { max-height:300px; overflow-y:auto; background:#f8f9fa; border-radius:6px; padding:12px; font-family:monospace; font-size:13px; }
    </style>""",
    unsafe_allow_html=True,
)

FIELD_LABELS = {
    "developer": "研发主体",
    "tech_product": "技术产品",
    "action_type": "事件动作",
    "version_metric": "版本/指标",
    "date": "事件日期",
}

# ──────────────────────────────────────────────────
# 缓存数据加载
# ──────────────────────────────────────────────────

def _load_documents():
    """从 documents.json 加载爬虫采集的原始文档。"""
    if not os.path.exists(DOCUMENTS_FILE):
        return []
    try:
        return load_json(DOCUMENTS_FILE) or []
    except Exception:
        return []


def _adapt_and_cache():
    """将 documents.json 适配为 articles 格式并缓存到 raw_news/。"""
    from crawler import adapt_for_extraction, save_as_articles
    docs = _load_documents()
    if not docs:
        return []
    articles = adapt_for_extraction(docs)
    out_path = os.path.join(RAW_NEWS_DIR, "adapted_corpus.json")
    save_json({"metadata": {"total": len(articles), "adapted_at": datetime.now().isoformat()}, "articles": articles}, out_path)
    return articles


def _load_articles():
    """
    加载事件抽取所需的 articles 列表。
    优先级：raw_news/*.json → documents.json 适配
    """
    files = sorted(
        [f for f in os.listdir(RAW_NEWS_DIR) if f.endswith(".json") and f != ".gitkeep"],
        reverse=True,
    )
    if files:
        data = load_json(os.path.join(RAW_NEWS_DIR, files[0]))
        articles = data.get("articles", []) if isinstance(data, dict) else []
        if articles:
            return articles

    docs = _load_documents()
    if docs:
        from crawler import adapt_for_extraction
        return adapt_for_extraction(docs)
    return []


def _load_results():
    data = load_json(DEFAULT_REGEX_RESULTS_FILE) if os.path.exists(DEFAULT_REGEX_RESULTS_FILE) else {}
    return data.get("results", [])


def _load_annotations():
    data = load_json(DEFAULT_EVAL_ANNOTATIONS_FILE) if os.path.exists(DEFAULT_EVAL_ANNOTATIONS_FILE) else {}
    if isinstance(data, dict):
        return data.get("annotations", {})
    return {}


# ──────────────────────────────────────────────────
# 抽取相关
# ──────────────────────────────────────────────────

def _run_regex_extraction(articles, extractor_cls, out_path):
    ext = extractor_cls()
    results = []
    for art in articles:
        fields = ext.extract(art)
        fields["article_id"] = art.get("id", "")
        fields["title"] = art.get("title", "")
        fields["source"] = art.get("source", "")
        fields["url"] = art.get("url", "")
        results.append(fields)
    output = {
        "metadata": {
            "total": len(results),
            "fields": EXTRACTION_FIELDS,
            "extractor": ext.name,
            "created_at": datetime.now().isoformat(),
        },
        "results": results,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    save_json(output, out_path)
    return output


def _results_to_csv(results_data, csv_path):
    rows = results_data.get("results", [])
    if not rows:
        return
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")


# ──────────────────────────────────────────────────
# 页面：系统概览
# ──────────────────────────────────────────────────

def page_overview():
    st.header("系统概览")

    articles = _load_articles()
    results = _load_results()
    annotations = _load_annotations()
    docs = _load_documents()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("原始文档", len(docs), help="documents.json 中的原始爬虫文档")
    c2.metric("已适配语料", len(articles), help="可供抽取的 articles 数量")
    c3.metric("抽取结果", len(results), help="已生成的抽取记录数")
    c4.metric("抽取字段", len(EXTRACTION_FIELDS))
    c5.metric("人工标注", len(annotations))

    st.divider()

    # ── 爬虫控制 ──
    st.subheader("🕷️ 数据采集")
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.caption("从 IT之家 / 36氪 / 新华网 / 新浪科技等 10 大科技源并发采集真实新闻。")
    with col_b:
        crawl_btn = st.button("启动爬虫采集", type="primary", use_container_width=True)

    if crawl_btn:
        from crawler import AsyncWebCrawler, save_as_articles
        log_placeholder = st.empty()
        with st.spinner("正在并发爬取中，请稍候..."):
            try:
                crawler = AsyncWebCrawler()
                docs = asyncio.run(crawler.crawl_all())
                if docs:
                    path = save_as_articles(docs)
                    st.success(f"采集完成！共 {len(docs)} 篇文档，已保存至 {path}")
                else:
                    st.warning("未获取到文档，请检查网络连接。")
            except Exception as e:
                st.error(f"爬虫异常: {e}")
        st.rerun()

    # ── 语料概览 ──
    if docs:
        st.subheader("📊 语料来源分布")
        domains = Counter()
        for d in docs:
            url = d.get("url", "")
            m = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if m:
                domains[m.group(1)] += 1
        source_rows = [{"来源域名": d, "文档数": c} for d, c in domains.most_common()]
        st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)

    # ── 抽取结果概览 ──
    if results:
        st.subheader("📊 字段覆盖情况")
        field_counts = {f: 0 for f in EXTRACTION_FIELDS}
        complete = 0
        for r in results:
            filled = sum(1 for f in EXTRACTION_FIELDS if r.get(f))
            if filled >= 4:
                complete += 1
            for f in EXTRACTION_FIELDS:
                if r.get(f):
                    field_counts[f] += 1
        cols = st.columns(len(EXTRACTION_FIELDS))
        for col, field in zip(cols, EXTRACTION_FIELDS):
            col.metric(FIELD_LABELS[field], field_counts[field])
        st.caption(f"较完整事件（≥4字段）：{complete} / {len(results)}")


# ──────────────────────────────────────────────────
# 页面：事件抽取
# ──────────────────────────────────────────────────

def page_extraction():
    st.header("事件抽取与筛选")

    articles = _load_articles()
    if not articles:
        st.warning("还没有语料数据。请先在「系统概览」中运行爬虫采集新闻。")
        return

    st.caption(f"当前语料：{len(articles)} 篇")

    c_alg, c_act = st.columns([2, 1])
    with c_alg:
        algorithm = st.selectbox(
            "抽取算法",
            ["优化正则（推荐）", "基础正则 baseline"],
        )
    with c_act:
        run_btn = st.button("开始抽取", type="primary", use_container_width=True)

    if run_btn:
        if algorithm.startswith("基础"):
            out_json = os.path.join(os.path.dirname(DEFAULT_REGEX_RESULTS_FILE), "basic_regex_results.json")
            out_csv = None
            extractor_cls = BasicRegexExtractor
        else:
            out_json = DEFAULT_REGEX_RESULTS_FILE
            out_csv = DEFAULT_REGEX_RESULTS_CSV
            extractor_cls = RegexExtractor

        with st.spinner(f"正在对所有 {len(articles)} 篇文章运行 {algorithm}..."):
            result_data = _run_regex_extraction(articles, extractor_cls, out_json)
            if out_csv:
                _results_to_csv(result_data, out_csv)
        st.success(f"抽取完成！共 {result_data['metadata']['total']} 条记录")
        st.rerun()

    # 展示已抽取结果
    results = _load_results()
    if not results:
        st.info("尚未生成抽取结果，请点击「开始抽取」。")
        return

    df = pd.DataFrame(results)
    for field in EXTRACTION_FIELDS:
        if field not in df.columns:
            df[field] = None

    left, mid, right = st.columns(3)
    with left:
        source_options = ["全部"] + sorted(x for x in df["source"].dropna().unique() if x)
        source = st.selectbox("来源筛选", source_options)
    with mid:
        action_options = ["全部"] + sorted(x for x in df["action_type"].dropna().unique() if x)
        action = st.selectbox("事件动作筛选", action_options)
    with right:
        keyword = st.text_input("标题/产品关键词搜索", "")

    view = df.copy()
    if source != "全部":
        view = view[view["source"] == source]
    if action != "全部":
        view = view[view["action_type"] == action]
    if keyword.strip():
        kw = keyword.strip()
        view = view[
            view["title"].fillna("").str.contains(kw, case=False, regex=False)
            | view["tech_product"].fillna("").str.contains(kw, case=False, regex=False)
        ]

    show_cols = ["title", "source", "developer", "tech_product", "action_type", "version_metric", "date", "url"]
    st.dataframe(view[show_cols], use_container_width=True, hide_index=True)

    csv_path = DEFAULT_REGEX_RESULTS_CSV
    if os.path.exists(csv_path):
        st.download_button(
            "下载 CSV 抽取结果",
            data=Path(csv_path).read_bytes(),
            file_name="regex_results.csv",
            mime="text/csv",
        )


# ──────────────────────────────────────────────────
# 页面：事件详情
# ──────────────────────────────────────────────────

def page_detail():
    st.header("事件详情")

    articles = _load_articles()
    results = _load_results()
    if not results:
        st.warning("请先在「事件抽取」页面生成抽取结果。")
        return

    art_map = {str(a.get("id")): a for a in articles}
    df = pd.DataFrame(results)
    options = [f"{r.get('article_id', '?')} | {str(r.get('title', ''))[:60]}" for r in results]
    selected = st.selectbox("选择事件", options)
    aid = selected.split(" | ", 1)[0]
    row = next((r for r in results if str(r.get("article_id")) == aid), {})
    article = art_map.get(aid, {})

    left, right = st.columns([3, 2])
    with left:
        st.subheader(article.get("title") or row.get("title", ""))
        st.caption(f"{article.get('source', '')}  {article.get('publish_time', '')}")
        if article.get("url"):
            st.write(article.get("url"))
        st.write(article.get("content") or article.get("summary") or "")
    with right:
        st.subheader("结构化事件")
        event_sentence = (
            f"{row.get('developer') or '未知主体'} 在 {row.get('date') or '未知日期'} "
            f"对 {row.get('tech_product') or '未知产品'} 进行了 "
            f"{row.get('action_type') or '未知动作'}，相关指标为 "
            f"{row.get('version_metric') or '未抽取'}。"
        )
        st.markdown(f"<div class='event-panel'>{event_sentence}</div>", unsafe_allow_html=True)
        st.table(pd.DataFrame(
            [{"字段": FIELD_LABELS[f], "值": row.get(f) or ""} for f in EXTRACTION_FIELDS]
        ))


# ──────────────────────────────────────────────────
# 页面：人工评价
# ──────────────────────────────────────────────────

def page_annotation():
    st.header("人工评价")

    results = _load_results()
    if not results:
        st.warning("请先在「事件抽取」页面生成抽取结果。")
        return

    annotations = _load_annotations()
    rows = results

    c1, c2 = st.columns([2, 1])
    with c1:
        mode = st.radio("样本范围", ["优先未标注", "全部样本"], horizontal=True)
    with c2:
        st.metric("已标注", len(annotations))

    candidates = rows
    if mode == "优先未标注":
        pending = [r for r in rows if str(r.get("article_id")) not in annotations]
        candidates = pending or rows

    labels = [f"{r.get('article_id', '?')} | {str(r.get('title', ''))[:70]}" for r in candidates]
    selected = st.selectbox("选择要标注的事件", labels)
    aid = selected.split(" | ", 1)[0]
    row = next((r for r in rows if str(r.get("article_id")) == aid), {})
    current = annotations.get(aid, {})

    st.subheader(row.get("title", ""))
    if row.get("url"):
        st.write(row.get("url"))

    with st.form("annotation_form"):
        new_annotation = {}
        for field in EXTRACTION_FIELDS:
            default = current.get(field, row.get(field) or "")
            new_annotation[field] = st.text_input(
                FIELD_LABELS[field],
                value=str(default or ""),
                help="留空表示该字段为空；可以直接修正。",
            )
        if st.form_submit_button("保存标注", type="primary"):
            annotations[aid] = {
                field: (value.strip() if value.strip() else None)
                for field, value in new_annotation.items()
            }
            output = {
                "metadata": {
                    "updated_at": datetime.now().isoformat(),
                    "fields": EXTRACTION_FIELDS,
                },
                "annotations": annotations,
            }
            save_json(output, DEFAULT_EVAL_ANNOTATIONS_FILE)
            st.success("标注已保存")
            st.rerun()


# ──────────────────────────────────────────────────
# 页面：评价指标
# ──────────────────────────────────────────────────

def page_metrics():
    st.header("评价指标")

    results = _load_results()
    annotations = _load_annotations()

    if not results:
        st.warning("请先生成抽取结果。")
        return
    if not annotations:
        st.info("尚未标注样本。请先在「人工评价」页面保存标注。")
        return

    metrics = calculate_extraction_metrics(results, annotations)
    save_json(metrics, DEFAULT_EVAL_METRICS_FILE)

    c1, c2, c3 = st.columns(3)
    c1.metric("Macro Precision", metrics["overall"]["Macro_Avg_Precision"])
    c2.metric("Macro Recall", metrics["overall"]["Macro_Avg_Recall"])
    c3.metric("Macro F1", metrics["overall"]["Macro_Avg_F1_Score"])
    st.caption(f"评价样本数：{metrics['summary']['total_annotated']}")

    table_rows = []
    for field in EXTRACTION_FIELDS:
        item = metrics["by_field"][field]
        table_rows.append({
            "字段": FIELD_LABELS[field],
            "TP": item["TP"], "FP": item["FP"], "FN": item["FN"],
            "Precision": item["Precision"], "Recall": item["Recall"], "F1": item["F1_Score"],
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────
# 页面：多媒体抽取
# ──────────────────────────────────────────────────

def page_multimodal():
    st.header("多媒体信息抽取")
    uploaded = st.file_uploader("上传科技发布海报或截图", type=["png", "jpg", "jpeg", "bmp"])
    if uploaded is None:
        st.caption("上传图片后，系统会先 OCR 识别文字，再复用事件抽取器抽取 5 个字段。")
        return

    os.makedirs(IMAGES_DIR, exist_ok=True)
    image_path = os.path.join(IMAGES_DIR, uploaded.name)
    with open(image_path, "wb") as f:
        f.write(uploaded.getbuffer())

    st.image(image_path, use_container_width=True)
    if st.button("运行 OCR 事件抽取", type="primary"):
        extractor = MultimodalExtractor()
        result = extractor.process_image(image_path)
        st.subheader("OCR 文本")
        st.write(result.get("ocr_text", ""))
        st.subheader("事件字段")
        st.json(result.get("extraction", {}))


# ──────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────

def main():
    st.sidebar.title("科技事件信息抽取系统")
    page = st.sidebar.radio(
        "导航",
        ["系统概览", "事件抽取", "事件详情", "人工评价", "评价指标", "多媒体抽取"],
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("自有爬虫采集 → 正则匹配抽取 → 人工评价 → OCR 多媒体")

    if page == "系统概览":
        page_overview()
    elif page == "事件抽取":
        page_extraction()
    elif page == "事件详情":
        page_detail()
    elif page == "人工评价":
        page_annotation()
    elif page == "评价指标":
        page_metrics()
    elif page == "多媒体抽取":
        page_multimodal()


if __name__ == "__main__":
    main()
