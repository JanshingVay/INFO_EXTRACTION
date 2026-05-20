"""
多媒体抽取模块 - 科技技术海报OCR

支持：
- 云原生大会PPT截图
- 开源项目Release喜报海报
- 芯片/模型发布海报
- OCR文字识别 + 科技事件抽取
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from config import IMAGES_DIR, OCR_CONFIG
from extractor.regex_extractor import RegexExtractor
from extractor.nlp_extractor import NLPExtractor

logger = logging.getLogger(__name__)


class MultimodalExtractor:
    """跨模态抽取器（图片 → OCR → 科技事件抽取）"""

    def __init__(self, ocr_engine: str = None):
        self.ocr_engine = ocr_engine or OCR_CONFIG.get("engine", "easyocr")
        self.languages = OCR_CONFIG.get("languages", ["ch_sim", "en"])
        self.extractor = RegexExtractor()

    def _ocr_with_easyocr(self, image_path: str) -> str:
        """使用EasyOCR识别图片文字"""
        try:
            import easyocr
            reader = easyocr.Reader(self.languages, gpu=False)
            results = reader.readtext(image_path, detail=0)
            return "\n".join(results)
        except ImportError:
            logger.error("EasyOCR not installed. Run: pip install easyocr")
            return ""
        except Exception as e:
            logger.error("OCR failed: %s", e)
            return ""

    def _ocr_with_pytesseract(self, image_path: str) -> str:
        """使用PyTesseract识别图片文字（备选）"""
        try:
            from PIL import Image
            import pytesseract
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            return text
        except ImportError:
            logger.error("PyTesseract not installed. Run: pip install pytesseract pillow")
            return ""
        except Exception as e:
            logger.error("OCR failed: %s", e)
            return ""

    def extract_text_from_image(self, image_path: str) -> str:
        """从图片提取文字"""
        if self.ocr_engine == "easyocr":
            return self._ocr_with_easyocr(image_path)
        else:
            return self._ocr_with_pytesseract(image_path)

    def process_image(self, image_path: str) -> Dict[str, Any]:
        """处理单张图片：OCR + 科技事件抽取"""
        logger.info("🖼️ 处理图片: %s", os.path.basename(image_path))

        ocr_text = self.extract_text_from_image(image_path)
        if not ocr_text:
            return {
                "image_path": image_path,
                "ocr_text": "",
                "extraction": {k: None for k in ["developer", "tech_product", "action_type", "version_metric", "date"]},
                "error": "OCR failed"
            }

        article = {
            "title": ocr_text[:100],
            "summary": ocr_text,
            "content": ocr_text,
            "id": os.path.basename(image_path),
        }

        extraction = self.extractor.extract(article)

        return {
            "image_path": image_path,
            "ocr_text": ocr_text,
            "extraction": extraction,
        }

    def process_directory(self, directory: str) -> List[Dict[str, Any]]:
        """批量处理目录下所有图片"""
        results = []
        for filename in os.listdir(directory):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                filepath = os.path.join(directory, filename)
                result = self.process_image(filepath)
                results.append(result)
        return results

    def save_results(self, results: List[Dict[str, Any]], filename: str = None):
        """保存结果"""
        if filename is None:
            filename = f"multimodal_tech_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(IMAGES_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("💾 已保存结果至: %s", filepath)
        return filepath


def generate_demo_image() -> str:
    """生成演示海报图片（开源项目Release喜报 / 云原生大会PPT）"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random

        width, height = 800, 1000
        img = Image.new('RGB', (width, height), color=(10, 25, 47))
        draw = ImageDraw.Draw(img)

        tech_types = ["开源项目Release", "云原生技术大会", "大模型发布", "芯片算力突破"]
        tech_type = random.choice(tech_types)

        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 60)
            font_medium = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 40)
            font_small = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 30)
        except:
            font_large = ImageFont.load_default()
            font_medium = font_large
            font_small = font_large

        y_offset = 100

        draw.text((width//2, y_offset), "科技技术喜报", fill=(100, 200, 255), font=font_large, anchor="mm")
        y_offset += 120

        if tech_type == "开源项目Release":
            projects = ["Kubernetes v1.30", "PyTorch 2.3", "React 19", "Rust 1.78"]
            project = random.choice(projects)
            draw.text((width//2, y_offset), project, fill=(255, 255, 255), font=font_large, anchor="mm")
            y_offset += 150

            release_info = "正式发布 开源项目Release"
            draw.text((width//2, y_offset), release_info, fill=(100, 255, 100), font=font_medium, anchor="mm")
            y_offset += 100

            org = random.choice(["CNCF基金会", "Meta AI", "Facebook", "Mozilla"])
            draw.text((width//2, y_offset), f"主办方：{org}", fill=(200, 200, 200), font=font_small, anchor="mm")
            y_offset += 150

        elif tech_type == "云原生技术大会":
            confs = ["KubeCon 2024", "QCon 全球软件开发大会", "ArchSummit 架构师峰会"]
            conf = random.choice(confs)
            draw.text((width//2, y_offset), conf, fill=(255, 255, 255), font=font_large, anchor="mm")
            y_offset += 150

            draw.text((width//2, y_offset), "云原生架构 容器化部署", fill=(100, 200, 255), font=font_medium, anchor="mm")
            y_offset += 100

            date_info = "2024年5月 上海"
            draw.text((width//2, y_offset), date_info, fill=(200, 200, 200), font=font_small, anchor="mm")
            y_offset += 150

        elif tech_type == "大模型发布":
            models = ["DeepSeek-V3", "Qwen 2.0", "Llama 3", "GPT-5"]
            model = random.choice(models)
            draw.text((width//2, y_offset), model, fill=(255, 255, 255), font=font_large, anchor="mm")
            y_offset += 150

            params = random.choice(["70B参数", "1.5T参数", "300B参数"])
            draw.text((width//2, y_offset), params, fill=(255, 150, 100), font=font_medium, anchor="mm")
            y_offset += 100

            company = random.choice(["DeepSeek", "通义千问", "Meta", "OpenAI"])
            draw.text((width//2, y_offset), company, fill=(200, 200, 200), font=font_small, anchor="mm")
            y_offset += 150

        else:
            chips = ["NVIDIA H200", "AMD MI300", "华为昇腾910"]
            chip = random.choice(chips)
            draw.text((width//2, y_offset), chip, fill=(255, 255, 255), font=font_large, anchor="mm")
            y_offset += 150

            perf = random.choice(["性能提升40%", "算力突破2000PFlops"])
            draw.text((width//2, y_offset), perf, fill=(100, 255, 200), font=font_medium, anchor="mm")
            y_offset += 100

            vendor = random.choice(["NVIDIA", "AMD", "华为"])
            draw.text((width//2, y_offset), vendor, fill=(200, 200, 200), font=font_small, anchor="mm")
            y_offset += 150

        date_banner = f"发布日期：{datetime.now().strftime('%Y-%m-%d')}"
        draw.text((width//2, y_offset), date_banner, fill=(150, 150, 150), font=font_small, anchor="mm")
        y_offset += 200

        draw.text((width//2, height-100), "技术驱动未来", fill=(100, 200, 255), font=font_small, anchor="mm")

        filename = f"tech_poster_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(IMAGES_DIR, filename)
        img.save(filepath)
        logger.info("✅ 生成演示科技海报: %s", filename)
        return filepath

    except ImportError:
        logger.error("PIL not installed. Run: pip install pillow")
        return ""
    except Exception as e:
        logger.error("生成演示图片失败: %s", e)
        return ""


def demo_pipeline():
    """演示完整流程：生成海报 → OCR → 科技事件抽取"""
    logger.info("🖥️  启动科技多媒体抽取演示...")

    image_path = generate_demo_image()
    if not image_path:
        logger.error("无法生成演示图片")
        return

    extractor = MultimodalExtractor()
    result = extractor.process_image(image_path)

    logger.info("\n" + "="*50)
    logger.info("OCR识别文字:")
    logger.info(result["ocr_text"][:300] + "..." if len(result["ocr_text"]) > 300 else result["ocr_text"])
    logger.info("\n抽取结果:")
    for k, v in result["extraction"].items():
        logger.info(f"  {k}: {v}")
    logger.info("="*50)

    return result


if __name__ == "__main__":
    demo_pipeline()
