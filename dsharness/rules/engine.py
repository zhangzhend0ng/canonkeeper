"""规则加载与执行。

表驱动（PLAN §4）：YAML 只声明 rule_id/name/severity/predicate/params；
加载期全部校验（severity 枚举、谓词存在、rule_id 唯一）——配置错误 fail fast，
绝不带病运行。YAML 一律 safe_load（input-deserialization harness N 级）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..store.db import BookView, Violation
from .predicates import PREDICATES

__all__ = ["Rule", "RuleError", "builtin_rules_dir", "load_rules", "run_rules"]

SEVERITIES: tuple[str, ...] = ("high", "medium", "low", "info")


class RuleError(ValueError):
    """规则文件/配置不合法。"""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    severity: str
    predicate: str
    params: Mapping[str, Any] = field(default_factory=dict)


def builtin_rules_dir() -> Path:
    return Path(__file__).parent / "builtin"


def load_builtin_rules() -> list[Rule]:
    return load_rules(sorted(builtin_rules_dir().glob("*.yaml")))


def load_rules(paths: Sequence[Path]) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise RuleError(f"{path.name}: 规则文件顶层必须是列表")
        for item in data:
            rule = _parse_rule(item, path.name)
            if rule.rule_id in seen:
                raise RuleError(f"{path.name}: rule_id 重复: {rule.rule_id}")
            seen.add(rule.rule_id)
            rules.append(rule)
    return rules


def run_rules(rules: Sequence[Rule], view: BookView) -> list[Violation]:
    violations: list[Violation] = []
    for rule in rules:
        predicate = PREDICATES[rule.predicate]  # 加载期已校验存在
        for violation in predicate(view, rule.params):
            violations.append(replace(violation, rule_id=rule.rule_id, severity=rule.severity))
    return violations


def _parse_rule(item: Any, source: str) -> Rule:
    if not isinstance(item, dict):
        raise RuleError(f"{source}: 规则条目必须是映射，得到 {type(item).__name__}")
    missing = {"rule_id", "name", "severity", "predicate"} - set(item)
    if missing:
        raise RuleError(f"{source}: 规则缺少字段 {sorted(missing)}: {item!r}")
    severity = str(item["severity"])
    if severity not in SEVERITIES:
        raise RuleError(f"{source}: severity 必须是 {'/'.join(SEVERITIES)}: {item['severity']!r}")
    predicate = str(item["predicate"])
    if predicate not in PREDICATES:
        raise RuleError(f"{source}: 未知谓词 {predicate!r}（可用: {sorted(PREDICATES)}）")
    params = item.get("params") or {}
    if not isinstance(params, dict):
        raise RuleError(f"{source}: params 必须是映射: {params!r}")
    return Rule(
        rule_id=str(item["rule_id"]),
        name=str(item["name"]),
        severity=severity,
        predicate=predicate,
        params=params,
    )
