"""切章行为测试。"""

from __future__ import annotations

import pytest

from dsharness.ingest import load_book_text, split_chapters


def test_splits_by_chapter_headings() -> None:
    text = "第一章 起点\n林昼睁眼。\n第二章 相遇\n他下山了。"
    chapters = split_chapters(text)
    assert [c.number for c in chapters] == [1, 2]
    assert [c.title for c in chapters] == ["第一章 起点", "第二章 相遇"]
    assert chapters[0].text == "林昼睁眼。"
    assert chapters[1].text == "他下山了。"


def test_text_before_first_heading_becomes_preface() -> None:
    chapters = split_chapters("楔子：天地初开。\n第一章 起点\n正文")
    assert (chapters[0].number, chapters[0].title) == (0, "前言")
    assert chapters[0].text == "楔子：天地初开。"
    assert chapters[1].number == 1


def test_single_heading_splits_structured_with_preface() -> None:
    """只有一个章节标题时仍走结构化切分，标题前内容归前言。"""
    chapters = split_chapters("第一章 独章\n正文若干")
    assert [(c.number, c.title) for c in chapters] == [(1, "第一章 独章")]


@pytest.mark.parametrize(
    "text",
    ["没有任何章节标题的一段很长的文本。" * 100],
    ids=["no_headings"],
)
def test_falls_back_to_chunking_with_no_headings(text: str) -> None:
    chapters = split_chapters(text, fallback_chunk_chars=100)
    assert len(chapters) >= 2
    assert all(c.title.startswith("块") for c in chapters)


def test_load_book_text_from_dir_joints_sorted_txt_files(tmp_path) -> None:
    (tmp_path / "b.txt").write_text("乙", encoding="utf-8")
    (tmp_path / "a.txt").write_text("甲", encoding="utf-8")
    assert load_book_text(tmp_path) == "甲\n乙"


def test_load_book_text_missing_path_raises() -> None:
    with pytest.raises(FileNotFoundError, match="不存在"):
        load_book_text("Z:/definitely/not/here.txt")
