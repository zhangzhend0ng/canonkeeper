"""CLI 测试：mock provider 走通 ingest→check→report 全链路（离线冒烟等价物）。"""

from __future__ import annotations

import json
from pathlib import Path

from canonkeeper.cli import main

BOOK_TEXT = (
    "第一章 出发\n林昼拜别青云宗，踏上北去的长路。\n"
    "第二章 破境\n当夜，林昼丹田一热，竟破了境。\n"
    "第三章 归来\n三日后，林昼回到青云宗。"
)


def _write_book(tmp_path: Path) -> Path:
    book = tmp_path / "book.txt"
    book.write_text(BOOK_TEXT, encoding="utf-8")
    return book


def test_full_pipeline_ingest_check_report_with_mock(tmp_path: Path) -> None:
    book = _write_book(tmp_path)
    db = tmp_path / "state.db"
    assert main(["ingest", str(book), "--db", str(db), "--provider", "mock"]) == 0
    assert db.exists()
    assert main(["check", str(db)]) == 0
    report = tmp_path / "report.md"
    assert main(["report", str(db), "--out", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "# canonkeeper 冲突报告" in text
    assert "《book.txt》" in text  # 元信息标注书名与模型版本


def test_limit_ingests_only_first_n_chapters(tmp_path: Path) -> None:
    book = _write_book(tmp_path)
    db = tmp_path / "state.db"
    assert main(["ingest", str(book), "--db", str(db), "--provider", "mock", "--limit", "1"]) == 0
    from canonkeeper.store.db import StateDB

    with StateDB(db) as state:
        assert len(state.extractions()) == 1


def test_replay_returns_chapter_json(tmp_path: Path, capsys) -> None:
    book = _write_book(tmp_path)
    db = tmp_path / "state.db"
    main(["ingest", str(book), "--db", str(db), "--provider", "mock"])
    capsys.readouterr()  # 清掉 ingest 的 stdout，只留 replay 输出
    assert main(["replay", str(db), "2"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["chapter"] == 2


def test_replay_missing_chapter_returns_error(tmp_path: Path) -> None:
    book = _write_book(tmp_path)
    db = tmp_path / "state.db"
    main(["ingest", str(book), "--db", str(db), "--provider", "mock"])
    assert main(["replay", str(db), "99"]) == 1


def test_ingest_missing_book_fails_cleanly(tmp_path: Path, capsys) -> None:
    rc = main(
        [
            "ingest", str(tmp_path / "nope.txt"),
            "--db", str(tmp_path / "x.db"),
            "--provider", "mock",
        ]
    )
    assert rc == 1
    assert "错误" in capsys.readouterr().err


def test_rules_command_lists_builtin_rules(capsys) -> None:
    assert main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "CHAR_001" in out and "TIME_006" in out


def test_stability_report_with_mock(tmp_path: Path) -> None:
    book = _write_book(tmp_path)
    out = tmp_path / "stability.md"
    assert main(
        ["stability", str(book), "--provider", "mock", "--runs", "2", "--out", str(out)]
    ) == 0
    text = out.read_text(encoding="utf-8")
    assert "Jaccard" in text
    assert "1.000" in text  # mock 确定性输出 → 完全一致
