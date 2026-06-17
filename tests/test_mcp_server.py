# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the memoir MCP server (FastMCP).

Exercises the tool logic (LLM-free) and the FastMCP registration/dispatch layer.
Skipped entirely when the optional ``mcp`` SDK isn't installed.
"""

import asyncio
import os
import subprocess

import pytest

pytest.importorskip("mcp")  # optional extra; skip if not installed

from memoir.mcp import server as S

_FACTS = [
    ("Feng prefers dark mode in all apps", "preferences.ui.theme"),
    ("Allergic to penicillin", "profile.personal.health"),
]


def _populate(store: str) -> None:
    S.ensure_store(store)
    for content, path in _FACTS:
        # LLM-free write with an explicit taxonomy path.
        subprocess.run(
            ["memoir", "-s", store, "remember", content, "-p", path, "-n", "default"],
            capture_output=True,
            check=False,
        )


@pytest.fixture
def store(tmp_path):
    s = str(tmp_path / "store")
    _populate(s)
    return s


def test_ensure_store_idempotent(tmp_path):
    s = str(tmp_path / "s")
    S.ensure_store(s)
    S.ensure_store(s)  # second call must not raise
    assert os.path.isdir(os.path.join(s, ".git"))


def test_resolve_store_path_default(monkeypatch):
    monkeypatch.delenv("MEMOIR_STORE", raising=False)
    assert S.resolve_store_path() == S.DEFAULT_STORE
    monkeypatch.setenv("MEMOIR_STORE", "/tmp/x")
    assert S.resolve_store_path() == "/tmp/x"


def test_recall_llm_free_ranks_by_query(store):
    out = S.recall(store, "dark mode theme")
    assert out["success"]
    keys = [m["key"] for m in out["memories"]]
    assert "preferences.ui.theme" in keys
    # taxonomy namespace is excluded from recall
    assert all(m["namespace"] != "taxonomy" for m in out["memories"])


def test_status_and_branches(store):
    assert S.status(store)["branch"] == "main"
    assert "main" in S.branches(store)["branches"]


def test_forget_removes_fact(store):
    res = asyncio.run(S.forget(store, "profile.personal.health"))
    assert res["success"]
    out = S.recall(store, "penicillin")
    assert all(m["key"] != "profile.personal.health" for m in out["memories"])


def test_recall_mode_default_and_env(monkeypatch, tmp_path):
    store = str(tmp_path / "s")
    S.ensure_store(store)

    def recall_mode_default(srv):
        async def run():
            tools = await srv.list_tools()
            recall = next(t for t in tools if t.name == "memoir_recall")
            return recall.inputSchema["properties"]["mode"].get("default")

        return asyncio.run(run())

    monkeypatch.delenv("MEMOIR_MCP_RECALL_MODE", raising=False)
    monkeypatch.delenv("MEMOIR_MCP_SEMANTIC_RECALL", raising=False)
    assert S.default_recall_mode() == "lexical"
    assert recall_mode_default(S.build_server(store)) == "lexical"

    monkeypatch.setenv("MEMOIR_MCP_RECALL_MODE", "tiered")
    assert recall_mode_default(S.build_server(store)) == "tiered"

    monkeypatch.setenv("MEMOIR_MCP_RECALL_MODE", "single")
    assert recall_mode_default(S.build_server(store)) == "single"

    # Back-compat: the old boolean knob still selects single.
    monkeypatch.delenv("MEMOIR_MCP_RECALL_MODE", raising=False)
    monkeypatch.setenv("MEMOIR_MCP_SEMANTIC_RECALL", "1")
    assert S.default_recall_mode() == "single"


def test_summarize_and_get_drill(store):
    # depth 3 → full keys; the model would pick from these then memoir_get.
    s = S.summarize(store, depth=3)
    keys = list(s["namespaces"]["default"].keys())
    assert "preferences.ui.theme" in keys
    assert all(not k.startswith("metrics.") for k in keys)  # metrics excluded

    # depth 1 → top-level prefixes (drill step for large stores)
    s1 = S.summarize(store, depth=1)
    assert "preferences" in s1["namespaces"]["default"]

    # prefix narrows the branch
    sp = S.summarize(store, depth=3, prefix="preferences")
    assert all(k.startswith("preferences") for k in sp["namespaces"]["default"])

    # get fetches the chosen keys
    got = S.get_memories(store, ["preferences.ui.theme"], namespace="default")
    found = [i for i in got["items"] if i["found"]]
    assert found
    assert "dark mode" in found[0]["content"].lower()

    # missing key → found=False
    miss = S.get_memories(store, ["does.not.exist"], namespace="default")
    assert miss["items"][0]["found"] is False


def test_fastmcp_registration_and_dispatch(store):
    srv = S.build_server(store)

    async def run():
        tools = await srv.list_tools()
        names = {t.name for t in tools}
        assert {
            "memoir_recall",
            "memoir_summarize",
            "memoir_get",
            "memoir_remember",
            "memoir_forget",
            "memoir_status",
            "memoir_branches",
            "memoir_checkout",
            "memoir_commits",
        } <= names
        ann = {t.name: t.annotations for t in tools}
        assert ann["memoir_summarize"].readOnlyHint is True
        assert ann["memoir_get"].readOnlyHint is True
        ann = {t.name: t.annotations for t in tools}
        assert ann["memoir_recall"].readOnlyHint is True
        assert ann["memoir_forget"].destructiveHint is True
        # dispatch a read-only tool through the FastMCP layer
        result = await srv.call_tool("memoir_status", {})
        assert result  # non-empty content
        return True

    assert asyncio.run(run())
