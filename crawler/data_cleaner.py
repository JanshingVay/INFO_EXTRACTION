import re
import html as html_module
from difflib import SequenceMatcher
from config import DATA_CLEAN_CONFIG


def normalize_whitespace(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +(\n+)", r"\1", text)
    text = re.sub(r"(\n+) +", r"\1", text)
    return text.strip()


def remove_html_entities(text):
    return html_module.unescape(text)


BOILERPLATE_PATTERNS = [
    re.compile(r"(?:Copyright|©)\s*(?:\d{4}[-—–]\d{4}|\d{4}).*", re.IGNORECASE),
    re.compile(r"版权所有[,，].*?(?:不得转载|保留所有权利).*", re.IGNORECASE),
    re.compile(r"All\s+Rights?\s+Reserved\.?", re.IGNORECASE),
    re.compile(r"(?:责任编辑|编辑|记者|责编)[:：]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:来源|作者|来源[:：])\s*\S+", re.IGNORECASE),
    re.compile(r"(?:分享到|微信|微博|QQ空间|一键分享|扫一扫)", re.IGNORECASE),
    re.compile(r"(?:返回搜狐|查看更多|返回首页|推荐阅读|相关推荐).*", re.IGNORECASE),
    re.compile(r"(?:声明[:：]|免责声明).*?(?:。|\.)", re.IGNORECASE),
    re.compile(r"【(?:纠错|责任编辑)】", re.IGNORECASE),
]


def remove_boilerplate(text):
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)
    return normalize_whitespace(text)


def clean_text(text):
    if not text:
        return ""
    text = remove_html_entities(text)
    text = normalize_whitespace(text)
    if DATA_CLEAN_CONFIG.get("remove_boilerplate", True):
        text = remove_boilerplate(text)
    return text


def title_similarity(title_a, title_b):
    return SequenceMatcher(None, title_a, title_b).ratio()


def deduplicate_by_title(documents, threshold=None):
    if threshold is None:
        threshold = DATA_CLEAN_CONFIG.get("dedup_by_title_similarity", 0.85)
    seen = []
    deduped = []
    removed_count = 0
    for doc in documents:
        title = doc.get("title", "")
        is_dup = False
        for seen_title in seen:
            if title_similarity(title, seen_title) >= threshold:
                is_dup = True
                break
        if is_dup:
            removed_count += 1
            continue
        seen.append(title)
        deduped.append(doc)
    if removed_count > 0:
        print(f"[DataCleaner] Removed {removed_count} duplicate documents by title similarity.")
    return deduped


def is_valid_document(doc, min_length=None):
    if min_length is None:
        min_length = DATA_CLEAN_CONFIG.get("min_content_length", 100)
    text = doc.get("text", "")
    if not text or len(text.strip()) < min_length:
        return False
    url = doc.get("url", "")
    if url and "example.com" in url:
        return False
    return True


def clean_documents(documents):
    cleaned = []
    seen_urls = set()
    skipped_invalid = 0
    skipped_dup_url = 0
    skipped_example = 0

    for doc in documents:
        if not is_valid_document(doc):
            skipped_invalid += 1
            continue

        url = doc.get("url", "")
        if url and "example.com" in url:
            skipped_example += 1
            continue

        if DATA_CLEAN_CONFIG.get("dedup_by_url", True):
            if url in seen_urls:
                skipped_dup_url += 1
                continue
            seen_urls.add(url)

        doc["title"] = clean_text(doc.get("title", ""))
        doc["text"] = clean_text(doc.get("text", ""))
        doc["date"] = (doc.get("date", "") or "").strip()

        max_title_len = DATA_CLEAN_CONFIG.get("max_title_length", 200)
        if len(doc["title"]) > max_title_len:
            doc["title"] = doc["title"][:max_title_len]

        cleaned.append(doc)

    if DATA_CLEAN_CONFIG.get("dedup_by_title_similarity", 0) > 0:
        cleaned = deduplicate_by_title(cleaned)

    print(f"[DataCleaner] Cleaned {len(documents)} documents -> {len(cleaned)} valid documents.")
    if skipped_invalid:
        print(f"  Skipped {skipped_invalid} too-short/invalid documents.")
    if skipped_dup_url:
        print(f"  Skipped {skipped_dup_url} duplicate URLs.")
    if skipped_example:
        print(f"  Skipped {skipped_example} example.com fake documents.")

    return cleaned
