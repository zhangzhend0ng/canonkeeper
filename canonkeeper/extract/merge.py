"""多遍抽取的确定性合并器（置信度加权自洽，arXiv 2502.06233 的落地）。

合并策略面向查全（union with votes）：
- entities：按 名字∪别名 的交集做并查集分组；名字/类型取多数票，attrs 按键取最高票值；
- state_changes：按 (实体, 属性) 分组取最高票（票数并列取先出现的遍）；
- events：按 (kind, 实体集, 引文前缀) 去重合并；
- relations / story_time.markers：并集；day_offset 取非空多数票；
- 合并结果是纯 ChapterExtraction（不携带票数字段，状态库契约不变）。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Sequence

from .schemas import ChapterExtraction, EntityMention, Event, Relation, StateChange, StoryTime

__all__ = ["merge_extractions"]


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _majority(options: Sequence[str]) -> str:
    """多数票；并列取最先出现的。"""
    counter = Counter(options)
    best = max(counter.values())
    for option in options:
        if counter[option] == best:
            return option
    return options[0] if options else ""


def _merge_entities(samples: Sequence[ChapterExtraction]) -> list[EntityMention]:
    """跨样本按 名字/别名 交集分组（并查集），组内多数票定名。"""
    keys: list[set[str]] = []
    items: list[EntityMention] = []
    for sample in samples:
        for mention in sample.entities:
            key_set = {_norm_key(mention.name), *(_norm_key(a) for a in mention.aliases)}
            merged_into: int | None = None
            for index, existing in enumerate(keys):
                if existing & key_set:
                    merged_into = index
                    break
            if merged_into is None:
                keys.append(key_set)
                items.append(mention)
            else:
                keys[merged_into] |= key_set
    groups: dict[int, list[EntityMention]] = defaultdict(list)
    for sample in samples:
        for mention in sample.entities:
            key_set = {_norm_key(mention.name), *(_norm_key(a) for a in mention.aliases)}
            for index, existing in enumerate(keys):
                if existing & key_set:
                    groups[index].append(mention)
                    break

    merged: list[EntityMention] = []
    for index in sorted(groups):
        group = groups[index]
        name = _majority([m.name for m in group])
        aliases: list[str] = []
        for mention in group:
            for alias in [mention.name, *mention.aliases]:
                if alias not in aliases:
                    aliases.append(alias)
        aliases = [a for a in aliases if a != name]
        attrs: dict[str, str] = {}
        attr_votes: dict[str, list[str]] = defaultdict(list)
        for mention in group:
            for key, value in mention.attrs.items():
                attr_votes[key].append(value)
        for key, values in attr_votes.items():
            attrs[key] = _majority(values)
        merged.append(EntityMention(name=name, type=_majority([m.type for m in group]),
                                    aliases=aliases, attrs=attrs))
    return merged


def _merge_state_changes(samples: Sequence[ChapterExtraction]) -> list[StateChange]:
    groups: dict[tuple[str, str], list[StateChange]] = defaultdict(list)
    for sample in samples:
        for change in sample.state_changes:
            groups[(_norm_key(change.entity), _norm_key(change.attr))].append(change)
    merged = []
    for group in groups.values():
        best = max(group, key=lambda c: (
            sum(1 for o in group if (o.kind, o.old, o.new) == (c.kind, c.old, c.new)),
            -group.index(c),
        ))
        merged.append(best)
    merged.sort(key=lambda c: (c.entity, c.attr))
    return merged


def _merge_events(samples: Sequence[ChapterExtraction]) -> list[Event]:
    seen: dict[tuple[str, str, str], Event] = {}
    votes: Counter = Counter()
    for sample in samples:
        local_keys = set()
        for event in sample.events:
            key = (event.kind, ",".join(sorted(event.entities)), _norm_key(event.quote)[:24])
            local_keys.add(key)
            votes[key] += 1
            seen.setdefault(key, event)
    ordered = sorted(seen, key=lambda k: -votes[k])
    return [seen[k] for k in ordered]


def _merge_relations(samples: Sequence[ChapterExtraction]) -> list[Relation]:
    seen: dict[tuple[str, str, str], Relation] = {}
    for sample in samples:
        for relation in sample.relations:
            key = (_norm_key(relation.subject), _norm_key(relation.object), _norm_key(relation.kind))
            existing = seen.get(key)
            if existing is None or existing.state != "建立":
                seen[key] = relation
    return list(seen.values())


def _merge_story_time(samples: Sequence[ChapterExtraction]) -> StoryTime:
    offsets = [s.story_time.day_offset for s in samples if s.story_time.day_offset is not None]
    markers: list[str] = []
    for sample in samples:
        for marker in sample.story_time.markers:
            if marker not in markers:
                markers.append(marker)
    first = samples[0].story_time
    day_offset: int | None = None
    if offsets:
        day_offset = int(_majority([str(o) for o in offsets]))
    return StoryTime(start=first.start, end=first.end, markers=markers, day_offset=day_offset)


def merge_extractions(extractions: Sequence[ChapterExtraction]) -> ChapterExtraction:
    """多遍抽取 → 单一合并结果。单元素输入原样返回（保证等价路径）。"""
    if not extractions:
        raise ValueError("merge_extractions 需要至少一份抽取结果")
    if len(extractions) == 1:
        return extractions[0]
    first = extractions[0]
    return ChapterExtraction(
        chapter=first.chapter,
        title=first.title,
        summary=next((e.summary for e in extractions if e.summary), ""),
        entities=_merge_entities(extractions),
        state_changes=_merge_state_changes(extractions),
        events=_merge_events(extractions),
        relations=_merge_relations(extractions),
        story_time=_merge_story_time(extractions),
    )
