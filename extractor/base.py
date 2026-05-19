"""
抽取器抽象基类
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseExtractor(ABC):
    """所有抽取器的抽象基类，定义统一接口"""

    def __init__(self, name: str = "BaseExtractor"):
        self.name = name

    @abstractmethod
    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        从单条新闻中抽取事件要素

        Args:
            article: 包含 title, summary, content 等字段的新闻字典

        Returns:
            {"Investor": str|None, "Target": str|None, "Amount": str|None,
             "Round": str|None, "Date": str|None}
        """
        ...

    def batch_extract(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Optional[str]]]:
        """
        批量抽取，返回结果列表
        """
        results = []
        for i, article in enumerate(articles):
            extracted = self.extract(article)
            extracted["article_id"] = article.get("id", str(i))
            extracted["extractor"] = self.name
            results.append(extracted)
        return results
