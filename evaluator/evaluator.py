"""
交互式人工评价系统

功能：
- 命令行交互式打标签（Ground Truth 标注）
- 支持断点续标（已标注条目自动恢复）
- 同时运行 RegexExtractor 与 NLPExtractor
- 自动计算两个抽取器的 Precision / Recall / F1-Score
- 支持整体评估与逐字段评估
- 支持标注数据 JSON 持久化
"""
import json
import os
import re
import glob
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple

from config import EXTRACTION_FIELDS, BASE_DIR
from extractor.regex_extractor import RegexExtractor
from extractor.nlp_extractor import NLPExtractor
from crawler.news_crawler import AsyncNewsCrawler
from utils.helpers import load_json, save_json

EVAL_DATA_DIR = os.path.join(BASE_DIR, "data", "evaluations")
os.makedirs(EVAL_DATA_DIR, exist_ok=True)


class EvaluationSystem:
    """命令行交互式评价系统"""

    def __init__(self, news_filepath: str = None):
        self.regex_extractor = RegexExtractor()
        self.nlp_extractor = NLPExtractor()
        self.fields = EXTRACTION_FIELDS

        self.articles: List[Dict[str, Any]] = []
        self.regex_results: Dict[str, Dict[str, Optional[str]]] = {}
        self.nlp_results: Dict[str, Dict[str, Optional[str]]] = {}
        self.ground_truth: Dict[str, Dict[str, Optional[str]]] = {}
        self._data_filepath = news_filepath
        self._anno_filepath = ""

        if news_filepath:
            self._load_articles(news_filepath)
        else:
            self._auto_load_latest()

    def _auto_load_latest(self):
        """自动加载最新的爬虫结果"""
        files = sorted(glob.glob(os.path.join(BASE_DIR, "data", "raw_news", "*.json")))
        if not files:
            print("❌ 未找到爬虫数据文件，请先运行爬虫！")
            return
        self._load_articles(files[-1])

    def _load_articles(self, filepath: str):
        """加载文章数据"""
        self._data_filepath = filepath
        self.articles = AsyncNewsCrawler.load_results(filepath)
        basename = os.path.splitext(os.path.basename(filepath))[0]
        self._anno_filepath = os.path.join(EVAL_DATA_DIR, f"annotations_{basename}.json")

        print(f"📄 已加载 {len(self.articles)} 篇文章")

        self._run_extractors()
        self._load_annotations()

    def _run_extractors(self):
        """运行两个抽取器"""
        print("⏳ 正在运行 RegexExtractor...")
        for art in self.articles:
            aid = art.get("id", "")
            self.regex_results[aid] = self.regex_extractor.extract(art)

        print("⏳ 正在运行 NLPExtractor...")
        for art in self.articles:
            aid = art.get("id", "")
            self.nlp_results[aid] = self.nlp_extractor.extract(art)

        print("✅ 抽取器运行完毕\n")

    def _load_annotations(self):
        """加载已有标注数据（支持断点续标）"""
        if os.path.exists(self._anno_filepath):
            data = load_json(self._anno_filepath)
            self.ground_truth = data.get("annotations", {})
            print(f"📝 已恢复 {len(self.ground_truth)} 条已有标注")
        else:
            self.ground_truth = {}

    def _save_annotations(self):
        """保存标注数据"""
        output = {
            "metadata": {
                "data_source": self._data_filepath,
                "total_articles": len(self.articles),
                "annotated_count": len(self.ground_truth),
                "last_updated": datetime.now().isoformat(),
                "fields": self.fields,
            },
            "annotations": self.ground_truth,
        }
        save_json(output, self._anno_filepath)
        print(f"💾 标注已保存至: {self._anno_filepath}")

    def _display_article(self, art: Dict[str, Any], idx: int):
        """展示单篇文章及两个抽取器的结果"""
        aid = art.get("id", "")
        title = art.get("title", "(无标题)")
        summary = art.get("summary", "")
        publish_time = art.get("publish_time", "")

        print(f"\n{'═' * 70}")
        print(f"  第 {idx+1}/{len(self.articles)} 篇")
        print(f"{'═' * 70}")
        print(f"  标题    : {title}")
        if publish_time:
            print(f"  发布时间: {publish_time}")
        if summary:
            summary_short = summary[:120] + "..." if len(summary) > 120 else summary
            print(f"  摘要    : {summary_short}")

        regex_res = self.regex_results.get(aid, {})
        nlp_res = self.nlp_results.get(aid, {})

        print(f"\n  {'字段':<12} {'RegexExtractor':<30} {'NLPExtractor':<30}")
        print(f"  {'─'*12} {'─'*30} {'─'*30}")
        for field in self.fields:
            r_val = regex_res.get(field) or "(空)"
            n_val = nlp_res.get(field) or "(空)"
            r_disp = r_val[:28] + ".." if len(str(r_val)) > 30 else r_val
            n_disp = n_val[:28] + ".." if len(str(n_val)) > 30 else n_val
            print(f"  {field:<12} {str(r_disp):<30} {str(n_disp):<30}")

        gt = self.ground_truth.get(aid, {})
        if gt:
            print(f"\n  📌 已有标注:")
            for field in self.fields:
                gt_val = gt.get(field)
                if gt_val:
                    print(f"     {field}: {gt_val}")
                else:
                    print(f"     {field}: (空)")

    def annotate_article(self, art_idx: int) -> bool:
        """标注单篇文章"""
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

        print(f"\n  📝 请输入正确的 Ground Truth（回车跳过，输入 * 标记为\"无\"）：")
        print(f"  ─────────────────────────────────────────────")

        annotation: Dict[str, Optional[str]] = {}
        hints = {
            "Investor": "投资方名称（如：红杉资本；腾讯），多个用中文分号；分隔",
            "Target": "被投企业名称（如：字节跳动）",
            "Amount": "融资金额原始字符串（如：3亿美元）",
            "Round": "融资轮次（如：A轮、B轮、天使轮、战略融资）",
            "Date": "发布日期（格式：YYYY-MM-DD，如：2026-01-15）",
        }
        for field in self.fields:
            hint = hints.get(field, "")
            default = existing.get(field, "")
            prompt = f"  {field} ({hint})"
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
        """批量标注所有文章"""
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
        """标注指定序号的单篇"""
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
        """列出已标注条目"""
        if not self.ground_truth:
            print("📭 暂未标注任何文章。")
            return

        print(f"\n📋 已标注 {len(self.ground_truth)} 篇：")
        print(f"  {'序号':<5} {'文章标题':<55}")
        print(f"  {'─'*5} {'─'*55}")
        for i, art in enumerate(self.articles):
            aid = art.get("id", "")
            if aid in self.ground_truth:
                title = art.get("title", "(无标题)")[:52]
                print(f"  {i+1:<5} {title:<55}")

    def _fuzzy_match(self, extracted: Optional[str], ground: Optional[str]) -> bool:
        """模糊匹配：处理格式化差异"""
        if extracted is None and ground is None:
            return True
        if extracted is None or ground is None:
            return False
        e = extracted.strip().lower().replace(" ", "").replace(",", "")
        g = ground.strip().lower().replace(" ", "").replace(",", "")
        return e == g

    def _set_match(self, extracted: Optional[str], ground: Optional[str]) -> Tuple[int, int, int]:
        """集合匹配：适用于 Investor（分号分隔的多值字段）
        Returns: (TP, FP, FN)
        """
        if extracted is None and ground is None:
            return 1, 0, 0
        if extracted is None:
            return 0, 0, 1
        if ground is None:
            return 0, 1, 0

        def _parse_set(s: Optional[str]) -> Set[str]:
            if not s:
                return set()
            parts = re.split(r"[；;,、]", s.strip())
            return {p.strip() for p in parts if p.strip()}

        e_set = _parse_set(extracted)
        g_set = _parse_set(ground)

        if not e_set and not g_set:
            return 1, 0, 0
        if not e_set:
            return 0, 0, len(g_set)
        if not g_set:
            return 0, len(e_set), 0

        tp = len(e_set & g_set)
        fp = len(e_set - g_set)
        fn = len(g_set - e_set)
        return tp, fp, fn

    def calculate_metrics(self) -> Dict[str, Any]:
        """计算两个抽取器的 Precision / Recall / F1"""
        if not self.ground_truth:
            print("❌ 没有标注数据，无法计算指标！")
            return {}

        common = set(self.regex_results.keys()) & set(self.nlp_results.keys()) & set(self.ground_truth.keys())
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
            field_results = {}

            for extractor_name, extractor_results in [
                ("RegexExtractor", self.regex_results),
                ("NLPExtractor", self.nlp_results),
            ]:
                if field == "Investor":
                    tp_total = fp_total = fn_total = 0
                    for aid in common:
                        extracted = extractor_results.get(aid, {}).get(field)
                        ground = self.ground_truth.get(aid, {}).get(field)
                        tp, fp, fn = self._set_match(extracted, ground)
                        tp_total += tp
                        fp_total += fp
                        fn_total += fn

                    p = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
                    r = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
                    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
                else:
                    correct = 0
                    retrieved = 0
                    relevant = 0
                    for aid in common:
                        extracted = extractor_results.get(aid, {}).get(field)
                        ground = self.ground_truth.get(aid, {}).get(field)
                        if extracted is not None:
                            retrieved += 1
                        if ground is not None:
                            relevant += 1
                        if extracted is not None and ground is not None and self._fuzzy_match(extracted, ground):
                            correct += 1

                    p = correct / retrieved if retrieved > 0 else 0.0
                    r = correct / relevant if relevant > 0 else 0.0
                    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

                field_results[extractor_name] = {
                    "Precision": round(p, 4),
                    "Recall": round(r, 4),
                    "F1_Score": round(f1, 4),
                }

            results["by_field"][field] = field_results

        for extractor_name in ["RegexExtractor", "NLPExtractor"]:
            p_sum = sum(results["by_field"][f][extractor_name]["Precision"] for f in self.fields)
            r_sum = sum(results["by_field"][f][extractor_name]["Recall"] for f in self.fields)
            f1_sum = sum(results["by_field"][f][extractor_name]["F1_Score"] for f in self.fields)
            n = len(self.fields)
            results["overall"][extractor_name] = {
                "Macro_Avg_Precision": round(p_sum / n, 4),
                "Macro_Avg_Recall": round(r_sum / n, 4),
                "Macro_Avg_F1_Score": round(f1_sum / n, 4),
            }

        return results

    def print_metrics(self, results: Dict[str, Any] = None):
        """打印评估指标表格"""
        if results is None:
            results = self.calculate_metrics()
        if not results:
            return

        print(f"\n{'═' * 75}")
        print(f"  基于 {results['summary']['total_annotated']} 条标注的评估结果")
        print(f"{'═' * 75}")

        sep = f"  {'─'*18} {'─'*18} {'─'*18}"
        header = f"  {'字段':<18} {'指标':<18} {'RegexExtractor':<18} {'NLPExtractor':<18}"

        for field in self.fields:
            print(f"\n  🏷  {field}")
            print(sep)
            print(header)
            print(sep)
            for metric in ["Precision", "Recall", "F1_Score"]:
                r_val = results["by_field"][field]["RegexExtractor"][metric]
                n_val = results["by_field"][field]["NLPExtractor"][metric]
                print(f"  {'':<18} {metric:<18} {r_val:<18.4f} {n_val:<18.4f}")

        print(f"\n  🏆 总体表现 (Macro Average)")
        print(sep)
        print(header)
        print(sep)
        for metric in ["Macro_Avg_Precision", "Macro_Avg_Recall", "Macro_Avg_F1_Score"]:
            display = metric.replace("Macro_Avg_", "")
            r_val = results["overall"]["RegexExtractor"].get(metric, 0)
            n_val = results["overall"]["NLPExtractor"].get(metric, 0)
            print(f"  {'':<18} {display:<18} {r_val:<18.4f} {n_val:<18.4f}")
        print(sep)

    def export_evaluation(self) -> str:
        """导出完整评估报告"""
        results = self.calculate_metrics()
        if not results:
            return ""

        per_article = []
        for art in self.articles:
            aid = art.get("id", "")
            if aid not in self.ground_truth:
                continue
            per_article.append({
                "article_id": aid,
                "title": art.get("title", ""),
                "ground_truth": self.ground_truth[aid],
                "regex_result": self.regex_results.get(aid, {}),
                "nlp_result": self.nlp_results.get(aid, {}),
            })

        report = {
            "metadata": results["summary"],
            "metrics": {
                "by_field": results["by_field"],
                "overall": results["overall"],
            },
            "per_article": per_article,
        }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(EVAL_DATA_DIR, f"evaluation_report_{timestamp}.json")
        save_json(report, report_path)
        print(f"\n📄 评估报告已导出: {report_path}")
        return report_path

    def interactive_menu(self):
        """交互式主菜单"""
        while True:
            annotated = len(self.ground_truth)
            total = len(self.articles)
            print(f"\n{'═' * 50}")
            print(f"  交互式人工评价系统")
            print(f"  已标注: {annotated}/{total} 篇")
            print(f"{'═' * 50}")
            print(f"  1. 📝 批量标注（继续未完成的）")
            print(f"  2. 📝 标注指定序号")
            print(f"  3. 📋 查看已标注列表")
            print(f"  4. 📊 计算并展示评估指标")
            print(f"  5. 💾 导出完整评估报告")
            print(f"  6. 🗑  清除所有标注")
            print(f"  7. 📂 加载其他数据文件")
            print(f"  0. 🚪 退出")
            print(f"{'═' * 50}")

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
                if annotated == 0:
                    print("⚠️  请先标注至少一篇文章！")
                else:
                    self.export_evaluation()
            elif choice == "6":
                confirm = input("⚠️  确定要清除所有标注吗？(y/n): ").strip().lower()
                if confirm == "y":
                    self.ground_truth = {}
                    if os.path.exists(self._anno_filepath):
                        backup = self._anno_filepath + ".bak"
                        shutil.move(self._anno_filepath, backup)
                        print(f"📦 原标注备份至: {backup}")
                    print("🗑  所有标注已清除！")
            elif choice == "7":
                files = sorted(glob.glob(os.path.join(BASE_DIR, "data", "raw_news", "*.json")))
                if not files:
                    print("❌ 没有找到数据文件！")
                    continue
                print("\n可用文件:")
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


if __name__ == "__main__":
    import sys
    import asyncio

    evaluator = EvaluationSystem()
    evaluator.interactive_menu()
