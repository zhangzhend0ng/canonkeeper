"""Provider 抽象层：一个 OpenAI-compatible 适配器通吃 DeepSeek/GLM/本地 vLLM（PLAN §1）。

分级调用：`Tier.FAST` 做批量抽取与初筛，`Tier.FLAGSHIP` 做终审。
异常策略（error-handling harness）：本库统一用异常；跨层边界统一翻译为
`ProviderError` 家族并携带上下文（provider 名/模型名/章号）。api_key 只从
环境变量读取，任何错误消息与日志不得包含密钥（logging harness #3）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol, Sequence

__all__ = [
    "Tier",
    "Message",
    "ProviderError",
    "ProviderConfig",
    "Provider",
    "OpenAICompatProvider",
    "MockProvider",
    "get_provider",
    "known_providers",
]


class Tier(str, Enum):
    """调用档位：成本-质量分层是 harness 内置策略（PLAN §1）。"""

    FAST = "fast"
    FLAGSHIP = "flagship"


# OpenAI 兼容 chat message：{"role": "system"|"user"|"assistant", "content": str}
Message = dict[str, str]


class ProviderError(RuntimeError):
    """Provider 边界错误。消息面向开发者，附上下文；绝不携带密钥。"""


@dataclass(frozen=True)
class ProviderConfig:
    """端点三元组 + 模型档位。api_key 只存环境变量名，不存值。"""

    name: str
    base_url: str
    fast_model: str
    flagship_model: str
    key_env: str

    def api_key(self) -> str:
        key = os.environ.get(self.key_env, "")
        if not key:
            raise ProviderError(
                f"环境变量 {self.key_env} 未设置（provider={self.name}）。"
                "密钥只走环境变量，不要写进代码或配置文件。"
            )
        return key

    def model_for(self, tier: Tier) -> str:
        return self.flagship_model if tier is Tier.FLAGSHIP else self.fast_model


class Provider(Protocol):
    """所有 provider 的最小契约：可知名 + 一次调用返回一段文本。"""

    @property
    def name(self) -> str: ...

    def chat(
        self,
        messages: Sequence[Message],
        *,
        tier: Tier = Tier.FAST,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str: ...


def _is_json_mode_rejected(exc: Exception) -> bool:
    """兼容端点不支持 response_format=json_object 时的识别（HTTP 400 或报文提及）。"""
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    return status == 400 or "response_format" in text


class OpenAICompatProvider:
    """OpenAI 兼容适配器。openai SDK 自带指数退避重试（瞬态错误），持久错误 fail fast。"""

    def __init__(self, config: ProviderConfig, client: Any | None = None) -> None:
        self._config = config
        self._client: Any | None = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # 延迟导入：纯规则/离线路径无需安装 SDK 也可用

            self._client = OpenAI(
                base_url=self._config.base_url,
                api_key=self._config.api_key(),
                max_retries=3,
                timeout=120.0,
            )
        return self._client

    @property
    def name(self) -> str:
        return self._config.name

    def model_names(self) -> dict[str, str]:
        return {"fast": self._config.fast_model, "flagship": self._config.flagship_model}

    def chat(
        self,
        messages: Sequence[Message],
        *,
        tier: Tier = Tier.FAST,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        client = self._ensure_client()
        model = self._config.model_for(tier)
        base_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [dict(m) for m in messages],
            "temperature": temperature,
        }
        try:
            if json_mode:
                try:
                    resp = client.chat.completions.create(
                        **base_kwargs, response_format={"type": "json_object"}
                    )
                except Exception as exc:  # noqa: BLE001 - 边界统一翻译
                    if not _is_json_mode_rejected(exc):
                        raise
                    # 兼容端点退回普通模式（prompt 已内嵌 JSON 指令）
                    resp = client.chat.completions.create(**base_kwargs)
            else:
                resp = client.chat.completions.create(**base_kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - 层边界：翻译为公共错误类型
            raise ProviderError(
                f"provider={self._config.name} model={model} 调用失败: {exc}"
            ) from exc
        content = resp.choices[0].message.content
        if not content:
            raise ProviderError(f"provider={self._config.name} model={model} 返回空内容")
        return content


class MockProvider:
    """确定性假 provider：单测与离线冒烟（`--provider mock`）用。逐条消费 responses，
    耗尽后循环最后一个。"""

    def __init__(self, responses: Sequence[str], name: str = "mock") -> None:
        if not responses:
            raise ProviderError("MockProvider 需要至少一条 responses")
        self._responses = list(responses)
        self._cursor = 0
        self.name = name
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: Sequence[Message],
        *,
        tier: Tier = Tier.FAST,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str:
        self.calls.append(
            {"messages": [dict(m) for m in messages], "tier": tier, "json_mode": json_mode}
        )
        response = self._responses[min(self._cursor, len(self._responses) - 1)]
        self._cursor += 1
        return response


# 内置注册表：base_url+默认模型（模型名可用 DSH_FAST_MODEL / DSH_FLAGSHIP_MODEL 覆盖）
_REGISTRY: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com",
        fast_model="deepseek-chat",
        flagship_model="deepseek-reasoner",
        key_env="DEEPSEEK_API_KEY",
    ),
    "glm": ProviderConfig(
        name="glm",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        fast_model="glm-4-flash",
        flagship_model="glm-4-plus",
        key_env="ZHIPU_API_KEY",
    ),
}

# 离线冒烟用样例抽取（`--provider mock` 时每章返回同构输出，chapter 由管线覆盖）：
# 让无 API key 的环境也能跑通 ingest→check→report 全链路。
MOCK_EXTRACTION_JSON = """{
  "chapter": 0,
  "title": "mock",
  "summary": "离线冒烟样例：与章节内容无关。",
  "entities": [
    {"name": "林昼", "type": "人物", "aliases": ["林师弟"], "attrs": {"境界": "炼气三层", "生死": "存活"}},
    {"name": "青云宗", "type": "组织", "aliases": [], "attrs": {}}
  ],
  "state_changes": [
    {"entity": "林昼", "attr": "境界", "old": "炼气二层", "new": "炼气三层", "kind": "升级", "quote": "林昼只觉丹田一热，竟是破了。"}
  ],
  "events": [
    {"kind": "登场", "entities": ["林昼"], "payload": {}, "quote": "林昼睁开眼时，天光正落在青云宗的石阶上。"}
  ],
  "relations": [
    {"subject": "林昼", "object": "青云宗", "kind": "所属", "state": "建立"}
  ],
  "story_time": {"start": "清晨", "end": "入夜", "markers": ["翌日清晨"], "day_offset": null}
}"""


def known_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_provider(name: str, *, client: Any | None = None) -> Provider:
    """按名字取 provider。`mock` 为离线样例 provider；未知名字 fail fast。"""
    key = name.strip().lower()
    if key == "mock":
        return MockProvider([MOCK_EXTRACTION_JSON])
    config = _REGISTRY.get(key)
    if config is None:
        raise ProviderError(
            f"未知 provider: {name}（可用: {', '.join(known_providers())} 或 mock）"
        )
    fast = os.environ.get("DSH_FAST_MODEL", config.fast_model)
    flagship = os.environ.get("DSH_FLAGSHIP_MODEL", config.flagship_model)
    if fast != config.fast_model or flagship != config.flagship_model:
        config = replace(config, fast_model=fast, flagship_model=flagship)
    return OpenAICompatProvider(config, client=client)
