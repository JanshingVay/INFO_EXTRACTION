"""Calculate extraction metrics from saved annotations."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os

from config import DEFAULT_EVAL_ANNOTATIONS_FILE, DEFAULT_EVAL_METRICS_FILE, DEFAULT_REGEX_RESULTS_FILE
from evaluator.metrics import calculate_extraction_metrics
from utils.helpers import load_json, save_json


def main() -> None:
    results_data = load_json(DEFAULT_REGEX_RESULTS_FILE)
    rows = results_data.get("results", [])
    if not os.path.exists(DEFAULT_EVAL_ANNOTATIONS_FILE):
        print(f"未找到人工标注文件: {DEFAULT_EVAL_ANNOTATIONS_FILE}")
        print("请先在 Streamlit 的“人工评价”页面保存标注，再计算指标。")
        return
    anno_data = load_json(DEFAULT_EVAL_ANNOTATIONS_FILE)
    annotations = anno_data.get("annotations", anno_data)
    metrics = calculate_extraction_metrics(rows, annotations)
    save_json(metrics, DEFAULT_EVAL_METRICS_FILE)
    print(f"已保存评价指标: {DEFAULT_EVAL_METRICS_FILE}")
    print(f"标注样本数: {metrics['summary']['total_annotated']}")
    print(f"Macro F1: {metrics['overall']['Macro_Avg_F1_Score']}")


if __name__ == "__main__":
    main()
