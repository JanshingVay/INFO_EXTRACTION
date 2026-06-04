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
import re
from typing import Dict, List, Optional, Any

from config import LLM_CONFIG, EXTRACTION_FIELDS
from extractor.base import BaseExtractor

logger = logging.getLogger(__name__)


# 系统提示词 - 指导LLM进行科技事件结构化抽取
_EXTRACTION_SYSTEM_PROMPT = """你是一个严谨的科技新闻事件信息抽取系统。请只抽取新闻标题和正文描述的“主事件”，不要抽取网页推荐、广告、评论、导航、相关阅读或背景噪声。

请严格按照以下JSON格式返回结果，不要包含任何其他内容：

{
  "developer": "研发主体（公司/机构/基金会/团队），如果没有明确主体则为null",
  "tech_product": "核心技术/产品/模型/芯片/系统/项目的完整名称，如果没有明确产品则为null",
  "action_type": "主事件动作，优先使用：发布、开源、升级、上线、修复、优化、适配、展示、众筹、人才引进、销量公布、合作、提出；如果不是明确事件则为null",
  "version_metric": "版本号或关键指标，必须保留单位和语义，如102.4 Tbps、2000mAh、节能25%、销量33476台；如果只是无关价格/编号/普通数字则为null",
  "date": "事件日期，统一为YYYY-MM-DD；没有明确事件日期时用发布时间；仍无法确定则为null"
}

抽取规则：
1. 标题权重最高。正文只用于补充标题中缺失的信息。
2. 不要把媒体名、栏目名、泛称（如“科技”“团队”“有限公司”）当作developer。
3. tech_product必须是具体产品或技术名，不要填“USB-C”“mAh”“今年”“最好的地方”等孤立词。
4. 对汇总类新闻，如果没有单一主事件，可以保留action_type和date，但developer/tech_product不要硬凑。
5. 某字段没有可靠依据时必须返回null，禁止臆测。
6. 输出必须是合法JSON，不要Markdown代码块，不要解释。"""


def _normalize_base_url(api_url: str) -> str:
    api_url = (api_url or "").strip().rstrip("/")
    if api_url.endswith("/chat/completions"):
        return api_url[: -len("/chat/completions")]
    return api_url


class NLPExtractor(BaseExtractor):
    """基于LLM的科技事件NLP抽取器（支持NER和依存分析）"""

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        model: str = None,
    ):
        super().__init__(name="NLPExtractor")
        self.api_url = _normalize_base_url(api_url or LLM_CONFIG["api_url"])
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.model = model or LLM_CONFIG["model"]
        self.temperature = LLM_CONFIG.get("temperature", 0.1)
        self.max_tokens = LLM_CONFIG.get("max_tokens", 800)
        self.last_error = None
        self.last_raw_response = None
        self.last_llm_used = False

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
            parts.append(f"正文节选：{content[:1200]}")

        text = "\n\n".join(parts)
        return (
            "请从以下科技技术新闻中抽取一个主事件的5个要素。"
            "如果新闻是销量汇总、列表或没有单一产品事件，请不要强行补全主体和产品。\n\n"
            f"{text}"
        )

    def _call_llm_api(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """调用LLM API进行抽取"""
        self.last_error = None
        self.last_raw_response = None
        self.last_llm_used = False
        if not self.api_key:
            self.last_error = "LLM API key not configured"
            logger.warning(self.last_error)
            return None

        user_prompt = self._build_user_prompt(article)

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_url,
            )

            request_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if "deepseek" in self.api_url.lower() or self.model.lower().startswith("deepseek"):
                request_payload["response_format"] = {"type": "json_object"}
            if "minimaxi" in self.api_url.lower() or self.model.lower().startswith("minimax"):
                # MiniMax OpenAI-compatible API can separate reasoning content.
                request_payload["extra_body"] = {"reasoning_split": True}

            response = client.chat.completions.create(**request_payload)

            raw_text = response.choices[0].message.content
            self.last_raw_response = raw_text
            parsed = self._parse_llm_response(raw_text)
            if parsed is not None:
                self.last_llm_used = True
            else:
                self.last_error = "LLM response parse failed"
            return parsed

        except ImportError:
            self.last_error = "openai package not installed"
            logger.warning(self.last_error)
            return None
        except Exception as e:
            self.last_error = f"LLM API call failed: {e}"
            logger.error(self.last_error)
            return None

    @staticmethod
    def _parse_llm_response(raw_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的JSON"""
        if not raw_text:
            return None
        raw_text = raw_text.strip()
        raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.S).strip()

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
            json_match = json_match.strip()
            brace_start = json_match.find("{")
            brace_end = json_match.rfind("}")
            if brace_start >= 0 and brace_end > brace_start:
                json_match = json_match[brace_start : brace_end + 1]
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
        """智能抽取科技事件5要素；API失败时不回退，显式返回错误状态。"""
        llm_result = self._call_llm_api(article)

        if llm_result is not None:
            llm_result["llm_used"] = True
            llm_result["api_failed"] = False
            llm_result["llm_error"] = None
            llm_result["llm_model"] = self.model
            return llm_result

        logger.warning("LLM unavailable, returning empty extraction")
        failed = {field: None for field in EXTRACTION_FIELDS}
        failed["llm_used"] = False
        failed["api_failed"] = True
        failed["llm_error"] = self.last_error or "LLM unavailable"
        failed["llm_model"] = self.model
        return failed

    def batch_extract(
        self, articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Optional[str]]]:
        results = []
        for i, article in enumerate(articles):
            extracted = self.extract(article)
            extracted["article_id"] = article.get("id", str(i))
            extracted["extractor"] = self.name
            results.append(extracted)
        return results
