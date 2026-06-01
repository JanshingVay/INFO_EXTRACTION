"""
多媒体抽取模块 - 科技海报/截图 OCR + 事件抽取

三引擎架构，自动选择可用引擎：
  1. PaddleOCR (推荐，中文识别最强)  -> 需 pip install paddleocr paddlepaddle
  2. EasyOCR (已安装，中英文均佳)    -> 需 pip install easyocr
  3. PyTesseract (轻量备选)          -> 需 pip install pytesseract + 安装 tesseract

特性:
- 图像预处理增强（灰度/对比度/降噪/二值化）
- 多引擎自动回退，无缝切换
- 批量处理 + 进度追踪
- OCR 文本 → 正则/LLM 事件抽取 → 结构化 5 字段
"""
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 确保项目根目录在 path 中（支持直接 python 脚本运行和模块导入两种方式）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import EXTRACTION_FIELDS, IMAGES_DIR, OCR_CONFIG
from extractor.regex_extractor import RegexExtractor

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────
# 图像预处理
# ──────────────────────────────────────────────────

def _preprocess_image(image_path: str) -> Optional[Any]:
    """
    图像预处理流水线：灰度 → 对比度增强 → 降噪 → 自适应二值化
    返回 (original, processed) 两张 PIL Image 的元组
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        img = Image.open(image_path).convert("RGB")

        # 增强对比度 (factor=1.5)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        # 增强锐度
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)

        # 转灰度
        gray = img.convert("L")

        # 自适应二值化：用大核模糊后做差值
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=15))
        binary = ImageOps.invert(
            ImageOps.invert(gray).point(
                lambda p: 255 if p > 128 else 0
            )
        )

        # 小核降噪
        binary = binary.filter(ImageFilter.MedianFilter(3))

        return gray, binary

    except ImportError:
        logger.warning("PIL not installed, skipping image preprocessing")
        return None
    except Exception as e:
        logger.debug("图像预处理失败: %s", e)
        return None


# ──────────────────────────────────────────────────
# OCR 引擎
# ──────────────────────────────────────────────────

def _ocr_paddle(image_path: str) -> Tuple[str, float]:
    """PaddleOCR - 中文 OCR 最强引擎"""
    import numpy as np
    from PIL import Image

    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang="ch", use_angle_cls=True, show_log=False)
        img = np.array(Image.open(image_path).convert("RGB"))
        results = ocr.ocr(img, cls=True)
        if not results or not results[0]:
            return "", 0.0

        lines = []
        total_conf = 0.0
        count = 0
        for line_info in results[0]:
            text = line_info[1][0]
            conf = line_info[1][1]
            if conf > 0.5:
                lines.append(text)
                total_conf += conf
                count += 1

        return "\n".join(lines), total_conf / count if count else 0.0

    except ImportError:
        return "", -1.0
    except Exception as e:
        logger.warning("PaddleOCR error: %s", e)
        return "", 0.0


def _ocr_easyocr(image_path: str, languages: List[str]) -> Tuple[str, float]:
    """EasyOCR - 中英文 OCR"""
    try:
        import easyocr

        reader = easyocr.Reader(languages, gpu=False, verbose=False)
        results = reader.readtext(image_path, detail=1)

        if not results:
            return "", 0.0

        lines = []
        total_conf = 0.0
        for bbox, text, conf in results:
            if conf > 0.1:  # 降低门限，中文 OCR 常见低置信度
                lines.append(text)
                total_conf += conf

        return "\n".join(lines), total_conf / len(results) if results else 0.0

    except ImportError:
        return "", -1.0
    except Exception as e:
        logger.warning("EasyOCR error: %s", e)
        return "", 0.0


def _ocr_pytesseract(image_path: str) -> Tuple[str, float]:
    """PyTesseract - 轻量备选"""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # PyTesseract 不提供逐字置信度，给一个经验值
        conf = 0.65 if len("\n".join(lines)) > 20 else 0.0
        return "\n".join(lines), conf

    except ImportError:
        return "", -1.0
    except Exception as e:
        logger.warning("PyTesseract error: %s", e)
        return "", 0.0


# ──────────────────────────────────────────────────
# 跨模态抽取器
# ──────────────────────────────────────────────────

class MultimodalExtractor:
    """
    跨模态抽取器：图片 → OCR → 科技事件抽取

    自动选择可用引擎，优先级：PaddleOCR > EasyOCR > PyTesseract
    失败时自动回退到下一个引擎。
    """

    def __init__(self, ocr_engine: str = None):
        self.ocr_engine = ocr_engine or OCR_CONFIG.get("engine", "easyocr")
        self.languages = OCR_CONFIG.get("languages", ["ch_sim", "en"])
        self.regex_extractor = RegexExtractor()
        self._engine_used = None

    # ── 引擎探测 ──

    @staticmethod
    def detect_available_engines() -> List[str]:
        """探测当前环境可用的 OCR 引擎"""
        engines = []
        try:
            import paddleocr  # noqa: F401
            engines.append("paddleocr")
        except ImportError:
            pass
        try:
            import easyocr  # noqa: F401
            engines.append("easyocr")
        except ImportError:
            pass
        try:
            import pytesseract  # noqa: F401
            engines.append("pytesseract")
        except ImportError:
            pass
        return engines

    # ── OCR 核心 ──

    def extract_text_from_image(self, image_path: str) -> Tuple[str, float, str]:
        """
        从图片提取文字，自动选择最佳引擎。

        Returns:
            (ocr_text, confidence, engine_name)
        """
        available = self.detect_available_engines()
        if not available:
            logger.error("无可用 OCR 引擎！请安装: pip install easyocr")
            return "", 0.0, "none"

        logger.info("可用 OCR 引擎: %s", available)

        # 按优先级尝试
        priority = ["paddleocr", "easyocr", "pytesseract"]
        ordered = [e for e in priority if e in available]

        # 预处理图片（可选优化）
        preprocessed = _preprocess_image(image_path)

        for engine in ordered:
            try:
                t0 = time.perf_counter()
                text, conf = self._run_engine(engine, image_path, preprocessed)
                elapsed = time.perf_counter() - t0

                if text and len(text.strip()) > 10:
                    self._engine_used = engine
                    logger.info(
                        "✅ %s 识别成功: %d 字符, 置信度 %.2f, 耗时 %.2fs",
                        engine, len(text), conf, elapsed,
                    )
                    return text, conf, engine
                else:
                    logger.debug("⏭️  %s 结果过短，尝试下一个引擎", engine)

            except Exception as e:
                logger.warning("⚠️  %s 异常: %s，回退下一个引擎", engine, e)

        return "", 0.0, "none"

    def _run_engine(self, engine: str, image_path: str, preprocessed) -> Tuple[str, float]:
        if engine == "paddleocr":
            text, conf = _ocr_paddle(image_path)
            if text and conf > 0:
                return text, conf
            # 用预处理图片重试
            if preprocessed:
                gray, binary = preprocessed
                tmp = os.path.join(IMAGES_DIR, "_tmp_preprocessed.png")
                binary.save(tmp)
                text2, conf2 = _ocr_paddle(tmp)
                os.remove(tmp) if os.path.exists(tmp) else None
                if conf2 > conf:
                    return text2, conf2
            return text, conf

        elif engine == "easyocr":
            text, conf = _ocr_easyocr(image_path, self.languages)
            if text and conf > 0:
                return text, conf
            if preprocessed:
                gray, binary = preprocessed
                tmp = os.path.join(IMAGES_DIR, "_tmp_preprocessed.png")
                binary.save(tmp)
                text2, conf2 = _ocr_easyocr(tmp, self.languages)
                os.remove(tmp) if os.path.exists(tmp) else None
                if conf2 > conf:
                    return text2, conf2
            return text, conf

        elif engine == "pytesseract":
            text, conf = _ocr_pytesseract(image_path)
            return text, conf

        return "", 0.0

    # ── 事件抽取 ──

    def process_image(self, image_path: str, use_nlp: bool = False) -> Dict[str, Any]:
        """处理单张图片：OCR + 科技事件抽取"""
        logger.info("🖼️  处理图片: %s", os.path.basename(image_path))

        ocr_text, confidence, engine = self.extract_text_from_image(image_path)

        result: Dict[str, Any] = {
            "image_path": image_path,
            "image_name": os.path.basename(image_path),
            "ocr_engine": engine,
            "ocr_confidence": round(confidence, 4),
            "ocr_text": ocr_text,
            "ocr_text_length": len(ocr_text),
            "extraction": {k: None for k in EXTRACTION_FIELDS},
            "processed_at": datetime.now().isoformat(),
        }

        if not ocr_text or len(ocr_text.strip()) < 5:
            result["error"] = "OCR 识别失败或文本过短"
            return result

        # 正则抽取
        article = {
            "title": ocr_text[:100],
            "summary": ocr_text,
            "content": ocr_text,
            "id": os.path.basename(image_path),
        }
        extraction = self.regex_extractor.extract(article)
        result["extraction"] = extraction

        # NLP 增强（可选，需要配置 API Key）
        if use_nlp:
            try:
                from extractor.nlp_extractor import NLPExtractor
                nlp = NLPExtractor()
                nlp_result = nlp.extract(article)
                if any(v for v in nlp_result.values()):
                    result["extraction_nlp"] = nlp_result
                    result["nlp_used"] = True
            except Exception as e:
                logger.debug("NLP 增强失败: %s", e)

        return result

    # ── 批量处理 ──

    def process_directory(
        self,
        directory: str = None,
        extensions: Tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".webp"),
    ) -> List[Dict[str, Any]]:
        """批量处理目录下所有图片"""
        if directory is None:
            directory = IMAGES_DIR

        files = sorted(
            f for f in os.listdir(directory)
            if f.lower().endswith(extensions)
        )
        logger.info("📁 发现 %d 张图片待处理", len(files))

        results = []
        for i, filename in enumerate(files, 1):
            logger.info("[%d/%d] %s", i, len(files), filename)
            result = self.process_image(os.path.join(directory, filename))
            results.append(result)

        return results

    # ── 结果保存 ──

    def save_results(self, results: List[Dict[str, Any]], filename: str = None) -> str:
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"multimodal_results_{ts}.json"

        filepath = os.path.join(IMAGES_DIR, filename)
        output = {
            "metadata": {
                "total": len(results),
                "ocr_engine": self._engine_used,
                "fields": EXTRACTION_FIELDS,
                "created_at": datetime.now().isoformat(),
            },
            "results": results,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("💾 已保存 %d 条结果至: %s", len(results), filepath)
        return filepath


# ──────────────────────────────────────────────────
# 演示海报生成
# ──────────────────────────────────────────────────

def generate_demo_image() -> str:
    """生成一张科技发布海报（开源项目Release / 大模型发布 / 芯片突破）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random

        width, height = 800, 1000
        img = Image.new("RGB", (width, height), color=(10, 25, 47))
        draw = ImageDraw.Draw(img)

        tech_types = ["开源项目Release", "云原生技术大会", "大模型发布", "芯片算力突破"]
        tech_type = random.choice(tech_types)

        # 尝试多种中文字体路径
        font_paths = [
            "/System/Library/Fonts/Supplemental/PingFang.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        font_large = font_medium = font_small = None
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font_large = ImageFont.truetype(fp, 72)
                    font_medium = ImageFont.truetype(fp, 48)
                    font_small = ImageFont.truetype(fp, 36)
                    break
                except Exception:
                    continue
        if font_large is None:
            # 无中文字体回退：用英文内容 + 默认字体（仍能被 OCR 识别）
            lang_fallback = True
            try:
                font_large = ImageFont.truetype("/Library/Fonts/Arial Unicode.ttf", 72)
                font_medium = ImageFont.truetype("/Library/Fonts/Arial Unicode.ttf", 48)
                font_small = ImageFont.truetype("/Library/Fonts/Arial Unicode.ttf", 36)
            except Exception:
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
        else:
            lang_fallback = False

        y = 100
        draw.text((width // 2, y), "科技技术喜报", fill=(100, 200, 255), font=font_large, anchor="mm")
        y += 120

        if tech_type == "开源项目Release":
            project = random.choice(["Kubernetes v1.30", "PyTorch 2.3", "React 19", "Rust 1.78"])
            draw.text((width // 2, y), project, fill=(255, 255, 255), font=font_large, anchor="mm")
            y += 150
            draw.text((width // 2, y), "正式发布 开源项目Release", fill=(100, 255, 100), font=font_medium, anchor="mm")
            y += 100
            org = random.choice(["CNCF基金会", "Meta AI", "Facebook", "Mozilla"])
            draw.text((width // 2, y), f"主办方：{org}", fill=(200, 200, 200), font=font_small, anchor="mm")
            y += 150

        elif tech_type == "云原生技术大会":
            conf = random.choice(["KubeCon 2024", "QCon 全球软件开发大会", "ArchSummit 架构师峰会"])
            draw.text((width // 2, y), conf, fill=(255, 255, 255), font=font_large, anchor="mm")
            y += 150
            draw.text((width // 2, y), "云原生架构 容器化部署", fill=(100, 200, 255), font=font_medium, anchor="mm")
            y += 100
            draw.text((width // 2, y), "2024年5月 上海", fill=(200, 200, 200), font=font_small, anchor="mm")
            y += 150

        elif tech_type == "大模型发布":
            model = random.choice(["DeepSeek-V3", "Qwen 2.0", "Llama 3", "GPT-5"])
            draw.text((width // 2, y), model, fill=(255, 255, 255), font=font_large, anchor="mm")
            y += 150
            draw.text((width // 2, y), random.choice(["70B参数", "1.5T参数", "300B参数"]), fill=(255, 150, 100), font=font_medium, anchor="mm")
            y += 100
            draw.text((width // 2, y), random.choice(["DeepSeek", "通义千问", "Meta", "OpenAI"]), fill=(200, 200, 200), font=font_small, anchor="mm")
            y += 150

        else:
            chip = random.choice(["NVIDIA H200", "AMD MI300", "华为昇腾910"])
            draw.text((width // 2, y), chip, fill=(255, 255, 255), font=font_large, anchor="mm")
            y += 150
            draw.text((width // 2, y), random.choice(["性能提升40%", "算力突破2000PFlops"]), fill=(100, 255, 200), font=font_medium, anchor="mm")
            y += 100
            draw.text((width // 2, y), random.choice(["NVIDIA", "AMD", "华为"]), fill=(200, 200, 200), font=font_small, anchor="mm")
            y += 150

        draw.text((width // 2, y), f"发布日期：{datetime.now().strftime('%Y-%m-%d')}", fill=(150, 150, 150), font=font_small, anchor="mm")

        filename = f"tech_poster_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(IMAGES_DIR, filename)
        img.save(filepath)
        logger.info("✅ 生成演示海报: %s", filename)
        return filepath

    except ImportError:
        logger.error("PIL not installed. Run: pip install pillow")
        return ""
    except Exception as e:
        logger.error("生成演示图片失败: %s", e)
        return ""


def demo_pipeline():
    """演示完整流程：生成海报 → OCR → 事件抽取"""
    logging.basicConfig(level=logging.INFO)

    print("🖥️  科技多媒体抽取演示")
    print("=" * 50)

    # 1. 生成海报
    image_path = generate_demo_image()
    if not image_path:
        print("❌ 无法生成演示图片（请安装 pillow）")
        return
    print(f"   📸 海报已生成: {os.path.basename(image_path)}")

    # 2. OCR + 抽取
    extractor = MultimodalExtractor()
    result = extractor.process_image(image_path)

    print(f"\n   🔤 OCR 引擎: {result.get('ocr_engine', 'unknown')}")
    print(f"   📏 识别 {result.get('ocr_text_length', 0)} 字符")
    print(f"   📊 置信度: {result.get('ocr_confidence', 0):.2%}")

    print("\n   📝 OCR 文本:")
    ocr = result.get("ocr_text", "")
    print(f"      {(ocr[:200] + '...') if len(ocr) > 200 else ocr}")

    print("\n   🎯 抽取事件:")
    for k, v in result.get("extraction", {}).items():
        print(f"      {k}: {v or '-'}")

    print("\n" + "=" * 50)
    return result


if __name__ == "__main__":
    demo_pipeline()
