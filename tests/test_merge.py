"""多遍抽取合并器测试（置信度自洽的确定性部分）。"""

from __future__ import annotations

import pytest

from canonkeeper.extract.merge import merge_extractions
from canonkeeper.extract.schemas import (
    ChapterExtraction,
    EntityMention,
    Event,
    StoryTime,
)
from helpers import change, entity


def _ext(chapter: int, **kwargs) -> ChapterExtraction:
    if "changes" in kwargs:  # 语义名 → 契约字段名
        kwargs["state_changes"] = kwargs.pop("changes")
    return ChapterExtraction(chapter=chapter, **kwargs)


def test_single_extraction_returned_as_is() -> None:
    ext = _ext(1, entities=[entity("林昼")])
    assert merge_extractions([ext]) is ext


def test_alias_overlap_entities_merge_with_majority_name() -> None:
    a = _ext(1, entities=[entity("林昼", aliases=["浮窗"], attrs={"剩余次数": "46次"})])
    b = _ext(1, entities=[entity("豆包App", aliases=["浮窗"], attrs={"剩余次数": "46次"})])
    c = _ext(1, entities=[entity("林昼", aliases=["浮窗"])])
    merged = merge_extractions([a, b, c])
    assert len(merged.entities) == 1
    assert merged.entities[0].name == "林昼"  # 2/3 多数票
    assert set(merged.entities[0].aliases) == {"豆包App", "浮窗"}
    assert merged.entities[0].attrs == {"剩余次数": "46次"}


def test_attr_takes_majority_value() -> None:
    a = _ext(1, entities=[entity("林昼", attrs={"金币": "21金币"})])
    b = _ext(1, entities=[entity("林昼", attrs={"金币": "21金币"})])
    c = _ext(1, entities=[entity("林昼", attrs={"金币": "9金币"})])
    merged = merge_extractions([a, b, c])
    assert merged.entities[0].attrs["金币"] == "21金币"


def test_state_changes_dedupe_by_entity_attr_keeping_majority() -> None:
    a = _ext(1, changes=[change("林昼", "金币", "21金币", old="5金币", kind="交易")])
    b = _ext(1, changes=[change("林昼", "金币", "21金币", old="5金币", kind="交易"),
                         change("林昼", "位置", "酒馆", kind="移师")])
    merged = merge_extractions([a, b])
    by_attr = {c.attr: c for c in merged.state_changes}
    assert set(by_attr) == {"金币", "位置"}
    assert by_attr["金币"].new == "21金币"


def test_events_dedupe_identical_keep_distinct() -> None:
    sell = Event(kind="售卖", entities=["林昼"], quote="十七分钟。七瓶卖完。净赚 16 金币。")
    rent = Event(kind="租借", entities=["林昼"], quote="三个金币一晚")
    a = _ext(1, events=[sell])
    b = _ext(1, events=[sell, rent])
    merged = merge_extractions([a, b])
    kinds = sorted(e.kind for e in merged.events)
    assert kinds == ["售卖", "租借"]  # 重复事件去重，不同事件保留


def test_day_offset_majority_and_markers_union() -> None:
    a = _ext(1, story_time=StoryTime(markers=["凌晨四点"], day_offset=3))
    b = _ext(1, story_time=StoryTime(markers=["凌晨四点", "上午十点"], day_offset=3))
    c = _ext(1, story_time=StoryTime(markers=["傍晚"], day_offset=4))
    merged = merge_extractions([a, b, c])
    assert merged.story_time.day_offset == 3  # 多数票
    assert merged.story_time.markers == ["凌晨四点", "上午十点", "傍晚"]  # 并集保序


def test_merge_requires_input() -> None:
    with pytest.raises(ValueError):
        merge_extractions([])


def test_summary_takes_first_non_empty() -> None:
    a = _ext(1, summary="")
    b = _ext(1, summary="摘要B")
    assert merge_extractions([a, b]).summary == "摘要B"
