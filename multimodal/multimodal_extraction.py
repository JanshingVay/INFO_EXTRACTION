"""
跨模态信息抽取模块 —— 图片 OCR 文本识别 → 投融资事件抽取

支持引擎：
  - EasyOCR（默认）：多语言，GPU 加速，中文识别精度高
  - PyTesseract（备选）：轻量级，零 GPU 依赖，需安装 tesseract

管线设计：
  Image File → OCR Engine → Raw Text → RegexExtractor → Structured Events
"""
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from config import OCR_CONFIG, IMAGES_DIR, BASE_DIR
from extractor.regex_extractor import RegexExtractor
from extractor.nlp_extractor import NLPExtractor

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class OCREngine(ABC):
    """OCR 引擎抽象基类"""

    def __init__(self, languages: List[str] = None):
        self.languages = languages or OCR_CONFIG.get("languages", ["ch_sim", "en"])
        self._loaded = False

    @abstractmethod
    def recognize(self, image_path: str) -> str:
        """识别图片中的全部文本"""
        ...

    @abstractmethod
    def recognize_with_regions(self, image_path: str) -> List[Dict[str, Any]]:
        """识别图片文本并返回位置信息"""
        ...

    @property
    @abstractmethod
    def engine_name(self) -> str:
        ...


class EasyOCREngine(OCREngine):
    """EasyOCR 引擎 —— 推荐使用"""

    def __init__(self, languages: List[str] = None, gpu: bool = True):
        super().__init__(languages)
        self._reader = None
        self._gpu = gpu

    @property
    def engine_name(self) -> str:
        return "EasyOCR"

    def _ensure_reader(self):
        if self._reader is not None:
            return
        try:
            import easyocr
            self._reader = easyocr.Reader(
                self.languages, gpu=self._gpu, verbose=False
            )
            self._loaded = True
            logger.info("EasyOCR reader initialized: languages=%s, gpu=%s", self.languages, self._gpu)
        except ImportError:
            raise ImportError(
                "EasyOCR not installed. Run: pip install easyocr\n"
                "Then try again."
            )

    def recognize(self, image_path: str) -> str:
        self._ensure_reader()
        results = self._reader.readtext(image_path, detail=0)
        return "\n".join(results) if results else ""

    def recognize_with_regions(self, image_path: str) -> List[Dict[str, Any]]:
        self._ensure_reader()
        raw_results = self._reader.readtext(image_path, detail=1)
        regions = []
        for bbox, text, conf in raw_results:
            x1, y1 = int(bbox[0][0]), int(bbox[0][1])
            x2, y2 = int(bbox[2][0]), int(bbox[2][1])
            regions.append({
                "text": text,
                "confidence": round(float(conf), 4),
                "bbox": [[int(p[0]), int(p[1])] for p in bbox],
                "position": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
            })
        return regions


class TesseractEngine(OCREngine):
    """PyTesseract 引擎 —— 备选方案，零 GPU 依赖"""

    def __init__(self, languages: List[str] = None):
        super().__init__(languages)

    @property
    def engine_name(self) -> str:
        return "PyTesseract"

    def _ensure_tesseract(self):
        if self._loaded:
            return
        try:
            import pytesseract
            self._pytesseract = pytesseract
            self._loaded = True
            logger.info("PyTesseract initialized")
        except ImportError:
            raise ImportError(
                "pytesseract not installed. Run: pip install pytesseract\n"
                "Also install tesseract OCR: brew install tesseract tesseract-lang"
            )

    def _build_lang_string(self) -> str:
        lang_map = {
            "ch_sim": "chi_sim",
            "ch_tra": "chi_tra",
            "en": "eng",
        }
        return "+".join(lang_map.get(l, l) for l in self.languages)

    def recognize(self, image_path: str) -> str:
        self._ensure_tesseract()
        from PIL import Image
        img = Image.open(image_path)
        lang = self._build_lang_string()
        text = self._pytesseract.image_to_string(img, lang=lang)
        return text.strip()

    def recognize_with_regions(self, image_path: str) -> List[Dict[str, Any]]:
        self._ensure_tesseract()
        from PIL import Image
        img = Image.open(image_path)
        lang = self._build_lang_string()
        raw = self._pytesseract.image_to_data(img, lang=lang, output_type=self._pytesseract.Output.DICT)

        regions = []
        for i, text in enumerate(raw["text"]):
            t = text.strip()
            if not t:
                continue
            regions.append({
                "text": t,
                "confidence": round(int(raw["conf"][i]) / 100.0, 4) if raw["conf"][i] != "-1" else 0.0,
                "position": {
                    "x": raw["left"][i],
                    "y": raw["top"][i],
                    "w": raw["width"][i],
                    "h": raw["height"][i],
                },
            })
        return regions


def create_ocr_engine(engine_name: str = None, **kwargs) -> OCREngine:
    """工厂函数：创建 OCR 引擎实例"""
    engine_name = engine_name or OCR_CONFIG.get("engine", "easyocr")
    languages = kwargs.pop("languages", None) or OCR_CONFIG.get("languages", ["ch_sim", "en"])

    if engine_name == "easyocr":
        return EasyOCREngine(languages=languages, **kwargs)
    elif engine_name in ("tesseract", "pytesseract"):
        return TesseractEngine(languages=languages)

    raise ValueError(f"Unknown OCR engine: {engine_name}. Use 'easyocr' or 'tesseract'.")


class MultimodalExtractor:
    """
    跨模态信息抽取管线

    处理流程：
      image → OCR text → extractor → structured events
    """

    def __init__(
        self,
        ocr_engine: OCREngine = None,
        ocr_engine_name: str = None,
        use_nlp: bool = False,
    ):
        self.ocr_engine = ocr_engine or create_ocr_engine(ocr_engine_name)
        self.regex_extractor = RegexExtractor()
        self.nlp_extractor = NLPExtractor() if use_nlp else None
        self._ocr_cache: Dict[str, str] = {}

        logger.info(
            "MultimodalExtractor initialized: engine=%s, nlp=%s",
            self.ocr_engine.engine_name,
            "enabled" if use_nlp else "disabled (regex only)",
        )

    def ocr_image(self, image_path: str) -> str:
        """对单张图片执行 OCR"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        if image_path in self._ocr_cache:
            return self._ocr_cache[image_path]

        logger.info("Running OCR on: %s", os.path.basename(image_path))
        start = time.time()
        text = self.ocr_engine.recognize(image_path)
        elapsed = time.time() - start

        logger.info(
            "OCR completed in %.2fs, %d chars extracted",
            elapsed, len(text),
        )

        self._ocr_cache[image_path] = text
        return text

    def ocr_with_details(self, image_path: str) -> List[Dict[str, Any]]:
        """对单张图片执行 OCR 并返回位置信息"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        return self.ocr_engine.recognize_with_regions(image_path)

    def extract_from_text(
        self, text: str, source_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        从 OCR 文本中抽取投融资事件要素

        Args:
            text: OCR 识别出的原始文本
            source_info: 来源图片信息

        Returns:
            包含 regex_result, nlp_result (如果启用), ocr_text_source 的完整结果
        """
        article = {
            "title": "",
            "summary": text,
            "content": text,
            "publish_time": source_info.get("date", "") if source_info else "",
            "source": source_info.get("source", "OCR") if source_info else "OCR",
            "id": source_info.get("image", "") if source_info else "",
        }

        regex_result = self.regex_extractor.extract(article)

        result = {
            "ocr_text": text,
            "ocr_text_length": len(text),
            "regex_result": {k: v for k, v in regex_result.items() if k not in ("extractor", "article_id")},
            "source": source_info,
        }

        if self.nlp_extractor:
            nlp_result = self.nlp_extractor.extract(article)
            result["nlp_result"] = {k: v for k, v in nlp_result.items() if k not in ("extractor", "article_id")}

        return result

    def process_image(
        self, image_path: str, source_info: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        完整管线：图片 → OCR → 抽取

        Args:
            image_path: 图片文件路径
            source_info: 额外来源信息

        Returns:
            完整的抽取结果
        """
        if source_info is None:
            source_info = {}
        source_info["image"] = os.path.basename(image_path)
        source_info["image_path"] = os.path.abspath(image_path)

        text = self.ocr_image(image_path)
        result = self.extract_from_text(text, source_info)
        result["ocr_regions"] = self.ocr_with_details(image_path)
        result["image_path"] = image_path
        result["processed_at"] = datetime.now().isoformat()
        return result

    def process_directory(
        self, directory: str, extensions: Tuple[str, ...] = None
    ) -> List[Dict[str, Any]]:
        """
        批量处理目录中的所有图片

        Args:
            directory: 图片目录
            extensions: 支持的文件扩展名

        Returns:
            所有图片的抽取结果列表
        """
        if extensions is None:
            extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")

        image_files = sorted(
            f for f in os.listdir(directory)
            if f.lower().endswith(extensions)
        )

        if not image_files:
            logger.warning("No images found in %s (extensions: %s)", directory, extensions)
            return []

        logger.info("Processing %d images in %s", len(image_files), directory)

        results = []
        for i, filename in enumerate(image_files):
            path = os.path.join(directory, filename)
            logger.info("[%d/%d] %s", i + 1, len(image_files), filename)
            try:
                result = self.process_image(path)
                results.append(result)
            except Exception as e:
                logger.error("Failed to process %s: %s", filename, e)
                results.append({
                    "image_path": path,
                    "error": str(e),
                    "processed_at": datetime.now().isoformat(),
                })

        logger.info("Batch processing complete: %d/%d succeeded", sum(1 for r in results if "error" not in r), len(results))
        return results

    def save_results(self, results: Any, filepath: str = None) -> str:
        """保存抽取结果到 JSON"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(IMAGES_DIR, f"ocr_extraction_{timestamp}.json")

        if not isinstance(results, list):
            results = [results]

        output = {
            "metadata": {
                "total": len(results),
                "ocr_engine": self.ocr_engine.engine_name,
                "success": sum(1 for r in results if "error" not in r),
                "extracted_at": datetime.now().isoformat(),
            },
            "results": results,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info("Results saved to: %s", filepath)
        return filepath


def generate_demo_image() -> str:
    """生成一张模拟科技新闻截图的测试图片"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.error("Pillow not installed. Run: pip install Pillow")
        return ""

    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 28)
        font_body = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 20)
        font_small = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 16)
    except (OSError, IOError):
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((40, 30), "【36氪快讯】", fill=(220, 50, 50), font=font_title)
    draw.text((40, 80), "月之暗面完成8亿美元B轮融资", fill=(20, 20, 20), font=font_title)

    draw.line([(40, 125), (760, 125)], fill=(200, 200, 200), width=1)

    draw.text((40, 145), "2026年5月15日 14:30", fill=(128, 128, 128), font=font_small)

    body_lines = [
        "据悉，AI大模型公司月之暗面（Moonshot AI）近日",
        "宣布完成8亿美元B轮融资，本轮由阿里巴巴集团领投，",
        "红杉资本中国基金、美团龙珠资本跟投。本轮融资完成后，",
        "公司估值达到30亿美元。",
        "",
        "月之暗面成立于2023年，专注于通用人工智能大模型",
        "研发，旗下产品包括智能助手等。此次融资将用于",
        "下一代大模型研发及商业化落地。",
        "",
        "阿里巴巴集团副总裁表示：\"我们看好月之暗面在大模型",
        "领域的技术积累，期待与其展开更深入的合作。\"",
    ]
    y = 180
    for line in body_lines:
        draw.text((40, y), line, fill=(50, 50, 50), font=font_body)
        y += 32

    draw.line([(40, 540), (760, 540)], fill=(200, 200, 200), width=1)
    draw.text((40, 555), "来源：36氪  |  作者：王白  |  编辑：李思", fill=(160, 160, 160), font=font_small)

    filepath = os.path.join(IMAGES_DIR, "demo_news_screenshot.png")
    img.save(filepath)
    logger.info("Demo image saved to: %s", filepath)
    return filepath


def demo_pipeline():
    """演示完整跨模态提取管线"""

    print("\n" + "=" * 60)
    print("  跨模态信息抽取管线演示")
    print("=" * 60)

    image_path = generate_demo_image()
    if not image_path:
        print("❌ 无法生成演示图片（需要 Pillow 库）")
        return

    print(f"\n📷 生成演示图片: {image_path}")
    print('   (模拟一张"月之暗面融资8亿美元B轮"的新闻截图)')

    extractor = MultimodalExtractor(ocr_engine_name="easyocr")

    print("\n⏳ 正在执行 OCR 文本识别...")
    result = extractor.process_image(image_path)

    print(f"\n📝 OCR 识别文本（{result['ocr_text_length']} 字符）：")
    print("─" * 50)
    print(result["ocr_text"] if result["ocr_text"] else "(OCR 未识别到文本)")
    print("─" * 50)

    print("\n🔍 RegexExtractor 抽取结果：")
    for field in ["Investor", "Target", "Amount", "Round", "Date"]:
        value = result["regex_result"].get(field) or "(未抽出)"
        print(f"   {field:<10}: {value}")

    filepath = extractor.save_results(result)
    print(f"\n💾 结果已保存: {filepath}")
    print("=" * 60)


if __name__ == "__main__":
    demo_pipeline()
