#!/usr/bin/env python3
"""
核心技术产品发布与升级大事件抽取系统 —— 主入口
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import glob
import json
import logging

from config import (
    DEFAULT_BASIC_RESULTS_FILE,
    RAW_NEWS_DIR,
    IMAGES_DIR,
    LLM_CONFIGURED,
    EXTRACTION_FIELDS,
    DEFAULT_CORPUS_FILE,
    DEFAULT_REGEX_RESULTS_FILE,
    DEFAULT_REGEX_RESULTS_CSV,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def print_banner():
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║    核心技术产品发布与升级大事件抽取系统                          ║
║    Tech Event Extraction System                                   ║
║                                                                   ║
║    5要素: 研发主体/技术产品/事件动作/版本指标/发布时间              ║
║    developer / tech_product / action_type / version_metric / date ║
║                                                                   ║
║    数据源: 复用作业2本地中文科技新闻语料                         ║
║    支持739篇语料 · 删除INFO_RETRIEVE后仍可运行                   ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    if LLM_CONFIGURED:
        print(" ✅ LLM API Key 已配置，可使用 NLPExtractor")
    else:
        print(" ⚠️  LLM API Key 未配置，将使用 RegexExtractor")
        print("    请在 config.py 中配置 api_key")
    print()


def print_main_menu():
    print("\n" + "=" * 50)
    print("  📋 主菜单")
    print("=" * 50)
    print("  1. 📦  构建/检查作业3本地语料")
    print("  2. 🔍  抽取科技事件要素并保存结果")
    print("  3. 📝  交互式人工标注/评测")
    print("  4. 📷  跨模态 OCR 抽取（海报 → 事件）")
    print("  5. 🎬  快速演示本地抽取流程")
    print("")
    print("  0. 🚪 退出")
    print("=" * 50)


def build_from_retrieve_menu():
    from utils.pipeline import convert_retrieve_documents, corpus_stats, load_corpus

    try:
        if os.path.exists(DEFAULT_CORPUS_FILE):
            corpus = load_corpus(DEFAULT_CORPUS_FILE)
            print(f"\n✅ 已找到作业3本地语料: {DEFAULT_CORPUS_FILE}")
        else:
            corpus = convert_retrieve_documents()
            print(f"\n✅ 已生成作业3语料: {DEFAULT_CORPUS_FILE}")
        stats = corpus_stats(corpus)
        print(f"   文档数量: {stats['total_articles']}")
        print(f"   来源数量: {stats['source_count']}")
        print("   该文件位于作业3目录内，后续删除 INFO_RETRIEVE 也可继续运行。")
    except Exception as e:
        print(f"\n❌ 构建失败: {e}")


def select_extractor():
    print("\n" + "-" * 45)
    print("  🤖  选择抽取算法")
    print("-" * 45)
    print("  1. 🧪  BasicRegexExtractor (基础正则 baseline)")
    print("  2. 🔧  OptimizedRegexExtractor (优化正则 - 推荐，无需配置)")
    if LLM_CONFIGURED:
        print("  3. 🧠  NLPExtractor (MiniMax API - 智能，已配置API)")
    else:
        print("  3. 🧠  NLPExtractor (MiniMax API - 需配置 API Key)")
    print("-" * 45)

    choice = input("请选择 [1-3]: ").strip()
    if choice == "1":
        from extractor.regex_extractor import BasicRegexExtractor
        return "BasicRegexExtractor", BasicRegexExtractor()
    elif choice == "2":
        from extractor.regex_extractor import RegexExtractor
        return "OptimizedRegexExtractor", RegexExtractor()
    elif choice == "3":
        from extractor.nlp_extractor import NLPExtractor
        return "NLPExtractor", NLPExtractor()
    else:
        print("⚠️ 默认选择 OptimizedRegexExtractor")
        from extractor.regex_extractor import RegexExtractor
        return "OptimizedRegexExtractor", RegexExtractor()


def run_extractor_menu():
    from config import DEFAULT_NLP_RESULTS_CSV, DEFAULT_NLP_RESULTS_FILE
    from utils.pipeline import (
        extraction_stats,
        run_algorithm_comparison,
        run_selectable_extraction,
        select_demo_rows,
    )

    if not os.path.exists(DEFAULT_CORPUS_FILE):
        print("⚠️  未找到作业3本地语料，正在尝试从作业2构建...")
        build_from_retrieve_menu()

    files = sorted(glob.glob(os.path.join(RAW_NEWS_DIR, "*.json")))
    if not files:
        print("⚠️  没有找到本地语料，请先构建作业3本地语料！")
        return

    print("\n" + "-" * 45)
    print("  🔍  抽取引擎菜单")
    print("-" * 45)
    print(f"  已找到 {len(files)} 个数据文件：")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {os.path.basename(f)}")
    print("\n  0. 返回主菜单")

    try:
        choice = input("\n请选择文件 (0 返回): ").strip()
        if choice == "0":
            return
        idx = int(choice) - 1
        if idx < 0 or idx >= len(files):
            print("❌ 无效选择")
            return

        filepath = files[idx]
        print(f"\n📄 正在加载: {os.path.basename(filepath)}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        articles = data.get("articles", [])

        extractor_name, extractor = select_extractor()

        print(f"\n⚙️  已初始化抽取器: {extractor_name}")
        optimized = None
        if os.path.abspath(filepath) == os.path.abspath(DEFAULT_CORPUS_FILE) and extractor_name == "BasicRegexExtractor":
            print("\n💾 正在运行基础正则 baseline 并保存结果...")
            optimized = run_selectable_extraction("basic", filepath)
            stats = extraction_stats(optimized)
            print(f"✅ 基础正则结果已保存: {DEFAULT_BASIC_RESULTS_FILE}")
            print(f"   较完整事件数(至少4字段): {stats['complete_events']}")
        elif os.path.abspath(filepath) == os.path.abspath(DEFAULT_CORPUS_FILE) and extractor_name == "OptimizedRegexExtractor":
            print("\n💾 正在运行优化正则并保存完整结果...")
            optimized = run_selectable_extraction("optimized", filepath)
            stats = extraction_stats(optimized)
            print(f"✅ 完整结果已保存: {DEFAULT_REGEX_RESULTS_FILE}")
            print(f"✅ CSV表格已保存: {DEFAULT_REGEX_RESULTS_CSV}")
            print(f"   较完整事件数(至少4字段): {stats['complete_events']}")
        elif os.path.abspath(filepath) == os.path.abspath(DEFAULT_CORPUS_FILE) and extractor_name == "NLPExtractor":
            limit_text = input("\nAPI抽取可能产生费用，请输入抽取篇数 [默认5，输入 all 跑全量]: ").strip()
            limit = None if limit_text.lower() == "all" else int(limit_text or "5")
            print(f"\n💾 正在运行 NLP/API 抽取，篇数: {'全部' if limit is None else limit}...")
            optimized = run_selectable_extraction("nlp", filepath, limit=limit)
            stats = extraction_stats(optimized)
            print(f"✅ API抽取结果已保存: {DEFAULT_NLP_RESULTS_FILE}")
            print(f"✅ API CSV表格已保存: {DEFAULT_NLP_RESULTS_CSV}")
            print(f"   较完整事件数(至少4字段): {stats['complete_events']}")

        print(f"\n" + "=" * 100)
        print(f"  {'序号':<4} {'标题':<40} {'研发主体':<12} {'技术产品':<16} {'事件动作':<12}")
        print(f"  {'-'*4} {'-'*40} {'-'*12} {'-'*16} {'-'*12}")

        if optimized:
            display_rows = select_demo_rows(optimized.get("results", []), limit=15)
        else:
            display_rows = []
            for art in articles:
                res = extractor.extract(art)
                row = {"title": art.get("title", ""), **res}
                display_rows.append(row)
            display_rows = select_demo_rows(display_rows, limit=15)

        for i, row in enumerate(display_rows, 1):
            title = row.get("title", "")[:38]
            dev = (row.get("developer") or "-")[:10]
            prod = (row.get("tech_product") or "-")[:14]
            action = (row.get("action_type") or "-")[:10]
            print(f"  {i:<4} {title:<40} {dev:<12} {prod:<16} {action:<12}")

        print(f"  {'-'*4} {'-'*40} {'-'*12} {'-'*16} {'-'*12}")
        print(f"  (仅显示前 15 条，{len(articles)} 条已完成抽取)")
        print(f"\n💡 完整抽取包含 5 字段：developer / tech_product / action_type / version_metric / date")

    except ValueError:
        print("❌ 请输入有效数字")


def run_evaluator_menu():
    files = sorted(glob.glob(os.path.join(RAW_NEWS_DIR, "*.json")))
    if not files:
        print("⚠️  没有找到本地语料，请先构建作业3本地语料！")
        return

    print("\n" + "-" * 45)
    print("  📝  评价系统菜单")
    print("-" * 45)
    print("  选择要标注/评测的数据源：")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {os.path.basename(f)}")
    print("\n  0. 返回主菜单")

    try:
        choice = input("\n请选择 (0 返回): ").strip()
        if choice == "0":
            return
        idx = int(choice) - 1
        if idx < 0 or idx >= len(files):
            print("❌ 无效选择")
            return

        from evaluator import EvaluationSystem
        evaluator = EvaluationSystem(files[idx])
        evaluator.interactive_menu()

    except ValueError:
        print("❌ 请输入有效数字")


def run_multimodal_menu():
    print("\n" + "-" * 45)
    print("  📷  跨模态 OCR 抽取")
    print("-" * 45)
    print("  1. 运行演示管线（生成科技海报 → OCR → 抽取）")
    print("  2. 处理 data/images/ 目录下所有图片")
    print("  3. 指定单个图片路径处理")
    print("  0. 返回主菜单")

    try:
        choice = input("\n请选择: ").strip()
        if choice == "1":
            from multimodal import demo_pipeline
            demo_pipeline()
        elif choice == "2":
            from multimodal import MultimodalExtractor
            extractor = MultimodalExtractor()
            results = extractor.process_directory(IMAGES_DIR)
            if results:
                extractor.save_results(results)
        elif choice == "3":
            path = input("\n请输入图片路径: ").strip()
            if not os.path.exists(path):
                print("❌ 文件不存在")
                return
            from multimodal import MultimodalExtractor
            extractor = MultimodalExtractor()
            result = extractor.process_image(path)
            print(f"\n✅ 抽取结果：")
            print(json.dumps(result.get("extraction", {}), ensure_ascii=False, indent=2))
        elif choice == "0":
            return
        else:
            print("❌ 无效选项")
    except Exception as e:
        logger.error("跨模态模块错误：%s", e)
        print(f"\n⚠️  提示：OCR 功能需要安装 easyocr")
        print("   运行：pip install easyocr")


def run_quick_demo():
    from utils.pipeline import extraction_stats, load_corpus, run_algorithm_comparison, select_demo_rows

    print("\n" + "=" * 55)
    print("  🎬  快速演示本地抽取流程")
    print("=" * 55)

    print("\n" + "-" * 55)
    print("  [1/3] 加载作业3本地语料")
    print("-" * 55)
    try:
        corpus = load_corpus(DEFAULT_CORPUS_FILE)
    except Exception as e:
        print(f"⚠️  未能加载本地语料: {e}")
        return
    articles = corpus.get("articles", [])
    print(f"\n✅ 已加载 {len(articles)} 篇中文科技新闻")

    print("\n" + "-" * 55)
    print("  [2/3] 运行基础/优化正则抽取并保存结果")
    print("-" * 55)

    _, optimized = run_algorithm_comparison(DEFAULT_CORPUS_FILE)
    stats = extraction_stats(optimized)
    print(f"✅ 抽取结果: {DEFAULT_REGEX_RESULTS_FILE}")
    print(f"✅ CSV结果: {DEFAULT_REGEX_RESULTS_CSV}")
    print(f"   较完整事件数: {stats['complete_events']}")

    print("\n  抽取样例：")
    for i, row in enumerate(select_demo_rows(optimized.get("results", []), limit=5), 1):
        print(f"\n  事件 {i}: {row.get('title', '')[:55]}")
        print(f"    developer:       {row.get('developer') or '-'}")
        print(f"    tech_product:    {row.get('tech_product') or '-'}")
        print(f"    action_type:     {row.get('action_type') or '-'}")
        print(f"    version_metric:  {row.get('version_metric') or '-'}")
        print(f"    date:            {row.get('date') or '-'}")

    print("\n" + "-" * 55)
    print("  [3/3] 抽取管线准备完毕")
    print("-" * 55)
    print("\n✅ 全流程演示完成！")
    print(f"\n💡 共处理 {len(articles)} 篇本地语料")
    print("\n💡 下一步：")
    print("   - 去运行主菜单的『交互式人工标注/评测』")
    print("   - 或运行『跨模态 OCR 抽取』看看海报识别效果")


def main():
    print_banner()

    while True:
        print_main_menu()
        choice = input("  请选择: ").strip()

        if choice == "1":
            build_from_retrieve_menu()
        elif choice == "2":
            run_extractor_menu()
        elif choice == "3":
            run_evaluator_menu()
        elif choice == "4":
            run_multimodal_menu()
        elif choice == "5":
            run_quick_demo()
        elif choice == "0":
            print("\n👋 再见！")
            break
        else:
            print("  ❌ 无效选项，请重新选择")


if __name__ == "__main__":
    main()
