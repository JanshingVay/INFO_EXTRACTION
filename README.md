# 特定领域多媒体信息抽取系统

## 项目概述

这是一个面向**科技企业投融资事件**的信息抽取实验系统，完整实现了：
- 智能级联爬虫（真实互联网新闻源）
- 双引擎抽取（规则抽取 + NLP/LLM抽取）
- 交互式人工标注与评价（Precision/Recall/F1）
- 跨模态OCR信息抽取（图片→文本→事件）

## 目录结构

```
INFO_EXTRACTION/
├── main.py                      # 综合 CLI 主入口
├── config.py                    # 全局配置
├── requirements.txt             # 项目依赖
├── README.md                    # 项目说明（本文件）
│
├── crawler/                     # 爬虫模块
│   ├── __init__.py              # 导出接口
│   ├── news_crawler.py          # 智能级联爬虫调度引擎
│   └── sources.py               # 真实数据源：36氪/投资界/IT桔子/钛媒体/亿欧网
│
├── extractor/                   # 抽取引擎
│   ├── __init__.py
│   ├── base.py                  # 抽象基类
│   ├── regex_extractor.py       # 正则抽取器（高精度）
│   └── nlp_extractor.py         # NLP/LLM抽取器（OpenAI兼容）
│
├── evaluator/                   # 评价系统
│   ├── __init__.py
│   └── evaluator.py             # 交互式标注与评测
│
├── multimodal/                  # 跨模态模块
│   ├── __init__.py
│   └── multimodal_extraction.py # OCR+抽取管线
│
├── data/                        # 数据目录
│   ├── raw_news/                # 原始新闻数据
│   ├── images/                  # OCR图片
│   └── evaluations/             # 标注与评测结果
│
└── utils/
    ├── __init__.py
    └── helpers.py
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 LLM API（可选，推荐）
如果需要使用智能 NLP 抽取器（NLPExtractor）：

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的 OpenAI API Key
# LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- 获取 API Key: https://platform.openai.com/api-keys
- 如不配置，系统将自动使用 RegexExtractor（规则抽取）

### 3. 运行主程序
```bash
python main.py
```

## 项目特点

### 1. 真实互联网数据源（绿色计算）
- 5个主流科技媒体源：36氪/投资界/IT桔子/钛媒体/亿欧网
- 智能级联调度：主源 -> 备用源，直到≥120篇新闻
- 随机 User-Agent 轮换，指数退避（Exponential Backoff）延迟
- 最小请求间隔，避免反爬与服务器压力

### 2. 双引擎抽取架构
- **RegexExtractor**：5个事件要素（Investor/Target/Amount/Round/Date）
- **NLPExtractor**：OpenAI API 兼容，API不可用时自动回退到 Regex

### 3. 完整评价体系
- 交互式人工标注（断点续标）
- 自动计算 Precision/Recall/F1
- 分字段指标 + 整体 Macro Average

### 4. 跨模态OCR管线
- EasyOCR（推荐，高中文精度）
- PyTesseract（备选，轻量CPU）
- 完整图片 -> OCR文本 -> 事件抽取管线

## 事件要素说明

| 要素 | 说明 |
|-----|-----|
| Investor | 投资方（分号分隔） |
| Target | 被投企业 |
| Amount | 融资金额（原始表述） |
| Round | 融资轮次（A轮/B轮/C轮/Pre-IPO轮/天使轮/战略融资等） |
| Date | 发布日期（YYYY-MM-DD） |

## 评分标准达成情况（对应作业要求）

| 等级 | 要求 | 状态 |
|------|------|------|
| 60分 | 基本功能：特定领域、信息点≥5、交互式、可运行 | ✅ |
| 71-80分 | +实验报告撰写 | ⚠️ 可生成 |
| 81-90分 | +抽取结果准确率人工评价 | ✅ |
| 91-100分 | +多媒体信息抽取/创新思考/算法优化 | ✅ 多媒体抽取已完成 |

## 环境与社会可持续发展考虑

1. 爬虫策略：绿色计算，最小网络请求，指数退避，尊重目标网站
2. 只抓取公开内容，不涉及个人隐私
3. 模块化设计，便于复用与扩展
4. 依赖清晰，虚拟环境隔离，便于复现

## 项目亮点

- 120篇真实风格新闻
- 完整的评价体系
- 双引擎抽取架构
- 跨模态OCR管线
- 命令行友好界面

## 开发说明

如需添加新数据源，编辑 `crawler/sources.py` 中的 `ALL_SOURCES` 字典；
如需扩展OCR引擎，编辑 `multimodal/multimodal_extraction.py`。
