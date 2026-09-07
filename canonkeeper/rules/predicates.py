"""内置判定谓词：纯函数 (BookView, params) -> list[Violation]。

- 不调 LLM、无 IO、确定性——判定逻辑 100% 可单测（PLAN §6 的卖点）。
- 谓词与规则参数解耦：YAML 绑定元数据与参数；同一谓词经不同参数服务多条规则
  （如 terminal_state_reuse 同时服务 ①死亡复现 与 ⑨毁品复用）。
- 谓词产出 Violation 时 rule_id/severity 留空，由引擎按所绑规则回填。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Mapping

from ..store.db import BookView, ChangeRec, Violation

__all__ = [
    "Predicate",
    "PREDICATES",
    "terminal_state_reuse",
    "realm_regression",
    "numeric_attr_monotonic",
    "location_continuity",
    "transfer_registered",
    "balance_continuity",
    "ledger_flow_recompute",
    "alias_collision",
    "time_regression",
]

Predicate = Callable[[BookView, Mapping[str, Any]], list[Violation]]


def _changes_by_entity(view: BookView) -> dict[int, list[ChangeRec]]:
    grouped: dict[int, list[ChangeRec]] = defaultdict(list)
    for change in view.changes:
        grouped[change.entity_id].append(change)
    for changes in grouped.values():
        changes.sort(key=lambda c: c.chapter)
    return grouped


def terminal_state_reuse(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """终态后复现（规则①⑨共用模式）：实体 attr 达到终态值（死亡/已毁…）后再次活动，
    且中间无复活类登记，则在首次复现章报违规。"""
    attr = str(params.get("attr", ""))
    terminal_value = str(params.get("terminal_value", ""))
    revive_kinds = {str(k) for k in params.get("revive_kinds", ())}
    violations: list[Violation] = []
    for entity_id, changes in _changes_by_entity(view).items():
        terminal_chapter: int | None = None
        for change in changes:
            if change.attr == attr and change.new == terminal_value:
                terminal_chapter = change.chapter
            elif change.kind in revive_kinds and terminal_chapter is not None:
                terminal_chapter = None  # 复活/修复登记有效，回到活动态
        if terminal_chapter is None:
            continue
        evidence = next(
            (c.quote for c in changes if c.chapter == terminal_chapter and c.attr == attr), ""
        )
        name = view.entities[entity_id].name
        for chapter in sorted(view.appearances.get(entity_id, ())):
            if chapter > terminal_chapter:
                violations.append(
                    Violation(
                        rule_id="",
                        severity="",
                        chapter=chapter,
                        entity_ids=[entity_id],
                        evidence_quote=evidence,
                        message=(
                            f"实体「{name}」在第{terminal_chapter}章登记终态"
                            f"（{attr}={terminal_value}），第{chapter}章仍活动且无复活类登记"
                        ),
                    )
                )
                break  # 每实体只报首次复现
    return violations


def _realm_rank(ladder: list[str], value: str) -> int | None:
    """境界值 → 阶梯序号。前缀匹配：「炼气三层」归入「炼气」档；不在阶梯则 None（跳过比较）。"""
    for index, name in enumerate(ladder):
        if value == name or value.startswith(name):
            return index
    return None


def realm_regression(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """境界单调（规则⑫）：attr 迁移在给定阶梯（低→高）上下降，且非废功类登记则报。"""
    attr = str(params.get("attr", "境界"))
    ladder: list[str] = [str(x) for x in params.get("ladder", ())]
    regress_kinds = {str(k) for k in params.get("regress_kinds", ())}
    violations: list[Violation] = []
    for entity_id, changes in _changes_by_entity(view).items():
        previous: ChangeRec | None = None
        for change in (c for c in changes if c.attr == attr):
            if previous is not None:
                old_rank = _realm_rank(ladder, change.new)
                prev_rank = _realm_rank(ladder, previous.new)
                if (
                    prev_rank is not None
                    and old_rank is not None
                    and old_rank < prev_rank
                    and change.kind not in regress_kinds
                ):
                    name = view.entities[entity_id].name
                    violations.append(
                        Violation(
                            rule_id="",
                            severity="",
                            chapter=change.chapter,
                            entity_ids=[entity_id],
                            evidence_quote=change.quote,
                            message=(
                                f"实体「{name}」境界从「{previous.new}」(第{previous.chapter}章)"
                                f"降到「{change.new}」，且无废功类登记（kind={change.kind}）"
                            ),
                        )
                    )
            previous = change
    return violations


def alias_collision(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """别名归一（规则⑱）：同一别名指向多个实体 → 疑似未归一，报 info 由人工裁决。"""
    violations: list[Violation] = []
    for alias, entity_ids in sorted(view.alias_collisions.items()):
        if len(entity_ids) < 2:
            continue
        names = "、".join(
            view.entities[eid].name for eid in sorted(entity_ids) if eid in view.entities
        )
        violations.append(
            Violation(
                rule_id="",
                severity="",
                chapter=0,
                entity_ids=sorted(entity_ids),
                message=f"别名「{alias}」同时指向多个实体（{names}），疑似同一实体未归一",
            )
        )
    return violations


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "两": 2}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_DIGITS_RE = re.compile(r"\d+")


def _parse_cn_number(text: str) -> int | None:
    """从文本解析数值：阿拉伯数字优先，否则尝试常见中文数字写法（十六/三十五/一百零三…）。
    模糊量词（多/余/左右/上下/几）返回 None——「七十多万」不是 70，宁漏不误。
    解析失败返回 None，调用方跳过不比较（宁可漏报不误报）。"""
    text = text.strip()
    match = _DIGITS_RE.search(text)
    if match:
        return int(match.group())
    if re.search(r"[多余几上下]", text):
        return None
    total = 0
    current = 0
    found = False
    for ch in text:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
            found = True
        elif ch in _CN_UNITS:
            total += (current if current > 0 else 1) * _CN_UNITS[ch]
            current = 0
            found = True
        elif found:
            break  # 数字号结束（如「十六岁」的「岁」）
    if not found:
        return None
    return total + current


def balance_continuity(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """账本连续性（规则⑮的可机检核心，游戏经济 QA 的移植）：同一实体的余额类属性
    变化链中，后一条的 old 与前一条的 new 均可解析为数值且不等 → 账本断裂。
    old 缺失或为模糊值（七十多万）时跳过——那是抽取缺口，不是账目矛盾。"""
    money_attrs = {str(a) for a in params.get("money_attrs", ())}
    violations: list[Violation] = []
    for entity_id, changes in _changes_by_entity(view).items():
        money_changes = [
            c for c in changes if any(m in c.attr or c.attr in m for m in money_attrs)
        ]
        previous: ChangeRec | None = None
        for current in money_changes:
            if previous is not None:
                prev_value = _parse_cn_number(previous.new)
                old_value = _parse_cn_number(current.old)
                if (
                    prev_value is not None
                    and old_value is not None
                    and prev_value != old_value
                ):
                    name = view.entities[entity_id].name
                    violations.append(
                        Violation(
                            rule_id="",
                            severity="",
                            chapter=current.chapter,
                            entity_ids=[entity_id],
                            evidence_quote=current.quote,
                            message=(
                                f"实体「{name}」{current.attr}账本断裂：第{previous.chapter}章末为"
                                f"「{previous.new}」，第{current.chapter}章变化却自「{current.old}」起"
                                f"（差 {prev_value - old_value} 不可解释）"
                            ),
                        )
                    )
            previous = current
    return violations


def ledger_flow_recompute(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """收支复算（规则⑮实验性扩展，财务流专用）：两次余额登记之间的收支事件金额代数和
    应等于余额差。仅精确数值参与（模糊值自动跳过）；sign 由 payload 键名启发式判定。"""
    money_attrs = {str(a) for a in params.get("money_attrs", ())}
    income_keys = {str(k) for k in params.get("income_keys", ())}
    expense_keys = {str(k) for k in params.get("expense_keys", ())}
    violations: list[Violation] = []
    for entity_id, changes in _changes_by_entity(view).items():
        money_changes = [
            c for c in changes if any(m in c.attr or c.attr in m for m in money_attrs)
        ]
        for previous, current in zip(money_changes, money_changes[1:]):
            old_value = _parse_cn_number(previous.new if not previous.old else previous.old)
            new_value = _parse_cn_number(current.new)
            if old_value is None or new_value is None:
                continue
            delta = new_value - old_value
            flow = 0
            has_flow = False
            for event in view.events:
                if entity_id not in event.entity_ids:
                    continue
                if not (previous.chapter <= event.chapter <= current.chapter):
                    continue
                for key, raw in event.payload.items():
                    value = _parse_cn_number(str(raw))
                    if value is None:
                        continue
                    if any(k in key for k in expense_keys):
                        flow -= value
                        has_flow = True
                    elif any(k in key for k in income_keys):
                        flow += value
                        has_flow = True
            if has_flow and flow != delta:
                name = view.entities[entity_id].name
                violations.append(
                    Violation(
                        rule_id="",
                        severity="",
                        chapter=current.chapter,
                        entity_ids=[entity_id],
                        message=(
                            f"实体「{name}」{current.attr}收支复算不符：第{previous.chapter}~"
                            f"{current.chapter}章间事件合计 {flow:+d}，但余额变动 {delta:+d}"
                            "（可能有未登记收支或抽取缺口，供人工核对）"
                        ),
                    )
                )
    return violations


def numeric_attr_monotonic(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """数值属性单调（规则②的通用化，如年龄）：attr 数值下降且无重生/回溯类登记则报。
    非数值写法（如「幼年」）跳过不比较。"""
    attr = str(params.get("attr", "年龄"))
    regress_kinds = {str(k) for k in params.get("regress_kinds", ())}
    violations: list[Violation] = []
    for entity_id, changes in _changes_by_entity(view).items():
        prev_change: ChangeRec | None = None
        prev_value: int | None = None
        for change in (c for c in changes if c.attr == attr):
            value = _parse_cn_number(change.new)
            if value is None:
                continue
            if (
                prev_value is not None
                and prev_change is not None
                and value < prev_value
                and change.kind not in regress_kinds
            ):
                name = view.entities[entity_id].name
                violations.append(
                    Violation(
                        rule_id="",
                        severity="",
                        chapter=change.chapter,
                        entity_ids=[entity_id],
                        evidence_quote=change.quote,
                        message=(
                            f"实体「{name}」{attr}从「{prev_change.new}」(第{prev_change.chapter}章)"
                            f"变为「{change.new}」，数值下降且无重生/回溯类登记（kind={change.kind}）"
                        ),
                    )
                )
            prev_change, prev_value = change, value
    return violations


def location_continuity(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """位置连续性（规则⑤）：实体出现于与最近登记位置不符的地点且无位置变更登记 →
    疑似瞬移。依赖抽取的事件 location，缺失或实体无位置历史时静默跳过。"""
    location_attr = str(params.get("location_attr", "位置"))
    loc_history: dict[int, list[ChangeRec]] = defaultdict(list)
    for change in view.changes:
        if change.attr == location_attr:
            loc_history[change.entity_id].append(change)
    for changes in loc_history.values():
        changes.sort(key=lambda c: c.chapter)
    violations: list[Violation] = []
    for event in view.events:
        if not event.location:
            continue
        for entity_id in event.entity_ids:
            history = loc_history.get(entity_id)
            if not history:
                continue
            if any(c.chapter == event.chapter for c in history):
                continue  # 同章已有位置变更 → 移动已登记
            prior = [c for c in history if c.chapter < event.chapter]
            if not prior:
                continue
            last = prior[-1]
            if _same_place(last.new, event.location):
                continue
            name = view.entities[entity_id].name
            violations.append(
                Violation(
                    rule_id="",
                    severity="",
                    chapter=event.chapter,
                    entity_ids=[entity_id],
                    evidence_quote=event.quote,
                    message=(
                        f"实体「{name}」第{event.chapter}章出现于「{event.location}」，"
                        f"但最近登记位置为「{last.new}」(第{last.chapter}章)且无移动登记"
                    ),
                )
            )
    return violations


def _same_place(a: str, b: str) -> bool:
    """地名互相包含即视为同地（「青云宗」⊂「青云宗大殿」）；精确不同才疑似瞬移。"""
    return a == b or a in b or b in a


def transfer_registered(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """所有权转移登记（规则⑪）：交易/赠予类事件涉及物品时，前后 window 章内应有
    所有权属性变更登记；未登记报违规（可能是抽取遗漏，供人工核对）。"""
    event_kinds = {str(k) for k in params.get("event_kinds", ())}
    ownership_attrs = {str(a) for a in params.get("ownership_attrs", ())}
    window = int(params.get("window", 1))
    violations: list[Violation] = []
    for event in view.events:
        if event.kind not in event_kinds:
            continue
        item_ids = [
            entity_id
            for entity_id in event.entity_ids
            if view.entities.get(entity_id) is not None
            and view.entities[entity_id].type == "物品"
        ]
        if not item_ids or len(event.entity_ids) < 2:
            continue  # 非物品交割（如情报交易）不在本规则范围
        for item_id in item_ids:
            registered = any(
                change.entity_id == item_id
                and change.attr in ownership_attrs
                and abs(change.chapter - event.chapter) <= window
                for change in view.changes
            )
            if not registered:
                name = view.entities[item_id].name
                violations.append(
                    Violation(
                        rule_id="",
                        severity="",
                        chapter=event.chapter,
                        entity_ids=[item_id],
                        evidence_quote=event.quote,
                        message=(
                            f"第{event.chapter}章{event.kind}事件涉及物品「{name}」，"
                            f"但前后{window}章内未登记所有权变更"
                        ),
                    )
                )
    return violations


def time_regression(view: BookView, params: Mapping[str, Any]) -> list[Violation]:
    """故事时间单调（规则⑥）：day_offset 相对前一章回落，且该章无闪回类标记则报。
    day_offset 缺失的章节跳过（宁可漏报，不基于模糊数据误报）。"""
    flashback_words = [str(w) for w in params.get("flashback_markers", ())]
    violations: list[Violation] = []
    previous: tuple[int, int] | None = None  # (chapter, day_offset)
    for chapter in sorted(view.timeline):
        story_time = view.timeline[chapter]
        if story_time.day_offset is None:
            continue
        if (
            previous is not None
            and story_time.day_offset < previous[1]
            and not any(word in " ".join(story_time.markers) for word in flashback_words)
        ):
            violations.append(
                Violation(
                    rule_id="",
                    severity="",
                    chapter=chapter,
                    entity_ids=[],
                    message=(
                        f"故事时间倒流：第{chapter}章 day_offset={story_time.day_offset}"
                        f" 早于第{previous[0]}章的 {previous[1]}，且无闪回标记"
                    ),
                )
            )
        previous = (chapter, story_time.day_offset)
    return violations


PREDICATES: dict[str, Predicate] = {
    "terminal_state_reuse": terminal_state_reuse,
    "realm_regression": realm_regression,
    "numeric_attr_monotonic": numeric_attr_monotonic,
    "location_continuity": location_continuity,
    "transfer_registered": transfer_registered,
    "balance_continuity": balance_continuity,
    "ledger_flow_recompute": ledger_flow_recompute,
    "alias_collision": alias_collision,
    "time_regression": time_regression,
}
