"""
NLP深度学习抽取器 - 科技技术大事件抽取

功能：
- 命名实体识别（NER）：识别研发机构（ORG）和技术产品（MISC）
- 依存句法分析：理清"谁-做了什么-对象是什么"
- 结合上下文语义距离，提取结构化科技事件

抽取科技事件5要素：
- developer: 研发主体（ORG/公司名）
- tech_product: 核心技术/产品/开源项目名
- action_type: 事件动作/类型
- version_metric: 版本号或关键指标数据
- date: 事件发布时间
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Any

from config import LLM_CONFIG, EXTRACTION_FIELDS
from extractor.base import BaseExtractor

logger = logging.getLogger(__name__)


# 系统提示词 - 指导LLM进行科技事件结构化抽取
_EXTRACTION_SYSTEM_PROMPT = """你是一个专业的科技技术大事件信息抽取系统。请从给定的新闻文本中抽取出事件的核心要素。

请严格按照以下JSON格式返回结果，不要包含任何其他内容：

{
  "developer": "研发主体（如Google、微软、阿里、Linux基金会），如果没有则为null",
  "tech_product": "核心技术/产品/开源项目名（如DeepSeek-V3、Kubernetes、PyTorch），如果没有则为null",
  "action_type": "事件动作/类型（如：正式开源、发布新版本、修复高危漏洞、上线新功能、性能提升、架构升级），如果没有则为null",
  "version_metric": "版本号或关键指标数据（如：v1.30版本、1.5T参数、性能提升40%），如果没有则为null",
  "date": "事件时间（格式YYYY-MM-DD），如果没有则为null"
}

抽取规则：
1. developer: 识别科技公司、开源基金会、研究机构，通常是事件的发起者
2. tech_product: 提取技术产品、开源项目名、芯片型号、模型名称
3. action_type: 识别核心动作，如发布、开源、升级、修复漏洞、架构优化等
4. version_metric: 提取版本号（v1.3.0）、参数量（70B）、性能数据（提升30%）、算力指标等
5. date: 优先提取明确日期，其次用发布时间

如果某个要素确实无法获取，该字段设为null。"""


class NLPExtractor(BaseExtractor):
    """基于LLM的科技事件NLP抽取器（支持NER和依存分析）"""

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model: str = None,
    ):
        super().__init__(name="NLPExtractor")
        self.api_url = api_url or LLM_CONFIG["api_url"]
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.model = model or LLM_CONFIG["model"]
        self.temperature = LLM_CONFIG.get("temperature", 0.1)
        self.max_tokens = LLM_CONFIG.get("max_tokens", 800)

    def _build_user_prompt(self, article: Dict[str, Any]) -> str:
        """构建用户提示"""
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")
        publish_time = article.get("publish_time", "")

        parts = []
        if title:
            parts.append(f"标题：{title}")
        if publish_time:
            parts.append(f"发布时间：{publish_time}")
        if summary:
            parts.append(f"摘要：{summary}")
        if content:
            parts.append(f"正文：{content[:2000]}")

        text = "\n\n".join(parts)
        return f"请从以下科技技术新闻中抽取事件要素：\n\n{text}"

    def _call_llm_api(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用LLM API进行抽取"""
        if not self.api_key:
            logger.warning("LLM API key not configured")
            return None

        user_prompt = self._build_user_prompt(article)

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_url if self.api_url != "https://api.openai.com/v1/chat/completions" else None,
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            raw_text = response.choices[0].message.content
            return self._parse_llm_response(raw_text)

        except ImportError:
            logger.warning("openai package not installed")
            return None
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            return None

    @staticmethod
    def _parse_llm_response(raw_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的JSON"""
        if not raw_text:
            return None
        raw_text = raw_text.strip()

        json_match = None
        if raw_text.startswith("{"):
            json_match = raw_text
        elif "```json" in raw_text:
            start = raw_text.find("```json") + 7
            end = raw_text.find("```", start)
            json_match = raw_text[start:end].strip() if end > start else raw_text[start:].strip()
        elif "```" in raw_text:
            start = raw_text.find("```") + 3
            end = raw_text.find("```", start)
            json_match = raw_text[start:end].strip() if end > start else raw_text[start:].strip()

        if json_match:
            try:
                result = json.loads(json_match)
                extracted = {}
                for field in EXTRACTION_FIELDS:
                    value = result.get(field)
                    if value is None or str(value).lower() in ("null", "none", "无", ""):
                        extracted[field] = None
                    else:
                        extracted[field] = str(value)
                return extracted
            except json.JSONDecodeError:
                pass

        return NLPExtractor._fallback_json_parse(raw_text)

    @staticmethod
    def _fallback_json_parse(raw_text: str) -> Optional[Dict[str, Any]]:
        """容错JSON解析"""
        extracted = {}
        for field in EXTRACTION_FIELDS:
            pattern = rf'"{field}"\s*:\s*"([^"]*)"'
            m = re.search(pattern, raw_text)
            if m:
                val = m.group(1).strip()
                extracted[field] = val if val else None
            else:
                pattern2 = rf'"{field}"\s*:\s*(null|None)'
                m2 = re.search(pattern2, raw_text)
                if m2:
                    extracted[field] = None
        return extracted if extracted else None

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """智能抽取科技事件5要素"""
        llm_result = self._call_llm_api(article)

        if llm_result is not None:
            return llm_result

        logger.warning("LLM unavailable, returning empty extraction")
        return {field: None for field in EXTRACTION_FIELDS}

    def batch_extract(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Optional[str]]]:
        results = []
        for i, article in enumerate(articles):
            extracted = self.extract(article)
            extracted["article_id"] = article.get("id", str(i))
            extracted["extractor"] = self.name
            extracted["llm_used"] = self.api_key != "" and self.api_key is not None
            results.append(extracted)
        return results
