"""抽取契约测试：LLM 输出是不可信输入，验证行为即契约（input-deserialization N 级）。"""

from __future__ import annotations

import pytest

from dsharness.extract.schemas import ChapterExtraction, EntityMention, Event


def test_minimal_extraction_fills_defaults() -> None:
    ext = ChapterExtraction.model_validate({"chapter": 3})
    assert ext.chapter == 3
    assert ext.entities == []
    assert ext.story_time.day_offset is None


def test_unknown_fields_are_ignored_not_rejected() -> None:
    """兼容端点常附带冗余字段：显式 ignore（见 schemas.py 文档化的取舍）。"""
    ext = ChapterExtraction.model_validate(
        {"chapter": 1, "mood": "紧张", "entities": [{"name": "林昼", "power_level": 99}]}
    )
    assert ext.entities[0].name == "林昼"
    assert set(ext.entities[0].model_fields_set) == {"name"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("剑修人物", "人物"), ("神秘物品", "物品"), ("完全乱写的值", "人物")],
    ids=["person_contains", "item_contains", "garbage_defaults"],
)
def test_entity_type_normalized_to_known_set(raw: str, expected: str) -> None:
    assert EntityMention(name="某物", type=raw).type == expected


def test_payload_values_flattened_to_str() -> None:
    e = Event(kind="交易", payload={"金额": 100, "地点": "坊市"})
    assert e.payload == {"金额": "100", "地点": "坊市"}


def test_empty_name_rejected() -> None:
    with pytest.raises(Exception, match="name"):
        EntityMention(name="  ")
