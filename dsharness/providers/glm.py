"""GLM(open.bigmodel.cn) 适配器（第二被试，对照实验用，PLAN §1）。

模型名可用 DSH_FAST_MODEL / DSH_FLAGSHIP_MODEL 覆盖；
API key 走环境变量 ZHIPU_API_KEY。
"""

from .base import _REGISTRY, ProviderConfig

_REGISTRY["glm"] = ProviderConfig(
    name="glm",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    fast_model="glm-4-flash",
    flagship_model="glm-4-plus",
    key_env="ZHIPU_API_KEY",
)
