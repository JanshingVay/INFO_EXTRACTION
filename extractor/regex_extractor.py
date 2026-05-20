"""
科技技术正则表达式抽取器

抽取科技事件5要素：
- developer: 研发主体（如Google、微软、阿里、Linux基金会）
- tech_product: 核心技术/产品/开源项目名（如DeepSeek-V3、Kubernetes、PyTorch）
- action_type: 事件动作/类型（如正式开源、发布新版本、修复高危漏洞、上线新功能）
- version_metric: 版本号或关键指标数据（如v1.30版本、1.5T参数、性能提升40%）
- date: 事件发布时间
"""
import re
from typing import Dict, Any, Optional

from extractor.base import BaseExtractor


# 常见研发机构/公司
DEVELOPER_NAMES = [
    "Google", "微软", "阿里巴巴", "腾讯", "百度", "Meta", "Apple",
    "Linux基金会", "Apache基金会", "CNCF", "GitHub", "OpenAI",
    "DeepSeek", "通义千问", "文心一言", "混元", "智谱", "智谱AI",
    "字节跳动", "美团", "京东", "华为", "英伟达", "AMD", "Intel",
    "AWS", "阿里云", "腾讯云", "百度云", "Azure", "GCP",
]

# 常见科技动作类型
TECH_ACTION_PATTERNS = [
    r"正式开源", r"开源发布", r"宣布开源",
    r"发布新版本", r"发布.*版本", r"正式发布",
    r"修复高危漏洞", r"安全更新", r"漏洞修复",
    r"上线新功能", r"功能更新", r"正式上线",
    r"性能提升", r"优化升级", r"重大更新",
    r"架构升级", r"架构优化", r"架构重构",
    r"模型升级", r"模型发布", r"新模型发布",
    r"芯片发布", r"芯片升级", r"算力突破",
]

# 版本号模式
VERSION_PATTERNS = [
    r"v?\d+\.\d+(?:\.\d+)?",
    r"\d+\.\d+ 版本",
    r"\d+\.\d+\.\d+",
    r"版本 [0-9.]+",
]

# 关键指标数据模式
METRIC_PATTERNS = [
    r"\d+\.?\d*T? ?参数",
    r"\d+\.?\d*B? ?参数",
    r"\d+\.?\d*M? ?参数",
    r"性能提升(?:\d+%?)",
    r"性能提升(?:\d+\.?\d*倍?)",
    r"推理速度提升(?:\d+%?)",
    r"准确率提升(?:\d+\.?\d*%?)",
    r"算力(?:达|突破|提升)?(?:\d+)?(?:万亿|百亿|十亿)?(?:PFlops|TFlops)?",
    r"延迟降低(?:\d+\.?\d*%?)",
    r"吞吐量提升(?:\d+\.?\d*%?)",
]


class RegexExtractor(BaseExtractor):
    """科技技术正则表达式抽取器"""

    def __init__(self):
        super().__init__(name="RegexExtractor")
        
        # 科技产品/项目名模式：匹配常见英文项目名和中文技术名
        self.product_pattern = re.compile(
            r'[A-Za-z][A-Za-z0-9_.-]*(-v?\d+)?|'
            r'《([^》]+)》|'
            r'["\']([^"\']+)["\']'
        )
        
        # 版本号模式
        self.version_pattern = re.compile('|'.join(VERSION_PATTERNS))
        
        # 日期模式
        self.date_pattern = re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})')
        
        # 动作模式
        self.action_pattern = re.compile('|'.join(TECH_ACTION_PATTERNS))
        
        # 指标模式
        self.metric_pattern = re.compile('|'.join(METRIC_PATTERNS))

    def _extract_developer(self, text: str) -> Optional[str]:
        """抽取研发主体（公司/机构）"""
        # 优先匹配已知研发机构
        for name in DEVELOPER_NAMES:
            if name in text:
                return name
        
        # 匹配常见模式：XXX宣布、XXX发布、XXX开源
        patterns = [
            r'^([A-Za-z\u4e00-\u9fa5]{2,12})(?:宣布|发布|开源|推出)',
            r'^([A-Za-z\u4e00-\u9fa5]{2,12})(?:正式|全新)?(?:发布|开源)',
            r'([A-Za-z\u4e00-\u9fa5]{2,12})(?:官方|团队)(?:发布|开源|推出)',
        ]
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return match.group(1)
        
        return None

    def _extract_tech_product(self, text: str) -> Optional[str]:
        """抽取科技产品/项目名"""
        # 先尝试匹配书名号和引号内容
        quote_matches = re.findall(r'[《]([^》]+)[》]|["\']([^"\']+)["\']', text)
        if quote_matches:
            for match in quote_matches:
                product = match[0] or match[1]
                if product and len(product) > 1:
                    return product
        
        # 尝试匹配英文项目名
        english_matches = re.findall(r'[A-Z][A-Za-z0-9_.-]*', text)
        if english_matches:
            # 优先返回最长的（更可能是项目名）
            english_matches.sort(key=lambda x: -len(x))
            for match in english_matches[:3]:
                if len(match) >= 3:
                    return match
        
        return None

    def _extract_action_type(self, text: str) -> Optional[str]:
        """抽取事件动作类型"""
        match = self.action_pattern.search(text)
        if match:
            return match.group(0)
        
        # 备选：常见科技动词
        verb_patterns = [
            r'(发布|开源|推出|上线|更新|升级)',
            r'(修复|优化|改进|重构)',
            r'(架构|模型|芯片|算力)',
            r'(漏洞|安全|性能|功能)',
        ]
        for pat in verb_patterns:
            match = re.search(pat, text)
            if match:
                # 组合上下文
                idx = match.start(0)
                start = max(0, idx - 4)
                end = min(len(text), idx + 6)
                return text[start:end]
        
        return None

    def _extract_version_metric(self, text: str) -> Optional[str]:
        """抽取版本号或关键指标数据"""
        # 优先匹配版本号
        version_match = self.version_pattern.search(text)
        if version_match:
            return version_match.group(0)
        
        # 匹配指标数据
        metric_match = self.metric_pattern.search(text)
        if metric_match:
            return metric_match.group(0)
        
        # 尝试匹配简单数字指标
        simple_patterns = [
            r"\d+\.?\d*%",
            r"\d+\.?\d*倍",
            r"\d+\.?\d*(?:T|G|M|B) ",
        ]
        for pat in simple_patterns:
            match = re.search(pat, text)
            if match:
                return match.group(0)
        
        return None

    def _extract_date(self, article: Dict[str, Any]) -> Optional[str]:
        """抽取日期"""
        # 优先使用publish_time
        publish_time = article.get("publish_time", "")
        if publish_time:
            match = self.date_pattern.search(publish_time)
            if match:
                y, m, d = match.groups()
                return f"{y}-{int(m):02d}-{int(d):02d}"
            return publish_time[:10] if len(publish_time) >= 10 else publish_time
        
        # 从标题/内容提取
        text = article.get("title", "") + " " + article.get("summary", "")
        match = self.date_pattern.search(text)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
        
        return None

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """从单条新闻抽取科技事件5要素"""
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")
        full_text = f"{title} {summary} {content}".strip()
        
        return {
            "developer": self._extract_developer(full_text),
            "tech_product": self._extract_tech_product(full_text),
            "action_type": self._extract_action_type(full_text),
            "version_metric": self._extract_version_metric(full_text),
            "date": self._extract_date(article),
        }
