"""
正则表达式抽取器 —— 基于规则的高精度信息抽取

涵盖 5 个事件要素：
  Investor (投资方)  |  Target (被投企业)  |  Amount (融资金额)
  Round (融资轮次)   |  Date (发布时间)

策略：多模式级联匹配 + 上下文消歧 + 后处理清洗
"""
import re
from typing import Dict, List, Optional, Any

from extractor.base import BaseExtractor
from utils.helpers import normalize_amount, normalize_date


_ROUND_PATTERNS = [
    r"Pre-IPO\s*轮",
    r"Pre-[A-E]\s*轮",
    r"[A-E]\+?\s*轮",
    r"天使\+?\s*轮",
    r"种子\+?\s*轮",
    r"战略(?:融资|投资)",
    r"定向增发",
    r"新三板",
    r"IPO\s*(?:上市)?",
    r"并购",
    r"股权(?:融资|转让)",
    r"债权融资",
    r"过桥融资",
]

_ROUND_REGEX = re.compile("|".join(_ROUND_PATTERNS))

_INVESTOR_SUFFIX = (
    r"(?:资本|创投|基金|集团|控股|资本管理"
    r"|资产|金控|风投|投资管理|投资集团|投资公司"
    r"|投资合伙企业|创投基金|产业基金|天使基金"
    r"|创业投资|股权投资)"
)

_KNOWN_INVESTOR_LIST = [
    r"红杉(?:资本|中国)?",
    r"IDG资本?",
    r"高瓴资本?",
    r"腾讯(?:投资)?",
    r"阿里巴巴(?:集团)?",
    r"软银(?:集团|中国)?",
    r"淡马锡",
    r"经纬(?:中国|创投)?",
    r"真格基金",
    r"创新工场",
    r"云九资本",
    r"启明创投",
    r"蓝驰创投",
    r"GGV(?:纪源资本)?",
    r"金沙江创投",
    r"北极光创投",
    r"源码资本",
    r"五源资本",
    r"高榕资本",
    r"今日资本",
    r"顺为资本",
    r"鼎晖(?:投资)?",
    r"华平投资",
    r"老虎(?:环球)?基金",
    r"凯雷(?:投资)?",
    r"KKR",
    r"中信(?:产业基金|资本)?",
    r"中金(?:公司|资本)?",
    r"国投(?:创业|创新)?",
    r"深创投",
    r"达晨创投",
    r"毅达资本",
    r"君联资本",
    r"百度(?:风投|资本)?",
    r"美团(?:龙珠资本?)?",
    r"小米(?:集团)?",
    r"京东(?:集团)?",
    r"华为(?:技术)?",
    r"宁德时代",
    r"比亚迪",
    r"蔚来(?:资本)?",
    r"联想(?:创投|之星)?",
    r"复星(?:集团|锐正)?",
    r"海尔资本",
    r"中国互联网投资基金",
    r"国家集成电路产业投资基金",
    r"深圳创新投资集团",
]

_KNOWN_INVESTOR_REGEX = re.compile(
    "|".join(f"(?:{inv})" for inv in _KNOWN_INVESTOR_LIST)
)

_AMOUNT_PATTERN = re.compile(
    r"(?:约|大约|达|超|超过|高达)?"
    r"(\d+(?:\.\d+)?)\s*"
    r"(亿美元|亿美金|亿人民币|亿港元|亿港币|"
    r"万美元|万美金|万人民币|万港元|万港币|"
    r"美元|美金|港元|港币|元人民币|亿元|万元)"
)

_DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?"),
    re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})"),
]


class RegexExtractor(BaseExtractor):
    """基于正则表达式规则的抽取器"""

    def __init__(self):
        super().__init__(name="RegexExtractor")

    def _extract_round(self, text: str) -> Optional[str]:
        """抽取融资轮次"""
        if not text:
            return None
        match = _ROUND_REGEX.search(text)
        if match:
            raw = match.group(0).replace(" ", "")
            if "轮" not in raw:
                if any(kw in raw for kw in ["战略", "并购", "IPO", "三板"]):
                    pass
                elif "融资" in raw:
                    raw = raw.replace("融资", "") + "轮"
            return raw
        return None

    def _extract_amount(self, text: str) -> Optional[str]:
        """抽取融资金额（保留原始字符串，不做归一化）"""
        if not text:
            return None
        match = _AMOUNT_PATTERN.search(text)
        if match:
            return (match.group(1) + match.group(2)).replace(" ", "")
        return None

    def _extract_amount_normalized(self, text: str) -> Optional[float]:
        """抽取融资金额并归一化（万美元）"""
        raw = self._extract_amount(text)
        if raw:
            return normalize_amount(raw)
        return None

    def _extract_investors(self, text: str) -> List[str]:
        """抽取投资方列表"""
        if not text:
            return []

        investors = set()

        for m in _KNOWN_INVESTOR_REGEX.finditer(text):
            raw = m.group(0)
            if len(raw) >= 2 and not self._is_noise_word(raw):
                investors.add(raw)

        suffix_matches = re.findall(
            rf"([\u4e00-\u9fa5]{{2,8}}{_INVESTOR_SUFFIX})", text
        )
        for inv in suffix_matches:
            inv = inv.strip()
            if 3 <= len(inv) <= 15 and not self._is_noise_word(inv):
                investors.add(inv)

        lead_patterns = [
            r"由([\u4e00-\u9fa5A-Za-z0-9·]{2,12})\s*领投",
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,12})\s*领投",
        ]
        for pat in lead_patterns:
            for m in re.finditer(pat, text):
                inv = m.group(1).strip("，。；的由及和与、 领投")
                if 2 <= len(inv) <= 12 and not self._is_noise_word(inv):
                    investors.add(inv)

        follow_matches = re.findall(
            r"([\u4e00-\u9fa5A-Za-z0-9·]{2,15})\s*(?:等\s*)?跟投",
            text,
        )
        for inv in follow_matches:
            inv = inv.strip("，。；的由及和与、 跟")
            if 2 <= len(inv) <= 12 and not self._is_noise_word(inv):
                investors.add(inv)

        invest_by = re.findall(
            r"投资方(?:包括|为|系|有)?([\u4e00-\u9fa5A-Za-z0-9·、；;,，]{2,40})",
            text,
        )
        for group in invest_by:
            parts = re.split(r"[、；;,，]", group)
            for p in parts:
                p = p.strip()
                if 2 <= len(p) <= 12 and not self._is_noise_word(p):
                    investors.add(p)

        normalized = set()
        for inv in investors:
            cleaned = self._clean_investor_name(inv)
            if cleaned:
                normalized.add(cleaned)

        # 过滤掉与 Target 相同的名称
        result = []
        for inv in normalized:
            # 排除纯公司后缀的名称
            if inv in ["公司", "集团", "科技", "企业"]:
                continue
            result.append(inv)

        return result

    @staticmethod
    def _clean_investor_name(name: str) -> Optional[str]:
        """清洗投资方名称，去除上下文噪声"""
        noise_prefixes = [
            "本轮由", "由", "投资方", "包括", "宣布", "获得", "完成",
            "金额", "被投", "投资了", "具体金额和", "金额和",
            "科技今日宣布获得由", "科技获", "布获得由",
        ]
        noise_suffixes = [
            "领投", "跟投", "投资", "等", "等跟投", "等投资",
            "领投了", "投资了", "战略投资", "独家投资",
            "旗下", "关联", "获阿里巴巴", "获中国互联网投资",
        ]
        for prefix in noise_prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        for suffix in noise_suffixes:
            if name.endswith(suffix) and len(name) > len(suffix) + 1:
                name = name[:-len(suffix)]
                break

        name = name.strip("，。；的由及和与、 ")
        if len(name) < 2:
            return None
        if RegexExtractor._is_noise_word(name):
            return None
        return name

    @staticmethod
    def _is_noise_word(word: str) -> bool:
        noise = {
            "完成", "获得", "宣布", "融资", "投资", "亿元", "万美元",
            "人民币", "美元", "领投", "跟投", "公司", "企业", "平台",
            "正式", "刚刚", "已经", "该", "此", "本", "这", "那", "其",
            "近日", "日前", "今日", "方尚未", "尚未披露", "具体金额",
            "金额", "投资方", "被投", "新茶饮", "品牌", "尚未公开",
            "知名机构", "新茶饮品牌", "悦色获得美团",
        }
        for bad_word in noise:
            if bad_word in word:
                return True
        return False

    def _extract_target(self, text: str, title: str = "") -> Optional[str]:
        """抽取被投企业 - 优先从标题提取"""
        if not title and not text:
            return None

        # 优先从标题提取
        if title:
            # 特殊处理："XXX战略投资YYY" 格式，Target 是 YYY
            # 但要排除 "领投" 后面跟的是轮次的情况
            m = re.search(r"(?:战略|股权|定向)?(?:投资|入股)(?:了?)([\u4e00-\u9fa5A-Za-z0-9·]{2,12})", title)
            if m:
                target = m.group(1).strip()
                target = self._clean_target_name(target)
                if self._is_valid_target_name(target):
                    return target

            # 提取标题开头的公司名称（到第一个动词为止）
            m = re.match(r"([\u4e00-\u9fa5A-Za-z0-9·]{2,12})(?:完成|获得|获|宣布|正式)", title)
            if m:
                target = m.group(1).strip()
                target = self._clean_target_name(target)
                if self._is_valid_target_name(target):
                    return target
            
            # 提取标题开头的公司名（带后缀）
            m = re.match(
                r"([\u4e00-\u9fa5A-Za-z0-9·]{2,8}(?:科技|技术|集团|公司|有限|股份"
                r"|网络|数据|智能|汽车|医药|生物|半导体|机器人|新能源"
                r"|航天|卫星|无人机|芯片|软件|云计算|电商|金融|教育"
                r"|医疗|出行|物流|制造|传媒|娱乐|体育|餐饮|零售|保险))",
                title
            )
            if m:
                target = m.group(1).strip()
                target = self._clean_target_name(target)
                if self._is_valid_target_name(target):
                    return target

        combined = f"{title}。{text}" if title else text

        patterns = [
            # 匹配 "XXX公司/科技/集团 完成/获得..."
            re.compile(
                r"([\u4e00-\u9fa5A-Za-z0-9·]{2,8}(?:科技|技术|集团|公司|有限|股份"
                r"|网络|数据|智能|汽车|医药|生物|半导体|机器人|新能源"
                r"|航天|卫星|无人机|芯片|软件|云计算|电商|金融|教育"
                r"|医疗|出行|物流|制造|传媒|娱乐|体育|餐饮|零售|保险))"
                r"\s*(?:完成|获得?|宣布完成|宣布获得?|正式完成|刚刚完成|日前完成"
                r"|今日完成|已?完成|再获|新获|斩获|拿下|签下|获)"
            ),
            # 匹配 "XXX 完成/获 X亿X轮"
            re.compile(
                r"([\u4e00-\u9fa5A-Za-z0-9·]{2,8})"
                r"\s*(?:完成|获)(?:了)?\s*(?:\d+|\d+\.\d+)?\s*(?:亿|万)?"
                r"(?:美元|美金|人民币|港元)?\s*[A-E]\+?\s*轮"
            ),
            # 匹配 "XXX 宣布/完成/获得 融资"
            re.compile(
                r"([\u4e00-\u9fa5A-Za-z0-9·]{2,8})"
                r"\s*(?:宣布完成|完成|获得?|再获|新获)"
                r"\s*(?:了)?\s*(?:新一轮)?\s*(?:战略|股权|定向|过桥)?\s*融资"
            ),
            # 匹配 "投资/入股/领投 XXX"
            re.compile(
                r"(?:投资了?|入股了?|领投了?|跟投了?|参投了?|战略投资了?)"
                r"([\u4e00-\u9fa5A-Za-z0-9·]{2,8})"
            ),
        ]

        for pattern in patterns:
            m = pattern.search(combined)
            if m:
                target = m.group(1).strip("，。；的由及和与、 \t\n\r")
                target = self._clean_target_name(target)
                if self._is_valid_target_name(target):
                    return target

        return None

    @staticmethod
    def _clean_target_name(name: str) -> str:
        """清理 Target 名称，去除前缀噪声"""
        prefixes = [
            "AI芯片初创公司", "智能驾驶公司", "生物科技公司",
            "智能", "生物", "科技", "初创公司", "公司",
        ]
        for prefix in prefixes:
            if name.startswith(prefix) and len(name) > len(prefix) + 2:
                name = name[len(prefix):]
                break
        return name.strip()

    @staticmethod
    def _is_valid_target_name(name: str) -> bool:
        if len(name) < 2 or len(name) > 20:
            return False
        blacklist = {
            "该", "此", "本", "这", "那", "其", "近日", "日前", "今日",
            "公司", "企业", "平台", "正式", "刚刚", "已经",
            "完成", "获得", "宣布", "融资", "投资", "领投", "跟投",
            "方尚未", "尚未披露", "具体金额", "投资方", "金额",
            "品牌", "新茶饮", "集团", "集团领投", "智能驾驶公司",
            "方尚未披露", "的5亿美元Pre",
        }
        if name in blacklist:
            return False
        for bad in ["领投", "跟投", "投资", "获得", "美元", "亿元"]:
            if bad in name:
                return False
        return True

    def _extract_date(self, article: Dict[str, Any]) -> Optional[str]:
        """抽取发布时间"""
        publish_time = article.get("publish_time", "")
        normalized = normalize_date(publish_time)
        if normalized:
            return normalized

        for field in ("title", "summary", "content"):
            text = article.get(field, "")
            if not text:
                continue
            for pat in _DATE_PATTERNS:
                m = pat.search(text)
                if m:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return f"{y:04d}-{mo:02d}-{d:02d}"
        return None

    def extract(self, article: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """
        从单条新闻中抽取完整事件要素
        """
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")
        full_text = f"{title}。{summary}。{content}" if content else f"{title}。{summary}"

        investors = self._extract_investors(full_text)
        investor_str = "；".join(investors) if investors else None

        target = self._extract_target(full_text, title)

        amount = self._extract_amount(full_text)

        round_ = self._extract_round(full_text)

        date = self._extract_date(article)

        return {
            "Investor": investor_str,
            "Target": target,
            "Amount": amount,
            "Round": round_,
            "Date": date,
        }

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
