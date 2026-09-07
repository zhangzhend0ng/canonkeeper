"""抽取管线测试：G&O 两步调用、重试与错误上下文（全部走 MockProvider，无网络）。"""

from __future__ import annotations

import json

import pytest

from canonkeeper.extract.extractor import (
    ExtractionError,
    PreviousState,
    extract_book,
    extract_chapter,
    parse_extraction,
    strip_code_fence,
)
from canonkeeper.providers.base import MockProvider
from helpers import chapter


def _good_json(n: int = 1) -> str:
    return json.dumps(
        {
            "chapter": n,
            "entities": [{"name": "林昼", "type": "人物"}],
            "state_changes": [
                {"entity": "林昼", "attr": "境界", "new": "炼气三层", "kind": "升级", "quote": "破了。"}
            ],
        },
        ensure_ascii=False,
    )


def test_strip_code_fence_tolerates_markdown_wrapper() -> None:
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_parse_overrides_model_claimed_chapter_number() -> None:
    extraction = parse_extraction(_good_json(99), 1)
    assert extraction.chapter == 1  # 管线权威


def test_parse_invalid_json_raises_with_chapter_context() -> None:
    with pytest.raises(ExtractionError, match="第3章"):
        parse_extraction("这不是 JSON", 3)


def test_parse_non_object_json_raises() -> None:
    with pytest.raises(ExtractionError, match="不是 JSON 对象"):
        parse_extraction("[1, 2]", 1)


def test_two_step_collect_then_organize() -> None:
    """G&O：第一段自由笔记（非 JSON 模式），第二段组织为 JSON（JSON 模式）。"""
    provider = MockProvider(["1. 林昼出场\n2. 境界突破炼气三层", _good_json(1)])
    extraction = extract_chapter(provider, chapter(1))
    assert extraction.entities[0].name == "林昼"
    assert len(provider.calls) == 2
    assert provider.calls[0]["json_mode"] is False  # 收集段：自由文本
    assert provider.calls[1]["json_mode"] is True  # 组织段：JSON 模式
    organize_content = provider.calls[1]["messages"][1]["content"]
    assert "事实笔记" in organize_content
    assert "林昼出场" in organize_content  # 笔记被带入组织段


def test_retry_recovers_from_bad_organize_output() -> None:
    provider = MockProvider(["自由笔记", "前缀说明 {{bad}}", _good_json(1)])
    extraction = extract_chapter(provider, chapter(1))
    assert extraction.entities[0].name == "林昼"
    assert len(provider.calls) == 3  # 收集 + 组织失败 + 错误反馈重试
    assert "不合规" in provider.calls[2]["messages"][-1]["content"]


def test_retry_exhausted_raises_with_context() -> None:
    provider = MockProvider(["自由笔记", "{{bad}}", "{{still bad}}"])
    with pytest.raises(ExtractionError, match="第2章.*重试后仍失败"):
        extract_chapter(provider, chapter(2))


def test_samples_three_merges_union() -> None:
    """自洽采样：三遍不同笔记/JSON → 并集合并（本例三遍各发现一个实体）。"""
    def json_with(name: str) -> str:
        return json.dumps(
            {"chapter": 1, "entities": [{"name": name, "type": "人物"}]}, ensure_ascii=False
        )

    provider = MockProvider(
        ["笔记A", json_with("林昼"), "笔记B", json_with("暗影石"), "笔记C", json_with("铁匠")]
    )
    extraction = extract_chapter(provider, chapter(1), samples=3)
    assert {e.name for e in extraction.entities} == {"林昼", "暗影石", "铁匠"}
    assert len(provider.calls) == 6  # 3 遍 × 2 步


def test_cross_chapter_context_injected() -> None:
    """前情状态注入：day_offset 与实体状态进入收集段与组织段 prompt。"""
    provider = MockProvider(["笔记", _good_json(2)])
    context = PreviousState(
        day_offset=3, entities={"林昼": {"金币": "21金币"}}, tail_events=["七瓶卖完"]
    )
    extract_chapter(provider, chapter(2), context=context)
    collect_content = provider.calls[0]["messages"][1]["content"]
    assert "第 3 天" in collect_content
    assert "金币=21金币" in collect_content
    assert "七瓶卖完" in collect_content
    assert "前情状态" in provider.calls[1]["messages"][1]["content"]


def test_extract_book_carries_state_across_chapters() -> None:
    good1 = json.dumps(
        {
            "chapter": 1,
            "entities": [{"name": "林昼", "type": "人物"}],
            "story_time": {"markers": ["第三天"], "day_offset": 3},
        },
        ensure_ascii=False,
    )
    good2 = json.dumps(
        {
            "chapter": 2,
            "entities": [{"name": "林昼", "attrs": {"金币": "21金币"}}],
            "story_time": {"markers": [], "day_offset": 4},
        },
        ensure_ascii=False,
    )
    provider = MockProvider(["笔记1", good1, "笔记2", good2])
    results = extract_book(provider, [chapter(1), chapter(2)])
    assert [e.chapter for e in results] == [1, 2]
    # 第 2 章的收集 prompt 应包含第 1 章观察到的 day_offset=3
    assert "第 3 天" in provider.calls[2]["messages"][1]["content"]
