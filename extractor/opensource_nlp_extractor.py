"""
Open-source NLP based extractor for Chinese technology event extraction.

This extractor uses jieba segmentation and POS tagging as the NLP module, then
combines domain lexicons and lightweight rules to extract the same 5 event
fields as the regex extractors.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

import jieba
import jieba.posseg as pseg

from extractor.base import BaseExtractor
from extractor.regex_extractor import (
    ACTION_RULES,
    DEVELOPER_NAMES,
    MEDIA_NAMES,
    METRIC_PATTERNS,
    PRODUCT_HINTS,
    PRODUCT_STOPWORDS,
    VERSION_PATTERNS,
    RegexExtractor,
    _clean_value,
    _first_match,
    _trim_product,
)


ORG_SUFFIXES = ("公司", "集团", "科技", "智能", "云", "基金会", "实验室", "研究院", "团队")
PRODUCT_POS = {"eng", "nz", "n", "x"}


class OpenSourceNLPExtractor(BaseExtractor):
    """jieba 分词/词性标注 + 领域规则的信息抽取器。"""

    def __init__(self):
        super().__init__(name="OpenSourceNLPExtractor")
        self.regex_fallback = RegexExtractor()
        for word in DEVELOPER_NAMES:
            jieba.add_word(word, tag="nt")
        for word in PRODUCT_HINTS:
            jieba.add_word(word, tag="n")
        for action, _patterns in ACTION_RULES:
            jieba.add_word(action, tag="v")

    @staticmethod
    def _priority_text(article: Dict[str, Any]) -> str:
        title = str(article.get("title") or "")
        summary = str(article.get("summary") or "")
        content = str(article.get("content") or "")
        return " ".join([title, summary[:500], content[:800]])

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [s.strip() for s in re.split(r"[。！？!?；;\n]", text) if s.strip()]

    def _tokens(self, text: str) -> List[Tuple[str, str]]:
        return [(w.word.strip(), w.flag) for w in pseg.cut(text) if w.word.strip()]

    def _extract_developer(self, text: str, tokens: List[Tuple[str, str]]) -> Optional[str]:
        for name in DEVELOPER_NAMES:
            if name in text and name not in MEDIA_NAMES:
                return name
        for word, flag in tokens:
            if word in MEDIA_NAMES:
                continue
            if flag == "nt" or word.endswith(ORG_SUFFIXES):
                if 2 <= len(word) <= 24:
                    return word
        return None

    def _extract_action_type(self, text: str, tokens: List[Tuple[str, str]]) -> Optional[str]:
        token_words = {word for word, _flag in tokens}
        for normalized, patterns in ACTION_RULES:
            if normalized in token_words:
                return normalized
            if _first_match(patterns, text):
                return normalized
        return None

    def _quoted_product(self, text: str) -> Optional[str]:
        for match in re.finditer(r"[《“\"]([^》”\"]{2,50})[》”\"]", text):
            candidate = match.group(1)
            if any(hint in candidate for hint in PRODUCT_HINTS) or re.search(r"[A-Za-z0-9]", candidate):
                return _trim_product(candidate)
        return None

    def _context_product(self, text: str) -> Optional[str]:
        hint_group = "|".join(PRODUCT_HINTS)
        patterns = [
            rf"(?:发布|推出|上线|升级|开源|宣布|亮相|适配)\s*([\u4e00-\u9fa5A-Za-z0-9_.-]{{2,30}}(?:{hint_group})?)",
            rf"([\u4e00-\u9fa5A-Za-z0-9_.-]{{2,30}}(?:{hint_group}))\s*(?:发布|上线|升级|开源)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = _trim_product(match.group(1))
                if value and value not in MEDIA_NAMES:
                    return value
        return None

    def _token_product(self, tokens: List[Tuple[str, str]]) -> Optional[str]:
        candidates: List[str] = []
        for idx, (word, flag) in enumerate(tokens):
            if word in PRODUCT_STOPWORDS or word in MEDIA_NAMES:
                continue
            if any(hint in word for hint in PRODUCT_HINTS) or flag in PRODUCT_POS:
                combined = word
                if idx + 1 < len(tokens):
                    nxt, _nxt_flag = tokens[idx + 1]
                    if any(hint in nxt for hint in PRODUCT_HINTS):
                        combined = word + nxt
                if re.search(r"[A-Za-z0-9]", combined) or any(h in combined for h in PRODUCT_HINTS):
                    candidates.append(combined)
        for candidate in sorted(set(candidates), key=len, reverse=True):
            value = _trim_product(candidate)
            if value and value not in PRODUCT_STOPWORDS:
                return value
        return None

    def _extract_tech_product(self, text: str, tokens: List[Tuple[str, str]]) -> Optional[str]:
        return self._quoted_product(text) or self._context_product(text) or self._token_product(tokens)

    def _extract_version_metric(self, text: str) -> Optional[str]:
        return _first_match(VERSION_PATTERNS + METRIC_PATTERNS, text)

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        text = self._priority_text(article)
        sentences = self._sentences(text)
        focus_text = " ".join(sentences[:5]) if sentences else text
        tokens = self._tokens(focus_text)

        extracted = {
            "developer": _clean_value(self._extract_developer(focus_text, tokens)),
            "tech_product": _clean_value(self._extract_tech_product(focus_text, tokens)),
            "action_type": _clean_value(self._extract_action_type(focus_text, tokens)),
            "version_metric": _clean_value(self._extract_version_metric(focus_text)),
            "date": _clean_value(RegexExtractor.extract_date(article)),
        }

        fallback = self.regex_fallback.extract(article)
        for key, value in fallback.items():
            if not extracted.get(key):
                extracted[key] = value
        return extracted
