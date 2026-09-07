"""SQLite 状态库（PLAN §3 schema 的落地）。

写策略：`rebuild()` 以「全书抽取结果」为唯一事实源，单事务全量重建各表——
同输入必得同状态（抽取往返可回放、可 diff），增量追章优化留待后续里程碑。
本模块不依赖 rules 层（层界：store 在下，rules 在上读 BookView）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from ..extract.schemas import ChapterExtraction, StoryTime
from .resolver import EntityResolver, ResolvedEntity

__all__ = ["StateDB", "Violation", "ChangeRec", "EventRec", "BookView", "build_book_view"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    attrs TEXT NOT NULL DEFAULT '{}',
    first_chapter INTEGER NOT NULL DEFAULT 0,
    last_chapter INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS state_changes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT '变更',
    attr TEXT NOT NULL,
    old TEXT NOT NULL DEFAULT '',
    new TEXT NOT NULL,
    quote TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_state_entity ON state_changes(entity_id, chapter);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    kind TEXT NOT NULL,
    entity_ids TEXT NOT NULL DEFAULT '[]',
    payload TEXT NOT NULL DEFAULT '{}',
    quote TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS relations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL,
    object_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT '建立',
    since_chapter INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS timeline(
    chapter INTEGER PRIMARY KEY,
    time_start TEXT NOT NULL DEFAULT '',
    time_end TEXT NOT NULL DEFAULT '',
    markers TEXT NOT NULL DEFAULT '[]',
    day_offset INTEGER
);
CREATE TABLE IF NOT EXISTS chapter_extractions(
    chapter INTEGER PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS violations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT NOT NULL,
    chapter INTEGER NOT NULL DEFAULT 0,
    entity_ids TEXT NOT NULL DEFAULT '[]',
    evidence_quote TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Violation:
    """一条冲突。rule_id/severity 可先空、由规则引擎绑定时回填。"""

    rule_id: str
    message: str
    chapter: int = 0
    entity_ids: list[int] = field(default_factory=list)
    evidence_quote: str = ""
    severity: str = "info"


@dataclass(frozen=True)
class ChangeRec:
    chapter: int
    entity_id: int
    kind: str
    attr: str
    old: str
    new: str
    quote: str


@dataclass(frozen=True)
class EventRec:
    chapter: int
    kind: str
    entity_ids: tuple[int, ...]
    quote: str
    location: str = ""


@dataclass(frozen=True)
class BookView:
    """规则引擎的只读输入：全部来自已验证的抽取数据。判定在此之上纯程序化（PLAN §2 地基）。"""

    entities: dict[int, ResolvedEntity]
    changes: list[ChangeRec]
    events: list[EventRec]
    appearances: dict[int, set[int]]  # entity_id -> 出场章集合
    timeline: dict[int, StoryTime]
    alias_collisions: dict[str, set[int]]


class StateDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.parent != Path(""):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- 生命周期 -----------------------------------------------------------

    def __enter__(self) -> "StateDB":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.conn.close()

    def close(self) -> None:
        self.conn.close()

    # -- 写入 ---------------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def rebuild(self, extractions: Sequence[ChapterExtraction]) -> EntityResolver:
        """以全书抽取结果为事实源，单事务重建实体/变更/事件/关系/时间线/原文。"""
        resolver = EntityResolver()
        for extraction in extractions:
            resolver.ingest(extraction)

        conn = self.conn
        with conn:
            for table in ("entities", "state_changes", "events", "relations", "timeline",
                          "chapter_extractions"):
                conn.execute(f"DELETE FROM {table}")
            # 第一遍：补齐变更/事件/关系引用的实体（含「未知」兜底），保证实体表完整
            for extraction in extractions:
                for change in extraction.state_changes:
                    resolver.ensure(change.entity, extraction.chapter)
                for event in extraction.events:
                    for name in event.entities:
                        resolver.ensure(name, extraction.chapter)
                for relation in extraction.relations:
                    resolver.ensure(relation.subject, extraction.chapter)
                    resolver.ensure(relation.object, extraction.chapter)
            for entity in resolver.entities.values():
                conn.execute(
                    "INSERT INTO entities(id, name, type, aliases, attrs, first_chapter, last_chapter) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (
                        entity.entity_id,
                        entity.name,
                        entity.type,
                        json.dumps(sorted(entity.aliases), ensure_ascii=False),
                        json.dumps(entity.attrs, ensure_ascii=False),
                        entity.first_chapter,
                        entity.last_chapter,
                    ),
                )
            for extraction in extractions:
                chapter = extraction.chapter
                for change in extraction.state_changes:
                    entity = resolver.ensure(change.entity, chapter)
                    conn.execute(
                        "INSERT INTO state_changes(chapter, entity_id, kind, attr, old, new, quote) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (chapter, entity.entity_id, change.kind, change.attr,
                         change.old, change.new, change.quote),
                    )
                for event in extraction.events:
                    entity_ids = [resolver.ensure(name, chapter).entity_id for name in event.entities]
                    conn.execute(
                        "INSERT INTO events(chapter, kind, entity_ids, payload, quote, location) "
                        "VALUES(?, ?, ?, ?, ?, ?)",
                        (chapter, event.kind,
                         json.dumps(entity_ids),
                         json.dumps(event.payload, ensure_ascii=False),
                         event.quote, event.location),
                    )
                for relation in extraction.relations:
                    subject = resolver.ensure(relation.subject, chapter)
                    obj = resolver.ensure(relation.object, chapter)
                    conn.execute(
                        "INSERT INTO relations(subject_id, object_id, kind, state, since_chapter) "
                        "VALUES(?, ?, ?, ?, ?)",
                        (subject.entity_id, obj.entity_id, relation.kind,
                         relation.state, chapter),
                    )
                st = extraction.story_time
                conn.execute(
                    "INSERT OR REPLACE INTO timeline(chapter, time_start, time_end, markers, day_offset) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (chapter, st.start, st.end,
                     json.dumps(st.markers, ensure_ascii=False), st.day_offset),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO chapter_extractions(chapter, title, raw) VALUES(?, ?, ?)",
                    (chapter, extraction.title, extraction.model_dump_json()),
                )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('alias_collisions', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (
                    json.dumps(
                        {alias: sorted(ids) for alias, ids in sorted(resolver.collisions.items())},
                        ensure_ascii=False,
                    ),
                ),
            )
        return resolver

    def replace_violations(self, violations: Iterable[Violation]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM violations")
            for violation in violations:
                self.conn.execute(
                    "INSERT INTO violations(rule_id, chapter, entity_ids, evidence_quote, severity, message) "
                    "VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        violation.rule_id,
                        violation.chapter,
                        json.dumps(violation.entity_ids),
                        violation.evidence_quote,
                        violation.severity,
                        violation.message,
                    ),
                )

    # -- 查询 ---------------------------------------------------------------

    def list_entities(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM entities ORDER BY id").fetchall()

    def entity_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM entities").fetchone()["n"])

    def state_changes(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM state_changes ORDER BY chapter, id"
        ).fetchall()

    def events(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM events ORDER BY chapter, id").fetchall()

    def relations(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM relations ORDER BY since_chapter, id").fetchall()

    def timeline(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM timeline ORDER BY chapter").fetchall()

    def extractions(self) -> list[ChapterExtraction]:
        """按章序回放全部抽取结果（M0 验收：抽取→入库→回放往返）。"""
        rows = self.conn.execute(
            "SELECT raw FROM chapter_extractions ORDER BY chapter"
        ).fetchall()
        return [ChapterExtraction.model_validate_json(row["raw"]) for row in rows]

    def get_extraction(self, chapter: int) -> ChapterExtraction | None:
        row = self.conn.execute(
            "SELECT raw FROM chapter_extractions WHERE chapter=?", (chapter,)
        ).fetchone()
        return ChapterExtraction.model_validate_json(row["raw"]) if row else None

    def violations(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM violations ORDER BY "
            "CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, "
            "chapter, id"
        ).fetchall()


def build_book_view(db: StateDB) -> BookView:
    """从状态库组装规则引擎输入。出场章 = 实体登记章 ∪ 状态变更章 ∪ 事件涉及章。"""
    entities: dict[int, ResolvedEntity] = {}
    alias_to_id: dict[str, int] = {}
    for row in db.list_entities():
        aliases = set(json.loads(row["aliases"]))
        entity = ResolvedEntity(
            entity_id=row["id"], name=row["name"], type=row["type"],
            aliases=aliases, attrs=json.loads(row["attrs"]),
            first_chapter=row["first_chapter"], last_chapter=row["last_chapter"],
        )
        entities[entity.entity_id] = entity
        for key in (entity.name, *aliases):
            alias_to_id.setdefault(key, entity.entity_id)

    changes = [
        ChangeRec(
            chapter=row["chapter"], entity_id=row["entity_id"], kind=row["kind"],
            attr=row["attr"], old=row["old"], new=row["new"], quote=row["quote"],
        )
        for row in db.state_changes()
    ]
    events = [
        EventRec(
            chapter=row["chapter"], kind=row["kind"],
            entity_ids=tuple(json.loads(row["entity_ids"])), quote=row["quote"],
            location=row["location"],
        )
        for row in db.events()
    ]

    appearances: dict[int, set[int]] = {}

    def touch(entity_id: int, chapter: int) -> None:
        appearances.setdefault(entity_id, set()).add(chapter)

    for extraction in db.extractions():
        for mention in extraction.entities:
            entity_id = alias_to_id.get(mention.name)
            if entity_id is not None:
                touch(entity_id, extraction.chapter)
    for change in changes:
        touch(change.entity_id, change.chapter)
    for event in events:
        for entity_id in event.entity_ids:
            touch(entity_id, event.chapter)

    timeline = {
        row["chapter"]: StoryTime(
            start=row["time_start"], end=row["time_end"],
            markers=json.loads(row["markers"]), day_offset=row["day_offset"],
        )
        for row in db.timeline()
    }
    collisions = {
        alias: set(ids)
        for alias, ids in json.loads(db.get_meta("alias_collisions", "{}")).items()
    }
    return BookView(
        entities=entities, changes=changes, events=events,
        appearances=appearances, timeline=timeline, alias_collisions=collisions,
    )
