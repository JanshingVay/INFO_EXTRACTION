"""Run event extraction on the local corpus."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DEFAULT_BASIC_RESULTS_FILE,
    DEFAULT_NLP_RESULTS_CSV,
    DEFAULT_NLP_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
    DEFAULT_REGEX_RESULTS_FILE,
)
from utils.pipeline import extraction_stats, run_algorithm_comparison, run_selectable_extraction


def main() -> None:
    parser = argparse.ArgumentParser(description="作业3信息抽取")
    parser.add_argument(
        "--extractor",
        choices=["comparison", "optimized", "basic", "open_nlp", "nlp"],
        default="comparison",
        help="comparison=基础正则+优化正则；open_nlp=jieba开源NLP抽取；nlp=API/LLM抽取",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制抽取前N篇，建议API抽取时先设置较小数值。",
    )
    args = parser.parse_args()

    if args.extractor == "comparison":
        _basic, result = run_algorithm_comparison()
        print(f"基础正则结果: {DEFAULT_BASIC_RESULTS_FILE}")
        print(f"优化正则结果: {DEFAULT_REGEX_RESULTS_FILE}")
        print(f"CSV表格结果: {DEFAULT_REGEX_RESULTS_CSV}")
    else:
        result = run_selectable_extraction(args.extractor, limit=args.limit)
        if args.extractor == "nlp":
            print(f"API/LLM抽取结果: {DEFAULT_NLP_RESULTS_FILE}")
            print(f"API/LLM CSV结果: {DEFAULT_NLP_RESULTS_CSV}")
        elif args.extractor == "open_nlp":
            print("开源NLP抽取结果: data/extraction_results/opensource_nlp_results.json")
            print("开源NLP CSV结果: data/extraction_results/opensource_nlp_results.csv")
        elif args.extractor == "basic":
            print(f"基础正则结果: {DEFAULT_BASIC_RESULTS_FILE}")
        else:
            print(f"优化正则结果: {DEFAULT_REGEX_RESULTS_FILE}")
            print(f"CSV表格结果: {DEFAULT_REGEX_RESULTS_CSV}")

    stats = extraction_stats(result)
    print(f"抽取记录数: {stats['total_results']}")
    print(f"较完整事件数(至少4字段): {stats['complete_events']}")
    print("字段覆盖数:")
    for field, count in stats["by_field"].items():
        print(f"  {field}: {count}")


if __name__ == "__main__":
    main()
