"""规则引擎：YAML 规则加载 + 纯程序化判定（不调 LLM，PLAN §2 可信度地基）。"""

from .engine import Rule, RuleError, builtin_rules_dir, load_rules, run_rules
from .predicates import PREDICATES

__all__ = ["Rule", "RuleError", "builtin_rules_dir", "load_rules", "run_rules", "PREDICATES"]
