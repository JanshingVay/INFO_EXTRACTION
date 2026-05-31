"""Tkinter fallback GUI for the information extraction system.

Streamlit remains the recommended interface. This desktop GUI uses only the
Python standard library, so the project still has an operable graphical
interface when third-party UI dependencies are unavailable.
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_CORPUS_FILE, DEFAULT_REGEX_RESULTS_FILE, EXTRACTION_FIELDS
from utils.helpers import load_json
from utils.pipeline import convert_retrieve_documents, extraction_stats, run_algorithm_comparison


FIELD_LABELS = {
    "developer": "研发主体",
    "tech_product": "技术产品",
    "action_type": "事件动作",
    "version_metric": "版本/指标",
    "date": "日期",
}


class ExtractionDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("科技事件信息抽取系统")
        self.root.geometry("1180x720")
        self.rows = []
        self.filtered_rows = []

        self._build_layout()
        self.load_results()

    def _build_layout(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Button(top, text="构建作业3语料", command=self.build_corpus).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="运行事件抽取", command=self.run_extraction).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="刷新结果", command=self.load_results).pack(side=tk.LEFT, padx=4)

        ttk.Label(top, text="筛选关键词").pack(side=tk.LEFT, padx=(24, 4))
        self.keyword_var = tk.StringVar()
        keyword_entry = ttk.Entry(top, textvariable=self.keyword_var, width=28)
        keyword_entry.pack(side=tk.LEFT)
        keyword_entry.bind("<Return>", lambda _event: self.apply_filter())
        ttk.Button(top, text="筛选", command=self.apply_filter).pack(side=tk.LEFT, padx=4)

        self.status_var = tk.StringVar(value="准备就绪")
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 0)).pack(fill=tk.X)

        columns = ["title", "source", *EXTRACTION_FIELDS, "url"]
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=24)
        headings = {
            "title": "标题",
            "source": "来源",
            "url": "URL",
            **FIELD_LABELS,
        }
        widths = {
            "title": 300,
            "source": 90,
            "developer": 100,
            "tech_product": 150,
            "action_type": 80,
            "version_metric": 120,
            "date": 90,
            "url": 260,
        }
        for col in columns:
            self.tree.heading(col, text=headings.get(col, col))
            self.tree.column(col, width=widths.get(col, 100), anchor=tk.W)

        scroll_y = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

    def build_corpus(self):
        try:
            corpus = convert_retrieve_documents()
            total = corpus.get("metadata", {}).get("total", 0)
            messagebox.showinfo("完成", f"已生成作业3语料：{total}篇\n{DEFAULT_CORPUS_FILE}")
        except Exception as exc:
            messagebox.showerror("构建失败", str(exc))

    def run_extraction(self):
        try:
            _basic, optimized = run_algorithm_comparison()
            stats = extraction_stats(optimized)
            self.load_results()
            messagebox.showinfo(
                "抽取完成",
                f"抽取记录：{stats['total_results']}\n"
                f"较完整事件：{stats['complete_events']}\n"
                f"结果文件：{DEFAULT_REGEX_RESULTS_FILE}",
            )
        except Exception as exc:
            messagebox.showerror("抽取失败", str(exc))

    def load_results(self):
        if not os.path.exists(DEFAULT_REGEX_RESULTS_FILE):
            self.rows = []
            self.filtered_rows = []
            self._refresh_table()
            self.status_var.set("尚未生成抽取结果，请先运行事件抽取。")
            return

        data = load_json(DEFAULT_REGEX_RESULTS_FILE)
        self.rows = data.get("results", [])
        self.filtered_rows = list(self.rows)
        self._refresh_table()
        self.status_var.set(f"已加载抽取结果：{len(self.rows)}条")

    def apply_filter(self):
        keyword = self.keyword_var.get().strip().lower()
        if not keyword:
            self.filtered_rows = list(self.rows)
        else:
            self.filtered_rows = [
                row for row in self.rows
                if keyword in str(row.get("title", "")).lower()
                or keyword in str(row.get("tech_product", "")).lower()
                or keyword in str(row.get("developer", "")).lower()
                or keyword in str(row.get("action_type", "")).lower()
            ]
        self._refresh_table()
        self.status_var.set(f"筛选结果：{len(self.filtered_rows)} / {len(self.rows)}")

    def _refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.filtered_rows[:1000]:
            values = [
                row.get("title", ""),
                row.get("source", ""),
                *(row.get(field, "") or "" for field in EXTRACTION_FIELDS),
                row.get("url", ""),
            ]
            self.tree.insert("", tk.END, values=values)


def main():
    root = tk.Tk()
    ExtractionDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
