"""MCP server 端到端测试：stdio 子进程 + 官方客户端会话（mock provider，无网络无密钥）。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from dsharness.pipeline import ingest_book_to_db  # noqa: E402

BOOK = "第一章 相识\n林昼在青云宗遇见了苏晚。\n第二章 突破\n林昼突破了炼气三层。"
TOOLS = {"ingest_book", "check_consistency", "query_entity", "replay_chapter", "get_report"}


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", "dsharness.mcp"])


def _make_db(tmp_path: Path) -> Path:
    book = tmp_path / "b.txt"
    book.write_text(BOOK, encoding="utf-8")
    db = tmp_path / "s.db"
    ingest_book_to_db(book, db, "mock")
    return db


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_server_lists_all_tools_and_serves(tmp_path: Path) -> None:
    db = _make_db(tmp_path)

    async def flow() -> None:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert TOOLS <= {tool.name for tool in listed.tools}

                check = await session.call_tool("check_consistency", {"db_path": str(db)})
                payload = json.loads(check.content[0].text)
                assert payload["rule_count"] >= 8
                assert payload["total"] == 0

                who = await session.call_tool(
                    "query_entity", {"db_path": str(db), "name": "林师弟"}
                )
                entity = json.loads(who.content[0].text)
                assert entity["name"] == "林昼"  # 别名归一命中
                assert entity["attrs"]["境界"] == "炼气三层"

                replay = await session.call_tool("replay_chapter", {"db_path": str(db), "chapter": 2})
                assert json.loads(replay.content[0].text)["chapter"] == 2

                report = await session.call_tool("get_report", {"db_path": str(db)})
                assert "dsharness 冲突报告" in report.content[0].text

    _run(flow())


def test_ingest_tool_full_path_via_mock(tmp_path: Path) -> None:
    book = tmp_path / "m.txt"
    book.write_text("第一章 起\n正文。\n", encoding="utf-8")
    db = tmp_path / "m.db"

    async def flow() -> None:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "ingest_book",
                    {"book_path": str(book), "db_path": str(db), "provider": "mock"},
                )
                stats = json.loads(result.content[0].text)
                assert stats["chapters"] == 1
                assert Path(db).exists()

    _run(flow())


def test_query_unknown_entity_returns_error_payload(tmp_path: Path) -> None:
    db = _make_db(tmp_path)

    async def flow() -> None:
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "query_entity", {"db_path": str(db), "name": "不存在的人"}
                )
                payload = json.loads(result.content[0].text)
                assert "error" in payload
                assert "林昼" in payload["known_entities"]

    _run(flow())
