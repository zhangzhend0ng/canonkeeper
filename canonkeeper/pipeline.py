"""组合管线：ingest 与 check 的共享实现（CLI 与 MCP server 复用，逻辑单份）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .extract import ChapterExtraction, extract_book
from .ingest import load_book_text, split_chapters
from .providers.base import Provider, get_provider
from .rules.engine import builtin_rules_dir, load_rules, run_rules
from .store.db import StateDB, Violation, build_book_view

__all__ = ["IngestStats", "ingest_book_to_db", "run_check"]


@dataclass(frozen=True)
class IngestStats:
    chapters: int
    entities: int
    db: str
    extracted: int = 0  # 本次实际抽取的章数（增量模式 < chapters）
    reused: int = 0     # 复用库中已有抽取的章数


def _provider_models(provider: Provider) -> dict[str, str]:
    model_names = getattr(provider, "model_names", None)
    if callable(model_names):
        return dict(model_names())
    return {"fast": provider.name, "flagship": provider.name}


def ingest_book_to_db(
    book: str | Path,
    db: str | Path,
    provider_name: str = "deepseek",
    *,
    limit: int = 0,
    samples: int = 1,
    incremental: bool = False,
    skip_errors: bool = False,
    progress: Callable[[int, int, ChapterExtraction | None], None] | None = None,
) -> IngestStats:
    """切章 → 逐章抽取 → 入库（含元信息标注）。

    incremental=True（事件溯源化增量追章）：已有抽取（chapter_extractions.raw）即事件日志，
    只抽取库中缺失的章，投影随全书一次性重建——追章成本只花在新章上。
    按章号对齐，适用于同一书稿文件追加新章后的再入库。
    """
    provider = get_provider(provider_name)
    chapters = split_chapters(load_book_text(book))
    if not chapters:
        raise ValueError(f"未切出任何章节（书稿为空或路径不对）: {book}")
    if limit > 0:
        chapters = chapters[:limit]

    existing: dict[int, ChapterExtraction] = {}
    if incremental and Path(db).exists():
        with StateDB(db) as state:
            existing = {e.chapter: e for e in state.extractions()}

    todo = [c for c in chapters if c.number not in existing]
    fresh = extract_book(
        provider, todo, samples=samples, skip_errors=skip_errors, progress=progress
    )
    by_chapter = {e.chapter: e for e in fresh}
    extractions = [existing.get(c.number) or by_chapter[c.number] for c in chapters]

    with StateDB(db) as state:
        resolver = state.rebuild(extractions)
        models = _provider_models(provider)
        state.set_meta("book_title", Path(book).name)
        state.set_meta("provider", provider_name)
        state.set_meta("model_fast", models.get("fast", "?"))
        state.set_meta("model_flagship", models.get("flagship", "?"))
        state.set_meta("ingested_at", datetime.now().astimezone().isoformat(timespec="seconds"))
        return IngestStats(
            chapters=len(extractions),
            entities=len(resolver.entities),
            db=str(db),
            extracted=len(fresh),
            reused=len(extractions) - len(fresh),
        )


def run_check(db: str | Path, extra_rules: Sequence[str | Path] = ()) -> tuple[int, list[Violation]]:
    """内置规则 + 额外规则 YAML，纯程序化判定；冲突写回状态库并返回。"""
    rule_paths = sorted(builtin_rules_dir().glob("*.yaml"))
    rule_paths += [Path(p) for p in extra_rules]
    rules = load_rules(rule_paths)
    with StateDB(db) as state:
        violations = run_rules(rules, build_book_view(state))
        state.replace_violations(violations)
        return len(rules), violations
