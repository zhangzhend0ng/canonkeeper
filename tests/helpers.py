"""测试数据构造辅助：纯函数，无 fixture、无副作用。"""

from __future__ import annotations

from typing import Mapping, Sequence

from canonkeeper.extract.schemas import (
    ChapterExtraction,
    EntityMention,
    Event,
    Relation,
    StateChange,
    StoryTime,
)
from canonkeeper.ingest import Chapter
from canonkeeper.store.db import BookView
from canonkeeper.store.resolver import ResolvedEntity


def entity(
    name: str,
    *,
    entity_type: str = "人物",
    aliases: Sequence[str] = (),
    attrs: Mapping[str, str] | None = None,
) -> EntityMention:
    return EntityMention(name=name, type=entity_type, aliases=list(aliases), attrs=dict(attrs or {}))


def change(
    target: str,
    attr: str,
    new: str,
    *,
    old: str = "",
    kind: str = "变更",
    chapter: int = 0,
    quote: str = "",
) -> StateChange:
    return StateChange(entity=target, attr=attr, new=new, old=old, kind=kind, chapter=chapter, quote=quote)


def event(kind: str, entities: Sequence[str] = (), quote: str = "") -> Event:
    return Event(kind=kind, entities=list(entities), quote=quote)


def relation(subject: str, obj: str, kind: str = "师徒", state: str = "建立") -> Relation:
    return Relation(subject=subject, object=obj, kind=kind, state=state)


def extraction(
    chapter: int,
    *,
    entities: Sequence[EntityMention] = (),
    changes: Sequence[StateChange] = (),
    events: Sequence[Event] = (),
    relations: Sequence[Relation] = (),
    story_time: StoryTime | None = None,
    title: str = "",
) -> ChapterExtraction:
    return ChapterExtraction(
        chapter=chapter,
        title=title,
        entities=list(entities),
        state_changes=list(changes),
        events=list(events),
        relations=list(relations),
        story_time=story_time or StoryTime(),
    )


def chapter(number: int, title: str = "", text: str = "正文") -> Chapter:
    return Chapter(number=number, title=title or f"第{number}章", text=text)


def make_view(
    *,
    entities: Sequence[str] = (),
    entity_types: Mapping[str, str] | None = None,
    changes: Sequence[object] = (),
    events: Sequence[object] = (),
    appearances: Mapping[int, set[int]] | None = None,
    timeline: Mapping[int, StoryTime] | None = None,
    collisions: Mapping[str, set[int]] | None = None,
) -> BookView:
    """按名字顺序分配 entity_id=1..n 的手工 BookView，供谓词单测。"""
    resolved: dict[int, ResolvedEntity] = {}
    types = entity_types or {}
    for index, name in enumerate(entities, start=1):
        resolved[index] = ResolvedEntity(entity_id=index, name=name, type=types.get(name, "人物"))
    return BookView(
        entities=resolved,
        changes=list(changes),  # type: ignore[arg-type]
        events=list(events),  # type: ignore[arg-type]
        appearances=dict(appearances or {}),
        timeline=dict(timeline or {}),
        alias_collisions={k: set(v) for k, v in (collisions or {}).items()},
    )
