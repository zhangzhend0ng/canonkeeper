"""dsh CLI：ingest / check / report / replay / stability / rules。

异常策略：各子命令只抛不捕，main() 顶层统一打印一次错误并返回 1
（error-handling harness：log once at outermost handler；--debug 重新抛出看栈）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Callable, Sequence

from . import __version__
from .extract import ChapterExtraction, ExtractionError, extract_book, extract_chapter
from .ingest import Chapter, load_book_text, split_chapters
from .pipeline import ingest_book_to_db, run_check
from .providers.base import ProviderError, get_provider, known_providers
from .report.render import render_report
from .rules.engine import RuleError, load_builtin_rules
from .store.db import StateDB

__all__ = ["main"]


def _progress(now: int, total: int, extraction: ChapterExtraction | None) -> None:
    if extraction is None:
        detail = "?"
    elif extraction.summary.startswith("[抽取失败"):
        detail = "抽取失败（占位回填）"
    else:
        detail = (
            f"实体{len(extraction.entities)} 事件{len(extraction.events)} "
            f"变更{len(extraction.state_changes)}"
        )
    title = extraction.title if extraction else ""
    print(f"[{now}/{total}] {title} — {detail}", file=sys.stderr)


# -- 子命令 ---------------------------------------------------------------


def _cmd_ingest(args: argparse.Namespace) -> int:
    print(f"provider={args.provider}，开始切章与抽取…", file=sys.stderr)
    stats = ingest_book_to_db(
        args.book,
        args.db,
        args.provider,
        limit=args.limit,
        samples=args.samples,
        incremental=args.incremental,
        skip_errors=args.skip_errors,
        progress=_progress,
    )
    print(
        f"入库完成: {args.db}（{stats.chapters} 章 / 实体 {stats.entities}"
        f" / 本次抽取 {stats.extracted} / 复用 {stats.reused}）"
    )
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    rule_count, violations = run_check(args.db, args.rules or [])
    print(f"检查完成: 规则 {rule_count} 条, 冲突 {len(violations)} 条（已写入 {args.db}）")
    for violation in violations[:20]:
        chapter = f"第{violation.chapter}章" if violation.chapter else "全书"
        print(f"  [{violation.severity}] {violation.rule_id} {chapter}: {violation.message}")
    if len(violations) > 20:
        print(f"  …其余 {len(violations) - 20} 条请用 `canonkeeper report` 查看")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    rules = load_builtin_rules()
    db = StateDB(args.db)
    try:
        markdown = render_report(db, rules)
    finally:
        db.close()
    if args.out:
        out_path = Path(args.out)
    else:
        out_dir = Path("reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{Path(args.db).stem}_report_{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"报告已写入 {out_path}")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    db = StateDB(args.db)
    try:
        if args.all:
            extractions = db.extractions()
        else:
            extraction = db.get_extraction(args.chapter)
            if extraction is None:
                print(f"错误: 库中不存在第{args.chapter}章", file=sys.stderr)
                return 1
            extractions = [extraction]
    finally:
        db.close()
    for extraction in extractions:
        print(json.dumps(extraction.model_dump(), ensure_ascii=False, indent=2))
    return 0


def _cmd_stability(args: argparse.Namespace) -> int:
    provider = get_provider(args.provider)
    chapters = split_chapters(load_book_text(args.book))
    if args.limit > 0:
        chapters = chapters[: args.limit]
    if not chapters:
        print("错误: 未切出任何章节", file=sys.stderr)
        return 1

    runs: dict[int, list[ChapterExtraction]] = {}
    for run_index in range(args.runs):
        print(f"== 稳定性抽取 第 {run_index + 1}/{args.runs} 遍 ==", file=sys.stderr)
        for chapter in chapters:
            runs.setdefault(chapter.number, []).append(
                extract_chapter(provider, chapter, samples=args.samples)
            )

    rows: list[tuple[Chapter, list[ChapterExtraction], float]] = []
    for chapter in chapters:
        variants = runs[chapter.number]
        alias_sets = [
            {m.name for m in e.entities} | {a for m in e.entities for a in m.aliases}
            for e in variants
        ]
        scores = [_jaccard(alias_sets[0], s) for s in alias_sets[1:]]
        rows.append((chapter, variants, mean(scores) if scores else 1.0))

    lines: list[str] = []
    lines.append("# canonkeeper 抽取往返稳定性报告")
    lines.append("")
    lines.append(f"- 书稿：{Path(args.book).name} · provider={args.provider} · 每章抽取 {args.runs} 遍")
    lines.append(f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("| 章 | 实体数(各遍) | 别名集 Jaccard(首遍 vs 其余) | 事件数(各遍) | 变更数(各遍) |")
    lines.append("|---|---|---|---|---|")
    for chapter, variants, score in rows:
        entity_counts = "/".join(str(len(e.entities)) for e in variants)
        event_counts = "/".join(str(len(e.events)) for e in variants)
        change_counts = "/".join(str(len(e.state_changes)) for e in variants)
        lines.append(
            f"| {chapter.number} {chapter.title} | {entity_counts} | {score:.3f} "
            f"| {event_counts} | {change_counts} |"
        )
    overall = mean(score for _, _, score in rows)
    lines.append("")
    lines.append(f"**全书平均别名集 Jaccard = {overall:.3f}**（1.0 为完全一致；"
                 "该值即 M0 验收指标：抽取往返稳定性）")
    markdown = "\n".join(lines) + "\n"

    if args.out:
        out_path = Path(args.out)
    else:
        out_dir = Path("reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"stability_{Path(args.book).stem}_{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"报告已写入 {out_path}", file=sys.stderr)
    return 0


def _cmd_rules(args: argparse.Namespace) -> int:
    for rule in load_builtin_rules():
        print(f"{rule.rule_id:10s} [{rule.severity:6s}] {rule.predicate:22s} {rule.name}")
    return 0


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


# -- 参数解析与入口 ---------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canonkeeper",
        description="canonkeeper —— 网文长篇三级验证 harness（见 PLAN.md）",
    )
    parser.add_argument("--version", action="version", version=f"canonkeeper {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="切章 + LLM 抽取 + 入库")
    p_ingest.add_argument("book", help="书稿路径（txt 文件或含 txt 的目录）")
    p_ingest.add_argument("--db", default=None, help="状态库路径（默认 books/<书名>.db）")
    p_ingest.add_argument("--provider", default="deepseek", help=f"provider（{ '/'.join(known_providers()) } 或 mock）")
    p_ingest.add_argument("--limit", type=int, default=0, help="只处理前 N 章（0=全部）")
    p_ingest.add_argument("--samples", type=int, default=1, help="每章自洽采样遍数（>1 并集合并，成本翻倍）")
    p_ingest.add_argument("--incremental", action="store_true", help="增量追章：只抽取库中缺失的章（按章号对齐）")
    p_ingest.add_argument("--skip-errors", action="store_true", help="单章抽取失败时占位跳过而非中断")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_check = sub.add_parser("check", help="运行规则引擎（纯程序化判定）")
    p_check.add_argument("db", help="状态库路径")
    p_check.add_argument("--rules", action="append", help="额外规则 YAML（可多次）")
    p_check.set_defaults(func=_cmd_check)

    p_report = sub.add_parser("report", help="渲染 markdown 冲突报告")
    p_report.add_argument("db", help="状态库路径")
    p_report.add_argument("--out", default=None, help="输出路径（默认 reports/<库名>_report_<时间>.md）")
    p_report.set_defaults(func=_cmd_report)

    p_replay = sub.add_parser("replay", help="回放某章抽取结果 JSON")
    p_replay.add_argument("db", help="状态库路径")
    p_replay.add_argument("chapter", type=int, nargs="?", default=0, help="章号")
    p_replay.add_argument("--all", action="store_true", help="回放全部章节")
    p_replay.set_defaults(func=_cmd_replay)

    p_stab = sub.add_parser("stability", help="抽取往返稳定性测量（M0 验收工具）")
    p_stab.add_argument("book", help="书稿路径")
    p_stab.add_argument("--provider", default="deepseek")
    p_stab.add_argument("--runs", type=int, default=2, help="每章抽取遍数（默认 2）")
    p_stab.add_argument("--samples", type=int, default=1, help="每遍自洽采样数")
    p_stab.add_argument("--limit", type=int, default=0, help="只测前 N 章")
    p_stab.add_argument("--out", default=None, help="输出路径")
    p_stab.set_defaults(func=_cmd_stability)

    p_rules = sub.add_parser("rules", help="列出内置规则")
    p_rules.set_defaults(func=_cmd_rules)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "func", None)
    if command is None:
        parser.error("缺少子命令")
    try:
        return int(command(args))
    except (ProviderError, ExtractionError, RuleError, ValueError, OSError) as exc:
        if getattr(args, "debug", False):
            raise
        print(f"错误: {exc}", file=sys.stderr)  # 顶层唯一错误出口
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
