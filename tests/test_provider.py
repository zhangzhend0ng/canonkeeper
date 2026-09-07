"""Provider 层测试：档位选模型、json_mode 兼容回退、密钥纪律（全部用 fake client，无网络）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dsharness.providers.base import (
    OpenAICompatProvider,
    ProviderConfig,
    ProviderError,
    Tier,
    get_provider,
)


class _FakeCompletions:
    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("超出脚本预设的调用次数")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=step))])


class _FakeClient:
    def __init__(self, script: list[Any]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(script))


class _FakeHTTPError(Exception):
    status_code = 400


def _config() -> ProviderConfig:
    return ProviderConfig(
        name="fake",
        base_url="http://localhost",
        fast_model="f-1",
        flagship_model="g-1",
        key_env="FAKE_KEY",
    )


def test_tier_selects_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_KEY", "k-test")
    fake = _FakeClient(["ok-flagship", "ok-fast"])
    provider = OpenAICompatProvider(_config(), client=fake)
    assert provider.chat([{"role": "user", "content": "q"}], tier=Tier.FLAGSHIP) == "ok-flagship"
    assert provider.chat([{"role": "user", "content": "q"}], tier=Tier.FAST) == "ok-fast"
    models = [call["model"] for call in fake.chat.completions.calls]
    assert models == ["g-1", "f-1"]


def test_missing_api_key_raises_naming_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAKE_KEY", raising=False)
    provider = OpenAICompatProvider(_config())
    with pytest.raises(ProviderError, match="FAKE_KEY"):
        provider.chat([{"role": "user", "content": "q"}])


def test_json_mode_falls_back_when_endpoint_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_KEY", "k-test")
    fake = _FakeClient([_FakeHTTPError("response_format unsupported"), "ok"])
    provider = OpenAICompatProvider(_config(), client=fake)
    assert provider.chat([{"role": "user", "content": "q"}], json_mode=True) == "ok"
    first, second = fake.chat.completions.calls
    assert "response_format" in first
    assert "response_format" not in second  # 400 后退回普通模式


def test_permanent_error_wraps_as_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_KEY", "k-test")
    fake = _FakeClient([_FakeHTTPError("invalid api key")])
    provider = OpenAICompatProvider(_config(), client=fake)
    with pytest.raises(ProviderError, match="provider=fake"):
        provider.chat([{"role": "user", "content": "q"}])


def test_get_provider_unknown_name_fails_fast() -> None:
    with pytest.raises(ProviderError, match="未知 provider"):
        get_provider("no-such-provider")


def test_mock_provider_works_offline() -> None:
    provider = get_provider("mock")
    content = provider.chat([{"role": "user", "content": "x"}], json_mode=True)
    assert '"entities"' in content  # 离线样例抽取
