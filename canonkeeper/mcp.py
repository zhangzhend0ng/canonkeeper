"""MCP server：把 canonkeeper 验证能力暴露给 MCP 宿主（deepseek-harness 等）。

定位（PLAN M3 生成回路）：agent 写前用 query_entity 查设定，写后用
check_consistency 跑硬验证器（纯程序化判定），get_report/replay_chapter
供人工与 agent 复核；ingest_book 负责新章节入库。

- 传输：stdio（dsh 经 @deepseek-ai/dsh-mcp-client 以 `mcp__canonkeeper__<tool>` 挂载，
  见仓库 plugin/ 目录的 bundle）。
- 工具返回 JSON 文本（get_report 返回 markdown）。
- 依赖可选 extra：pip install "canonkeeper[mcp]"。本模块顶层不 import mcp，
  未安装时 CLI/库功能不受影响。
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from .pipeline import ingest_book_to_db, run_check
from .store.db import StateDB, build_book_view

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = ["create_server", "main"]


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# -- 工具实现（纯函数，便于脱离 MCP 直接单测） --------------------------------


def ingest_book(
    book_path: str,
    db_path: str,
    provider: str = "deepseek",
    limit: int = 0,
    skip_errors: bool = False,
) -> str:
    """切章并逐章 LLM 抽取后入库（写后验证的第一步）。

    Args:
        book_path: 书稿路径（txt 文件或含 txt 的目录）。
        db_path: 状态库 SQLite 路径（不存在则创建）。
        provider: deepseek / glm / mock（mock 无需 API key，返回固定样例抽取）。
        limit: 只处理前 N 章（0=全部）。
        skip_errors: 单章抽取失败时占位跳过而非中断。
    """
    stats = ingest_book_to_db(
        book_path, db_path, provider, limit=limit, skip_errors=skip_errors
    )
    return _json(
        {"chapters": stats.chapters, "entities": stats.entities, "db": stats.db}
    )


def check_consistency(db_path: str, extra_rules: list[str] | None = None) -> str:
    """对状态库运行规则引擎（纯程序化判定，不调 LLM），返回冲突列表并写回状态库。

    Args:
        db_path: 状态库路径（需已 ingest）。
        extra_rules: 额外规则 YAML 路径列表（内置 8 条之外的自定义规则）。
    """
    rule_count, violations = run_check(db_path, extra_rules or [])
    return _json(
        {
            "rule_count": rule_count,
            "total": len(violations),
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "chapter": v.chapter,
                    "entity_ids": v.entity_ids,
                    "message": v.message,
                    "quote": v.evidence_quote,
                }
                for v in violations
            ],
        }
    )


def query_entity(db_path: str, name: str) -> str:
    """按名字或别名查实体：当前属性、状态变更史、关系、出场章（写前查设定用）。

    Args:
        db_path: 状态库路径。
        name: 实体名或别名，如「林昼」「林师弟」。
    """
    with StateDB(db_path) as db:
        target = None
        for row in db.list_entities():
            if row["name"] == name or name in json.loads(row["aliases"]):
                target = row
                break
        if target is None:
            return _json(
                {
                    "error": f"实体「{name}」不在库中",
                    "known_entities": [r["name"] for r in db.list_entities()],
                }
            )
        entity_id = target["id"]
        view = build_book_view(db)
        name_by_id = {eid: ent.name for eid, ent in view.entities.items()}
        changes = [
            {
                "chapter": c.chapter,
                "kind": c.kind,
                "attr": c.attr,
                "old": c.old,
                "new": c.new,
                "quote": c.quote,
            }
            for c in view.changes
            if c.entity_id == entity_id
        ]
        relations = []
        for row in db.relations():
            if entity_id not in (row["subject_id"], row["object_id"]):
                continue
            other = row["object_id"] if row["subject_id"] == entity_id else row["subject_id"]
            relations.append(
                {
                    "kind": row["kind"],
                    "state": row["state"],
                    "since_chapter": row["since_chapter"],
                    "other": name_by_id.get(other, f"#{other}"),
                    "direction": "out" if row["subject_id"] == entity_id else "in",
                }
            )
        return _json(
            {
                "name": target["name"],
                "type": target["type"],
                "aliases": json.loads(target["aliases"]),
                "attrs": json.loads(target["attrs"]),
                "first_chapter": target["first_chapter"],
                "last_chapter": target["last_chapter"],
                "appearances": sorted(view.appearances.get(entity_id, ())),
                "state_changes": changes,
                "relations": relations,
            }
        )


def replay_chapter(db_path: str, chapter: int) -> str:
    """回放某章的抽取结果 JSON（核对抽取往返、定位误报来源）。

    Args:
        db_path: 状态库路径。
        chapter: 章号。
    """
    with StateDB(db_path) as db:
        extraction = db.get_extraction(chapter)
    if extraction is None:
        return _json({"error": f"库中不存在第{chapter}章"})
    return _json(extraction.model_dump())


def get_report(db_path: str) -> str:
    """渲染 markdown 冲突报告全文（含规则覆盖清单与证据引文）。"""
    from .report.render import render_report
    from .rules.engine import load_builtin_rules

    rules = load_builtin_rules()
    with StateDB(db_path) as db:
        return render_report(db, rules)


def create_server() -> "FastMCP":
    """组装 FastMCP server（需要 mcp extra）。"""
    from mcp.server.fastmcp import FastMCP

    server: FastMCP = FastMCP("canonkeeper")
    for tool in (ingest_book, check_consistency, query_entity, replay_chapter, get_report):
        server.tool()(tool)
    return server


def main() -> int:
    """console script 入口（canonkeeper-mcp）：stdio 传输，阻塞运行。"""
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
    except ImportError as exc:
        print(
            f"错误: MCP 支持未安装（{exc}）。请安装: pip install 'canonkeeper[mcp]'",
            file=sys.stderr,
        )
        return 1
    create_server().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
