"""Calculate extraction metrics from saved annotations."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DEFAULT_BASIC_RESULTS_FILE,
    DEFAULT_NLP_RESULTS_FILE,
    DEFAULT_OPEN_NLP_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_FILE,
    EVAL_DIR,
)
from evaluator.metrics import calculate_extraction_metrics
from utils.helpers import load_json, save_json


EVAL_TARGETS = {
    "regex": {
        "name": "优化正则结果",
        "result_file": DEFAULT_REGEX_RESULTS_FILE,
        "annotation_file": os.path.join(EVAL_DIR, "annotations_regex.json"),
        "metrics_file": os.path.join(EVAL_DIR, "metrics_regex.json"),
    },
    "open_nlp": {
        "name": "开源 NLP 结果",
        "result_file": DEFAULT_OPEN_NLP_RESULTS_FILE,
        "annotation_file": os.path.join(EVAL_DIR, "annotations_opensource_nlp.json"),
        "metrics_file": os.path.join(EVAL_DIR, "metrics_opensource_nlp.json"),
    },
    "nlp": {
        "name": "DeepSeek API 结果",
        "result_file": DEFAULT_NLP_RESULTS_FILE,
        "annotation_file": os.path.join(EVAL_DIR, "annotations_nlp.json"),
        "metrics_file": os.path.join(EVAL_DIR, "metrics_nlp.json"),
    },
    "basic": {
        "name": "基础正则结果",
        "result_file": DEFAULT_BASIC_RESULTS_FILE,
        "annotation_file": os.path.join(EVAL_DIR, "annotations_basic.json"),
        "metrics_file": os.path.join(EVAL_DIR, "metrics_basic.json"),
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="计算作业3信息抽取人工评价指标")
    parser.add_argument(
        "--target",
        choices=sorted(EVAL_TARGETS),
        default="regex",
        help="选择要评价的抽取结果，默认 regex=优化正则。",
    )
    args = parser.parse_args()

    target = EVAL_TARGETS[args.target]
    results_data = load_json(target["result_file"])
    rows = results_data.get("results", [])
    if not os.path.exists(target["annotation_file"]):
        print(f"未找到人工标注文件: {target['annotation_file']}")
        print("请先在 Streamlit 的“人工评价”页面保存标注，再计算指标。")
        return
    anno_data = load_json(target["annotation_file"])
    annotations = anno_data.get("annotations", anno_data)
    metrics = calculate_extraction_metrics(rows, annotations)
    metrics["summary"]["result_name"] = target["name"]
    metrics["summary"]["result_file"] = target["result_file"]
    metrics["summary"]["annotation_file"] = target["annotation_file"]
    save_json(metrics, target["metrics_file"])
    print(f"评价对象: {target['name']}")
    print(f"已保存评价指标: {target['metrics_file']}")
    print(f"标注样本数: {metrics['summary']['total_annotated']}")
    print(f"抽取结果数: {metrics['summary']['total_extractions']}")
    print(f"Macro F1: {metrics['overall']['Macro_Avg_F1_Score']}")


if __name__ == "__main__":
    main()
