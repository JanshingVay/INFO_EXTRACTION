"""
抽取器基类模块 - 核心技术产品发布与升级大事件抽取

科技事件5要素定义：
- developer: 研发主体（如Google、微软、阿里、Linux基金会）
- tech_product: 核心技术/产品/开源项目名（如DeepSeek-V3、Kubernetes、PyTorch）
- action_type: 事件动作/类型（如正式开源、发布新版本、修复高危漏洞、上线新功能）
- version_metric: 版本号或关键指标数据（如v1.30版本、1.5T参数、性能提升40%）
- date: 事件发布时间
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


EVENT_KEYS = ["developer", "tech_product", "action_type", "version_metric", "date"]


class BaseExtractor(ABC):
    """抽取器抽象基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        从单条新闻中抽取科技事件要素

        Args:
            article: 包含title, summary, content等字段的文章字典

        Returns:
            包含5个要素的字典: {developer, tech_product, action_type, version_metric, date}
        """
        pass

    def batch_extract(
        self, articles: list
    ) -> list:
        """批量抽取"""
        results = []
        for i, article in enumerate(articles):
            extracted = self.extract(article)
            extracted["article_id"] = article.get("id", str(i))
            extracted["extractor"] = self.name
            results.append(extracted)
        return results
