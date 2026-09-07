"""报告渲染：状态库 violations → markdown（PLAN §2 最后一站）。

报告标注 provider/模型版本（PLAN §1：模型是受控常量，所有结论标注版本号）。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Sequence

from ..rules.engine import Rule
from ..store.db import StateDB

__all__ = ["render_report"]

_SEVERITY_ORDER: tuple[str, ...] = ("high", "medium", "low", "info")
_SEVERITY_CN = {"high": "高", "medium": "中", "low": "低", "info": "提示"}


def _entity_names(db: StateDB, entity_ids: Sequence[int]) -> str:
    names: list[str] = []
    for entity_id in entity_ids:
        row = db.conn.execute("SELECT name FROM entities WHERE id=?", (entity_id,)).fetchone()
        names.append(row["name"] if row else f"#{entity_id}")
    return "、".join(names)


def render_report(db: StateDB, rules: Sequence[Rule]) -> str:
    violations = db.violations()
    counts = Counter(row["severity"] for row in violations)
    total = sum(counts.values())

    lines: list[str] = []
    title = db.get_meta("book_title", "未命名书稿")
    lines.append(f"# dsharness 冲突报告：《{title}》")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    provider = db.get_meta("provider", "?")
    fast = db.get_meta("model_fast", "?")
    flagship = db.get_meta("model_flagship", "?")
    lines.append(f"- 抽取模型：provider={provider}（fast={fast} / flagship={flagship}）"
                 f"（抽取时间 {db.get_meta('ingested_at', '?')}）")
    chapter_rows = db.conn.execute("SELECT COUNT(*) AS n FROM chapter_extractions").fetchone()
    change_rows = db.conn.execute("SELECT COUNT(*) AS n FROM state_changes").fetchone()
    lines.append(
        f"- 规模：{chapter_rows['n']} 章 · 实体 {db.entity_count()} · 状态变更 {change_rows['n']}"
    )
    summary = " · ".join(f"{_SEVERITY_CN.get(s, s)} {counts.get(s, 0)}" for s in _SEVERITY_ORDER)
    lines.append(f"- **冲突总数 {total}**（{summary}）")
    if rules:
        lines.append("- 覆盖规则：" + "、".join(f"`{r.rule_id}`" for r in rules))
    lines.append("")

    lines.append("## 冲突明细")
    lines.append("")
    if not violations:
        lines.append("**未检出冲突。**注意：这只是当前覆盖规则的判定结果，不代表全书无设定矛盾。")
    current_rule = ""
    for row in violations:
        if row["rule_id"] != current_rule:
            current_rule = row["rule_id"]
            rule = next((r for r in rules if r.rule_id == current_rule), None)
            rule_name = rule.name if rule else ""
            lines.append(
                f"### [{_SEVERITY_CN.get(row['severity'], row['severity'])}] "
                f"{current_rule} — {rule_name}"
            )
            lines.append("")
        entity_part = f" · 实体：{_entity_names(db, row['entity_ids'])}" if row["entity_ids"] else ""
        chapter_part = f"第{row['chapter']}章" if row["chapter"] else "全书"
        lines.append(f"- **{chapter_part}**{entity_part} — {row['message']}")
        if row["evidence_quote"]:
            lines.append(f"  > 「{row['evidence_quote']}」")
    lines.append("")
    return "\n".join(lines)
