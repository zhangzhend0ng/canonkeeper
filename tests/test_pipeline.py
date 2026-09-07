"""共享管线测试（CLI 与 MCP server 的共同实现）。"""

from __future__ import annotations

from pathlib import Path

from canonkeeper.pipeline import ingest_book_to_db, run_check

BOOK = "第一章 相识\n林昼在青云宗遇见了苏晚。\n第二章 突破\n林昼突破了炼气三层。"


def test_ingest_then_check_roundtrip(tmp_path: Path) -> None:
    book = tmp_path / "b.txt"
    book.write_text(BOOK, encoding="utf-8")
    db = tmp_path / "s.db"
    stats = ingest_book_to_db(book, db, "mock")
    assert stats.chapters == 2
    assert stats.entities >= 1

    rule_count, violations = run_check(db)
    assert rule_count >= 8  # 内置规则全部参与
    assert isinstance(violations, list)  # mock 数据确定性 → 期望无冲突
    assert violations == []


def test_run_check_accepts_extra_rules(tmp_path: Path) -> None:
    book = tmp_path / "b.txt"
    book.write_text(BOOK, encoding="utf-8")
    db = tmp_path / "s.db"
    ingest_book_to_db(book, db, "mock")
    rules = tmp_path / "extra.yaml"
    rules.write_text(
        "- rule_id: X_999\n  name: n\n  severity: info\n  predicate: alias_collision\n",
        encoding="utf-8",
    )
    rule_count, _ = run_check(db, [rules])
    assert rule_count >= 9  # 内置 + 1


def test_ingest_empty_book_raises_value_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    try:
        ingest_book_to_db(empty, tmp_path / "x.db", "mock")
    except ValueError as exc:
        assert "未切出任何章节" in str(exc)
    else:
        raise AssertionError("空书稿应抛 ValueError")


def test_incremental_ingest_extracts_only_missing(tmp_path) -> None:
    """事件溯源化增量追章：已有章复用库中抽取，只对缺失章花 API。"""
    book = tmp_path / "b.txt"
    book.write_text(
        "第一章 一\n正文一。\n第二章 二\n正文二。\n第三章 三\n正文三。", encoding="utf-8"
    )
    db = tmp_path / "s.db"
    stats_first = ingest_book_to_db(book, db, "mock", limit=2)
    assert stats_first.extracted == 2 and stats_first.reused == 0

    stats_second = ingest_book_to_db(book, db, "mock", incremental=True)
    assert stats_second.chapters == 3
    assert stats_second.extracted == 1  # 只抽第 3 章
    assert stats_second.reused == 2  # 前两章复用事件日志

    from canonkeeper.store.db import StateDB

    with StateDB(db) as state:
        assert [e.chapter for e in state.extractions()] == [1, 2, 3]
