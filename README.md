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
│   ├── __init__.py
│   ├── multimodal_extraction.py   # OCR图片信息抽取
│   ├── api_client.py              # 第三方多模态 API 调用
│   └── local_vl.py                # 本地开源多模态模型调用
├── utils/
│   ├── helpers.py
│   └── pipeline.py                # 数据转换、批量抽取、统计
└── data/
    ├── raw_news/from_info_retrieve.json
    ├── extraction_results/basic_regex_results.json
    ├── extraction_results/regex_results.json
    ├── extraction_results/regex_results.csv
    ├── multimodal_api_config.json
    ├── local_vl_config.json
    ├── evaluations/
    └── images/
```

## 快速运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

如果只使用 `desktop_app.py`，不需要 Streamlit；如果使用 OCR，需要安装 `easyocr` 或 `pytesseract`。

**本地多模态模型可选依赖**（按需安装）：
- 基础多模态：`pip install torch transformers accelerate pillow`
- Qwen2.5-VL 增强：`pip install qwen-vl-utils`
- InternVL2：`pip install transformers pillow`

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

如需使用 DeepSeek API，请复制 `.env.example` 为 `.env` 并填写：

```env
LLM_API_URL=https://api.deepseek.com
LLM_API_KEY=你的DeepSeek_API_Key
LLM_MODEL=deepseek-v4-flash
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

## 多媒体信息抽取（图片/视频 → 事件）

系统实现三种多媒体信息抽取方式：

1. **OCR + 正则引擎**：本地免费，纯离线，仅支持图片
2. **本地开源多模态大模型**：直接理解视觉内容，支持图片和视频，无需联网（首推 Qwen2.5-VL）
3. **云端多模态大模型 API**：精度最高，支持图片和视频，使用 OpenAI 兼容协议（Kimi/MiniMax/DeepSeek等）

---

### 方式1：OCR + 正则引擎（本地/免费）

系统实现完整的多媒体信息抽取管线，支持从图像中识别文本并抽取科技事件。采用**三引擎自动回退架构**，按优先级 `PaddleOCR > EasyOCR > PyTesseract` 自动选择最佳可用引擎。

#### 引擎对比

| 引擎 | 安装命令 | 中文精度 | 速度 | 推荐场景 |
|------|----------|:---:|:---:|----------|
| **PaddleOCR** | `pip install paddleocr paddlepaddle` | ★★★★★ | ★★★ | 推荐，中文识别最强 |
| **EasyOCR** | `pip install easyocr` | ★★★★ | ★★ | 已安装即用，中英文均可 |
| **PyTesseract** | `pip install pytesseract` + 安装 tesseract | ★★★ | ★★★★★ | 轻量备选 |

#### 图像预处理增强

```
原图 → 对比度增强(1.5x) → 锐度增强(2x) → 灰度 → 自适应二值化 → 中值滤波降噪 → OCR
```

#### 使用方式

**1. 上传图片（Streamlit 前端）**

启动前端后，进入「多媒体抽取」页面：
- 选择「🔧 OCR + 正则引擎」
- 上传科技海报/发布会截图/PPT 页面
- 点击「运行 OCR 事件抽取」
- 查看 OCR 文本 + 结构化 5 字段结果
- 支持「生成演示海报」一键体验完整流程
- 可选「NLP 增强」用 LLM 对 OCR 结果做二次抽取

**2. 命令行演示**

```bash
python -m multimodal.multimodal_extraction
```

**3. API 调用**

```python
from multimodal import MultimodalExtractor

extractor = MultimodalExtractor()
result = extractor.process_image("data/images/poster.png")
print(result["extraction"])  # {developer, tech_product, action_type, ...}

# 批量处理
results = extractor.process_directory("data/images/")
extractor.save_results(results)
```

---

### 方式2：本地开源多模态大模型

系统接入两个行业领先开源多模态大模型：

| 模型 | 安装/加载说明 | 推荐配置 | 图片 | 视频 |
|------|--------------|:---:|:---:|:---:|
| **Qwen/Qwen2.5-VL-3B-Instruct** | `pip install transformers torch pillow accelerate qwen-vl-utils` | 8GB VRAM (GPU) 更适合作业演示 | ✅ | ✅ |

#### 本地多模态性能需求

| 模式 | 内存需求 | 显存需求 | 单图推断耗时 |
|------|:--------:|:--------:|:---------:|
| **CPU量化** | 32GB+ RAM | 0 | 20-60秒 |
| **GPU bfloat16 加载** | 16GB RAM | 8GB VRAM 建议使用 3B | 3-10秒 |

#### 使用方式

**1. Streamlit 前端**
- 选择「🖥️ 本地开源多模态大模型」
- 在配置面板填入模型名称和设备（如 `Qwen/Qwen2.5-VL-3B-Instruct`）
- 上传图片或视频，点击「本地多模态模型抽取」

**2. 代码调用**

```python
from multimodal import extract_with_local_vl

# 默认使用 config.py 配置
result = extract_with_local_vl("data/images/poster.png")

# 或传入自定义配置
config = {
    "model": "Qwen/Qwen2.5-VL-3B-Instruct",
    "device": "auto",
    "temperature": 0.3,
    "max_tokens": 2048,
    "system_prompt": "你是科技事件抽取专家..."
}
result = extract_with_local_vl("data/images/poster.png", config)
```

---

### 方式3：云端多模态大模型 API

使用 OpenAI 兼容协议，支持 Kimi/MiniMax/DeepSeek 等厂商，图片和视频均支持（Kimi 支持视频 base64 上传）。

#### 配置方式

在 Streamlit 前端「多模态 API 配置」面板填写：
- API 地址：`https://api.moonshot.cn/v1` 或其他厂商地址
- API Key：你的 Kimi/MiniMax 等平台 Key
- 模型名称：如 `kimi-k2.6`
- System Prompt：抽取提示模板

也可以通过 `.env` 配置默认值：

```env
MULTIMODAL_API_URL=https://api.moonshot.cn/v1
MULTIMODAL_API_KEY=你的API_Key
MULTIMODAL_MODEL=kimi-k2.6
```

#### 使用方式

```python
from multimodal import extract_with_multimodal_api

result = extract_with_multimodal_api("data/images/poster.png")
print(result["extraction"])
```

## 可持续发展考虑

1. 复用作业2已落盘语料，避免为了作业3重复爬取网络资源。
2. 语料、抽取结果、评价结果全部本地缓存，减少重复计算。
3. 数据来自公开科技新闻，不采集个人隐私数据。
4. 抽取结果用于课程实验和知识组织，不用于自动化决策。
5. 模块化设计便于复用与维护，减少后续重复开发成本。
