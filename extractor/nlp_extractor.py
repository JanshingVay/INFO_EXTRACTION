"""
NLP / 大模型智能抽取器

支持两种模式：
  1. LLM 模式（默认）：调用 OpenAI 兼容 API，通过提示工程进行结构化抽取
  2. 本地规则回退模式：当 API 不可用时自动回退到增强版正则抽取
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any

from config import LLM_CONFIG, EXTRACTION_FIELDS
from extractor.base import BaseExtractor
from extractor.regex_extractor import RegexExtractor

logger = logging.getLogger(__name__)


_EXTRACTION_SYSTEM_PROMPT = """你是一个专业的科技企业投融资事件信息抽取系统。请从给定的新闻文本中抽取出事件要素。

请严格按照以下 JSON 格式返回结果，不要包含任何其他内容：

{
  "Investor": "投资方名称（多个用中文分号；分隔），如果没有则为 null",
  "Target": "被投企业名称，如果没有则为 null",
  "Amount": "融资金额原始字符串（如：3亿美元），如果没有则为 null",
  "Round": "融资轮次（如：天使轮、A轮、B轮、C轮、D轮、Pre-IPO轮、战略融资等），如果没有则为 null",
  "Date": "融资事件发生的日期（格式YYYY-MM-DD），如果没有则从文中推断可能的日期"
}

规则说明：
- Investor: 识别领投方、跟投方等投资机构。注意区分投资方与被投企业，投资方通常是资本、基金、创投、集团等。
- Target: 被投资的公司/企业，通常是融资事件的发起方。
- Amount: 提取明确的金额数字和货币单位，保留原始表述。
- Round: 天使轮/种子轮/A轮/A+轮/B轮/B+轮/C轮/C+轮/D轮/Pre-IPO轮/战略融资/战略投资 等。
- Date: 优先用新闻中明确提到的日期，其次用发布时间推断。
- 如果某个要素确实无法从文本中获取，该字段值设为 null。"""


class NLPExtractor(BaseExtractor):
    """基于大模型 API 的智能抽取器"""

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model: str = None,
        fallback_to_regex: bool = True,
    ):
        super().__init__(name="NLPExtractor")
        self.api_url = api_url or LLM_CONFIG["api_url"]
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.model = model or LLM_CONFIG["model"]
        self.fallback_to_regex = fallback_to_regex
        self._regex_extractor = RegexExtractor() if fallback_to_regex else None

    def _build_user_prompt(self, article: Dict[str, Any]) -> str:
        """根据文章构建抽取提示"""
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
            parts.append(f"正文：{content}")

        text = "\n\n".join(parts)
        return f"请从以下科技新闻中抽取投融资事件要素：\n\n{text}"

    def _call_llm_api(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用大模型 API"""
        if not self.api_key:
            logger.warning("LLM API key not configured, falling back to regex")
            return None

        user_prompt = self._build_user_prompt(article)

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_url if self.api_url != "https://api.openai.com/v1" else None,
            )

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            raw_text = response.choices[0].message.content
            return self._parse_llm_response(raw_text)

        except ImportError:
            logger.warning("openai package not installed, trying requests fallback")
            return self._call_llm_api_requests(article)
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            return None

    def _call_llm_api_requests(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """通过 requests 库直接调用 LLM API（不需要 openai 包）"""
        user_prompt = self._build_user_prompt(article)

        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            }

            resp = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["choices"][0]["message"]["content"]
            return self._parse_llm_response(raw_text)

        except Exception as e:
            logger.error("LLM API requests fallback failed: %s", e)
            return None

    @staticmethod
    def _parse_llm_response(raw_text: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 返回的 JSON"""
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
        """容错 JSON 解析"""
        import re
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
        """
        智能抽取单条新闻事件要素
        - 优先使用 LLM API
        - API 不可用时自动回退到正则抽取器
        """
        llm_result = self._call_llm_api(article)

        if llm_result is not None:
            return llm_result

        if self.fallback_to_regex and self._regex_extractor:
            logger.info("LLM unavailable, falling back to RegexExtractor for: %s",
                        article.get("title", "")[:50])
            result = self._regex_extractor.extract(article)
            return result

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
