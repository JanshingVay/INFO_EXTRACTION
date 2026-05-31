import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    DEFAULT_BASIC_RESULTS_FILE,
    DEFAULT_CORPUS_FILE,
    DEFAULT_EVAL_ANNOTATIONS_FILE,
    DEFAULT_EVAL_METRICS_FILE,
    DEFAULT_NLP_RESULTS_CSV,
    DEFAULT_NLP_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
    EXTRACTION_FIELDS,
    IMAGES_DIR,
)
from evaluator.metrics import calculate_extraction_metrics
from multimodal import MultimodalExtractor
from utils.helpers import load_json, save_json
from utils.pipeline import (
    convert_retrieve_documents,
    corpus_stats,
    extraction_stats,
    load_corpus,
    run_algorithm_comparison,
    run_selectable_extraction,
)


st.set_page_config(
    page_title="科技事件信息抽取系统",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.3rem; padding-bottom: 2rem; }
    .metric-note { color: #6b7280; font-size: 0.9rem; }
    .event-panel {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 14px 16px;
        background: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


FIELD_LABELS = {
    "developer": "研发主体",
    "tech_product": "技术产品",
    "action_type": "事件动作",
    "version_metric": "版本/指标",
    "date": "事件日期",
}


def read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        return load_json(path)
    except Exception:
        return default


@st.cache_data(show_spinner=False)
def cached_corpus():
    return read_json(DEFAULT_CORPUS_FILE, {})


@st.cache_data(show_spinner=False)
def cached_results(path=DEFAULT_REGEX_RESULTS_FILE):
    return read_json(path, {})


@st.cache_data(show_spinner=False)
def cached_annotations():
    data = read_json(DEFAULT_EVAL_ANNOTATIONS_FILE, {"annotations": {}})
    return data if isinstance(data, dict) else {"annotations": {}}


def clear_data_cache():
    cached_corpus.clear()
    cached_results.clear()
    cached_annotations.clear()


def get_articles_by_id(corpus):
    return {str(a.get("id")): a for a in corpus.get("articles", [])}


def results_dataframe(results_data):
    rows = results_data.get("results", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for field in EXTRACTION_FIELDS:
        if field not in df.columns:
            df[field] = None
    return df


def save_annotations(annotations):
    output = {
        "metadata": {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "fields": EXTRACTION_FIELDS,
            "note": "由Streamlit图形界面人工标注生成",
        },
        "annotations": annotations,
    }
    save_json(output, DEFAULT_EVAL_ANNOTATIONS_FILE)
    clear_data_cache()


def page_overview():
    st.header("系统概览")
    corpus = cached_corpus()
    results_data = cached_results()
    annotations_data = cached_annotations()

    corpus_exists = bool(corpus.get("articles"))
    results_exists = bool(results_data.get("results"))
    annotations = annotations_data.get("annotations", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("本地语料", len(corpus.get("articles", [])) if corpus_exists else 0)
    c2.metric("抽取结果", len(results_data.get("results", [])) if results_exists else 0)
    c3.metric("抽取字段", len(EXTRACTION_FIELDS))
    c4.metric("人工标注", len(annotations))

    st.subheader("数据准备")
    left, right = st.columns(2)
    with left:
        if st.button("从作业2语料构建作业3语料", type="primary", use_container_width=True):
            try:
                convert_retrieve_documents()
                clear_data_cache()
                st.success(f"已生成 {DEFAULT_CORPUS_FILE}")
            except Exception as exc:
                st.error(f"构建失败：{exc}")
    with right:
        if st.button("运行基础/优化正则抽取", use_container_width=True):
            try:
                run_algorithm_comparison()
                clear_data_cache()
                st.success("抽取完成，已保存 JSON 和 CSV 结果")
            except Exception as exc:
                st.error(f"抽取失败：{exc}")

    if corpus_exists:
        stats = corpus_stats(corpus)
        st.subheader("语料来源")
        source_rows = [
            {"来源": source, "文档数": count}
            for source, count in stats["sources"].items()
        ]
        st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)

    if results_exists:
        stats = extraction_stats(results_data)
        st.subheader("字段覆盖情况")
        cols = st.columns(len(EXTRACTION_FIELDS))
        for col, field in zip(cols, EXTRACTION_FIELDS):
            col.metric(FIELD_LABELS[field], stats["by_field"].get(field, 0))
        st.caption(f"较完整事件数：{stats['complete_events']}，定义为至少抽取出4个字段。")


def page_extraction():
    st.header("事件抽取与筛选")
    corpus = cached_corpus()
    if not corpus.get("articles"):
        st.warning("请先在系统概览中构建作业3语料。")
        return

    c_alg, c_limit = st.columns([2, 1])
    with c_alg:
        algorithm = st.selectbox(
            "抽取算法",
            ["基础正则 baseline", "优化正则（推荐，全量离线）", "NLP/API（MiniMax，可选增强）"],
        )
    with c_limit:
        api_limit = st.number_input("API抽取篇数", min_value=1, max_value=739, value=5, step=1)

    if algorithm.startswith("基础"):
        result_path = DEFAULT_BASIC_RESULTS_FILE
        result_csv = None
    elif algorithm.startswith("NLP"):
        result_path = DEFAULT_NLP_RESULTS_FILE
        result_csv = DEFAULT_NLP_RESULTS_CSV
    else:
        result_path = DEFAULT_REGEX_RESULTS_FILE
        result_csv = DEFAULT_REGEX_RESULTS_CSV

    if st.button("运行抽取", type="primary"):
        try:
            if algorithm.startswith("NLP"):
                run_selectable_extraction("nlp", limit=int(api_limit))
                st.success(f"API抽取完成，已保存 {DEFAULT_NLP_RESULTS_FILE}")
            elif algorithm.startswith("基础"):
                run_selectable_extraction("basic")
                st.success(f"基础正则抽取完成，已保存 {DEFAULT_BASIC_RESULTS_FILE}")
            else:
                run_selectable_extraction("optimized")
                st.success(f"优化正则抽取完成，已保存 {DEFAULT_REGEX_RESULTS_FILE}")
            clear_data_cache()
        except Exception as exc:
            st.error(f"抽取失败：{exc}")
        return

    results_data = cached_results(result_path)
    df = results_dataframe(results_data)
    if df.empty:
        st.info("尚未生成该算法的抽取结果，请点击运行抽取。")
        return

    left, mid, right = st.columns(3)
    with left:
        source_options = ["全部"] + sorted(x for x in df["source"].dropna().unique())
        source = st.selectbox("来源", source_options)
    with mid:
        action_options = ["全部"] + sorted(x for x in df["action_type"].dropna().unique())
        action = st.selectbox("事件动作", action_options)
    with right:
        keyword = st.text_input("标题/产品关键词", "")

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

    show_cols = [
        "title",
        "source",
        "developer",
        "tech_product",
        "action_type",
        "version_metric",
        "date",
        "url",
    ]
    st.dataframe(view[show_cols], use_container_width=True, hide_index=True)
    if result_csv:
        st.download_button(
            "下载CSV抽取结果",
            data=Path(result_csv).read_bytes() if os.path.exists(result_csv) else b"",
            file_name=os.path.basename(result_csv),
            mime="text/csv",
            disabled=not os.path.exists(result_csv),
        )


def page_detail():
    st.header("事件详情")
    corpus = cached_corpus()
    results_data = cached_results()
    df = results_dataframe(results_data)
    if df.empty:
        st.warning("请先生成抽取结果。")
        return

    articles = get_articles_by_id(corpus)
    options = [
        f"{row.article_id} | {str(row.title)[:60]}"
        for row in df.itertuples(index=False)
    ]
    selected = st.selectbox("选择事件", options)
    aid = selected.split(" | ", 1)[0]
    row = df[df["article_id"] == aid].iloc[0].to_dict()
    article = articles.get(aid, {})

    left, right = st.columns([3, 2])
    with left:
        st.subheader(article.get("title") or row.get("title"))
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


def page_annotation():
    st.header("人工评价")
    results_data = cached_results()
    df = results_dataframe(results_data)
    if df.empty:
        st.warning("请先生成抽取结果。")
        return

    annotations_data = cached_annotations()
    annotations = annotations_data.get("annotations", {})
    rows = df.to_dict("records")

    c1, c2 = st.columns([2, 1])
    with c1:
        mode = st.radio("样本范围", ["优先未标注", "全部样本"], horizontal=True)
    with c2:
        st.metric("已标注", len(annotations))

    candidate_rows = rows
    if mode == "优先未标注":
        pending = [r for r in rows if str(r.get("article_id")) not in annotations]
        candidate_rows = pending or rows

    labels = [
        f"{r.get('article_id')} | {str(r.get('title'))[:70]}"
        for r in candidate_rows
    ]
    selected = st.selectbox("选择要标注的事件", labels)
    aid = selected.split(" | ", 1)[0]
    row = next(r for r in rows if str(r.get("article_id")) == aid)
    current = annotations.get(aid, {})

    st.subheader(row.get("title", ""))
    if row.get("url"):
        st.write(row.get("url"))

    with st.form("annotation_form"):
        new_annotation = {}
        for field in EXTRACTION_FIELDS:
            default = current.get(field)
            if default is None:
                default = row.get(field) or ""
            new_annotation[field] = st.text_input(
                FIELD_LABELS[field],
                value=str(default or ""),
                help="留空表示该字段为空；可以直接修正为人工认为正确的值。",
            )
        submitted = st.form_submit_button("保存标注", type="primary")

    if submitted:
        annotations[aid] = {
            field: (value.strip() if value.strip() else None)
            for field, value in new_annotation.items()
        }
        save_annotations(annotations)
        st.success("标注已保存")


def page_metrics():
    st.header("评价指标")
    results_data = cached_results()
    annotations_data = cached_annotations()
    rows = results_data.get("results", [])
    annotations = annotations_data.get("annotations", {})

    if not rows:
        st.warning("请先生成抽取结果。")
        return
    if not annotations:
        st.info("尚未标注样本。请先在人工评价页面保存标注。")
        return

    metrics = calculate_extraction_metrics(rows, annotations)
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
            "TP": item["TP"],
            "FP": item["FP"],
            "FN": item["FN"],
            "Precision": item["Precision"],
            "Recall": item["Recall"],
            "F1": item["F1_Score"],
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    st.success(f"指标已同步保存到 {DEFAULT_EVAL_METRICS_FILE}")


def page_multimodal():
    st.header("多媒体信息抽取")
    uploaded = st.file_uploader("上传科技发布海报或截图", type=["png", "jpg", "jpeg", "bmp"])
    if uploaded is None:
        st.caption("上传图片后，系统会先OCR识别文字，再复用事件抽取器抽取5个字段。")
        return

    os.makedirs(IMAGES_DIR, exist_ok=True)
    image_path = os.path.join(IMAGES_DIR, uploaded.name)
    with open(image_path, "wb") as f:
        f.write(uploaded.getbuffer())

    st.image(image_path, use_container_width=True)
    if st.button("运行OCR事件抽取", type="primary"):
        extractor = MultimodalExtractor()
        result = extractor.process_image(image_path)
        st.subheader("OCR文本")
        st.write(result.get("ocr_text", ""))
        st.subheader("事件字段")
        st.json(result.get("extraction", {}))


def main():
    st.sidebar.title("科技事件信息抽取系统")
    page = st.sidebar.radio(
        "导航",
        ["系统概览", "事件抽取", "事件详情", "人工评价", "评价指标", "多媒体抽取"],
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("作业3：中文科技新闻事件抽取 / 正则规则 / 人工评价 / OCR")

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
