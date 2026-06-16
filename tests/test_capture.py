"""
Tests for `memoir capture` — turn-transcript fact extraction.

Extraction (the LLM call) is mocked; the storage path (pre-classified
`remember`) runs for real against a temp store, so these exercise the full
parse → filter → persist plumbing without network or API keys.

Run with: pytest tests/test_capture.py -v
"""

import json
import os
import shutil
import tempfile

import pytest
from click.testing import CliRunner

from memoir.cli.commands.capture import _parse_facts
from memoir.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store():
    """A freshly initialized temp store."""
    path = tempfile.mkdtemp(prefix="memoir_capture_test_")
    CliRunner().invoke(cli, ["new", path])
    yield path
    if os.path.exists(path):
        shutil.rmtree(path)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """Stand-in for the litellm/claude-cli wrapper: returns canned TSV."""

    def __init__(self, content):
        self._content = content

    async def ainvoke(self, prompt):
        # Capture must pass a system+user message list, not a bare string.
        assert isinstance(prompt, list)
        roles = [m["role"] for m in prompt]
        assert roles == ["system", "user"]
        return _FakeResp(self._content)


def _patch_llm(monkeypatch, content):
    monkeypatch.setattr("memoir.llm.get_llm", lambda **kw: _FakeLLM(content))


# ---------------------------------------------------------------------------
# _parse_facts — pure transcript-output parsing
# ---------------------------------------------------------------------------


class TestParseFacts:
    def test_single_fact(self):
        out = _parse_facts("preferences.food.dietary\tPrefers vegetarian meals")
        assert out == [(["preferences.food.dietary"], "Prefers vegetarian meals")]

    def test_multi_path_line(self):
        line = "relationships.family.children,schedule.recurring.hobbies\tMia has piano Tuesdays"
        out = _parse_facts(line)
        assert out == [
            (
                ["relationships.family.children", "schedule.recurring.hobbies"],
                "Mia has piano Tuesdays",
            )
        ]

    def test_drops_lines_without_tab(self):
        assert _parse_facts("here are the facts I found:") == []

    def test_drops_short_facts(self):
        # Fact below the minimum length guard.
        assert _parse_facts("preferences.food.dietary\tno") == []

    def test_drops_invalid_paths(self):
        # Uppercase / hyphen / single-segment paths must be rejected.
        bad = "\n".join(
            [
                "Preferences.Food.Dietary\tvalid-looking fact text",
                "food-dietary.x.y\tvalid-looking fact text",
                "singleword\tvalid-looking fact text",
            ]
        )
        assert _parse_facts(bad) == []

    def test_accepts_two_to_four_levels(self):
        text = "\n".join(
            [
                "profile.personal\ttwo level fact here",
                "a.b.c.d\tfour level fact here",
            ]
        )
        out = _parse_facts(text)
        assert [p for p, _ in out] == [["profile.personal"], ["a.b.c.d"]]

    def test_mixed_valid_and_noise(self):
        text = "\n".join(
            [
                "Here's what I found:",
                "preferences.food.dietary\tPrefers vegetarian meals",
                "",
                "garbage line no tab",
            ]
        )
        out = _parse_facts(text)
        assert out == [(["preferences.food.dietary"], "Prefers vegetarian meals")]


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


class TestCaptureCLI:
    def test_empty_stdin_is_silent(self, runner, store):
        result = runner.invoke(cli, ["--json", "-s", store, "capture"], input="")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {"captured": [], "count": 0, "profile": "assistant"}

    def test_extraction_persists_facts(self, runner, store, monkeypatch):
        _patch_llm(
            monkeypatch,
            "preferences.food.dietary\tPrefers vegetarian meals\n"
            "profile.personal.name\tGoes by Dr. Chen",
        )
        result = runner.invoke(
            cli,
            ["--json", "-s", store, "capture", "--profile", "assistant"],
            input="[Human]\nI'm vegetarian, call me Dr. Chen\n[Assistant]\nGot it.\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["count"] == 2
        paths = {item["key"] for item in data["captured"]}
        assert paths == {"preferences.food.dietary", "profile.personal.name"}
        # Each capture created a commit.
        assert all(item["commit_hash"] for item in data["captured"])

        # The facts are actually retrievable from the store.
        got = runner.invoke(
            cli, ["--json", "-s", store, "get", "preferences.food.dietary"]
        )
        assert "vegetarian" in got.output.lower()

    def test_multipath_fact_stored_at_all_paths(self, runner, store, monkeypatch):
        _patch_llm(
            monkeypatch,
            "relationships.family.children,schedule.recurring.hobbies"
            "\tDaughter Mia has piano every Tuesday",
        )
        result = runner.invoke(
            cli,
            ["--json", "-s", store, "capture"],
            input="[Human]\nMia has piano Tuesdays\n[Assistant]\nNoted.\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["count"] == 1
        assert set(data["captured"][0]["keys"]) == {
            "relationships.family.children",
            "schedule.recurring.hobbies",
        }

    def test_silent_extraction_returns_empty(self, runner, store, monkeypatch):
        # Model emitted nothing durable — the normal case.
        _patch_llm(monkeypatch, "")
        result = runner.invoke(
            cli,
            ["--json", "-s", store, "capture"],
            input="[Human]\nwhat time is it?\n[Assistant]\n3pm.\n",
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 0
        assert data["captured"] == []

    def test_malformed_output_filtered(self, runner, store, monkeypatch):
        _patch_llm(
            monkeypatch,
            "Sure! Here are the durable facts:\n"
            "preferences.food.dietary\tPrefers vegetarian meals\n"
            "this line has no tab and should be dropped",
        )
        result = runner.invoke(
            cli,
            ["--json", "-s", store, "capture"],
            input="[Human]\nx\n[Assistant]\ny\n",
        )
        data = json.loads(result.output)
        assert data["count"] == 1

    def test_coding_profile_selectable(self, runner, store, monkeypatch):
        _patch_llm(
            monkeypatch,
            "workflow.coding.testing\tRuns make test before every commit",
        )
        result = runner.invoke(
            cli,
            ["--json", "-s", store, "capture", "--profile", "coding"],
            input="[Human]\nalways run make test first\n[Assistant]\nWill do.\n",
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["profile"] == "coding"
        assert data["count"] == 1

    def test_no_store_errors(self, runner, monkeypatch, tmp_path):
        monkeypatch.delenv("MEMOIR_STORE", raising=False)
        monkeypatch.chdir(tmp_path)  # not a store
        _patch_llm(monkeypatch, "preferences.food.dietary\tlikes pizza a lot")
        result = runner.invoke(cli, ["capture"], input="[Human]\nx\n[Assistant]\ny\n")
        # cwd fallback is not a real store → storage fails, non-zero exit.
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Packaged templates
# ---------------------------------------------------------------------------


class TestTemplates:
    @pytest.mark.parametrize("profile", ["assistant", "coding"])
    def test_template_exists_and_has_placeholder(self, profile):
        from memoir.cli.commands.capture import _load_template

        tmpl = _load_template(profile)
        assert "${TAXONOMY_BLOCK}" in tmpl
        assert "<TAB>" in tmpl  # output-format contract documented
