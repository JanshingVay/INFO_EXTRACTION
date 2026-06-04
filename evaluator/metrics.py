"""Field-level evaluation utilities for event extraction."""
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from config import EXTRACTION_FIELDS


def fuzzy_match(extracted: Optional[str], ground: Optional[str]) -> bool:
    if extracted is None and ground is None:
        return True
    if extracted is None or ground is None:
        return False
    e = str(extracted).strip().lower().replace(" ", "").replace(",", "，")
    g = str(ground).strip().lower().replace(" ", "").replace(",", "，")
    return e == g or e in g or g in e


def normalize_blank(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in {"*", "None", "null", "NULL", "无", "未抽取"}:
        return None
    return value


def calculate_extraction_metrics(
    extraction_rows: Iterable[Dict[str, Any]],
    annotations: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    extraction_rows = list(extraction_rows)
    rows = {str(row.get("article_id")): row for row in extraction_rows}
    common = sorted(set(rows) & set(str(k) for k in annotations.keys()))

    results: Dict[str, Any] = {
        "summary": {
            "total_annotated": len(common),
            "total_extractions": len(extraction_rows),
            "total_unique_extractions": len(rows),
            "evaluated_at": datetime.now().isoformat(timespec="seconds"),
            "fields": EXTRACTION_FIELDS,
        },
        "by_field": {},
        "overall": {},
    }

    for field in EXTRACTION_FIELDS:
        tp = fp = fn = 0
        for aid in common:
            extracted = normalize_blank(rows[aid].get(field))
            ground = normalize_blank(annotations.get(aid, {}).get(field))
            matched = fuzzy_match(extracted, ground)

            if extracted is not None and ground is not None and matched:
                tp += 1
            elif extracted is not None and (ground is None or not matched):
                fp += 1
            elif ground is not None and (extracted is None or not matched):
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results["by_field"][field] = {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "Precision": round(precision, 4),
            "Recall": round(recall, 4),
            "F1_Score": round(f1, 4),
        }

    field_count = max(len(EXTRACTION_FIELDS), 1)
    results["overall"] = {
        "Macro_Avg_Precision": round(
            sum(results["by_field"][f]["Precision"] for f in EXTRACTION_FIELDS) / field_count,
            4,
        ),
        "Macro_Avg_Recall": round(
            sum(results["by_field"][f]["Recall"] for f in EXTRACTION_FIELDS) / field_count,
            4,
        ),
        "Macro_Avg_F1_Score": round(
            sum(results["by_field"][f]["F1_Score"] for f in EXTRACTION_FIELDS) / field_count,
            4,
        ),
    }
    return results
