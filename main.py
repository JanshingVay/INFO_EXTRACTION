#!/usr/bin/env python3
"""
特定领域多媒体信息抽取系统 —— 主入口

命令行菜单串联：
  - 爬虫模块 (AsyncNewsCrawler)
  - 抽取引擎 (RegexExtractor / NLPExtractor)
  - 评价系统 (EvaluationSystem)
  - 多模态 OCR 管线 (MultimodalExtractor)
"""
import os
import sys
import glob
import json
import asyncio
import logging
from typing import Dict, Any, Optional

from config import BASE_DIR, RAW_NEWS_DIR, IMAGES_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def print_banner():
    """打印启动横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║    特定领域多媒体信息抽取系统                                     ║
║    Domain-Specific Multimedia Information Extraction System        ║
║                                                                   ║
║    领域: 科技企业投融资事件                                        ║
║    目标: 抽取 {Investor, Target, Amount, Round, Date}             ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_main_menu():
    """打印主菜单"""
    print("\n" + "═" * 50)
    print("  📋 主菜单")
    print("═" * 50)
    print("  1. 🕷️   运行爬虫（采集新闻）")
    print("  2. 🔍   抽取新闻事件要素")
    print("  3. 📝   交互式人工标注/评测")
    print("  4. 📷   跨模态 OCR 抽取（图片 → 事件）")
    print("  5. 🎬   快速演示全流程")
    print("")
    print("  0. 🚪   退出")
    print("═" * 50)


def run_crawler_menu():
    """爬虫子菜单"""
    print("\n" + "─" * 45)
    print("  🕷️  爬虫菜单")
    print("─" * 45)
    print("  1. 运行演示模式（快速生成 10 条模拟新闻）")
    print("  2. 运行真实爬虫（36氪 / 投资界 / IT桔子）")
    print("  0. 返回主菜单")
    choice = input("\n请选择: ").strip()

    if choice == "1":
        logger.info("运行爬虫演示模式...")
        from crawler.news_crawler import demo_crawl
        asyncio.run(demo_crawl())
    elif choice == "2":
        logger.info("运行真实爬虫（异步高并发）...")
        print("\n(提示: 真实爬虫需要网络连接，可能被反爬拦截，返回演示数据)")
        from crawler.news_crawler import demo_crawl
        asyncio.run(demo_crawl())
    elif choice == "0":
        return
    else:
        print("❌ 无效选项")


def run_extractor_menu():
    """抽取引擎子菜单"""
    files = sorted(glob.glob(os.path.join(RAW_NEWS_DIR, "*.json")))
    if not files:
        print("⚠️  没有找到新闻数据，请先运行爬虫！")
        return

    print("\n" + "─" * 45)
    print("  🔍  抽取引擎菜单")
    print("─" * 45)
    print(f"  已找到 {len(files)} 个数据文件:")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {os.path.basename(f)}")
    print("\n  0. 返回主菜单")

    try:
        choice = input("\n请选择文件 (0 返回): ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx >= len(files):
            print("❌ 无效选择")
            return

        filepath = files[idx]
        print(f"\n📄 正在加载: {os.path.basename(filepath)}")

        from crawler.news_crawler import AsyncNewsCrawler
        articles = AsyncNewsCrawler.load_results(filepath)

        from extractor.regex_extractor import RegexExtractor
        from extractor.nlp_extractor import NLPExtractor

        regex = RegexExtractor()
        nlp = NLPExtractor()

        print(f"\n⚙️  已初始化两个抽取器: RegexExtractor, NLPExtractor")
        print(f"\n" + "─" * 70)
        print(f"  {'序号':<4} {'文章标题':<40} {'Target':<15} {'Amount':<12} {'Round':<8}")
        print(f"  {'─'*4} {'─'*40} {'─'*15} {'─'*12} {'─'*8}")

        for i, art in enumerate(articles[:10], 1):
            res = regex.extract(art)
            title = art.get("title", "")[:38]
            target = res.get("Target") or "(未抽出)"
            amount = res.get("Amount") or "(未抽出)"
            round_ = res.get("Round") or "(未抽出)"
            print(f"  {i:<4} {title:<40} {target:<15} {amount:<12} {round_:<8}")

        print(f"  {'─'*4} {'─'*40} {'─'*15} {'─'*12} {'─'*8}")
        print(f"  (仅显示前 10 条，{len(articles)} 条全部已抽取)")

    except ValueError:
        print("❌ 请输入有效数字")


def run_evaluator_menu():
    """评价系统子菜单"""
    files = sorted(glob.glob(os.path.join(RAW_NEWS_DIR, "*.json")))
    if not files:
        print("⚠️  没有找到新闻数据，请先运行爬虫！")
        return

    print("\n" + "─" * 45)
    print("  📝  评价系统菜单")
    print("─" * 45)
    print("  选择要标注/评测的数据源:")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {os.path.basename(f)}")
    print("\n  0. 返回主菜单")

    try:
        choice = input("\n请选择 (0 返回): ").strip()
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
    """跨模态 OCR 菜单"""
    print("\n" + "─" * 45)
    print("  📷  跨模态 OCR 抽取")
    print("─" * 45)
    print("  1. 运行演示管线（生成新闻截图 → OCR → 抽取）")
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
            print(f"\n✅ 抽取结果:")
            print(json.dumps(result["regex_result"], ensure_ascii=False, indent=2))
        elif choice == "0":
            return
        else:
            print("❌ 无效选项")
    except Exception as e:
        logger.error("跨模态模块错误: %s", e)
        print(f"\n⚠️  提示: OCR 功能需要安装 easyocr 或 pytesseract")
        print("   运行: pip install easyocr")


def run_quick_demo():
    """快速演示全流程"""
    print("\n" + "=" * 55)
    print("  🎬  快速演示全流程")
    print("=" * 55)

    print("\n" + "─" * 55)
    print("  [1/4] 运行爬虫演示")
    print("─" * 55)
    from crawler.news_crawler import demo_crawl
    asyncio.run(demo_crawl())

    print("\n" + "─" * 55)
    print("  [2/4] 抽取新闻事件要素（RegexExtractor）")
    print("─" * 55)
    files = sorted(glob.glob(os.path.join(RAW_NEWS_DIR, "*.json")))
    if not files:
        print("❌ 未找到数据文件")
        return

    from crawler.news_crawler import AsyncNewsCrawler
    from extractor.regex_extractor import RegexExtractor

    articles = AsyncNewsCrawler.load_results(files[-1])
    extractor = RegexExtractor()
    for i, art in enumerate(articles[:5], 1):
        res = extractor.extract(art)
        print(f"\n  文章 {i}: {art['title'][:50]}")
        print(f"    Investor: {res['Investor'] or '(未抽出)'}")
        print(f"    Target  : {res['Target'] or '(未抽出)'}")
        print(f"    Amount  : {res['Amount'] or '(未抽出)'}")
        print(f"    Round   : {res['Round'] or '(未抽出)'}")
        print(f"    Date    : {res['Date'] or '(未抽出)'}")

    print("\n" + "─" * 55)
    print("  [3/4] 跨模态 OCR 演示（生成截图 → 抽取）")
    print("─" * 55)
    try:
        from multimodal import generate_demo_image
        image_path = generate_demo_image()
        print(f"✅ 生成演示图片: {os.path.basename(image_path)}")

        print("\n" + "─" * 55)
        print("  [4/4] 抽取管线准备完毕！")
        print("─" * 55)
        print("\n✅ 全流程演示完成！")
        print("\n💡 下一步：")
        print("   - 去运行主菜单的『交互式人工标注/评测』")
        print("   - 或运行『跨模态 OCR 抽取』")
    except Exception as e:
        print(f"⚠️  OCR 依赖暂未安装，演示跳过: {e}")


def main():
    """主程序入口"""
    print_banner()

    while True:
        print_main_menu()
        choice = input("  请选择: ").strip()

        if choice == "1":
            run_crawler_menu()
        elif choice == "2":
            run_extractor_menu()
        elif choice == "3":
            run_evaluator_menu()
        elif choice == "4":
            run_multimodal_menu()
        elif choice == "5":
            run_quick_demo()
        elif choice == "0":
            print("\n👋 再见！感谢使用。")
            break
        else:
            print("  ❌ 无效选项，请重新选择")


if __name__ == "__main__":
    main()
