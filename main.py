#!/usr/bin/env python3
"""
核心技术产品发布与升级大事件抽取系统 —— 前端入口

默认启动 Streamlit 图形界面，未安装则回退到 Tkinter 标准库界面。
"""
import os
import signal
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LLM_CONFIGURED


def _print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║    核心技术产品发布与升级大事件抽取系统                          ║
║    Tech Event Extraction System                                   ║
║                                                                   ║
║    5要素: 研发主体/技术产品/事件动作/版本指标/发布时间              ║
║    数据源: IT之家/36氪/新华网/人民网/凤凰网/网易/新浪/环球/澎湃     ║
║    100%真实数据 · 零假生成                                       ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
""")


def _launch_streamlit():
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    print("🚀 正在启动 Streamlit 图形界面...")
    print("   浏览器打开后即可使用完整功能。")
    print("   按 Ctrl+C 可安全退出。\n")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", app_path,
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 正在安全关闭...")
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()
        print("👋 系统已安全退出。")


def _launch_tkinter():
    from desktop_app import main as tk_main
    print("⚠️  Streamlit 未安装，使用 Tkinter 标准库界面。")
    print("   如需更好体验，请运行: pip install streamlit")
    print("   按 Ctrl+C 可安全退出。\n")
    try:
        tk_main()
    except KeyboardInterrupt:
        print("\n👋 系统已安全退出。")


def main():
    _print_banner()

    if not LLM_CONFIGURED:
        print(" ⚠️  LLM API Key 未配置，NLP 抽取功能将在前端中被限制。")

    try:
        import streamlit  # noqa: F401
        _launch_streamlit()
    except ImportError:
        _launch_tkinter()


if __name__ == "__main__":
    main()
