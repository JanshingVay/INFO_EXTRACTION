"""
通用工具函数
"""
import json
import re
import os
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_json(filepath: str) -> Any:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, filepath: str, indent: int = 2):
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def normalize_amount(amount_str: str) -> Optional[float]:
    """将金额字符串归一化为万美元"""
    if not amount_str:
        return None
    amount_str = amount_str.strip().replace(" ", "").replace(",", "")
    pattern = r"([\d.]+)\s*(亿|万|美元|美金|元|人民币|港元|港币)?"
    match = re.search(pattern, amount_str)
    if not match:
        return None
    try:
        value = float(match.group(1))
        unit = match.group(2) or ""
        if "亿" in unit:
            if "美元" in amount_str or "美金" in amount_str:
                value *= 10000
            else:
                value = value * 10000 / 7.2
        elif "万" in unit:
            if "美元" in amount_str or "美金" in amount_str:
                pass
            else:
                value = value / 7.2
        elif "美元" in amount_str or "美金" in amount_str:
            pass
        elif "港元" in amount_str or "港币" in amount_str:
            value = value / 7.8
        else:
            value = value / 7.2
        return round(value, 2)
    except (ValueError, TypeError):
        return None


def normalize_date(date_str: str) -> Optional[str]:
    """将日期字符串归一化为 YYYY-MM-DD"""
    if not date_str:
        return None
    patterns = [
        (r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日]?", "%Y-%m-%d"),
        (r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", "%Y-%m-%d"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, date_str)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return date_str


def extract_chinese_companies(text: str) -> List[str]:
    """从文本中提取疑似公司名称"""
    patterns = [
        r"(?:^|[，。；\s])?([\u4e00-\u9fa5]{2,8}(?:科技|技术|集团|公司|资本|基金|创投|投资|银行|证券|保险|网络|数据|智能|汽车|医药|生物|半导体))",
        r"([\u4e00-\u9fa5]{2,6}(?:创投|资本|基金))",
    ]
    results = []
    for pat in patterns:
        results.extend(re.findall(pat, text))
    return list(set(results))
