"""
Tests for get_llm backend resolution — specifically that an explicitly
requested litellm backend is honored STRICTLY (no silent claude-cli
fallback), while the default (unset) keeps the convenient auto-fallback.

This underpins the Hermes plugin's requirement to never shell out to the
`claude` CLI.

Run with: pytest tests/test_llm_backend.py -v
"""

import pytest

from memoir.llm.claude_cli_client import ClaudeCLIWrapper
from memoir.llm.litellm_client import get_llm


@pytest.fixture(autouse=True)
def _no_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _pretend_claude_installed(monkeypatch):
    # get_llm does `import shutil; shutil.which("claude")`.
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None
    )


def test_forced_litellm_does_not_fall_back_to_claude_cli(monkeypatch):
    monkeypatch.setenv("MEMOIR_LLM_BACKEND", "litellm")
    _pretend_claude_installed(monkeypatch)
    # Claude model + no key + claude on PATH would normally auto-fall-back;
    # the explicit litellm backend must force a clear error instead.
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_llm(model="claude-haiku-4-5")


def test_default_backend_still_falls_back(monkeypatch):
    monkeypatch.delenv("MEMOIR_LLM_BACKEND", raising=False)
    _pretend_claude_installed(monkeypatch)
    llm = get_llm(model="claude-haiku-4-5")
    assert isinstance(llm, ClaudeCLIWrapper)


def test_explicit_claude_cli_backend_unaffected(monkeypatch):
    monkeypatch.setenv("MEMOIR_LLM_BACKEND", "claude-cli")
    llm = get_llm(model="claude-haiku-4-5")
    assert isinstance(llm, ClaudeCLIWrapper)


def test_forced_litellm_with_key_builds_litellm(monkeypatch):
    monkeypatch.setenv("MEMOIR_LLM_BACKEND", "litellm")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _pretend_claude_installed(monkeypatch)
    llm = get_llm(model="claude-haiku-4-5")
    assert not isinstance(llm, ClaudeCLIWrapper)  # litellm wrapper
