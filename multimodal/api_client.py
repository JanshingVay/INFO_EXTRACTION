import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

from config import EXTRACTION_FIELDS, load_multimodal_api_config

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}


def _normalize_base_url(api_url: str) -> str:
    url = (api_url or "").strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url


def _parse_api_response(raw_text: str) -> Dict[str, Optional[str]]:
    extraction = {k: None for k in EXTRACTION_FIELDS}
    if not raw_text:
        return extraction

    raw_text = raw_text.strip()

    json_str = None
    if raw_text.startswith("{"):
        json_str = raw_text
    elif "```json" in raw_text:
        s = raw_text.find("```json") + 7
        e = raw_text.find("```", s)
        json_str = raw_text[s:e].strip() if e > s else raw_text[s:].strip()
    elif "```" in raw_text:
        s = raw_text.find("```") + 3
        e = raw_text.find("```", s)
        json_str = raw_text[s:e].strip() if e > s else raw_text[s:].strip()

    if json_str:
        try:
            parsed = json.loads(json_str)
            for f in EXTRACTION_FIELDS:
                v = parsed.get(f)
                if v and str(v).lower() not in ("null", "none", ""):
                    extraction[f] = str(v)
            return extraction
        except json.JSONDecodeError:
            pass

    for field in EXTRACTION_FIELDS:
        m = re.search(rf'"{field}"\s*:\s*"([^"]*)"', raw_text)
        if m and m.group(1).strip():
            extraction[field] = m.group(1).strip()
    return extraction


def extract_with_multimodal_api(
    media_path: str,
    api_url: str = None,
    api_key: str = None,
    model: str = None,
    system_prompt: str = None,
) -> Dict[str, Any]:
    """
    使用第三方多模态大模型通过 OpenAI SDK 从图片/视频中抽取事件。

    自动根据文件扩展名判断媒体类型：
      - 图片：使用 image_url 类型
      - 视频：使用 video_url 类型

    Returns:
        {
            "extraction": {developer, tech_product, action_type, version_metric, date},
            "api_engine": "gpt-4o",
            "media_type": "image" | "video",
            "api_latency": 3.5,
            "raw_response": "..."
        }
    """
    config = load_multimodal_api_config()

    api_url = api_url or config["api_url"]
    api_key = api_key or config["api_key"]
    model = model or config["model"]
    system_prompt = system_prompt or config["system_prompt"]

    if not api_key:
        return {"error": "API Key 未配置", "extraction": {k: None for k in EXTRACTION_FIELDS}}

    ext = os.path.splitext(media_path)[1].lower()

    if ext in VIDEO_EXTENSIONS:
        media_type = "video"
        mime_prefix = "video"
        content_type = "video_url"
        content_key = "video_url"
    else:
        media_type = "image"
        mime_prefix = "image"
        content_type = "image_url"
        content_key = "image_url"

    with open(media_path, "rb") as f:
        raw_data = f.read()

    data_uri = f"data:{mime_prefix}/{ext.lstrip('.')};base64,{base64.b64encode(raw_data).decode('utf-8')}"

    base_url = _normalize_base_url(api_url)
    logger.info("使用 %s SDK 模式调用: base_url=%s, model=%s, media_type=%s",
                media_type, base_url, model, media_type)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请从这段媒体内容中抽取出科技发布事件的核心要素。"},
                        {
                            "type": content_type,
                            content_key: {"url": data_uri},
                        },
                    ],
                },
            ],
        )
        elapsed = time.perf_counter() - t0

        raw_text = response.choices[0].message.content
        extraction = _parse_api_response(raw_text)

        return {
            "extraction": extraction,
            "api_engine": model,
            "media_type": media_type,
            "api_latency": round(elapsed, 2),
            "raw_response": raw_text[:500],
        }

    except ImportError:
        return {"error": "请安装 openai SDK: pip install openai", "extraction": {k: None for k in EXTRACTION_FIELDS}}
    except Exception as e:
        err_msg = str(e)[:300]
        logger.error("多模态 API 调用失败: %s", err_msg)
        return {"error": err_msg, "extraction": {k: None for k in EXTRACTION_FIELDS}}
