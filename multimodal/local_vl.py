"""
本地开源多模态模型抽取模块 - 支持 Qwen2.5-VL / InternVL2
"""
import os
import time
import json
import re
import logging
from typing import Any, Dict, Optional

from config import (
    EXTRACTION_FIELDS,
    load_local_vl_config,
)

logger = logging.getLogger(__name__)


def _parse_api_response(raw_text: str) -> Dict[str, Optional[str]]:
    """解析本地多模态模型返回的 JSON 文本。"""
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


def extract_with_local_vl(
    media_path: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    使用本地开源多模态大模型从图片/视频中抽取事件。

    支持模型:
      - Qwen/Qwen2.5-VL-7B-Instruct
      - OpenGVLab/InternVL2-8B-Instruct
      - ... 其他兼容 OpenAI Completions 接口的本地模型

    Args:
        media_path: 图片或视频路径
        config: 本地多模态配置字典，缺省从 load_local_vl_config() 加载

    Returns:
        包含 extraction / media_type / local_model / latency / raw_response 的字典
    """
    config = config or load_local_vl_config()

    ext = os.path.splitext(media_path)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}
    media_type = "video" if is_video else "image"

    model_name = config.get("model", "Qwen/Qwen2.5-VL-7B-Instruct")
    device = config.get("device", "auto")
    system_prompt = config.get("system_prompt", "")
    temperature = config.get("temperature", 0.3)
    max_tokens = config.get("max_tokens", 2048)

    logger.info(f"本地多模态模型: {model_name} (device: {device})")
    logger.info(f"处理媒体: {media_path} (type: {media_type})")

    try:
        # 方案 1: Qwen2.5-VL (使用 transformers, 最主流)
        if "Qwen" in model_name or "qwen" in model_name.lower():
            return _call_qwen_vl(
                media_path=media_path,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                device=device,
            )
        # 方案 2: InternVL2
        elif "InternVL" in model_name or "internvl" in model_name.lower():
            return _call_internvl2(
                media_path=media_path,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                device=device,
            )
        # 方案 3: 通用 OpenAI 兼容本地服务器（如 vLLM / Ollama）
        else:
            return _call_openai_compatible_local(
                media_path=media_path,
                config=config,
            )
    except ImportError as e:
        logger.error(f"缺少依赖库，请安装: pip install transformers torch pillow accelerate")
        return {"error": f"依赖缺失: {e}", "extraction": {k: None for k in EXTRACTION_FIELDS}}
    except Exception as e:
        logger.error(f"本地多模态模型调用失败: {e}")
        return {"error": str(e), "extraction": {k: None for k in EXTRACTION_FIELDS}}


def _call_qwen_vl(
    media_path: str,
    model_name: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
    device: str,
) -> Dict[str, Any]:
    from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
    from PIL import Image
    import torch

    t0 = time.perf_counter()

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device,
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    ext = os.path.splitext(media_path)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    if is_video:
        from qwen_vl_utils import process_video
        video_info = process_video(media_path, fps=1, max_num=16)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": video_info},
                    {"type": "text", "text": "请从这段视频中抽取出科技发布事件的核心要素。"},
                ],
            }
        )
    else:
        image = Image.open(media_path).convert("RGB")
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": "请从这张图片中抽取出科技发布事件的核心要素。"},
                ],
            }
        )

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=text, images=[] if is_video else [image], videos=[] if not is_video else [video_info], return_tensors="pt").to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=max_tokens, temperature=temperature)
    generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
    raw_text = processor.batch_decode(generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]

    latency = round(time.perf_counter() - t0, 2)
    extraction = _parse_api_response(raw_text)

    return {
        "extraction": extraction,
        "local_model": model_name,
        "media_type": "video" if is_video else "image",
        "latency": latency,
        "raw_response": raw_text[:500],
    }


def _call_internvl2(
    media_path: str,
    model_name: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
    device: str,
) -> Dict[str, Any]:
    from transformers import AutoProcessor, AutoModel
    from PIL import Image
    import torch

    t0 = time.perf_counter()

    model = AutoModel.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16,
        device_map=device,
        trust_remote_code=True,
    )
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    ext = os.path.splitext(media_path)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}

    if is_video:
        logger.warning("InternVL2 当前仅支持图片，降级为取第一帧处理")
        # 取第一帧
        import cv2
        cap = cv2.VideoCapture(media_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return {"error": "无法读取视频第一帧", "extraction": {k: None for k in EXTRACTION_FIELDS}}
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    else:
        image = Image.open(media_path).convert("RGB")

    question = "请从这张图片中抽取出科技发布事件的核心要素。"
    prompt = f"{system_prompt}\n\n用户: {question}"

    pixel_values = processor(image, return_tensors="pt", test_query=prompt, num_image=1).pixel_values.to(model.device, torch.bfloat16)

    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_new_tokens=max_tokens, temperature=temperature, test_query=prompt)
    raw_text = processor.decode(generated_ids[0], skip_special_tokens=True)

    latency = round(time.perf_counter() - t0, 2)
    extraction = _parse_api_response(raw_text)

    return {
        "extraction": extraction,
        "local_model": model_name,
        "media_type": "video" if is_video else "image",
        "latency": latency,
        "raw_response": raw_text[:500],
    }


def _call_openai_compatible_local(
    media_path: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    通用方案：假设本地模型已通过 vLLM / Ollama / text-generation-webui 等起成 OpenAI 兼容 API
    config 中的 api_url 指向本地服务地址
    """
    from openai import OpenAI

    api_url = config.get("api_url", "http://localhost:11434/v1")
    api_key = config.get("api_key", "dummy")
    model = config.get("model", "internvl2")
    system_prompt = config.get("system_prompt", "")
    temperature = config.get("temperature", 0.3)
    max_tokens = config.get("max_tokens", 2048)

    t0 = time.perf_counter()

    ext = os.path.splitext(media_path)[1].lower()
    is_video = ext in {".mp4", ".mov", ".avi", ".webm", ".mkv"}

    import base64
    with open(media_path, "rb") as f:
        raw_data = f.read()

    mime_prefix = "video" if is_video else "image"
    data_uri = f"data:{mime_prefix}/{ext.lstrip('.')};base64,{base64.b64encode(raw_data).decode('utf-8')}"
    content_type = "video_url" if is_video else "image_url"
    content_key = "video_url" if is_video else "image_url"

    client = OpenAI(api_key=api_key, base_url=api_url)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请从这段媒体中抽取出科技发布事件的核心要素。"},
                    {
                        "type": content_type,
                        content_key: {"url": data_uri},
                    },
                ],
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw_text = response.choices[0].message.content
    latency = round(time.perf_counter() - t0, 2)
    extraction = _parse_api_response(raw_text)

    return {
        "extraction": extraction,
        "local_model": model,
        "media_type": "video" if is_video else "image",
        "latency": latency,
        "raw_response": raw_text[:500],
    }
