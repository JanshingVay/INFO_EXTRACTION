"""
全局配置模块 - 核心技术产品发布与升级大事件抽取系统
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_NEWS_DIR = os.path.join(DATA_DIR, "raw_news")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
EVAL_DIR = os.path.join(DATA_DIR, "evaluations")

for d in [DATA_DIR, RAW_NEWS_DIR, IMAGES_DIR, EVAL_DIR]:
    os.makedirs(d, exist_ok=True)

CRAWLER_CONFIG = {
    "max_concurrency": 8,
    "request_timeout": 20,
    "retry_times": 2,
    "rate_limit": 0.3,
    "max_pages": 5,
    "min_content_length": 120,
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# 科技大事件核心关键词过滤
TECH_KEYWORDS = [
    "开源", "架构", "发布", "升级", "漏洞", "算力", "模型", "芯片",
    "版本", "API", "SDK", "框架", "平台", "系统", "软件", "硬件",
    "正式版", "公测", "上线", "修复", "更新", "迭代", "里程碑",
]

# 科技事件5要素定义
EXTRACTION_FIELDS = ["developer", "tech_product", "action_type", "version_metric", "date"]

LLM_CONFIG = {
    "api_url": "https://api.openai.com/v1/chat/completions",
    "api_key": "",
    "model": "gpt-3.5-turbo",
    "temperature": 0.1,
    "max_tokens": 800,
}

LLM_CONFIGURED = bool(LLM_CONFIG.get("api_key"))

OCR_CONFIG = {
    "engine": "easyocr",
    "languages": ["ch_sim", "en"],
}
