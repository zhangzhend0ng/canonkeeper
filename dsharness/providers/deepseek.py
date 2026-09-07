"""DeepSeek 适配器（首发默认被试，PLAN §1）。

模型名只是注册表默认值：deepseek-chat（V3 系，低价快速档）、
deepseek-reasoner（R1 系，旗舰终审档）；上游改名时用
DSH_FAST_MODEL / DSH_FLAGSHIP_MODEL 环境变量覆盖，无需改代码。
"""

from .base import _REGISTRY, ProviderConfig

_REGISTRY["deepseek"] = ProviderConfig(
    name="deepseek",
    base_url="https://api.deepseek.com",
    fast_model="deepseek-chat",
    flagship_model="deepseek-reasoner",
    key_env="DEEPSEEK_API_KEY",
)
