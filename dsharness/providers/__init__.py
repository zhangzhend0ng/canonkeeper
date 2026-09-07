"""Provider 适配器包。import 本包即注册全部内置适配器。"""

from . import deepseek, glm  # noqa: F401  (import for registration side effect)
from .base import (
    MockProvider,
    OpenAICompatProvider,
    Provider,
    ProviderConfig,
    ProviderError,
    Tier,
    get_provider,
    known_providers,
)

__all__ = [
    "deepseek",
    "glm",
    "MockProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "Tier",
    "get_provider",
    "known_providers",
]
