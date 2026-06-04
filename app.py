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
    DEFAULT_BASIC_RESULTS_FILE,
    DEFAULT_EVAL_ANNOTATIONS_FILE,
    DEFAULT_EVAL_METRICS_FILE,
    DEFAULT_NLP_RESULTS_CSV,
    DEFAULT_NLP_RESULTS_FILE,
    DEFAULT_OPEN_NLP_RESULTS_CSV,
    DEFAULT_OPEN_NLP_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
    DEFAULT_REGEX_RESULTS_FILE,
    DOCUMENTS_FILE,
    EVAL_DIR,
    EXTRACTION_FIELDS,
    IMAGES_DIR,
    LLM_CONFIG,
    LLM_CONFIGURED,
    RAW_NEWS_DIR,
    load_multimodal_api_config,
    save_multimodal_api_config,
)
from evaluator.metrics import calculate_extraction_metrics
from extractor.nlp_extractor import NLPExtractor
from extractor.opensource_nlp_extractor import OpenSourceNLPExtractor
from extractor.regex_extractor import BasicRegexExtractor, RegexExtractor
from multimodal import MultimodalExtractor
from utils.helpers import load_json, save_json


st.set_page_config(page_title="科技事件信息抽取系统", layout="wide")
st.markdown(
    """<style>
    .block-container { padding-top: 2.4rem; padding-bottom: 2rem; }
    h1, h2, h3 {
        line-height: 1.28 !important;
        padding-top: 0.18rem;
        padding-bottom: 0.18rem;
        overflow: visible;
    }
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
    existing = [p for _label, p in _result_file_options()]
    if not existing:
        return []
    latest = max(existing, key=os.path.getmtime)
    data = load_json(latest)
    return data.get("results", [])


def _latest_csv_path():
    candidates = [DEFAULT_REGEX_RESULTS_CSV, DEFAULT_OPEN_NLP_RESULTS_CSV, DEFAULT_NLP_RESULTS_CSV]
    existing = [p for p in candidates if os.path.exists(p)]
    return max(existing, key=os.path.getmtime) if existing else None


def _result_file_options(include_baseline: bool = True):
    options = [
        ("优化正则结果", DEFAULT_REGEX_RESULTS_FILE),
        ("开源 NLP 结果", DEFAULT_OPEN_NLP_RESULTS_FILE),
        ("DeepSeek API 结果", DEFAULT_NLP_RESULTS_FILE),
    ]
    if include_baseline:
        options.append(("基础正则 baseline", DEFAULT_BASIC_RESULTS_FILE))
    return [(label, path) for label, path in options if os.path.exists(path)]


def _result_key(path):
    return Path(path).stem.replace("_results", "")


def _annotation_path_for(result_path):
    return os.path.join(EVAL_DIR, f"annotations_{_result_key(result_path)}.json")


def _metrics_path_for(result_path):
    return os.path.join(EVAL_DIR, f"metrics_{_result_key(result_path)}.json")


def _load_selected_results(label="选择评价结果", include_baseline: bool = True):
    options = _result_file_options(include_baseline=include_baseline)
    if not options:
        return None, None, []
    labels = [
        f"{name} ({Path(path).name}, {datetime.fromtimestamp(os.path.getmtime(path)).strftime('%m-%d %H:%M')})"
        for name, path in options
    ]
    selected = st.selectbox(label, labels)
    idx = labels.index(selected)
    name, path = options[idx]
    data = load_json(path)
    rows = data.get("results", []) if isinstance(data, dict) else []
    return name, path, rows


def _load_annotations(path=DEFAULT_EVAL_ANNOTATIONS_FILE):
    data = load_json(path) if os.path.exists(path) else {}
    if isinstance(data, dict):
        return data.get("annotations", {})
    return {}


def _load_all_annotations_count() -> int:
    total = 0
    if not os.path.exists(EVAL_DIR):
        return 0
    for name in os.listdir(EVAL_DIR):
        if not name.startswith("annotations_") or not name.endswith(".json"):
            continue
        data = _load_annotations(os.path.join(EVAL_DIR, name))
        total += len(data)
    return total


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
    annotation_count = _load_all_annotations_count()
    docs = _load_documents()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("原始文档", len(docs), help="documents.json 中的原始爬虫文档")
    c2.metric("已适配语料", len(articles), help="可供抽取的 articles 数量")
    c3.metric("抽取结果", len(results), help="已生成的抽取记录数")
    c4.metric("抽取字段", len(EXTRACTION_FIELDS))
    c5.metric("人工标注", annotation_count)

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
            ["优化正则（推荐）", "开源 NLP（jieba 分词/词性）", "大模型 API 抽取（DeepSeek）"],
        )
        extraction_keyword = st.text_input(
            "抽取前关键词过滤（可选）",
            "",
            help="只对标题、摘要或正文中包含该关键词的文章运行抽取；留空则抽取全部语料。",
        )
        api_limit = None
        if "API" in algorithm:
            api_limit = st.number_input(
                "API 抽取篇数",
                min_value=1,
                max_value=len(articles),
                value=min(5, len(articles)),
                step=1,
                help="API 调用会消耗额度，建议先小批量测试。",
            )
            st.caption(
                f"当前 API 配置：{LLM_CONFIG.get('model')} / "
                f"{'已配置 Key' if LLM_CONFIGURED else '未配置 Key，API 抽取会失败并显示错误'}"
            )
    with c_act:
        run_btn = st.button("开始抽取", type="primary", use_container_width=True)

    if run_btn:
        candidate_articles = articles
        if extraction_keyword.strip():
            kw = extraction_keyword.strip().lower()
            candidate_articles = [
                art for art in articles
                if kw in str(art.get("title", "")).lower()
                or kw in str(art.get("summary", "")).lower()
                or kw in str(art.get("content", "")).lower()
            ]
            if not candidate_articles:
                st.warning(f"没有找到包含「{extraction_keyword.strip()}」的文章，请更换关键词或清空过滤条件。")
                return

        if algorithm.startswith("开源"):
            out_json = DEFAULT_OPEN_NLP_RESULTS_FILE
            out_csv = DEFAULT_OPEN_NLP_RESULTS_CSV
            extractor_cls = OpenSourceNLPExtractor
            run_articles = candidate_articles
        elif "API" in algorithm:
            out_json = DEFAULT_NLP_RESULTS_FILE
            out_csv = DEFAULT_NLP_RESULTS_CSV
            extractor_cls = NLPExtractor
            run_articles = candidate_articles[: int(api_limit or 5)]
        else:
            out_json = DEFAULT_REGEX_RESULTS_FILE
            out_csv = DEFAULT_REGEX_RESULTS_CSV
            extractor_cls = RegexExtractor
            run_articles = candidate_articles

        keyword_note = f"（关键词：{extraction_keyword.strip()}）" if extraction_keyword.strip() else ""
        with st.spinner(f"正在对 {len(run_articles)} 篇文章运行 {algorithm}{keyword_note}..."):
            result_data = _run_regex_extraction(run_articles, extractor_cls, out_json)
            if out_csv:
                _results_to_csv(result_data, out_csv)
        st.success(f"抽取完成！共 {result_data['metadata']['total']} 条记录{keyword_note}")
        if algorithm and "API" in algorithm:
            rows = result_data.get("results", [])
            failed_count = sum(1 for r in rows if r.get("api_failed"))
            if failed_count:
                st.error(f"有 {failed_count} 条 API 调用失败，未进行正则回退，请查看 llm_error 字段。")
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
        keyword = st.text_input("结果表关键词筛选", "")

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

    show_cols = ["title", "source", "developer", "tech_product", "action_type", "version_metric", "date"]
    for optional_col in ("llm_used", "api_failed", "llm_error", "llm_model", "llm_postprocessed"):
        if optional_col in view.columns:
            show_cols.append(optional_col)
    show_cols.append("url")
    st.dataframe(view[show_cols], use_container_width=True, hide_index=True)

    csv_path = _latest_csv_path()
    if csv_path:
        st.download_button(
            "下载 CSV 抽取结果",
            data=Path(csv_path).read_bytes(),
            file_name=Path(csv_path).name,
            mime="text/csv",
        )


# ──────────────────────────────────────────────────
# 页面：事件详情
# ──────────────────────────────────────────────────

def page_detail():
    st.header("事件详情")

    articles = _load_articles()
    result_name, _result_path, results = _load_selected_results("选择查看的抽取结果")
    if not results:
        st.warning("请先在「事件抽取」页面生成抽取结果。")
        return
    st.caption(f"当前查看：{result_name}")

    art_map = {str(a.get("id")): a for a in articles}
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

    result_name, result_path, results = _load_selected_results(include_baseline=False)
    if not results:
        st.warning("请先在「事件抽取」页面生成抽取结果。")
        return

    annotation_path = _annotation_path_for(result_path)
    annotations = _load_annotations(annotation_path)
    rows = results

    c1, c2 = st.columns([2, 1])
    with c1:
        mode = st.radio("样本范围", ["优先未标注", "全部样本"], horizontal=True)
    with c2:
        st.metric("已标注", len(annotations))
    st.caption(f"当前评价对象：{result_name}；标注文件：{annotation_path}")

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
                    "result_file": result_path,
                    "result_name": result_name,
                },
                "annotations": annotations,
            }
            save_json(output, annotation_path)
            st.success("标注已保存")
            st.rerun()


# ──────────────────────────────────────────────────
# 页面：评价指标
# ──────────────────────────────────────────────────

def page_metrics():
    st.header("评价指标")

    result_name, result_path, results = _load_selected_results(include_baseline=False)
    if not results:
        st.warning("请先生成抽取结果。")
        return

    annotation_path = _annotation_path_for(result_path)
    metrics_path = _metrics_path_for(result_path)
    annotations = _load_annotations(annotation_path)

    if not results:
        st.warning("请先生成抽取结果。")
        return
    if not annotations:
        st.info(f"当前结果尚未标注。请先在「人工评价」页面保存标注：{annotation_path}")
        return

    metrics = calculate_extraction_metrics(results, annotations)
    metrics.setdefault("summary", {})
    metrics["summary"]["result_name"] = result_name
    metrics["summary"]["result_file"] = result_path
    metrics["summary"]["annotation_file"] = annotation_path
    save_json(metrics, metrics_path)

    c1, c2, c3 = st.columns(3)
    c1.metric("Macro Precision", metrics["overall"]["Macro_Avg_Precision"])
    c2.metric("Macro Recall", metrics["overall"]["Macro_Avg_Recall"])
    c3.metric("Macro F1", metrics["overall"]["Macro_Avg_F1_Score"])
    st.caption(f"评价对象：{result_name}；评价样本数：{metrics['summary']['total_annotated']}；指标文件：{metrics_path}")

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
    st.header("🎬 多媒体信息抽取（图片/视频 → 事件）")
    st.caption("支持三种抽取方式：本地 OCR 正则 / 本地开源多模态大模型 / 云端多模态大模型 API")

    # ── 引入 config 函数 ──
    from config import (
        load_multimodal_api_config,
        save_multimodal_api_config,
        load_local_vl_config,
        save_local_vl_config,
    )

    # ── 提取方式选择 ──
    mode = st.radio(
        "📌 提取方式",
        [
            "🔧 OCR + 正则引擎（本地/免费）",
            "🖥️ 本地开源多模态大模型（Qwen2.5-VL/InternVL2）",
            "🧠 多模态大模型 API（云端/高精度）",
        ],
        horizontal=True,
    )

    use_api = mode.startswith("🧠")
    use_local_vl = mode.startswith("🖥️")

    # ── 配置面板 ──
    if use_local_vl:
        with st.expander("⚙️ 本地多模态模型配置", expanded=True):
            vl_config = load_local_vl_config()
            col1, col2 = st.columns(2)
            with col1:
                model = st.text_input(
                    "模型名称",
                    value=vl_config.get("model", "Qwen/Qwen2.5-VL-3B-Instruct"),
                    placeholder="Qwen/Qwen2.5-VL-3B-Instruct",
                    key="local_vl_model",
                )
                device = st.text_input(
                    "设备",
                    value=vl_config.get("device", "auto"),
                    placeholder="auto / cpu / cuda / mps",
                    key="local_vl_device",
                )
            with col2:
                temperature = st.number_input(
                    "Temperature",
                    value=float(vl_config.get("temperature", 0.3)),
                    min_value=0.0, max_value=1.0, step=0.1,
                    key="local_vl_temperature",
                )
                max_tokens = st.number_input(
                    "Max Tokens",
                    value=int(vl_config.get("max_tokens", 2048)),
                    min_value=128, max_value=4096, step=128,
                    key="local_vl_max_tokens",
                )

            system_prompt = st.text_area(
                "System Prompt（系统提示词）",
                value=vl_config.get("system_prompt", ""),
                height=200,
                key="local_vl_prompt",
            )

            c_save1, c_save2, c_reset = st.columns([1, 1, 1])
            with c_save1:
                if st.button("💾 保存配置", type="primary", use_container_width=True,
                             help="配置将持久化存储到 data/local_vl_config.json"):
                    new_config = {
                        "model": model,
                        "device": device,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "system_prompt": system_prompt,
                    }
                    path = save_local_vl_config(new_config)
                    st.success(f"✅ 已保存至 {path}")
            with c_reset:
                if st.button("🔄 重置为默认", use_container_width=True):
                    default_prompt = (
                        "你是一个专业的科技事件信息抽取系统。请仔细观察图片/视频内容，"
                        "从中抽取出科技发布事件的核心要素。\n\n"
                        "请严格按照以下JSON格式返回结果，不要包含任何其他内容：\n\n"
                        "{\n"
                        '  "developer": "研发主体（公司/基金会/研究机构），没有则为null",\n'
                        '  "tech_product": "核心技术/产品/开源项目名，没有则为null",\n'
                        '  "action_type": "事件动作（如：发布、开源、升级、修复漏洞等），没有则为null",\n'
                        '  "version_metric": "版本号或关键指标数据（如v1.30、70B参数、性能提升40%），没有则为null",\n'
                        '  "date": "事件日期（YYYY-MM-DD格式），没有则为null"\n'
                        "}"
                    )
                    save_local_vl_config({
                        "model": "Qwen/Qwen2.5-VL-3B-Instruct",
                        "device": "auto",
                        "temperature": 0.3,
                        "max_tokens": 2048,
                        "system_prompt": default_prompt,
                    })
                    st.success("已重置为默认配置，请刷新页面。")
                    st.rerun()

    elif use_api:
        with st.expander("⚙️ 多模态 API 配置", expanded=True):
            api_config = load_multimodal_api_config()

            col1, col2 = st.columns(2)
            with col1:
                api_url = st.text_input(
                    "API 地址 (Base URL)",
                    value=api_config.get("api_url", ""),
                    placeholder="https://api.moonshot.cn/v1",
                    key="mm_api_url",
                )
                model = st.text_input(
                    "模型名称",
                    value=api_config.get("model", "kimi-k2.6"),
                    placeholder="kimi-k2.6",
                    key="mm_model",
                )
            with col2:
                api_key = st.text_input(
                    "API Key",
                    value=api_config.get("api_key", ""),
                    type="password",
                    placeholder="sk-...",
                    key="mm_api_key",
                )

            system_prompt = st.text_area(
                "System Prompt（系统提示词）",
                value=api_config.get("system_prompt", ""),
                height=200,
                key="mm_prompt",
                help="发送给大模型的系统指令，定义抽取格式和要求。",
            )

            c_save1, c_save2, c_reset = st.columns([1, 1, 1])
            with c_save1:
                if st.button("💾 保存配置", type="primary", use_container_width=True,
                             help="API 地址、模型和提示词会持久化；API Key 不写入 JSON，建议放在 .env 中"):
                    new_config = {
                        "api_url": api_url,
                        "api_key": api_key,
                        "model": model,
                        "system_prompt": system_prompt,
                    }
                    path = save_multimodal_api_config(new_config)
                    st.success(f"✅ 已保存至 {path}")
                    if api_key:
                        st.info("API Key 已用于当前会话；为避免误提交，未写入配置文件。长期使用请写入 .env 的 MULTIMODAL_API_KEY。")
            with c_reset:
                if st.button("🔄 重置为默认", use_container_width=True):
                    import os as _os
                    default_prompt = (
                        "你是一个专业的科技事件信息抽取系统。请仔细观察图片内容，"
                        "从中抽取出科技发布事件的核心要素。\n\n"
                        "请严格按照以下JSON格式返回结果，不要包含任何其他内容：\n\n"
                        "{\n"
                        '  "developer": "研发主体（公司/基金会/研究机构），没有则为null",\n'
                        '  "tech_product": "核心技术/产品/开源项目名，没有则为null",\n'
                        '  "action_type": "事件动作（如：发布、开源、升级、修复漏洞等），没有则为null",\n'
                        '  "version_metric": "版本号或关键指标数据（如v1.30、70B参数、性能提升40%），没有则为null",\n'
                        '  "date": "事件日期（YYYY-MM-DD格式），没有则为null"\n'
                        "}"
                    )
                    save_multimodal_api_config({
                        "api_url": "https://api.moonshot.cn/v1",
                        "api_key": "",
                        "model": "kimi-k2.6",
                        "system_prompt": default_prompt,
                    })
                    st.success("已重置为默认配置，请刷新页面。")
                    st.rerun()

    else:
        # OCR 模式：探测可用引擎
        from multimodal.multimodal_extraction import MultimodalExtractor
        engines = MultimodalExtractor.detect_available_engines()
        if not engines:
            st.error("⚠️ 未检测到 OCR 引擎！请安装: `pip install easyocr`")
            st.code("pip install easyocr", language="bash")
            return

        engine_names = {
            "paddleocr": "PaddleOCR (中文最强)",
            "easyocr": "EasyOCR (中英文均可)",
            "pytesseract": "PyTesseract (轻量备选)",
        }
        engine_labels = [f"{engine_names.get(e, e)}" for e in engines]
        st.info(f"🟢 检测到 {len(engines)} 个 OCR 引擎可用：{' / '.join(engine_labels)}")

    st.divider()

    # ── 图片上传 + 演示海报 ──
    col_demo_left, col_demo_right = st.columns([2, 1])
    with col_demo_right:
        if st.button("🎲 生成演示海报", use_container_width=True):
            from multimodal import generate_demo_image
            demo_path = generate_demo_image()
            if demo_path:
                st.session_state["demo_image"] = demo_path
                st.success("演示海报已生成！")
                st.rerun()

        demo_image = st.session_state.get("demo_image", "")
        if demo_image:
            if st.button("🗑️ 清除演示海报", use_container_width=True):
                if os.path.exists(demo_image):
                    os.remove(demo_image)
                st.session_state.pop("demo_image", None)
                st.rerun()

    with col_demo_left:
        uploaded = st.file_uploader(
            "📤 上传科技海报/截图/视频",
            type=["png", "jpg", "jpeg", "bmp", "webp", "mp4", "mov", "avi", "webm"],
            key="mm_upload",
        )

    # 显示媒体
    demo_image = st.session_state.get("demo_image", "")
    if demo_image and not uploaded:
        st.image(demo_image, caption="🎲 自动生成的演示海报", use_container_width=True)
        filepath = demo_image
        is_video = False
    elif uploaded:
        os.makedirs(IMAGES_DIR, exist_ok=True)
        filepath = os.path.join(IMAGES_DIR, uploaded.name)
        with open(filepath, "wb") as f:
            f.write(uploaded.getbuffer())
        is_video = os.path.splitext(uploaded.name)[1].lower() in {".mp4", ".mov", ".avi", ".webm", ".mkv"}
        if is_video:
            st.video(filepath)
        else:
            st.image(filepath, use_container_width=True)
    else:
        st.caption("👆 上传图片/视频或点击「生成演示海报」开始体验。")
        return

    # ── 运行抽取 ──
    if not use_api and not use_local_vl and is_video:
        st.warning("⚠️ 视频文件不支持本地 OCR 提取，请切换到「本地开源多模态大模型」或「多模态大模型 API」模式。")
        return

    c_extract, c_nlp = st.columns([2, 1])
    with c_extract:
        if use_api:
            btn_label = "🧠 多模态 API 抽取"
        elif use_local_vl:
            btn_label = "🖥️ 本地多模态模型抽取"
        else:
            btn_label = "🔍 运行 OCR 事件抽取"
        run_ocr = st.button(
            btn_label,
            type="primary", use_container_width=True,
        )
    with c_nlp:
        if not use_api and not use_local_vl:
            use_nlp = st.checkbox("NLP增强", help="用 LLM 对 OCR 结果做二次抽取（需配置 API Key）")
        else:
            use_nlp = False

    if run_ocr:
        if use_local_vl:
            # ── 本地多模态模型路径 ──
            vl_config = load_local_vl_config()
            media_label = "视频" if is_video else "图片"
            from multimodal.local_vl import extract_with_local_vl
            with st.spinner(f"正在加载并运行 {vl_config['model']} 分析{media_label}..."):
                result = extract_with_local_vl(
                    media_path=filepath,
                    config=vl_config,
                )

            if result.get("error"):
                st.error(result["error"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("本地模型", result.get("local_model", "-"))
                c2.metric("耗时", f"{result.get('latency', 0):.1f}s")
                extraction = result.get("extraction", {})
                c3.metric("命中字段", sum(1 for v in extraction.values() if v))

                st.subheader("🎯 抽取事件 5 字段")
                field_cols = st.columns(5)
                for col, field in zip(field_cols, EXTRACTION_FIELDS):
                    val = extraction.get(field) or "—"
                    col.metric(FIELD_LABELS[field], val)

                if result.get("raw_response"):
                    with st.expander("📝 模型原始响应"):
                        st.text(result["raw_response"])

        elif use_api:
            # ── 多模态 API 路径 ──
            current_api_key = (api_key or "").strip()
            if not current_api_key:
                st.error("❌ 请先在配置面板中填写 API Key")
            else:
                from multimodal.api_client import extract_with_multimodal_api
                media_label = "视频" if is_video else "图片"
                with st.spinner(f"正在调用 {model} 分析{media_label}..."):
                    result = extract_with_multimodal_api(
                        media_path=filepath,
                        api_url=api_url,
                        api_key=current_api_key,
                        model=model,
                        system_prompt=system_prompt,
                    )

                if result.get("error"):
                    st.error(result["error"])
                else:
                    # 结果展示
                    c1, c2, c3 = st.columns(3)
                    c1.metric("API 引擎", result.get("api_engine", "-"))
                    c2.metric("耗时", f"{result.get('api_latency', 0):.1f}s")
                    extraction = result.get("extraction", {})
                    c3.metric("命中字段", sum(1 for v in extraction.values() if v))

                    st.subheader("🎯 抽取事件 5 字段")
                    field_cols = st.columns(5)
                    for col, field in zip(field_cols, EXTRACTION_FIELDS):
                        val = extraction.get(field) or "—"
                        col.metric(FIELD_LABELS[field], val)

                    if result.get("raw_response"):
                        with st.expander("📝 API 原始响应"):
                            st.text(result["raw_response"])
        else:
            # ── OCR 路径 ──
            from multimodal.multimodal_extraction import MultimodalExtractor
            extractor = MultimodalExtractor()
            with st.spinner("OCR 识别中..."):
                result = extractor.process_image(filepath, use_nlp=use_nlp)

            if result.get("error"):
                st.error(result["error"])
                return

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("OCR 引擎", result.get("ocr_engine", "-"))
            c2.metric("识别字符数", result.get("ocr_text_length", 0))
            c3.metric("置信度", f"{result.get('ocr_confidence', 0):.1%}")
            c4.metric("正则命中", sum(1 for v in result["extraction"].values() if v))

            st.subheader("📝 OCR 识别文本")
            st.text_area("OCR 结果", result.get("ocr_text", ""), height=150, disabled=True)

            st.subheader("🎯 抽取事件 5 字段")
            field_cols = st.columns(5)
            extraction = result.get("extraction", {})
            for col, field in zip(field_cols, EXTRACTION_FIELDS):
                val = extraction.get(field) or "—"
                col.metric(FIELD_LABELS[field], val)

            if result.get("nlp_used") and "extraction_nlp" in result:
                st.subheader("🧠 NLP 增强抽取")
                nlp_cols = st.columns(5)
                for col, field in zip(nlp_cols, EXTRACTION_FIELDS):
                    val = result["extraction_nlp"].get(field) or "—"
                    col.metric(f"{FIELD_LABELS[field]} (LLM)", val)

        st.divider()
        if use_api:
            st.caption("💡 提示：多模态 API 直接让大模型『看』图片并理解内容，对模糊截图/海报/图表均有较好效果。")
        else:
            st.caption("💡 提示：也可以切换到「多模态大模型 API」模式，用 GPT-4V 等直接理解图片内容。")


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
