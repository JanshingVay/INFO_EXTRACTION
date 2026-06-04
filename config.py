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
            os.environ[key] = value


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
DEFAULT_OPEN_NLP_RESULTS_FILE = os.path.join(EXTRACTION_RESULTS_DIR, "opensource_nlp_results.json")
DEFAULT_OPEN_NLP_RESULTS_CSV = os.path.join(EXTRACTION_RESULTS_DIR, "opensource_nlp_results.csv")
DEFAULT_NLP_RESULTS_FILE = os.path.join(EXTRACTION_RESULTS_DIR, "nlp_results.json")
DEFAULT_NLP_RESULTS_CSV = os.path.join(EXTRACTION_RESULTS_DIR, "nlp_results.csv")
DEFAULT_EVAL_ANNOTATIONS_FILE = os.path.join(EVAL_DIR, "annotations_from_info_retrieve.json")
DEFAULT_EVAL_METRICS_FILE = os.path.join(EVAL_DIR, "metrics_from_info_retrieve.json")

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

# ============================================================
# 高性能异步爬虫配置 (async_crawler.py + data_cleaner.py)
# ============================================================

DOCUMENTS_FILE = os.path.join(DATA_DIR, "documents.json")

CRAWL_MIN_DOCS = 700
CRAWL_TIMEOUT = 15
CRAWL_DELAY = 0.3
CRAWL_MAX_DOCS = 800

VSM_TOP_K = 20

EVAL_QUERIES_FILE = os.path.join(DATA_DIR, "eval_queries.json")

CRAWL_SOURCES = [
    {
        "name": "IT之家",
        "base_url": "https://www.ithome.com",
        "list_urls": [
            "https://www.ithome.com/",
            "https://www.ithome.com/cat/44.html",
            "https://www.ithome.com/cat/48.html",
            "https://www.ithome.com/cat/59.html",
            "https://www.ithome.com/cat/106.html",
        ],
        "article_url_patterns": ["/0/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": "post_content"},
            {"tag": "div", "class_": "content"},
        ],
        "date_format": r"(\d{4}/\d{1,2}/\d{1,2})|(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "36氪科技",
        "base_url": "https://36kr.com",
        "list_urls": [
            "https://36kr.com/information/technology",
            "https://36kr.com/information/web",
        ],
        "article_url_patterns": ["/p/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": "common-width"},
            {"tag": "div", "class_": "content"},
            {"tag": "article"},
        ],
        "date_format": r"(\d{4}年\d{1,2}月\d{1,2}日)|(\d{4}-\d{2}-\d{2})|(\d{4}/\d{1,2}/\d{1,2})",
        "enabled": True,
    },
    {
        "name": "新华网科技",
        "base_url": "http://www.news.cn/tech",
        "list_urls": [
            "http://www.news.cn/tech/index.html",
        ],
        "article_url_patterns": ["/202"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "id": "detail-content"},
            {"tag": "div", "class_": r"(article|content)"},
        ],
        "date_format": r"(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "人民网科技",
        "base_url": "http://scitech.people.com.cn",
        "list_urls": [
            "http://scitech.people.com.cn/GB/index1.html",
            "http://scitech.people.com.cn/GB/index2.html",
            "http://scitech.people.com.cn/GB/index3.html",
        ],
        "article_url_patterns": ["/GB/", "/n1/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(article|content|text|detail|body)"},
        ],
        "date_format": r"(\d{4}年\d{1,2}月\d{1,2}日)|(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "凤凰网科技",
        "base_url": "https://tech.ifeng.com",
        "list_urls": [
            "https://tech.ifeng.com/",
        ],
        "article_url_patterns": ["/c/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(article|content|text)"},
            {"tag": "article"},
        ],
        "date_format": r"(\d{4}年\d{1,2}月\d{1,2}日)|(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "网易科技",
        "base_url": "https://tech.163.com",
        "list_urls": [
            "https://tech.163.com/",
        ],
        "article_url_patterns": ["/article/", "/tech/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(post_content|content|article)"},
        ],
        "date_format": r"(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "新浪科技",
        "base_url": "https://tech.sina.com.cn",
        "list_urls": [
            "https://tech.sina.com.cn/",
            "https://tech.sina.com.cn/internet/",
        ],
        "article_url_patterns": ["/doc-", "/detail-"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(article|content|artibody)"},
        ],
        "date_format": r"(\d{4}年\d{2}月\d{2}日)|(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "环球网科技",
        "base_url": "https://tech.huanqiu.com",
        "list_urls": [
            "https://tech.huanqiu.com/",
        ],
        "article_url_patterns": ["/article/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(article|content|text)"},
        ],
        "date_format": r"(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "澎湃新闻",
        "base_url": "https://www.thepaper.cn",
        "list_urls": [
            "https://www.thepaper.cn/channel_2594",
        ],
        "article_url_patterns": ["/newsDetail"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(newscontent|article|content)"},
        ],
        "date_format": r"(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
    {
        "name": "和讯科技",
        "base_url": "https://tech.hexun.com",
        "list_urls": [
            "https://tech.hexun.com/",
        ],
        "article_url_patterns": ["/tech/"],
        "title_selector": "h1",
        "content_selectors": [
            {"tag": "div", "class_": r"(article|content|text)"},
        ],
        "date_format": r"(\d{4}年\d{1,2}月\d{1,2}日)|(\d{4}-\d{2}-\d{2})",
        "enabled": True,
    },
]

DATA_CLEAN_CONFIG = {
    "min_content_length": 100,
    "max_title_length": 200,
    "dedup_by_url": True,
    "dedup_by_title_similarity": 0.85,
    "remove_boilerplate": True,
    "normalize_whitespace": True,
}

# ============================================================
# 科技大事件核心关键词
# ============================================================

TECH_KEYWORDS = [
    "开源", "架构", "发布", "升级", "漏洞", "算力", "模型", "芯片",
    "版本", "API", "SDK", "框架", "平台", "系统", "软件", "硬件",
    "正式版", "公测", "上线", "修复", "更新", "迭代", "里程碑",
]

# 科技事件5要素定义
EXTRACTION_FIELDS = ["developer", "tech_product", "action_type", "version_metric", "date"]

# ============================================================
# LLM / OCR 配置
# ============================================================

LLM_CONFIG = {
    "api_url": os.getenv("LLM_API_URL", "https://api.deepseek.com"),
    "api_key": os.getenv("LLM_API_KEY", ""),
    "model": os.getenv("LLM_MODEL", "deepseek-v4-flash"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "800")),
}

LLM_CONFIGURED = bool(LLM_CONFIG.get("api_key"))

OCR_CONFIG = {
    "engine": "easyocr",
    "languages": ["ch_sim", "en"],
}

# ============================================================
# 多模态 API 配置（图片 → 多模态大模型 → 事件抽取）
# 前端可配置，配置自动持久化到 data/multimodal_api_config.json
# 优先级：JSON 文件 > .env 环境变量 > 默认值
# ============================================================

MULTIMODAL_API_CONFIG_FILE = os.path.join(DATA_DIR, "multimodal_api_config.json")

MULTIMODAL_API_CONFIG_DEFAULTS = {
    "api_url": os.getenv("MULTIMODAL_API_URL", "https://api.openai.com/v1/chat/completions"),
    "api_key": os.getenv("MULTIMODAL_API_KEY", ""),
    "model": os.getenv("MULTIMODAL_MODEL", "gpt-4o"),
    "system_prompt": (
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
    ),
}


def load_multimodal_api_config() -> dict:
    """
    加载多模态 API 配置。
    优先级：持久化 JSON > .env 默认值
    """
    config = dict(MULTIMODAL_API_CONFIG_DEFAULTS)
    if os.path.exists(MULTIMODAL_API_CONFIG_FILE):
        try:
            import json
            with open(MULTIMODAL_API_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except Exception:
            pass
    return config


def save_multimodal_api_config(config: dict) -> str:
    """持久化多模态 API 配置到 JSON 文件。"""
    import json
    os.makedirs(DATA_DIR, exist_ok=True)
    # 只保存与默认值不同的字段 + 总是保存敏感字段
    persist_keys = {"api_url", "api_key", "model", "system_prompt"}
    to_save = {k: v for k, v in config.items() if k in persist_keys}
    with open(MULTIMODAL_API_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    return MULTIMODAL_API_CONFIG_FILE


# 模块级加载（可被前端刷新）
MULTIMODAL_API_CONFIG = load_multimodal_api_config()

# ============================================================
# 本地多模态模型配置（图片/视频 → 本地开源大模型 → 事件抽取）
# 前端可配置，配置自动持久化到 data/local_vl_config.json
# ============================================================

LOCAL_VL_CONFIG_FILE = os.path.join(DATA_DIR, "local_vl_config.json")

LOCAL_VL_CONFIG_DEFAULTS = {
    "enabled": False,
    "model": os.getenv("LOCAL_VL_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct"),
    "device": os.getenv("LOCAL_VL_DEVICE", "auto"),
    "max_tokens": int(os.getenv("LOCAL_VL_MAX_TOKENS", "2048")),
    "temperature": float(os.getenv("LOCAL_VL_TEMPERATURE", "0.3")),
    "system_prompt": (
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
    ),
}


def load_local_vl_config() -> dict:
    """
    加载本地多模态配置。
    优先级：持久化 JSON > .env 默认值
    """
    config = dict(LOCAL_VL_CONFIG_DEFAULTS)
    if os.path.exists(LOCAL_VL_CONFIG_FILE):
        try:
            import json
            with open(LOCAL_VL_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config.update(saved)
        except Exception:
            pass
    return config


def save_local_vl_config(config: dict) -> str:
    """持久化本地多模态配置到 JSON 文件。"""
    import json
    os.makedirs(DATA_DIR, exist_ok=True)
    persist_keys = {"enabled", "model", "device", "max_tokens", "temperature", "system_prompt"}
    to_save = {k: v for k, v in config.items() if k in persist_keys}
    with open(LOCAL_VL_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)
    return LOCAL_VL_CONFIG_FILE


# 模块级加载
LOCAL_VL_CONFIG = load_local_vl_config()
