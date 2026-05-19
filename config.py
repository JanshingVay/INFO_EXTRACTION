"""
全局配置模块
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_NEWS_DIR = os.path.join(DATA_DIR, "raw_news")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for d in [DATA_DIR, RAW_NEWS_DIR, IMAGES_DIR]:
    os.makedirs(d, exist_ok=True)

CRAWLER_CONFIG = {
    "max_concurrency": 10,
    "request_timeout": 30,
    "retry_times": 3,
    "retry_delay": 2,
    "rate_limit": 1.0,
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

NEWS_SOURCES = {
    "36kr": {
        "name": "36氪",
        "base_url": "https://36kr.com",
        "api_url": "https://36kr.com/api/search/article?q={keyword}&page={page}&per_page=20",
        "keywords": ["融资", "投资", "A轮", "B轮", "C轮", "D轮", "天使轮", "Pre-IPO"],
    },
    "pedaily": {
        "name": "投资界",
        "base_url": "https://www.pedaily.cn",
        "api_url": "https://www.pedaily.cn/api/search?keyword={keyword}&page={page}",
        "keywords": ["融资", "投资", "VC", "PE", "天使轮", "A轮", "B轮", "C轮"],
    },
    "itjuzi": {
        "name": "IT桔子",
        "base_url": "https://www.itjuzi.com",
        "api_url": "https://www.itjuzi.com/search?key={keyword}&page={page}",
        "keywords": ["融资", "投资"],
    },
}

EXTRACTION_FIELDS = ["Investor", "Target", "Amount", "Round", "Date"]

LLM_CONFIG = {
    "api_url": os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions"),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "model": os.environ.get("LLM_MODEL", "gpt-3.5-turbo"),
}

OCR_CONFIG = {
    "engine": "easyocr",
    "languages": ["ch_sim", "en"],
}
