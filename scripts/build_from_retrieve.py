"""Build the assignment 3 corpus from assignment 2 local documents."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULT_CORPUS_FILE, INFO_RETRIEVE_DOCUMENTS_FILE
from utils.pipeline import convert_retrieve_documents, corpus_stats


def main() -> None:
    corpus = convert_retrieve_documents(
        source_file=INFO_RETRIEVE_DOCUMENTS_FILE,
        output_file=DEFAULT_CORPUS_FILE,
    )
    stats = corpus_stats(corpus)
    print(f"已生成作业3语料: {DEFAULT_CORPUS_FILE}")
    print(f"文档数量: {stats['total_articles']}")
    print(f"来源数量: {stats['source_count']}")


if __name__ == "__main__":
    main()
