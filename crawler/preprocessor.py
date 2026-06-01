import jieba
import re
import os

STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "所", "为", "所以", "因为", "但是", "然而", "而且", "虽然", "如果",
    "可以", "这个", "那个", "哪个", "什么", "怎么", "怎样", "如何",
    "吗", "呢", "吧", "啊", "哦", "嗯", "哈", "嘛", "呗",
    "与", "及", "或", "且", "但", "而", "则", "其", "之", "以", "于",
    "从", "对", "被", "把", "向", "让", "将", "由", "使",
    "该", "各", "某", "每", "全", "整", "另", "别", "共", "同",
    "能", "能够", "可能", "可以", "需要", "应该", "必须", "一定",
    "已", "已经", "曾", "曾经", "将", "将要", "正在", "一直", "还是",
    "只", "只有", "只是", "只要", "不过", "但", "但是", "却",
    "很", "太", "非常", "十分", "特别", "比较", "更", "最",
    "第一", "第二", "第三", "首先", "其次", "最后", "然后", "接着",
    "来", "去", "进", "出", "上", "下", "过", "回", "起",
    "做", "作", "搞", "弄", "用", "拿", "给", "为",
    "吗", "呢", "吧", "啊", "哦", "嗯", "哈", "嘛", "呗",
    "呀", "啦", "哟", "哇", "嘿", "喂", "嗨",
    "www", "com", "cn", "http", "https", "html", "htm",
    "nbsp", "quot", "amp", "lt", "gt",
}

def load_stopwords(filepath=None):
    """Load stopwords from file or use built-in set."""
    custom = set()
    if filepath and os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    custom.add(word)
    return STOPWORDS | custom


class TextPreprocessor:
    """Chinese text preprocessing with jieba segmentation."""

    def __init__(self, stopwords_file=None):
        self.stopwords = load_stopwords(stopwords_file)

    def clean_text(self, text):
        """Remove special characters and normalize whitespace."""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def segment(self, text):
        """Segment Chinese text using jieba."""
        cleaned = self.clean_text(text)
        words = jieba.lcut(cleaned)
        tokens = []
        for w in words:
            w = w.strip().lower()
            if not w:
                continue
            if w in self.stopwords:
                continue
            if len(w) == 1 and not '\u4e00' <= w <= '\u9fff':
                continue
            if re.match(r'^\d+$', w):
                continue
            tokens.append(w)
        return tokens

    def process_documents(self, documents):
        """Segment all documents and attach tokens."""
        for doc in documents:
            full_text = doc["title"] + " " + doc["text"]
            doc["tokens"] = self.segment(full_text)
        return documents


if __name__ == "__main__":
    p = TextPreprocessor()
    test = "人工智能技术正在改变世界，深度学习是其中的重要分支。"
    print(p.segment(test))
