# 中文科技事件信息抽取系统

本项目是作业3的信息抽取实验系统，基于作业2信息检索系统已经采集并本地存储的中文科技新闻语料实现。系统面向“核心技术产品发布与升级事件”，抽取 5 个能够组合成事件的信息点，并提供图形化展示、人工评价和多媒体 OCR 信息抽取尝试。

## 任务对应关系

| 作业3要求 | 本项目实现 |
| --- | --- |
| 特定领域语料，不低于100篇 | 复用作业2中文科技新闻语料，转换后共739篇 |
| 本地存储 | `data/raw_news/from_info_retrieve.json` |
| 抽取不少于5个信息点 | `developer / tech_product / action_type / version_metric / date` |
| 信息点能组合成事件 | “研发主体在某日期对某技术产品执行某动作，并伴随版本或指标变化” |
| 至少实现正则表达式抽取 | `BasicRegexExtractor` + `OptimizedRegexExtractor` |
| 抽取结果展示 | Streamlit界面、Tkinter兜底界面、JSON/CSV结果文件 |
| 人工评价 | 图形化标注，字段级 Precision / Recall / F1 |
| 扩展创新 | 规则优化对比、多媒体 OCR 到事件抽取 |
| 可持续发展考虑 | 复用本地语料，避免重复爬取；只处理公开新闻；结果本地缓存 |

## 事件字段

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `developer` | 研发主体 / 发布主体 | 华为、OpenAI、腾讯 |
| `tech_product` | 技术产品 / 模型 / 平台 / 芯片 / 软件 | GPT-5、HarmonyOS、AI芯片 |
| `action_type` | 事件动作 | 发布、推出、升级、开源、修复、上线 |
| `version_metric` | 版本号 / 参数量 / 性能指标 / 规模数据 | v1.2、70B参数、提升40%、4928万次 |
| `date` | 事件日期 | 2026-05-31 |

## 目录结构

```text
INFO_EXTRACTION/
├── app.py                         # Streamlit图形界面
├── desktop_app.py                 # Tkinter标准库兜底界面
├── main.py                        # 命令行入口
├── config.py                      # 路径与字段配置
├── 实验报告.md                    # 作业3实验报告
├── scripts/
│   ├── build_from_retrieve.py     # 从作业2语料构建作业3语料
│   ├── run_extraction.py          # 运行基础/优化正则抽取
│   └── evaluate_extraction.py     # 根据人工标注计算评价指标
├── extractor/
│   ├── base.py
│   ├── regex_extractor.py         # 基础正则与优化正则
│   └── nlp_extractor.py           # LLM抽取，可自动回退正则
├── evaluator/
│   ├── evaluator.py               # 命令行人工评价
│   └── metrics.py                 # 字段级评价指标
├── multimodal/
│   └── multimodal_extraction.py   # OCR图片信息抽取
├── utils/
│   ├── helpers.py
│   └── pipeline.py                # 数据转换、批量抽取、统计
└── data/
    ├── raw_news/from_info_retrieve.json
    ├── extraction_results/basic_regex_results.json
    ├── extraction_results/regex_results.json
    ├── extraction_results/regex_results.csv
    ├── evaluations/
    └── images/
```

## 快速运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

如果只使用 `desktop_app.py`，不需要 Streamlit；如果使用 OCR，需要安装 `easyocr` 或 `pytesseract`。

### 2. 构建作业3语料

开发阶段可从作业2目录转换语料：

```bash
python scripts/build_from_retrieve.py
```

该步骤会生成：

```text
data/raw_news/from_info_retrieve.json
```

生成后，作业3已经不再依赖 `INFO_RETRIEVE/` 目录。

### 3. 运行抽取

```bash
python scripts/run_extraction.py
```

输出文件：

```text
data/extraction_results/basic_regex_results.json
data/extraction_results/regex_results.json
data/extraction_results/regex_results.csv
```

当前已生成结果规模：

| 指标 | 数值 |
| --- | ---: |
| 语料文档数 | 739 |
| 抽取记录数 | 739 |
| 较完整事件数（至少4字段） | 506 |
| developer覆盖数 | 569 |
| tech_product覆盖数 | 717 |
| action_type覆盖数 | 516 |
| version_metric覆盖数 | 400 |
| date覆盖数 | 738 |

也可以选择单独运行某一种抽取器：

```bash
# 优化正则，全量离线抽取
python scripts/run_extraction.py --extractor optimized

# 基础正则 baseline
python scripts/run_extraction.py --extractor basic

# NLP/API 抽取，建议先限制少量样本，避免API费用失控
python scripts/run_extraction.py --extractor nlp --limit 5
```

NLP/API 抽取结果会保存到：

```text
data/extraction_results/nlp_results.json
data/extraction_results/nlp_results.csv
```

如需使用 MiniMax API，请复制 `.env.example` 为 `.env` 并填写：

```env
LLM_API_URL=https://api.minimaxi.com/v1
LLM_API_KEY=你的MiniMax_API_Key
LLM_MODEL=MiniMax-M2.7-highspeed
```

`.env` 已加入 `.gitignore`，不要提交真实 Key。

### 4. 启动图形界面

推荐使用 Streamlit：

```bash
streamlit run app.py
```

如果没有安装 Streamlit，可以使用标准库界面：

```bash
python desktop_app.py
```

### 5. 人工评价

在 Streamlit 的“人工评价”页面逐条修正字段，系统会保存：

```text
data/evaluations/annotations_from_info_retrieve.json
```

之后在“评价指标”页面或命令行计算：

```bash
python scripts/evaluate_extraction.py
```

指标文件：

```text
data/evaluations/metrics_from_info_retrieve.json
```

## 算法优化说明

系统实现两类正则抽取器：

- `BasicRegexExtractor`：仅基于标题和简单模式抽取，作为 baseline。
- `OptimizedRegexExtractor`：加入领域词典、动作归一化、标题优先与正文补充、日期归一化、版本/指标模式等规则。

当前批量结果显示，优化正则相较基础正则显著提高了字段覆盖和较完整事件数量：

| 算法 | developer | tech_product | action_type | version_metric | date | 较完整事件 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 基础正则 | 146 | 437 | 139 | 100 | 738 | 57 |
| 优化正则 | 569 | 717 | 516 | 400 | 738 | 506 |

## 多媒体信息抽取

系统支持图片到事件的抽取流程：

```text
科技发布海报/截图 -> OCR文字识别 -> 正则事件抽取 -> 5字段结构化展示
```

可在 Streamlit “多媒体抽取”页面上传图片，也可以使用 `multimodal/multimodal_extraction.py` 中的演示管线。

## 可持续发展考虑

1. 复用作业2已落盘语料，避免为了作业3重复爬取网络资源。
2. 语料、抽取结果、评价结果全部本地缓存，减少重复计算。
3. 数据来自公开科技新闻，不采集个人隐私数据。
4. 抽取结果用于课程实验和知识组织，不用于自动化决策。
5. 模块化设计便于复用与维护，减少后续重复开发成本。
