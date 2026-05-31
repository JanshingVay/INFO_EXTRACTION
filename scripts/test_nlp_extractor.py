"""Smoke test for the optional NLP/LLM extractor."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LLM_CONFIG, LLM_CONFIGURED
from extractor.nlp_extractor import NLPExtractor


def main() -> None:
    print("LLM configured:", LLM_CONFIGURED)
    print("Base URL:", LLM_CONFIG["api_url"])
    print("Model:", LLM_CONFIG["model"])
    if not LLM_CONFIGURED:
        print("未配置 LLM_API_KEY，将自动回退到 RegexExtractor。")

    article = {
        "id": "demo",
        "title": "华为发布 HarmonyOS 6.0，系统流畅度提升 30%",
        "summary": "华为今日发布 HarmonyOS 6.0，面向多设备场景升级系统能力。",
        "content": "发布日期：2026-05-31。华为发布 HarmonyOS 6.0，系统流畅度提升 30%。",
        "publish_time": "2026-05-31",
    }
    result = NLPExtractor().extract(article)
    print("抽取结果:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
