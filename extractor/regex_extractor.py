"""
Regular-expression based extractors for Chinese technology news events.

Target event:
developer 在 date 对 tech_product 进行了 action_type，并伴随 version_metric。
"""
import re
from typing import Any, Dict, List, Optional

from extractor.base import BaseExtractor


DEVELOPER_NAMES = [
    "OpenAI", "Google", "DeepMind", "Meta", "Microsoft", "微软", "Apple", "苹果",
    "Amazon", "AWS", "NVIDIA", "英伟达", "AMD", "Intel", "英特尔", "特斯拉",
    "华为", "荣耀", "小米", "OPPO", "vivo", "联想", "阿里", "阿里巴巴",
    "阿里云", "腾讯", "腾讯云", "百度", "百度智能云", "字节跳动", "火山引擎",
    "京东", "美团", "网易", "快手", "科大讯飞", "商汤", "智谱", "智谱AI",
    "DeepSeek", "月之暗面", "MiniMax", "零一万物", "阶跃星辰", "昆仑万维",
    "蚂蚁集团", "360", "小鹏", "理想", "蔚来", "比亚迪", "高通", "联发科",
    "台积电", "三星", "Linux基金会", "Apache基金会", "CNCF", "GitHub",
]

MEDIA_NAMES = {
    "IT之家", "新浪科技", "网易科技", "凤凰网科技", "新华网", "人民网",
    "环球网", "澎湃新闻", "36氪", "CSDN", "InfoQ", "51CTO", "开源中国",
}

PRODUCT_HINTS = [
    "大模型", "模型", "芯片", "处理器", "GPU", "CPU", "平台", "系统", "应用",
    "框架", "数据库", "浏览器", "机器人", "手机", "汽车", "算法", "智能体",
    "操作系统", "云服务", "助手", "API", "SDK", "搜索", "引擎", "软件",
]

ACTION_RULES = [
    ("开源", [r"正式开源", r"宣布开源", r"开源发布", r"开放源代码", r"开源"]),
    ("发布", [r"正式发布", r"发布(?:了|新|全新)?", r"推出", r"亮相", r"宣布"]),
    ("升级", [r"升级", r"更新", r"迭代", r"改版", r"焕新"]),
    ("上线", [r"上线", r"接入", r"开放", r"公测", r"内测"]),
    ("修复", [r"修复", r"安全更新", r"漏洞修补", r"补丁"]),
    ("优化", [r"优化", r"性能提升", r"提速", r"架构升级", r"架构优化"]),
    ("适配", [r"适配", r"支持", r"兼容"]),
]

VERSION_PATTERNS = [
    r"\bv?\d+(?:\.\d+){1,3}(?:\s*(?:版|版本|正式版|Beta|beta|RC))?",
    r"\b[A-Z]?\d{2,4}\s*(?:芯片|处理器|GPU|CPU)",
]

METRIC_PATTERNS = [
    r"\d+(?:\.\d+)?\s*(?:万亿|千亿|百亿|亿|万)?\s*(?:参数|tokens?|Token|上下文|次|台|颗|张)",
    r"\d+(?:\.\d+)?\s*(?:GB|TB|MB|TOPS|TFLOPS|PFLOPS|W|nm|纳米)",
    r"(?:提升|增长|降低|减少|加速|提速)\s*\d+(?:\.\d+)?\s*%",
    r"\d+(?:\.\d+)?\s*%",
    r"\d+(?:\.\d+)?\s*倍",
]

PRODUCT_STOPWORDS = {
    "CEO", "IT", "AI", "API", "SDK", "URL", "HTTP", "USB", "WiFi", "App",
    "Windows", "Android", "iOS",
}


def _clean_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip(" ，。；:：、|/-")
    return value or None


def _first_match(patterns: List[str], text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(0)
    return None


def _normalize_date_parts(year: str, month: str, day: str) -> Optional[str]:
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except (TypeError, ValueError):
        return None


def _trim_product(candidate: str) -> Optional[str]:
    candidate = re.split(r"[，,。；;：:]|新增|包括|支持|提醒|今日|消息", candidate)[0]
    candidate = candidate.strip(" 「」《》“”\"'、/ ")
    return candidate if len(candidate) >= 2 else None


class BasicRegexExtractor(BaseExtractor):
    """Baseline extractor used for algorithm comparison in the report."""

    def __init__(self):
        super().__init__(name="BasicRegexExtractor")

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        text = str(article.get("title") or "")
        developer = None
        for name in DEVELOPER_NAMES[:18]:
            if name in text and name not in MEDIA_NAMES:
                developer = name
                break

        product = None
        quote = re.search(r"[《“\"]([^》”\"]{2,40})[》”\"]", text)
        if quote:
            product = quote.group(1)
        else:
            product_match = re.search(r"[A-Z][A-Za-z0-9_.-]{2,}(?:\s?[A-Z0-9][A-Za-z0-9_.-]*)?", text)
            if product_match:
                product = product_match.group(0)

        action = None
        for normalized, patterns in ACTION_RULES:
            if _first_match(patterns, text):
                action = normalized
                break

        version_metric = _first_match(VERSION_PATTERNS + METRIC_PATTERNS, text)
        date = RegexExtractor.extract_date(article)

        return {
            "developer": _clean_value(developer),
            "tech_product": _clean_value(product),
            "action_type": _clean_value(action),
            "version_metric": _clean_value(version_metric),
            "date": _clean_value(date),
        }


class RegexExtractor(BaseExtractor):
    """Optimized regular-expression extractor with domain lexicons."""

    def __init__(self):
        super().__init__(name="OptimizedRegexExtractor")
        self.action_regexes = [
            (normalized, [re.compile(p, re.I) for p in patterns])
            for normalized, patterns in ACTION_RULES
        ]
        self.version_metric_pattern = re.compile(
            "|".join(f"(?:{p})" for p in VERSION_PATTERNS + METRIC_PATTERNS),
            flags=re.I,
        )

    @staticmethod
    def _full_text(article: Dict[str, Any]) -> str:
        return " ".join(
            str(article.get(key) or "") for key in ("title", "summary", "content")
        )

    @staticmethod
    def _priority_text(article: Dict[str, Any]) -> str:
        title = str(article.get("title") or "")
        summary = str(article.get("summary") or "")
        content = str(article.get("content") or "")
        return " ".join([title, summary[:600], content[:800]])

    @staticmethod
    def extract_date(article: Dict[str, Any]) -> Optional[str]:
        candidates = [
            str(article.get("publish_time") or ""),
            str(article.get("date") or ""),
            str(article.get("title") or ""),
            str(article.get("summary") or ""),
            str(article.get("content") or "")[:500],
        ]
        text = " ".join(candidates)

        match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})(?:日)?", text)
        if match:
            return _normalize_date_parts(match.group(1), match.group(2), match.group(3))

        publish_year = None
        year_match = re.search(r"(\d{4})", str(article.get("publish_time") or article.get("date") or ""))
        if year_match:
            publish_year = year_match.group(1)
        md_match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
        if md_match and publish_year:
            return _normalize_date_parts(publish_year, md_match.group(1), md_match.group(2))
        return None

    def _extract_developer(self, article: Dict[str, Any]) -> Optional[str]:
        text = self._priority_text(article)
        for name in DEVELOPER_NAMES:
            if name in text and name not in MEDIA_NAMES:
                return name

        patterns = [
            r"(?:据|由)?([\u4e00-\u9fa5A-Za-z0-9]{2,18}(?:公司|集团|科技|智能|云|基金会|实验室|团队))(?:宣布|发布|推出|上线|开源|升级)",
            r"([\u4e00-\u9fa5A-Za-z0-9]{2,18})(?:官方|方面|团队)(?:宣布|发布|推出|上线|开源|升级)",
            r"^([\u4e00-\u9fa5A-Za-z0-9]{2,18})(?:发布|推出|宣布|开源|上线|升级)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1)
                if candidate not in MEDIA_NAMES:
                    return candidate
        return None

    def _extract_action_type(self, article: Dict[str, Any]) -> Optional[str]:
        text = self._priority_text(article)
        for normalized, patterns in self.action_regexes:
            for pattern in patterns:
                if pattern.search(text):
                    return normalized
        return None

    def _extract_version_metric(self, article: Dict[str, Any]) -> Optional[str]:
        text = self._priority_text(article)
        match = self.version_metric_pattern.search(text)
        return match.group(0) if match else None

    def _quoted_product(self, text: str) -> Optional[str]:
        for match in re.finditer(r"[《“\"]([^》”\"]{2,50})[》”\"]", text):
            candidate = match.group(1)
            if any(word in candidate for word in ("报告", "声明", "消息", "通知")):
                continue
            if "、" in candidate and not any(hint in candidate for hint in PRODUCT_HINTS):
                continue
            if (
                any(hint in candidate for hint in PRODUCT_HINTS)
                or re.search(r"[A-Za-z0-9]", candidate)
            ):
                return _trim_product(candidate)
        return None

    def _title_product(self, article: Dict[str, Any]) -> Optional[str]:
        title = str(article.get("title") or "")
        patterns = [
            r"([\u4e00-\u9fa5A-Za-z0-9_.-]{2,24}(?:应用市场|云盘|浏览器|操作系统|大模型|模型|芯片|手机|机器人|平台|系统|助手|处理器))",
            r"(?:发布|推出|上线|升级|开源|展示|亮相)\s+([A-Za-z][A-Za-z0-9 /._-]{1,45})",
            r"([A-Za-z][A-Za-z0-9_.-]*(?:\s*/\s*[A-Za-z][A-Za-z0-9_.-]*)?\s+\d+(?:\.\d+)*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, title, flags=re.I)
            if match:
                value = _trim_product(match.group(1))
                if value and value not in PRODUCT_STOPWORDS:
                    return value
        return None

    def _english_product(self, text: str) -> Optional[str]:
        patterns = [
            r"\b[A-Z][A-Za-z0-9_.-]{2,}(?:[-\s]?[A-Z0-9][A-Za-z0-9_.-]{1,}){0,3}\b",
            r"\b(?:GPT|Qwen|Llama|Claude|Gemini|DeepSeek|Kimi|Sora|HarmonyOS|Windows|Android|iOS)\s?[A-Za-z0-9_.-]*\b",
        ]
        candidates: List[str] = []
        for pattern in patterns:
            candidates.extend(re.findall(pattern, text, flags=re.I))
        for candidate in sorted(set(candidates), key=len, reverse=True):
            value = candidate.strip()
            if value and value not in PRODUCT_STOPWORDS and not value.isdigit():
                return value
        return None

    def _chinese_product(self, text: str) -> Optional[str]:
        hint_group = "|".join(PRODUCT_HINTS)
        patterns = [
            rf"([\u4e00-\u9fa5A-Za-z0-9_.-]{{2,28}}(?:{hint_group}))",
            rf"(?:发布|推出|上线|升级|开源|宣布|亮相)\s*([\u4e00-\u9fa5A-Za-z0-9_.-]{{2,28}}(?:{hint_group})?)",
            rf"([\u4e00-\u9fa5A-Za-z0-9_.-]{{2,20}})\s*(?:正式)?(?:发布|上线|开源|升级)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                candidate = match.group(1)
                if candidate not in MEDIA_NAMES and len(candidate) >= 2:
                    return candidate
        return None

    def _extract_tech_product(self, article: Dict[str, Any]) -> Optional[str]:
        text = self._priority_text(article)
        return (
            self._title_product(article)
            or self._quoted_product(text)
            or self._chinese_product(text)
            or self._english_product(text)
        )

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        return {
            "developer": _clean_value(self._extract_developer(article)),
            "tech_product": _clean_value(self._extract_tech_product(article)),
            "action_type": _clean_value(self._extract_action_type(article)),
            "version_metric": _clean_value(self._extract_version_metric(article)),
            "date": _clean_value(self.extract_date(article)),
        }
