"""抽取管线测试：解析、重试与错误上下文（全部走 MockProvider，无网络）。"""

from __future__ import annotations

import json

import pytest

from canonkeeper.extract.extractor import (
    ExtractionError,
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


def test_retry_recovers_from_bad_output() -> None:
    provider = MockProvider(["前缀说明 {{bad}}", _good_json(1)])
    extraction = extract_chapter(provider, chapter(1))
    assert extraction.entities[0].name == "林昼"
    assert len(provider.calls) == 2  # 首次 + 错误反馈重试一次
    assert "不合规" in provider.calls[1]["messages"][-1]["content"]


def test_retry_exhausted_raises_with_context() -> None:
    provider = MockProvider(["{{bad}}", "{{still bad}}"])
    with pytest.raises(ExtractionError, match="第2章.*重试后仍失败"):
        extract_chapter(provider, chapter(2))
