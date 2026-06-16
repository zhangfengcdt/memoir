"""
Tests for the Hermes memoir memory provider plugin (plugins/hermes/).

The plugin runs in-process inside Hermes but must also import cleanly WITHOUT
hermes-agent installed (packaging hygiene + so these tests run in this repo).
We load it via importlib from the plugin directory; the package's relative
`from .bridge import` falls back to a flat `from bridge import` when exec'd
outside a package, and the MemoryProvider ABC falls back to `object`.

The bridge's subprocess calls are never made here — a fake bridge is injected.

Run with: pytest tests/test_hermes_plugin.py -v
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "hermes"


@pytest.fixture(scope="module")
def plugin():
    """Load the plugin package (provider) and its bridge module."""
    sys.path.insert(0, str(_PLUGIN_DIR))
    import bridge as bridge_mod

    spec = importlib.util.spec_from_file_location(
        "hermes_memoir_provider", _PLUGIN_DIR / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod, bridge_mod
    if str(_PLUGIN_DIR) in sys.path:
        sys.path.remove(str(_PLUGIN_DIR))


_DEFAULT_RECALL_ITEMS = [
    {
        "key": "preferences.food.dietary",
        "found": True,
        "value": {"content": "vegetarian"},
    },
    {
        "key": "schedule.recurring.hobbies",
        "found": True,
        "value": {"content": "yoga on Mondays"},
    },
    {"key": "missing.key.here", "found": False, "value": None},
]


class FakeBridge:
    """Records calls; returns canned (ok, payload) tuples — no subprocess."""

    def __init__(self, store_path=".", *, avail=True):
        self.store_path = store_path
        self.model = None
        self._avail = avail
        self.captures = []
        self.remembers = []
        self.recalls = []
        self.forgets = []
        self.checkouts = []
        self.syncs = []
        self.existing_branches = {"main"}  # branches that "exist" here
        self.current = "main"
        # Per-branch dry-run preview override: {branch: {"added_keys":[...]}}.
        self.sync_previews: dict = {}
        # Per-namespace recall items override: {namespace: [items]}.
        self.recall_items: dict = {}
        # Namespaces where forget reports the key absent (for fallback tests).
        self.forget_absent: set = set()

    def available(self):
        return self._avail

    def ensure_store(self):
        return True

    def summarize(self, depth=3, namespace="default"):
        return True, {"total_memories": 7}

    def capture(self, transcript, *, profile="assistant", namespace="default"):
        self.captures.append((transcript, profile, namespace))
        return True, {"captured": []}

    def recall(self, *, namespace="default", max_keys=50):
        self.recalls.append((namespace, max_keys))
        items = self.recall_items.get(namespace, _DEFAULT_RECALL_ITEMS)
        return True, {"items": items}

    def remember(self, content, *, path=None, replace=False, namespace="default"):
        self.remembers.append((content, path, replace, namespace))
        return True, {"key": path or "auto.path.here"}

    def forget(self, path, *, namespace="default"):
        self.forgets.append((path, namespace))
        if namespace in self.forget_absent:
            return True, {"found": False, "key": path}
        return True, {"key": path, "commit_hash": "abc123de"}

    def status(self):
        return True, {"branch": "main", "commit_count": 3, "memory_count": 5}

    def checkout(self, branch, *, create=False):
        self.checkouts.append((branch, create))
        if create:
            self.existing_branches.add(branch)
        self.current = branch
        return True, {"branch": branch}

    def has_branch(self, branch):
        return branch in self.existing_branches

    def branches(self):
        return True, {
            "branches": sorted(self.existing_branches),
            "current": self.current,
        }

    def sync_branch(self, source, *, into="main", dry_run=False):
        self.syncs.append((source, into, dry_run))
        prev = self.sync_previews.get(source, {"added_keys": ["a.b.c"]})
        out = {
            "success": True,
            "added_keys": prev.get("added_keys", []),
            "updated_keys": prev.get("updated_keys", []),
            "restored_branch": "main",
        }
        if not dry_run:
            out["commit_hash"] = "sync1234"
        return True, out


def _make_provider(plugin, **overrides):
    mod, _ = plugin
    p = mod.MemoirProvider()
    p._bridge = overrides.get("bridge", FakeBridge())
    p._capture_enabled = overrides.get("capture_enabled", True)
    p._agent_context = overrides.get("agent_context", "primary")
    return p


# ---------------------------------------------------------------------------
# Packaging / import hygiene
# ---------------------------------------------------------------------------


class TestImportHygiene:
    def test_imports_without_hermes(self, plugin):
        mod, _ = plugin
        # hermes-agent isn't installed here, so the ABC falls back to object.
        assert mod.MemoirProvider.__mro__[1] is object

    def test_register_calls_register_memory_provider(self, plugin):
        mod, _ = plugin
        captured = {}

        class Ctx:
            def register_memory_provider(self, provider):
                captured["provider"] = provider

        mod.register(Ctx())
        assert isinstance(captured["provider"], mod.MemoirProvider)
        assert captured["provider"].name == "memoir"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    @pytest.mark.parametrize(
        "text",
        [
            "my password = hunter2longvalue",
            "sk-abcdefghijklmnop0123456789",
            "AKIAIOSFODNN7EXAMPLE",
            "ghp_0123456789abcdefghij0123",
            "4111111111111111",
        ],
    )
    def test_secret_detector_flags(self, plugin, text):
        mod, _ = plugin
        assert mod._looks_like_secret(text) is True

    def test_secret_detector_allows_normal_facts(self, plugin):
        mod, _ = plugin
        assert mod._looks_like_secret("Prefers vegetarian meals") is False
        assert mod._looks_like_secret("Daughter Mia has piano on Tuesdays") is False

    def test_slugify(self, plugin):
        mod, _ = plugin
        assert mod._slugify("User Profile") == "user_profile"
        assert mod._slugify("") == "note"
        assert mod._slugify("favorite-color!") == "favorite_color"

    def test_messages_to_transcript(self, plugin):
        mod, _ = plugin
        msgs = [
            {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "I'm vegetarian"},
            {"role": "assistant", "content": "Noted."},
            {"role": "tool", "content": "ignore"},
        ]
        out = mod._messages_to_transcript(msgs)
        assert "[Human]\nI'm vegetarian" in out
        assert "[Assistant]\nNoted." in out
        assert "ignore me" not in out

    def test_messages_to_transcript_multimodal(self, plugin):
        mod, _ = plugin
        msgs = [{"role": "user", "content": [{"type": "text", "text": "hi there"}]}]
        assert "[Human]\nhi there" in mod._messages_to_transcript(msgs)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class TestTools:
    def test_tool_schemas(self, plugin):
        p = _make_provider(plugin)
        names = {s["name"] for s in p.get_tool_schemas()}
        assert names == {
            "memoir_recall",
            "memoir_remember",
            "memoir_forget",
            "memoir_sync",
            "memoir_status",
        }

    def test_recall_tool(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(p.handle_tool_call("memoir_recall", {"query": "food dietary"}))
        # Two found items returned (the not-found one is dropped); the
        # query-matching item ranks first.
        assert out["count"] == 2
        assert out["results"][0]["path"] == "preferences.food.dietary"
        assert {r["path"] for r in out["results"]} == {
            "preferences.food.dietary",
            "schedule.recurring.hobbies",
        }

    def test_recall_requires_query(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(p.handle_tool_call("memoir_recall", {}))
        assert "error" in out

    def test_remember_tool(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(
            p.handle_tool_call("memoir_remember", {"content": "Prefers tea"})
        )
        assert out["stored"] is True
        assert p._bridge.remembers == [("Prefers tea", None, False, "default")]

    def test_remember_refuses_secret(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(
            p.handle_tool_call(
                "memoir_remember", {"content": "my api_key = sk-abcdef0123456789xyz"}
            )
        )
        assert "error" in out
        assert p._bridge.remembers == []  # nothing stored

    def test_forget_tool(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(
            p.handle_tool_call("memoir_forget", {"path": "profile.personal.pets"})
        )
        assert out["forgotten"] is True
        assert out["key"] == "profile.personal.pets"
        assert p._bridge.forgets == [("profile.personal.pets", "default")]

    def test_forget_requires_path(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(p.handle_tool_call("memoir_forget", {}))
        assert "error" in out
        assert p._bridge.forgets == []

    def test_forget_not_found(self, plugin):
        p = _make_provider(plugin)
        # Bridge reports the key was absent (no commit created).
        p._bridge.forget = lambda path, **kw: (True, {"found": False, "key": path})
        out = json.loads(p.handle_tool_call("memoir_forget", {"path": "no.such.key"}))
        assert out["forgotten"] is False
        assert "error" in out

    def test_sync_lists_unmerged_branches(self, plugin):
        p = _make_provider(plugin)
        p._bridge.existing_branches.update({"hermes/f1", "hermes/f2"})
        p._bridge.sync_previews = {
            "hermes/f1": {"added_keys": ["a.b.c", "d.e.f"], "updated_keys": []},
            "hermes/f2": {"added_keys": [], "updated_keys": []},  # nothing to merge
        }
        out = json.loads(p.handle_tool_call("memoir_sync", {}))
        # Only f1 has changes; f2 (and main/current) are excluded.
        assert out["count"] == 1
        assert out["unmerged"][0]["branch"] == "hermes/f1"
        assert out["unmerged"][0]["added"] == 2

    def test_sync_excludes_main_and_current(self, plugin):
        p = _make_provider(plugin)
        p._bridge.existing_branches.update({"hermes/cur"})
        p._bridge.current = "hermes/cur"  # checked-out branch is skipped
        p._bridge.sync_previews = {"hermes/cur": {"added_keys": ["x.y.z"]}}
        out = json.loads(p.handle_tool_call("memoir_sync", {}))
        assert out["count"] == 0

    def test_sync_dry_run_preview(self, plugin):
        p = _make_provider(plugin)
        p._bridge.sync_previews = {"hermes/f1": {"added_keys": ["a.b.c"]}}
        out = json.loads(
            p.handle_tool_call("memoir_sync", {"branch": "hermes/f1", "dry_run": True})
        )
        assert out["dry_run"] is True
        assert out["added"] == 1
        assert p._bridge.syncs == [("hermes/f1", "main", True)]

    def test_sync_merges_branch(self, plugin):
        p = _make_provider(plugin)
        p._bridge.sync_previews = {"hermes/f1": {"added_keys": ["a.b.c", "d.e.f"]}}
        out = json.loads(p.handle_tool_call("memoir_sync", {"branch": "hermes/f1"}))
        assert out["merged"] is True
        assert out["into"] == "main"
        assert out["added"] == 2
        assert out["commit"] == "sync1234"
        assert p._bridge.syncs == [("hermes/f1", "main", False)]

    def test_status_tool(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(p.handle_tool_call("memoir_status", {}))
        assert out["branch"] == "main"

    def test_unknown_tool(self, plugin):
        p = _make_provider(plugin)
        out = json.loads(p.handle_tool_call("nope", {}))
        assert "error" in out

    def test_unavailable_bridge_degrades(self, plugin):
        p = _make_provider(plugin, bridge=FakeBridge(avail=False))
        out = json.loads(p.handle_tool_call("memoir_recall", {"query": "x"}))
        assert "error" in out


# ---------------------------------------------------------------------------
# Capture (write) paths
# ---------------------------------------------------------------------------


class TestCapture:
    def test_sync_turn_captures(self, plugin):
        p = _make_provider(plugin)
        p.sync_turn("I'm vegetarian", "Noted.", messages=[{}, {}])
        p.shutdown()  # join the background capture thread
        assert len(p._bridge.captures) == 1
        transcript, profile, ns = p._bridge.captures[0]
        assert "[Human]\nI'm vegetarian" in transcript
        assert "[Assistant]\nNoted." in transcript
        assert profile == "assistant"
        assert ns == "default"  # unscoped by default
        assert p._captured_through == 2

    def test_sync_turn_skips_non_primary_context(self, plugin):
        p = _make_provider(plugin, agent_context="subagent")
        p.sync_turn("hello", "hi")
        p.shutdown()
        assert p._bridge.captures == []

    def test_sync_turn_skips_when_capture_disabled(self, plugin):
        p = _make_provider(plugin, capture_enabled=False)
        p.sync_turn("hello", "hi")
        p.shutdown()
        assert p._bridge.captures == []

    def test_pre_compress_sweeps_only_tail(self, plugin):
        p = _make_provider(plugin)
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ok"},
        ]
        p.sync_turn("first", "ok", messages=msgs)
        # Two more messages appended after the turn was captured.
        msgs += [
            {"role": "user", "content": "remember I like tea"},
            {"role": "assistant", "content": "got it"},
        ]
        ret = p.on_pre_compress(msgs)
        p.shutdown()
        assert ret == ""  # contributes nothing to the compression summary
        # The session-end-style sweep captured only the new tail.
        tail_transcript = p._bridge.captures[-1][0]
        assert "remember I like tea" in tail_transcript
        assert "first" not in tail_transcript

    def test_on_memory_write_mirrors(self, plugin):
        p = _make_provider(plugin)
        p.on_memory_write("add", "User Profile", "Lives in Seattle")
        p.shutdown()
        # join the mirror thread by polling briefly
        import time

        for _ in range(50):
            if p._bridge.remembers:
                break
            time.sleep(0.02)
        assert p._bridge.remembers
        _content, path, replace, _ns = p._bridge.remembers[0]
        assert path == "profile.assistant.user_profile"
        assert replace is True

    def test_on_memory_write_ignores_removals_and_secrets(self, plugin):
        p = _make_provider(plugin)
        p.on_memory_write("remove", "x", "anything")
        p.on_memory_write("add", "creds", "password = supersecretvalue")
        p.shutdown()
        assert p._bridge.remembers == []


# ---------------------------------------------------------------------------
# Bridge CLI resolution
# ---------------------------------------------------------------------------


class TestBridgeResolution:
    def test_prefers_path_memoir(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        monkeypatch.setattr(
            bridge_mod.shutil,
            "which",
            lambda name: "/usr/bin/memoir" if name == "memoir" else None,
        )
        b = bridge_mod.MemoirBridge("/tmp/x")
        assert b._cli() == ["memoir"]
        assert b.available() is True

    def test_falls_back_to_uvx(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        monkeypatch.setattr(
            bridge_mod.shutil,
            "which",
            lambda name: "/usr/bin/uvx" if name == "uvx" else None,
        )
        b = bridge_mod.MemoirBridge("/tmp/x")
        argv = b._cli()
        assert argv[0] == "uvx"
        assert f"memoir-ai=={bridge_mod.MEMOIR_AI_PIN}" in argv

    def test_recall_summarizes_then_gets_excluding_metrics(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args[0] == "summarize":
                return True, {
                    "prefix_counts": {
                        "default": {
                            "preferences.food.dietary": 1,
                            "metrics.turn.main": 1,
                        }
                    }
                }
            if args[0] == "get":
                keys = [a for a in args[1:] if a not in ("-n", "default")]
                return True, {
                    "items": [
                        {"key": k, "found": True, "value": {"content": "x"}}
                        for k in keys
                    ]
                }
            return True, {}

        monkeypatch.setattr(b, "run", fake_run)
        ok, _payload = b.recall()
        assert ok
        get_call = next(c for c in calls if c[0] == "get")
        assert "preferences.food.dietary" in get_call
        assert "metrics.turn.main" not in get_call  # machine metrics excluded

    def test_recall_empty_namespace_degrades_to_empty(self, plugin, monkeypatch):
        # A fresh store has no `default` namespace yet — summarize errors with
        # "not found"; recall must treat that as "nothing stored", not an error.
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")

        def fake_run(args, **kw):
            if args[0] == "summarize":
                return False, {
                    "error": "Namespace 'default' not found. Available: taxonomy"
                }
            raise AssertionError("get should not be called when summarize is empty")

        monkeypatch.setattr(b, "run", fake_run)
        ok, payload = b.recall()
        assert ok is True
        assert payload == {"items": []}

    def test_forget_existing_key_deletes(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args[0] == "get":
                return True, {"items": [{"key": args[1], "found": True}]}
            if args[0] == "forget":
                return True, {"success": True, "key": args[1], "commit_hash": "c0ffee"}
            return True, {}

        monkeypatch.setattr(b, "run", fake_run)
        ok, payload = b.forget("profile.personal.pets")
        assert ok is True
        assert payload["commit_hash"] == "c0ffee"
        assert any(c[0] == "forget" for c in calls)

    def test_forget_missing_key_skips_commit(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            if args[0] == "get":
                return True, {"items": [{"key": args[1], "found": False}]}
            return True, {}

        monkeypatch.setattr(b, "run", fake_run)
        ok, payload = b.forget("no.such.key")
        assert ok is True
        assert payload == {"found": False, "key": "no.such.key"}
        # No `forget` subprocess — we don't create no-op delete commits.
        assert not any(c[0] == "forget" for c in calls)

    def test_unavailable_when_nothing_resolves(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        monkeypatch.setattr(bridge_mod.shutil, "which", lambda name: None)
        b = bridge_mod.MemoirBridge("/tmp/x")
        assert b._cli() is None
        assert b.available() is False
        ok, payload = b.run(["status"])
        assert ok is False
        assert "error" in payload

    def test_env_forces_litellm_and_passes_model_and_base_url(self, plugin):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge(
            "/tmp/x", model="claude-opus-4-8", base_url="https://proxy.example/v1"
        )
        env = b._build_env()
        # Never claude-cli; always direct provider API.
        assert env["MEMOIR_LLM_BACKEND"] == "litellm"
        assert env["MEMOIR_LLM_MODEL"] == "claude-opus-4-8"
        assert env["MEMOIR_LLM_BASE_URL"] == "https://proxy.example/v1"

    def test_env_omits_model_and_base_url_when_unset(self, plugin):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")
        env = b._build_env()
        assert env["MEMOIR_LLM_BACKEND"] == "litellm"
        # Both fall through to memoir's own defaults / provider default.
        assert "MEMOIR_LLM_MODEL" not in env
        assert "MEMOIR_LLM_BASE_URL" not in env


class TestModelSelection:
    def test_config_model_pins(self, plugin, monkeypatch, tmp_path):
        mod, bridge_mod = plugin
        # Keep initialize hermetic: unavailable CLI → returns right after the
        # bridge (with its model) is constructed, no real `memoir new`.
        monkeypatch.setattr(bridge_mod.shutil, "which", lambda name: None)
        # memoir.json pins a model; it must win over any host model.
        (tmp_path / "memoir.json").write_text(json.dumps({"model": "gpt-4o-mini"}))
        monkeypatch.setattr(
            mod.MemoirProvider, "_host_model", staticmethod(lambda: "claude-opus-4-8")
        )
        p = mod.MemoirProvider()
        p.initialize("s", hermes_home=str(tmp_path), agent_context="primary")
        assert p._bridge.model == "gpt-4o-mini"

    def test_follows_host_model_when_unpinned(self, plugin, monkeypatch, tmp_path):
        mod, bridge_mod = plugin
        monkeypatch.setattr(bridge_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            mod.MemoirProvider, "_host_model", staticmethod(lambda: "claude-opus-4-8")
        )
        p = mod.MemoirProvider()
        p.initialize("s", hermes_home=str(tmp_path), agent_context="primary")
        assert p._bridge.model == "claude-opus-4-8"

    def test_on_turn_start_tracks_live_model(self, plugin):
        p = _make_provider(plugin)  # no config pin
        p._config_model = None
        p.on_turn_start(1, "hi", model="claude-sonnet-4-6")
        assert p._bridge.model == "claude-sonnet-4-6"

    def test_on_turn_start_respects_pin(self, plugin):
        p = _make_provider(plugin)
        p._config_model = "gpt-4o-mini"
        p._bridge.model = "gpt-4o-mini"
        p.on_turn_start(1, "hi", model="claude-opus-4-8")
        assert p._bridge.model == "gpt-4o-mini"  # pin not overridden

    def test_base_url_from_config_flows_to_bridge(self, plugin, monkeypatch, tmp_path):
        mod, bridge_mod = plugin
        monkeypatch.setattr(bridge_mod.shutil, "which", lambda name: None)
        (tmp_path / "memoir.json").write_text(
            json.dumps({"base_url": "https://proxy.example/v1"})
        )
        p = mod.MemoirProvider()
        p.initialize("s", hermes_home=str(tmp_path), agent_context="primary")
        assert p._bridge.base_url == "https://proxy.example/v1"


class TestSessionBranching:
    def test_branch_for_session_sanitizes(self, plugin):
        mod, _ = plugin
        assert mod.MemoirProvider._branch_for_session("abc-123") == "hermes/abc-123"
        # Unsafe ref chars collapse to '-'.
        assert mod.MemoirProvider._branch_for_session("a b:c~/..") == "hermes/a-b-c"
        assert mod.MemoirProvider._branch_for_session("") == "hermes/session"

    def test_fork_creates_and_checks_out_branch(self, plugin):
        p = _make_provider(plugin)
        p.on_session_switch("fork1", parent_session_id="root", reason="branch")
        assert p._bridge.checkouts == [("hermes/fork1", True)]

    def test_resume_existing_fork_checks_out_its_branch(self, plugin):
        p = _make_provider(plugin)
        p._bridge.existing_branches.add("hermes/fork1")  # fork branch exists
        p.on_session_switch("fork1", parent_session_id="root", reason="resume")
        assert p._bridge.checkouts == [("hermes/fork1", False)]

    def test_resume_non_forked_session_returns_to_main(self, plugin):
        p = _make_provider(plugin)
        p.on_session_switch("plain", parent_session_id="root", reason="resume")
        assert p._bridge.checkouts == [("main", False)]

    def test_compression_does_not_switch_branch(self, plugin):
        p = _make_provider(plugin)
        p.on_session_switch(
            "rolled-over-id", parent_session_id="root", reason="compression"
        )
        assert p._bridge.checkouts == []  # continuation — stay put

    def test_reset_returns_to_main(self, plugin):
        p = _make_provider(plugin)
        p.on_session_switch("whatever", reset=True, reason="resume")
        assert p._bridge.checkouts == [("main", False)]
        assert p._captured_through == 0  # capture cursor reset

    def test_disabled_branching_never_checks_out(self, plugin):
        p = _make_provider(plugin)
        p._branching_enabled = False
        p.on_session_switch("fork1", reason="branch")
        assert p._bridge.checkouts == []

    def test_shutdown_resets_to_main(self, plugin):
        # Exiting a session (e.g. a fork) must leave the store on main.
        p = _make_provider(plugin)
        p._store_path = ""  # avoid real event-file writes
        p.shutdown()
        assert ("main", False) in p._bridge.checkouts

    def test_disabled_branching_shutdown_no_reset(self, plugin):
        p = _make_provider(plugin)
        p._store_path = ""
        p._branching_enabled = False
        p.shutdown()
        assert p._bridge.checkouts == []

    def test_switch_is_visible_in_session(self, plugin, capsys):
        p = _make_provider(plugin)
        p.on_session_switch("fork1", parent_session_id="root", reason="branch")
        err = capsys.readouterr().err
        assert "memoir" in err
        assert "hermes/fork1" in err

    def test_failed_switch_surfaces_error(self, plugin, capsys):
        p = _make_provider(plugin)
        p._bridge.checkout = lambda branch, **kw: (False, {"error": "boom"})
        p.on_session_switch("fork1", parent_session_id="root", reason="branch")
        err = capsys.readouterr().err
        assert "failed" in err
        assert "boom" in err

    def test_bridge_checkout_and_has_branch(self, plugin, monkeypatch):
        _, bridge_mod = plugin
        b = bridge_mod.MemoirBridge("/tmp/x")

        def fake_run(args, **kw):
            if args[0] == "checkout":
                return True, {"branch": args[1]}
            if args[0] == "branch":
                return True, {"branches": ["main", "hermes/fork1"], "current": "main"}
            return True, {}

        monkeypatch.setattr(b, "run", fake_run)
        ok, _ = b.checkout("hermes/fork1", create=True)
        assert ok is True
        assert b.has_branch("hermes/fork1") is True
        assert b.has_branch("hermes/nope") is False


class TestScopedMemory:
    def test_derive_scope_ns(self, plugin):
        mod, _ = plugin
        d = mod.MemoirProvider._derive_scope_ns
        assert (
            d("chat", {"platform": "telegram", "chat_id": "123456789"})
            == "scope_telegram_123456789"
        )
        assert d("profile", {"agent_identity": "work"}) == "scope_profile_work"
        # Off, or missing scope key → shared default (current behavior).
        assert d("off", {"chat_id": "123"}) == "default"
        assert d("chat", {}) == "default"
        assert d("profile", {}) == "default"

    def test_derive_scope_ns_sanitizes(self, plugin):
        mod, _ = plugin
        # Namespaces can't contain ':' — everything non-alphanumeric collapses.
        ns = mod.MemoirProvider._derive_scope_ns(
            "chat", {"platform": "Tele Gram", "chat_id": "abc-123:x"}
        )
        assert ns == "scope_tele_gram_abc_123_x"
        assert ":" not in ns

    def test_initialize_resolves_scope(self, plugin, monkeypatch, tmp_path):
        mod, bridge_mod = plugin
        monkeypatch.setattr(bridge_mod.shutil, "which", lambda name: None)
        (tmp_path / "memoir.json").write_text(json.dumps({"scope": "chat"}))
        p = mod.MemoirProvider()
        p.initialize(
            "s",
            hermes_home=str(tmp_path),
            agent_context="primary",
            platform="telegram",
            chat_id="98765",
        )
        assert p._scope_mode == "chat"
        assert p._scope_ns == "scope_telegram_98765"

    def test_scope_off_reads_only_default(self, plugin):
        p = _make_provider(plugin)  # scope off → _scope_ns == "default"
        assert p._recall_namespaces() == ["default"]

    def test_scoped_capture_and_remember_use_scope_ns(self, plugin):
        p = _make_provider(plugin)
        p._scope_ns = "scope_telegram_123"
        p.sync_turn("I'm vegetarian", "Noted.", messages=[{}, {}])
        p.shutdown()
        assert p._bridge.captures[0][2] == "scope_telegram_123"  # capture namespace
        p.handle_tool_call("memoir_remember", {"content": "Prefers tea"})
        assert p._bridge.remembers[0][3] == "scope_telegram_123"  # remember namespace

    def test_scoped_recall_merges_default_and_scope(self, plugin):
        p = _make_provider(plugin)
        p._scope_ns = "scope_x"
        p._bridge.recall_items = {
            "scope_x": [
                {
                    "key": "goals.personal.travel",
                    "found": True,
                    "value": {"content": "Japan (private)"},
                },
            ],
            "default": [
                {
                    "key": "profile.personal.identity",
                    "found": True,
                    "value": {"content": "Jordan"},
                },
                {
                    "key": "goals.personal.travel",
                    "found": True,
                    "value": {"content": "GLOBAL"},
                },
            ],
        }
        out = json.loads(
            p.handle_tool_call("memoir_recall", {"query": "travel identity"})
        )
        # Reads both namespaces; scope shadows the same-key global entry.
        assert {n for n, _ in p._bridge.recalls} == {"scope_x", "default"}
        by_path = {r["path"]: r["content"] for r in out["results"]}
        assert by_path["goals.personal.travel"] == "Japan (private)"
        assert by_path["profile.personal.identity"] == "Jordan"

    def test_scoped_forget_falls_back_to_default(self, plugin):
        p = _make_provider(plugin)
        p._scope_ns = "scope_x"
        p._bridge.forget_absent = {"scope_x"}  # key isn't in the scope ns
        out = json.loads(
            p.handle_tool_call("memoir_forget", {"path": "profile.personal.identity"})
        )
        assert out["forgotten"] is True
        # Tried scope first, then default.
        assert [ns for _, ns in p._bridge.forgets] == ["scope_x", "default"]
