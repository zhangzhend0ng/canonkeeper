"""切章 ingestion：整书 txt → 章节序列（PLAN §2 第一站）。"""

from .splitter import Chapter, load_book_text, split_chapters

__all__ = ["Chapter", "load_book_text", "split_chapters"]
