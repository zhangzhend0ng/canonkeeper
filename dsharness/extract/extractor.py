"""抽取管线：章节文本 → provider(FAST 档) → 验证后的 ChapterExtraction。

可靠性策略（PLAN §8「抽取错误率=检测器上限」）：
- 解析/验证失败时，把错误回喂给模型重试一次（错误反馈重试）；
- 重试仍失败 → ExtractionError（附章号与原始返回片段），由调用方决定 fail fast
  还是跳过（skip_errors，非关键路径降级不中断整书，error-handling #7）。
所有错误消息只含正文片段，不含密钥。
"""

from __future__ import annotations

import json
import re
from typing import Callable, Sequence

from pydantic import ValidationError

from ..ingest.splitter import Chapter
from ..providers.base import Provider, Tier
from .prompt import build_messages
from .schemas import ChapterExtraction

__all__ = ["ExtractionError", "strip_code_fence", "parse_extraction", "extract_chapter", "extract_book"]

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class ExtractionError(RuntimeError):
    """抽取失败（非法 JSON / schema 验证不过 / 重试耗尽）。"""


def strip_code_fence(text: str) -> str:
    """宽容处理兼容端点可能附带的 markdown 围栏。"""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def parse_extraction(raw: str, chapter_number: int) -> ChapterExtraction:
    """原始返回 → 验证后的 ChapterExtraction。解析与验证错误都翻译为 ExtractionError，
    消息附章号与原文片段（≤200 字），便于人工排查。"""
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"第{chapter_number}章: 返回不是合法 JSON ({exc})，原文前200字={raw[:200]!r}"
        ) from exc
    if not isinstance(data, dict):
        raise ExtractionError(f"第{chapter_number}章: 返回不是 JSON 对象（type={type(data).__name__}）")
    try:
        extraction = ChapterExtraction.model_validate(data)
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:3]
        )
        raise ExtractionError(f"第{chapter_number}章: schema 验证失败 — {summary}") from exc
    extraction.chapter = chapter_number  # 管线权威，覆盖模型自报
    return extraction


def extract_chapter(
    provider: Provider, chapter: Chapter, *, tier: Tier = Tier.FAST
) -> ChapterExtraction:
    """单章抽取：一次调用 + 一次错误反馈重试。"""
    messages = build_messages(chapter)
    raw = provider.chat(messages, tier=tier, json_mode=True)
    try:
        return parse_extraction(raw, chapter.number)
    except ExtractionError as first_error:
        retry_messages = [
            *messages,
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": f"上面的输出不合规（{first_error}）。请重新只输出一个符合给定 JSON Schema 的对象，不要任何其他文本。",
            },
        ]
        raw_retry = provider.chat(retry_messages, tier=tier, json_mode=True)
        try:
            return parse_extraction(raw_retry, chapter.number)
        except ExtractionError as retry_error:
                raise ExtractionError(
                    f"第{chapter.number}章: 抽取重试后仍失败 — {retry_error}"
                ) from first_error


def extract_book(
    provider: Provider,
    chapters: Sequence[Chapter],
    *,
    tier: Tier = Tier.FAST,
    skip_errors: bool = False,
    progress: Callable[[int, int, ChapterExtraction | None], None] | None = None,
) -> list[ChapterExtraction]:
    """逐章抽取。skip_errors=True 时失败章记为占位（summary 标注抽取失败）并继续；
    否则首个失败立即抛出。progress(now, total, extraction|None) 在每章完成后回调。"""
    results: list[ChapterExtraction] = []
    for chapter in chapters:
        extraction: ChapterExtraction | None
        try:
            extraction = extract_chapter(provider, chapter, tier=tier)
        except ExtractionError:
            if not skip_errors:
                raise
            extraction = ChapterExtraction(
                chapter=chapter.number,
                title=chapter.title,
                summary=f"[抽取失败，占位回填] {chapter.title}",
            )
        results.append(extraction)
        if progress is not None:
            progress(chapter.number, len(chapters), extraction)
    return results
