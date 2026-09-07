"""抽取管线（G&O 两段式 + 可选自洽采样 + 跨章有状态注入）。

- 第一段「收集」：自由笔记，不受格式约束（查全优先，arXiv 2402.13364）；
- 第二段「组织」：把笔记整理为 schema JSON，错误反馈重试一次；
- samples>1 时多遍采样并集合并（置信度自洽，arXiv 2502.06233；采样温度自动抬高保证多样性）；
- extract_book 顺序抽取时逐章累积 PreviousState 并注入下章 prompt（修 day_offset 断链
  与账本 old 回填断裂——GraphRAG/MemGPT 一脉的「抽取时回灌状态」思路的最小实现）。

异常策略：解析/验证失败回喂重试一次，仍失败抛 ExtractionError（附章号），
调用方决定 fail fast 或 skip_errors 降级。错误消息不含密钥。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from pydantic import ValidationError

from ..ingest.splitter import Chapter
from ..providers.base import Provider, Tier
from .merge import merge_extractions
from .prompt import build_collect_messages, build_organize_messages
from .schemas import ChapterExtraction

__all__ = [
    "ExtractionError",
    "PreviousState",
    "strip_code_fence",
    "parse_extraction",
    "extract_chapter",
    "extract_book",
    "merge_extractions",
]

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$")


class ExtractionError(RuntimeError):
    """抽取失败（非法 JSON / schema 验证不过 / 重试耗尽）。"""


def strip_code_fence(text: str) -> str:
    """宽容处理兼容端点可能附带的 markdown 围栏。"""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def parse_extraction(raw: str, chapter_number: int) -> ChapterExtraction:
    """原始返回 → 验证后的 ChapterExtraction。解析与验证错误都翻译为 ExtractionError。"""
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


@dataclass
class PreviousState:
    """跨章状态快照：随 extract_book 顺序抽取逐章累积，注入下一章 prompt。"""

    day_offset: int | None = None
    entities: dict[str, dict[str, str]] = field(default_factory=dict)  # 名字 -> 当前 attrs
    tail_events: list[str] = field(default_factory=list)  # 最近事件引文（≤3 条）

    def note(self) -> str:
        lines: list[str] = []
        if self.day_offset is not None:
            lines.append(f"- 故事时间已推进到约开局后第 {self.day_offset} 天；本章 day_offset 应在此基础上按本章时间标记累计。")
        if self.entities:
            lines.append("- 主要实体当前状态：")
            for name, attrs in list(self.entities.items())[:20]:
                text = ", ".join(f"{k}={v}" for k, v in attrs.items()) or "（无记录属性）"
                lines.append(f"  · {name}：{text}")
        if self.tail_events:
            lines.append("- 最近情节：" + "；".join(self.tail_events))
        return "\n".join(lines)

    def observe(self, extraction: ChapterExtraction) -> None:
        if extraction.story_time.day_offset is not None:
            self.day_offset = extraction.story_time.day_offset
        for mention in extraction.entities:
            self.entities.setdefault(mention.name, {}).update(mention.attrs)
        self.tail_events = [e.quote for e in extraction.events if e.quote][-3:]


def extract_chapter(
    provider: Provider,
    chapter: Chapter,
    *,
    tier: Tier = Tier.FAST,
    temperature: float = 0.0,
    samples: int = 1,
    context: PreviousState | None = None,
    sampling_temperature: float = 0.6,
) -> ChapterExtraction:
    """单章抽取：收集（自由笔记）→ 组织（JSON，错误反馈重试一次）。

    samples=1 保持温度 0 可复现；samples>1 自动用 sampling_temperature 采样并合并
    （并集投票，查全面向）。context 提供前情状态时注入两段 prompt。"""
    if samples < 1:
        raise ValueError("samples 至少为 1")
    context_note = context.note() if context else ""
    effective_temperature = temperature if samples == 1 else max(temperature, sampling_temperature)
    extractions: list[ChapterExtraction] = []
    for _ in range(samples):
        notes = provider.chat(
            build_collect_messages(chapter, context_note), tier=tier, temperature=effective_temperature
        )
        extractions.append(_organize(provider, chapter, notes, context_note, tier, temperature))
    return merge_extractions(extractions)


def _organize(
    provider: Provider,
    chapter: Chapter,
    notes: str,
    context_note: str,
    tier: Tier,
    temperature: float,
) -> ChapterExtraction:
    messages = build_organize_messages(chapter, notes, context_note)
    # 万字章的实体/变更 JSON 可超默认输出上限（DeepSeek 默认 4096 会被截断成非法 JSON）
    raw = provider.chat(messages, tier=tier, json_mode=True, temperature=temperature, max_tokens=8192)
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
        raw_retry = provider.chat(retry_messages, tier=tier, json_mode=True, temperature=temperature)
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
    temperature: float = 0.0,
    samples: int = 1,
    carry_context: bool = True,
    skip_errors: bool = False,
    progress: Callable[[int, int, ChapterExtraction | None], None] | None = None,
) -> list[ChapterExtraction]:
    """顺序逐章抽取；carry_context=True 时前情状态跨章注入（按章序依赖，需按顺序调用）。
    skip_errors=True 时失败章占位回填并继续；否则首个失败立即抛出。"""
    results: list[ChapterExtraction] = []
    state = PreviousState() if carry_context else None
    for chapter in chapters:
        extraction: ChapterExtraction | None
        try:
            extraction = extract_chapter(
                provider, chapter, tier=tier, temperature=temperature, samples=samples, context=state
            )
        except ExtractionError:
            if not skip_errors:
                raise
            extraction = ChapterExtraction(
                chapter=chapter.number,
                title=chapter.title,
                summary=f"[抽取失败，占位回填] {chapter.title}",
            )
        results.append(extraction)
        if state is not None:
            state.observe(extraction)
        if progress is not None:
            progress(chapter.number, len(chapters), extraction)
    return results
