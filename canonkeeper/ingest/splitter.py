"""切章：识别中文网文章节标题；无标题时退化为定长分块，保证数据不丢。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Chapter", "load_book_text", "split_chapters"]

# 行首章节标题：第X章/回/节（数字或中文数字），后接可选标题
_HEADING_RE = re.compile(
    r"^\s*(第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章回节])\s*[:：、.\-— ]?\s*(.*)$"
)


@dataclass(frozen=True)
class Chapter:
    """一章。number 为全书顺序号（从 1 起；标题前的前言为 0）。"""

    number: int
    title: str
    text: str


def load_book_text(path: str | Path) -> str:
    """读取书稿：单 txt 文件，或目录下（按文件名排序）全部 txt 拼接。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"书稿路径不存在: {p}")
    if p.is_dir():
        txt_files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".txt")
        if not txt_files:
            raise FileNotFoundError(f"目录 {p} 下没有 .txt 文件")
        return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in txt_files)
    return p.read_text(encoding="utf-8", errors="replace")


def split_chapters(text: str, *, fallback_chunk_chars: int = 3000) -> list[Chapter]:
    """按章节标题切分；一个标题都没有时按定长切块（title 用「块N」占位）。"""
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            label, title = match.group(1), match.group(2).strip()
            headings.append((lineno, f"{label} {title}".strip()))

    if len(headings) < 1:
        return _chunk_fallback(text, fallback_chunk_chars)

    chapters: list[Chapter] = []
    head_body = "\n".join(lines[: headings[0][0]]).strip()
    if head_body:
        chapters.append(Chapter(number=0, title="前言", text=head_body))
    for idx, (start, title) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        chapters.append(Chapter(number=idx + 1, title=title, text=body))
    return chapters


def _chunk_fallback(text: str, size: int) -> list[Chapter]:
    if not text.strip():
        return []
    size = max(1, size)
    return [
        Chapter(number=i + 1, title=f"块{i + 1}", text=text[i : i + size].strip())
        for i in range(0, len(text), size)
    ]
