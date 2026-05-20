"""
交互式人工评价系统 - 科技技术大事件

功能：
- 命令行交互式打标签（Ground Truth 标注）
- 支持断点续标
- 自动计算 Precision/Recall/F1 指标
- 标注数据持久化
"""
import json
import os
import re
import glob
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any

from config import EXTRACTION_FIELDS, EVAL_DIR
from utils.helpers import load_json, save_json


class EvaluationSystem:
    """交互式人工评价系统"""

    def __init__(self, news_filepath: str = None):
        from extractor.regex_extractor import RegexExtractor
        self.extractor = RegexExtractor()
        self.fields = EXTRACTION_FIELDS
        self.field_descriptions = {
            "developer": "研发主体（公司/基金会/研究机构）",
            "tech_product": "核心技术/产品/开源项目名",
            "action_type": "事件动作（开源/发布/升级/修复等）",
            "version_metric": "版本号或关键指标数据",
            "date": "发布日期（YYYY-MM-DD）",
        }

        self.articles: List[Dict[str, Any]] = []
        self.extractions: Dict[str, Dict[str, Optional[str]]] = {}
        self.ground_truth: Dict[str, Dict[str, Optional[str]]] = {}
        self._data_filepath = news_filepath
        self._anno_filepath = ""

        if news_filepath:
            self._load_articles(news_filepath)
        else:
            self._auto_load_latest()

    def _auto_load_latest(self):
        files = sorted(glob.glob(os.path.join(EVAL_DIR, "..", "raw_news", "*.json")))
        if not files:
            print("❌ 未找到爬虫数据文件，请先运行爬虫！")
            return
        self._load_articles(files[-1])

    def _load_articles(self, filepath: str):
        self._data_filepath = filepath
        data = load_json(filepath)
        self.articles = data.get("articles", [])
        basename = os.path.splitext(os.path.basename(filepath))[0]
        self._anno_filepath = os.path.join(EVAL_DIR, f"annotations_{basename}.json")
        print(f"📄 已加载 {len(self.articles)} 篇文章")

        self._run_extractor()
        self._load_annotations()

    def _run_extractor(self):
        print("⏳ 正在运行 RegexExtractor...")
        for art in self.articles:
            aid = art.get("id", "")
            self.extractions[aid] = self.extractor.extract(art)
        print("✅ 抽取完成\n")

    def _load_annotations(self):
        if os.path.exists(self._anno_filepath):
            data = load_json(self._anno_filepath)
            self.ground_truth = data.get("annotations", {})
            print(f"📝 已恢复 {len(self.ground_truth)} 条已有标注")
        else:
            self.ground_truth = {}

    def _save_annotations(self):
        output = {
            "metadata": {
                "data_source": self._data_filepath,
                "total_articles": len(self.articles),
                "annotated_count": len(self.ground_truth),
                "last_updated": datetime.now().isoformat(),
                "fields": self.fields,
            },
            "articles": self.articles,
            "annotations": self.ground_truth,
        }
        save_json(output, self._anno_filepath)
        print(f"💾 标注已保存至: {self._anno_filepath}")

    def _display_article(self, art: Dict[str, Any], idx: int):
        aid = art.get("id", "")
        title = art.get("title", "(无标题)")
        summary = art.get("summary", "")
        publish_time = art.get("publish_time", "")

        print(f"\n{'═' * 80}")
        print(f"  第 {idx+1}/{len(self.articles)} 篇")
        print(f"{'═' * 80}")
        print(f"  标题：{title}")
        if publish_time:
            print(f"  发布时间：{publish_time}")
        if summary:
            print(f"  摘要：{summary[:140]}")

        extraction = self.extractions.get(aid, {})
        print(f"\n  🤖  自动抽取结果：")
        print(f"  {'─' * 78}")
        for field in self.fields:
            val = extraction.get(field) or "(未抽取)"
            desc = self.field_descriptions.get(field, "")
            print(f"  {field:>12}: {val:<30} [{desc}]")

        gt = self.ground_truth.get(aid, {})
        if gt:
            print(f"\n  📌  已有标注：")
            print(f"  {'─' * 78}")
            for field in self.fields:
                gt_val = gt.get(field) or "(未标注)"
                print(f"  {field:>12}: {gt_val}")

    def annotate_article(self, art_idx: int) -> bool:
        if art_idx < 0 or art_idx >= len(self.articles):
            print(f"❌ 序号 {art_idx+1} 超出范围 (1-{len(self.articles)})")
            return False

        art = self.articles[art_idx]
        aid = art.get("id", "")
        self._display_article(art, art_idx)

        existing = self.ground_truth.get(aid, {})

        if existing:
            print(f"\n  ⚠️  此篇已有标注。是否覆盖？")
            choice = input("  输入 y 覆盖 / n 保留 / q 退出: ").strip().lower()
            if choice == "q":
                return False
            if choice == "n":
                print("  保留原标注，返回菜单。")
                return True
            print("  🔄 覆盖原标注...")

        print(f"\n  📝 请输入正确的 Ground Truth（回车保留抽取结果，输入 * 标记为空）：")
        print(f"  {'─' * 78}")

        annotation: Dict[str, Optional[str]] = {}
        for field in self.fields:
            desc = self.field_descriptions.get(field, "")
            default = existing.get(field) or self.extractions.get(aid, {}).get(field)
            prompt = f"  {field:>12} ({desc})"
            if default:
                prompt += f" [默认: {default}]"
            prompt += ": "

            value = input(prompt).strip()
            if value == "*":
                annotation[field] = None
            elif value == "":
                annotation[field] = default if default else None
            else:
                annotation[field] = value

        self.ground_truth[aid] = annotation
        self._save_annotations()
        print(f"  ✅ 第 {art_idx+1} 篇标注完成！")
        return True

    def annotate_all(self):
        if not self.articles:
            print("❌ 没有文章数据！")
            return

        annotated = set(self.ground_truth.keys())
        todo = [i for i, art in enumerate(self.articles) if art.get("id", "") not in annotated]

        if not todo:
            print("✅ 所有文章已完成标注！")
            return

        print(f"\n📝 待标注: {len(todo)} 篇（共 {len(self.articles)} 篇）")
        print(f"   已完成: {len(self.articles) - len(todo)} 篇\n")

        for idx in todo:
            ok = self.annotate_article(idx)
            if not ok:
                break

    def annotate_one(self, idx: int = None):
        if not self.articles:
            print("❌ 没有文章数据！")
            return

        if idx is None:
            annotated = set(self.ground_truth.keys())
            todo = [i for i, art in enumerate(self.articles) if art.get("id", "") not in annotated]
            if not todo:
                print("✅ 所有文章已完成标注！")
                return
            idx = todo[0]

        self.annotate_article(idx)

    def list_annotations(self):
        if not self.ground_truth:
            print("📭 暂未标注任何文章。")
            return

        print(f"\n📋 已标注 {len(self.ground_truth)} 篇：")
        print(f"  {'序号':<5} {'文章标题':<65}")
        print(f"  {'─'*5} {'─'*65}")
        for i, art in enumerate(self.articles):
            aid = art.get("id", "")
            if aid in self.ground_truth:
                title = art.get("title", "(无标题)")[:62]
                print(f"  {i+1:<5} {title:<65}")

    def _fuzzy_match(self, extracted: Optional[str], ground: Optional[str]) -> bool:
        if extracted is None and ground is None:
            return True
        if extracted is None or ground is None:
            return False
        e = extracted.strip().lower().replace(" ", "").replace(",", "")
        g = ground.strip().lower().replace(" ", "").replace(",", "")
        return e == g or e in g or g in e

    def calculate_metrics(self) -> Dict[str, Any]:
        if not self.ground_truth:
            print("❌ 没有标注数据，无法计算指标！")
            return {}

        common = set(self.extractions.keys()) & set(self.ground_truth.keys())
        if not common:
            print("❌ 没有匹配到的标注-抽取对！")
            return {}

        print(f"\n📊 正在计算指标（基于 {len(common)} 条标注）...\n")

        results: Dict[str, Any] = {
            "summary": {
                "total_annotated": len(common),
                "total_articles": len(self.articles),
                "evaluated_at": datetime.now().isoformat(),
            },
            "by_field": {},
            "overall": {},
        }

        for field in self.fields:
            tp = fp = fn = 0
            for aid in common:
                extracted = self.extractions.get(aid, {}).get(field)
                ground = self.ground_truth.get(aid, {}).get(field)

                if extracted is not None and ground is not None and self._fuzzy_match(extracted, ground):
                    tp += 1
                elif extracted is not None and (ground is None or not self._fuzzy_match(extracted, ground)):
                    fp += 1
                elif ground is not None and (extracted is None or not self._fuzzy_match(extracted, ground)):
                    fn += 1

            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

            results["by_field"][field] = {
                "Precision": round(p, 4),
                "Recall": round(r, 4),
                "F1_Score": round(f1, 4),
            }

        n = len(self.fields)
        p_sum = sum(results["by_field"][f]["Precision"] for f in self.fields)
        r_sum = sum(results["by_field"][f]["Recall"] for f in self.fields)
        f1_sum = sum(results["by_field"][f]["F1_Score"] for f in self.fields)
        results["overall"] = {
            "Macro_Avg_Precision": round(p_sum / n, 4),
            "Macro_Avg_Recall": round(r_sum / n, 4),
            "Macro_Avg_F1_Score": round(f1_sum / n, 4),
        }

        return results

    def print_metrics(self, results: Dict[str, Any] = None):
        if results is None:
            results = self.calculate_metrics()
        if not results:
            return

        print(f"\n{'═' * 80}")
        print(f"  基于 {results['summary']['total_annotated']} 条标注的评估结果")
        print(f"{'═' * 80}")

        sep = f"  {'─' * 20} {'─' * 15} {'─' * 15}"
        header = f"  {'字段':<20} {'指标':<15} {'值':<15}"

        for field in self.fields:
            print(f"\n  🏷  {field}")
            print(sep)
            print(header)
            print(sep)
            for metric in ["Precision", "Recall", "F1_Score"]:
                val = results["by_field"][field][metric]
                print(f"  {'':<20} {metric:<15} {val:<15.4f}")

        print(f"\n  🏆  整体表现 (Macro Average)")
        print(sep)
        print(header)
        print(sep)
        for metric in ["Macro_Avg_Precision", "Macro_Avg_Recall", "Macro_Avg_F1_Score"]:
            display = metric.replace("Macro_Avg_", "")
            val = results["overall"][metric]
            print(f"  {'':<20} {display:<15} {val:<15.4f}")
        print(sep)

    def interactive_menu(self):
        while True:
            annotated = len(self.ground_truth)
            total = len(self.articles)

            print(f"\n{'═' * 60}")
            print(f"  交互式人工评价系统 - 娱乐圈事件")
            print(f"  已标注: {annotated}/{total} 篇")
            print(f"{'═' * 60}")
            print(f"  1. 📝 批量标注（继续未完成的）")
            print(f"  2. 📝 标注指定序号")
            print(f"  3. 📋 查看已标注列表")
            print(f"  4. 📊 计算并展示评估指标")
            print(f"  5. 🗑  清除所有标注")
            print(f"  6. 📂 加载其他数据文件")
            print(f"  0. 🚪 退出")
            print(f"{'═' * 60}")

            choice = input("  请输入选项: ").strip()

            if choice == "1":
                self.annotate_all()
            elif choice == "2":
                try:
                    idx_str = input(f"  请输入序号 (1-{total}): ").strip()
                    idx = int(idx_str) - 1
                    self.annotate_one(idx)
                except ValueError:
                    print("❌ 请输入有效数字！")
            elif choice == "3":
                self.list_annotations()
            elif choice == "4":
                if annotated == 0:
                    print("⚠️  请先标注至少一篇文章！")
                else:
                    results = self.calculate_metrics()
                    self.print_metrics(results)
            elif choice == "5":
                confirm = input("⚠️  确定要清除所有标注吗？(y/n): ").strip().lower()
                if confirm == "y":
                    self.ground_truth = {}
                    if os.path.exists(self._anno_filepath):
                        backup = self._anno_filepath + ".bak"
                        shutil.move(self._anno_filepath, backup)
                        print(f"📦 原标注备份至: {backup}")
                    print("🗑  所有标注已清除！")
            elif choice == "6":
                files = sorted(glob.glob(os.path.join(EVAL_DIR, "..", "raw_news", "*.json")))
                if not files:
                    print("❌ 没有找到数据文件！")
                    continue
                print("\n可用文件：")
                for i, f in enumerate(files):
                    print(f"  {i+1}. {os.path.basename(f)}")
                try:
                    f_idx = int(input("请选择: ").strip()) - 1
                    if 0 <= f_idx < len(files):
                        self._load_articles(files[f_idx])
                except ValueError:
                    print("❌ 无效输入")
            elif choice == "0":
                print("👋 再见！")
                break
            else:
                print("❌ 无效选项，请重新输入！")
