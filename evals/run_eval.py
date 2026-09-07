"""事实级查全评测器：把「手工对账」变成可重复评测（M0/M1 质量门）。

用法（仓库根目录）：
  .venv/Scripts/python evals/run_eval.py \
      --labels evals/labels/bench-v1.yaml \
      --texts <章节文本根目录> \
      --provider deepseek \
      --out evals/results/latest.md

口径与人工对账一致：
- number 只认「结构化字段」（attrs 值 / payload 值 / change old|new / day_offset），
  quote 与 summary 是原文回显，不计入捕获；
- 每条 fact 可 must:false（只报告不计分）；
- signal（伏笔/钩子/承诺）单列，不进主查全分。

版权：第三方文本原文不入仓库，--texts 指向本地目录。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canonkeeper.extract.extractor import PreviousState, extract_chapter  # noqa: E402
from canonkeeper.extract.schemas import ChapterExtraction  # noqa: E402
from canonkeeper.extract.extractor import ExtractionError  # noqa: E402
from canonkeeper.ingest.splitter import Chapter  # noqa: E402
from canonkeeper.providers.base import get_provider  # noqa: E402

SCORED_KINDS = ("number", "entity", "attr", "change", "event", "relation", "time")


def norm(text: str) -> str:
    return re.sub(r"[\s,，]+", "", str(text))


def digits(text: str) -> str:
    return re.sub(r"\D", "", str(text))


def _alias_hit(label: str, aliases: Sequence[str], target: str) -> bool:
    pool = {label, *aliases}
    return any(target == p or p in target or target in p for p in pool if p)


def entity_matches(ext: ChapterExtraction, label_name: str, label_aliases: Sequence[str]) -> list[Any]:
    out = []
    for mention in ext.entities:
        if _alias_hit(label_name, label_aliases, mention.name) or any(
            _alias_hit(label_name, label_aliases, a) for a in mention.aliases
        ):
            out.append(mention)
    return out


def num_hit(label_value: str, alts: Sequence[str], candidates: Sequence[str]) -> bool:
    ln = norm(label_value)
    for candidate in candidates:
        cn = norm(candidate)
        if ln and ln in cn:
            return True
        ld, cd = digits(label_value), digits(candidate)
        if ld and cd and ld == cd:
            return True
    return any(num_hit(a, (), candidates) for a in alts)


def preprocess(text: str) -> str:
    """md 标题转纯文本；去除扫描稿行尾数字+反斜杠伪影（`……"16\\`）。"""
    text = re.sub(r"(?m)^\s*#\s*(第[^\n]*章[^\n]*)$", r"\1", text)
    return re.sub(r"(?m)\s*\d+\\\s*$", "", text)


def structured_candidates(ext: ChapterExtraction) -> list[str]:
    out: list[str] = []
    for mention in ext.entities:
        out.extend(str(v) for v in mention.attrs.values())
    for event in ext.events:
        out.extend(str(v) for v in event.payload.values())
    for change in ext.state_changes:
        out.extend([change.old, change.new])
    if ext.story_time.day_offset is not None:
        out.append(str(ext.story_time.day_offset))
    return [c for c in out if c]


@dataclass
class ChapterEval:
    book: str
    chapter: int
    hits: dict[str, list[str]] = field(default_factory=dict)
    misses: dict[str, list[str]] = field(default_factory=dict)

    def add(self, scored: bool, kind: str, fact_id: str, hit: bool) -> None:
        if not scored:
            return
        bucket = self.hits.setdefault(kind, []) if hit else self.misses.setdefault(kind, [])
        bucket.append(fact_id)


def match_fact(fact: dict[str, Any], ext: ChapterExtraction) -> bool:
    kind = fact["kind"]
    aliases = [str(a) for a in fact.get("aliases", [])]
    alts = [str(a) for a in fact.get("alt", [])]
    if kind == "number":
        return num_hit(str(fact["value"]), alts, structured_candidates(ext))
    if kind == "entity":
        return bool(entity_matches(ext, str(fact["name"]), aliases))
    if kind == "attr":
        mentions = entity_matches(ext, str(fact["entity"]), [])
        label_attr = str(fact["attr"])
        label_value = str(fact["value"])
        for mention in mentions:
            for key, value in mention.attrs.items():
                if (label_attr in key or key in label_attr) and num_hit(label_value, alts, [str(value)]):
                    return True
        return False
    if kind == "change":
        label_entity, label_attr, label_new = str(fact["entity"]), str(fact["attr"]), str(fact["new"])
        for change in ext.state_changes:
            entity_ok = _alias_hit(label_entity, [], change.entity) or any(
                _alias_hit(label_entity, [], a) for a in change.entity.split("、")
            )
            if entity_ok and (label_attr in change.attr or change.attr in label_attr) \
                    and num_hit(label_new, alts, [change.new]):
                return True
        return False
    if kind == "event":
        kind_name = str(fact["kind_name"])
        label_entities = [str(e) for e in fact.get("entities", [])]
        for event in ext.events:
            kind_ok = kind_name in event.kind or event.kind in kind_name
            entities_ok = all(
                any(_alias_hit(le, [], name) for name in event.entities) for le in label_entities
            )
            if kind_ok and entities_ok:
                return True
        return False
    if kind == "relation":
        label_subject, label_object, label_rel = str(fact["subject"]), str(fact["object"]), str(fact["rel"])
        for relation in ext.relations:
            if (relation.state or "建立") != "建立":
                continue
            pair = {relation.subject, relation.object}
            subjects_ok = any(
                _alias_hit(label_subject, [], p) or _alias_hit(label_object, [], p) for p in pair
            )
            both = sum(
                1 for p in pair if _alias_hit(label_subject, [], p) or _alias_hit(label_object, [], p)
            )
            if subjects_ok and both == 2 and (label_rel in relation.kind or relation.kind in label_rel):
                return True
        return False
    if kind == "time":
        return ext.story_time.day_offset == fact.get("day_offset")
    if kind == "signal":
        haystack = norm(ext.model_dump_json())
        return any(norm(str(k)) in haystack for k in fact.get("keywords", []))
    raise ValueError(f"未知事实类型: {kind}")


def get_extraction(
    provider: Any,
    block: dict[str, Any],
    texts_root: Path,
    cache_dir: Path,
    samples: int,
    context: PreviousState | None,
) -> ChapterExtraction:
    """带磁盘缓存的章节抽取：同标注同参数不重复烧 API（评测会反复迭代）。"""
    key = norm(f"{block['book']}-第{block['chapter']}章-s{samples}-gao")
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        return ChapterExtraction.model_validate_json(cache_path.read_text(encoding="utf-8"))
    raw = preprocess((texts_root / str(block["text"])).read_text(encoding="utf-8", errors="replace"))
    chapter = Chapter(number=int(block["chapter"]), title=f"第{block['chapter']}章", text=raw)
    extraction = extract_chapter(provider, chapter, samples=samples, context=context)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(extraction.model_dump_json(), encoding="utf-8")
    return extraction


def run(labels_path: Path, texts_root: Path, provider_name: str, out_path: Path, samples: int) -> None:
    blocks = yaml.safe_load(labels_path.read_text(encoding="utf-8"))
    provider = get_provider(provider_name)
    cache_dir = out_path.parent / "cache"
    results: list[tuple[dict[str, Any], ChapterExtraction, ChapterEval]] = []
    error_chapters: list[str] = []
    # 同书章节按标注顺序共享前情状态（跨章有状态抽取在评测中同样生效）
    book_states: dict[str, PreviousState] = {}

    for block in blocks:
        book = str(block["book"])
        context = book_states.setdefault(book, PreviousState())
        try:
            extraction = get_extraction(provider, block, texts_root, cache_dir, samples, context)
        except ExtractionError as exc:
            # 抽取失败 = 该章零查全，如实计入（不让失败章节静默消失）
            print(f"[{book} 第{block['chapter']}章] 抽取失败: {exc}")
            extraction = ChapterExtraction(
                chapter=int(block["chapter"]),
                summary=f"[抽取失败] {exc}",
            )
            error_chapters.append(f"{book} 第{block['chapter']}章")
        context.observe(extraction)
        evaluation = ChapterEval(book=book, chapter=int(block["chapter"]))
        for fact in block["facts"]:
            hit = match_fact(fact, extraction)
            evaluation.add(bool(fact.get("must", True)), str(fact["kind"]), str(fact["id"]), hit)
        results.append((block, extraction, evaluation))
        print(
            f"[{block['book']} 第{block['chapter']}章] 抽取完成："
            f"实体{len(extraction.entities)} 变更{len(extraction.state_changes)} 事件{len(extraction.events)}"
        )

    lines: list[str] = ["# canonkeeper 事实级查全评测", "", f"- 时间：{datetime.now().astimezone().isoformat(timespec='seconds')}",
                        f"- provider：{provider_name} · 标注：{labels_path.name}", ""]
    lines += ["| 章 | " + " | ".join(SCORED_KINDS) + " | 信号(signal) |",
              "|---|" + "---|" * (len(SCORED_KINDS) + 1)]
    totals: dict[str, list[int]] = {k: [0, 0] for k in SCORED_KINDS}
    for block, _ext, ev in results:
        cells = []
        for kind in SCORED_KINDS:
            hit = len(ev.hits.get(kind, []))
            total = hit + len(ev.misses.get(kind, []))
            totals[kind][0] += hit
            totals[kind][1] += total
            cells.append(f"{hit}/{total}" if total else "—")
        sig_total = len(ev.hits.get("signal", [])) + len(ev.misses.get("signal", []))
        sig_hit = len(ev.hits.get("signal", []))
        cells.append(f"{sig_hit}/{sig_total}" if sig_total else "—")
        lines.append(f"| {block['book']} 第{block['chapter']}章 | " + " | ".join(cells) + " |")
    lines.append("")
    lines += ["## 分品类总查全", "", "| 品类 | 查全 |", "|---|---|"]
    if error_chapters:
        lines.append(f"- **抽取失败章节（按零查全计）**：{'、'.join(error_chapters)}")
    for kind in SCORED_KINDS:
        hit, total = totals[kind]
        if total:
            lines.append(f"| {kind} | {hit}/{total} = {hit / total:.0%} |")
    signal_hit = sum(len(ev.hits.get("signal", [])) for _, _, ev in results)
    signal_total = sum(len(ev.hits.get("signal", [])) + len(ev.misses.get("signal", [])) for _, _, ev in results)
    if signal_total:
        lines.append(f"| signal | {signal_hit}/{signal_total} = {signal_hit / signal_total:.0%} |")

    lines += ["", "## 漏报明细", ""]
    for block, _ext, ev in results:
        chapter_misses = [(k, fid) for k in SCORED_KINDS for fid in ev.misses.get(k, [])]
        if not chapter_misses:
            continue
        lines.append(f"### {block['book']} 第{block['chapter']}章")
        for kind, fact_id in chapter_misses:
            fact = next(f for f in block["facts"] if str(f["id"]) == fact_id)
            lines.append(f"- [{kind}] {fact_id}: {fact.get('note') or fact.get('value') or fact.get('name')}")
        lines.append("")

    report = "\n".join(lines) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="canonkeeper 事实级查全评测")
    parser.add_argument("--labels", required=True, help="标注 YAML（evals/labels/*.yaml）")
    parser.add_argument("--texts", required=True, help="章节文本根目录（版权文本不入仓库）")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--samples", type=int, default=1, help="自洽采样遍数（>1 时并集合并）")
    parser.add_argument("--out", default="evals/results/latest.md")
    args = parser.parse_args(argv)
    run(Path(args.labels), Path(args.texts), args.provider, Path(args.out), args.samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
