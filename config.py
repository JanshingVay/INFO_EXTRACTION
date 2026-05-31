"""
全局配置模块 - 核心技术产品发布与升级大事件抽取系统
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(filepath: str) -> None:
    """Load simple KEY=VALUE pairs without adding python-dotenv as a dependency."""
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(BASE_DIR, ".env"))

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_NEWS_DIR = os.path.join(DATA_DIR, "raw_news")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
EVAL_DIR = os.path.join(DATA_DIR, "evaluations")
EXTRACTION_RESULTS_DIR = os.path.join(DATA_DIR, "extraction_results")

DEFAULT_CORPUS_FILE = os.path.join(RAW_NEWS_DIR, "from_info_retrieve.json")
DEFAULT_REGEX_RESULTS_FILE = os.path.join(EXTRACTION_RESULTS_DIR, "regex_results.json")
DEFAULT_REGEX_RESULTS_CSV = os.path.join(EXTRACTION_RESULTS_DIR, "regex_results.csv")
DEFAULT_BASIC_RESULTS_FILE = os.path.join(EXTRACTION_RESULTS_DIR, "basic_regex_results.json")
DEFAULT_NLP_RESULTS_FILE = os.path.join(EXTRACTION_RESULTS_DIR, "nlp_results.json")
DEFAULT_NLP_RESULTS_CSV = os.path.join(EXTRACTION_RESULTS_DIR, "nlp_results.csv")
DEFAULT_EVAL_ANNOTATIONS_FILE = os.path.join(EVAL_DIR, "annotations_from_info_retrieve.json")
DEFAULT_EVAL_METRICS_FILE = os.path.join(EVAL_DIR, "metrics_from_info_retrieve.json")

# Development-only source path. The converted corpus is copied into data/raw_news,
# so the finished project can run after INFO_RETRIEVE is removed.
INFO_RETRIEVE_DOCUMENTS_FILE = os.path.join(
    BASE_DIR, "INFO_RETRIEVE", "data", "documents.json"
)

for d in [DATA_DIR, RAW_NEWS_DIR, IMAGES_DIR, EVAL_DIR, EXTRACTION_RESULTS_DIR]:
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
    "api_url": os.getenv("LLM_API_URL", "https://api.minimaxi.com/v1"),
    "api_key": os.getenv("LLM_API_KEY", ""),
    "model": os.getenv("LLM_MODEL", "MiniMax-M2.7-highspeed"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "800")),
}

LLM_CONFIGURED = bool(LLM_CONFIG.get("api_key"))

OCR_CONFIG = {
    "engine": "easyocr",
    "languages": ["ch_sim", "en"],
}
