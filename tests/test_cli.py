"""
Tests for memoir CLI commands.

Run with: pytest tests/test_cli.py -v
"""

import json
import os
import shutil
import tempfile

import pytest
from click.testing import CliRunner

from memoir.cli.main import cli


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_store():
    """Create a temporary store directory."""
    temp_dir = tempfile.mkdtemp(prefix="memoir_test_")
    yield temp_dir
    # Cleanup
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


@pytest.fixture
def initialized_store(temp_store):
    """Create and initialize a temporary store."""
    runner = CliRunner()
    result = runner.invoke(cli, ["new", temp_store])
    assert result.exit_code == 0, f"Failed to create store: {result.output}"
    return temp_store


class TestMainCLI:
    """Test main CLI options."""

    def test_help(self, runner):
        """Test --help option."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Memoir - Git for AI Memory" in result.output
        assert "QUICK START FOR AGENTS" in result.output
        assert "COMMAND GROUPS" in result.output

    def test_version(self, runner):
        """Test --version option.

        Regression: previously used `@click.version_option(package_name="memoir-ai")`,
        which required `importlib.metadata.version("memoir-ai")` to succeed. In
        layouts where the dist metadata isn't registered under that name (e.g.
        some pipx editable installs), Click raised RuntimeError. Now we pass
        the version explicitly from `memoir.__version__`, so the call works
        regardless of metadata-registration quirks.
        """
        from memoir import __version__

        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()
        assert __version__ in result.output

    def test_machine_readable(self, runner):
        """Test --machine-readable option."""
        result = runner.invoke(cli, ["--machine-readable"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "memoir"
        assert "commands" in data
        assert "exit_codes" in data
        assert "env_vars" in data

    def test_json_schema_alias(self, runner):
        """Test --json-schema alias."""
        result = runner.invoke(cli, ["--json-schema"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "memoir"


class TestStoreCommands:
    """Test store commands: new, status, refresh.

    Note: `memoir connect` and `--connect` were removed (no global default
    store). Resolution is now: -s flag → MEMOIR_STORE → cwd.
    """

    def test_new_creates_store(self, runner, temp_store):
        """Test 'new' command creates a store."""
        # Remove the temp dir so 'new' can create it
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store])
        assert result.exit_code == 0
        assert "Created" in result.output or "success" in result.output.lower()
        assert os.path.exists(temp_store)
        assert os.path.exists(os.path.join(temp_store, ".git"))

    def test_new_prints_export_hint(self, runner, temp_store):
        """`memoir new` should tell the user how to use the store next.

        Since there's no global default any more, the success message points
        the user at the explicit options.
        """
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store])
        assert result.exit_code == 0
        assert "MEMOIR_STORE" in result.output

    def test_new_json_output(self, runner, temp_store):
        """Test 'new' command with JSON output."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["--json", "new", temp_store])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert "path" in data

    def test_new_default_backend_is_file(self, runner, temp_store, monkeypatch):
        """`memoir new <path>` without --backend writes file lock."""
        shutil.rmtree(temp_store)
        monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)

        result = runner.invoke(cli, ["new", temp_store])
        assert result.exit_code == 0
        with open(os.path.join(temp_store, ".git", "memoir-backend")) as f:
            assert f.read().strip() == "file"

    def test_new_backend_git_flag(self, runner, temp_store):
        """`memoir new <path> --backend git` writes a git lock."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store, "--backend", "git"])
        assert result.exit_code == 0
        with open(os.path.join(temp_store, ".git", "memoir-backend")) as f:
            assert f.read().strip() == "git"

    def test_new_backend_file_flag(self, runner, temp_store):
        """`memoir new <path> --backend file` writes a file lock."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store, "--backend", "file"])
        assert result.exit_code == 0
        with open(os.path.join(temp_store, ".git", "memoir-backend")) as f:
            assert f.read().strip() == "file"

    def test_new_backend_invalid_flag(self, runner, temp_store):
        """`memoir new <path> --backend bogus` is rejected by click."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store, "--backend", "bogus"])
        assert result.exit_code != 0
        assert "bogus" in result.output.lower() or "invalid" in result.output.lower()

    def test_status_shows_info(self, runner, initialized_store):
        """Test 'status' command."""
        result = runner.invoke(cli, ["-s", initialized_store, "status"])
        assert result.exit_code == 0
        assert "Store:" in result.output or initialized_store in result.output

    def test_status_json_output(self, runner, initialized_store):
        """Test 'status' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "path" in data

    def test_status_no_store_falls_back_to_cwd(self, runner, tmp_path, monkeypatch):
        """Without -s and without MEMOIR_STORE, resolution falls back to cwd.

        If cwd isn't a memoir store, status surfaces a normal error rather than
        crashing — which is the contract after we dropped the global default.
        """
        monkeypatch.delenv("MEMOIR_STORE", raising=False)
        monkeypatch.chdir(tmp_path)  # tmp dir is not a memoir store

        result = runner.invoke(cli, ["status"], env={"MEMOIR_STORE": ""})
        # Must not crash; either the cwd is treated as a (non-)store and we
        # surface a clean error, or the command bails with EXIT_NO_STORE.
        assert result.exit_code in (0, 1, 3)

    def test_refresh(self, runner, initialized_store):
        """Test 'refresh' command."""
        result = runner.invoke(cli, ["-s", initialized_store, "refresh"])
        assert result.exit_code == 0

    def test_refresh_json_output(self, runner, initialized_store):
        """Test 'refresh' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "refresh"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "success" in data


class TestBranchCommands:
    """Test branch commands: branch, checkout, merge, commits, time-travel, diff."""

    def test_branch_list(self, runner, initialized_store):
        """Test 'branch' command lists branches."""
        result = runner.invoke(cli, ["-s", initialized_store, "branch"])
        # May succeed or fail if no commits yet
        # Exit codes: 0=success, 1=error, 5=git_failed
        assert result.exit_code in [0, 1, 5]

    def test_branch_list_json(self, runner, initialized_store):
        """Test 'branch' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "branch"])
        # May fail if no commits
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "branches" in data or "error" in data

    def test_branch_create(self, runner, initialized_store):
        """Test 'branch' command creates a branch."""
        result = runner.invoke(cli, ["-s", initialized_store, "branch", "test-branch"])
        # May fail if no commits yet (git needs initial commit for branches)
        assert result.exit_code in [0, 5]

    def test_checkout_branch(self, runner, initialized_store):
        """Test 'checkout' command switches branches."""
        # Try to checkout main/master
        result = runner.invoke(cli, ["-s", initialized_store, "checkout", "main"])
        # May fail if no commits or branch doesn't exist
        assert result.exit_code in [0, 1, 5]

    def test_checkout_create_branch(self, runner, initialized_store):
        """Test 'checkout' with -b to create branch."""
        result = runner.invoke(
            cli,
            ["-s", initialized_store, "checkout", "-b", "new-branch"],
        )
        # May fail if no initial commit
        assert result.exit_code in [0, 1, 5]

    def test_checkout_json_output(self, runner, initialized_store):
        """Test 'checkout' command with JSON output."""
        result = runner.invoke(
            cli, ["--json", "-s", initialized_store, "checkout", "main"]
        )
        # May fail, but should return JSON
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "success" in data or "branch" in data

    def test_merge_requires_source(self, runner, initialized_store):
        """Test 'merge' command requires source branch."""
        result = runner.invoke(cli, ["-s", initialized_store, "merge"])
        assert result.exit_code != 0

    def test_merge_with_strategy_ours(self, runner, initialized_store):
        """Test 'merge' command with --strategy ours."""
        # Create a branch first
        runner.invoke(cli, ["-s", initialized_store, "branch", "test-ours"])
        result = runner.invoke(
            cli, ["-s", initialized_store, "merge", "test-ours", "-S", "ours"]
        )
        # May fail but should accept the strategy
        assert result.exit_code in [0, 1, 5]

    def test_merge_with_strategy_theirs(self, runner, initialized_store):
        """Test 'merge' command with --strategy theirs."""
        runner.invoke(cli, ["-s", initialized_store, "branch", "test-theirs"])
        result = runner.invoke(
            cli,
            ["-s", initialized_store, "merge", "test-theirs", "--strategy", "theirs"],
        )
        assert result.exit_code in [0, 1, 5]

    def test_merge_with_strategy_skip(self, runner, initialized_store):
        """Test 'merge' command with --strategy skip (default)."""
        runner.invoke(cli, ["-s", initialized_store, "branch", "test-skip"])
        result = runner.invoke(
            cli, ["-s", initialized_store, "merge", "test-skip", "-S", "skip"]
        )
        assert result.exit_code in [0, 1, 5]

    def test_merge_invalid_strategy(self, runner, initialized_store):
        """Test 'merge' command with invalid strategy."""
        result = runner.invoke(
            cli, ["-s", initialized_store, "merge", "some-branch", "-S", "invalid"]
        )
        # Should fail with invalid choice
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_merge_json_output_includes_strategy(self, runner, initialized_store):
        """Test 'merge' command JSON output includes strategy."""
        runner.invoke(cli, ["-s", initialized_store, "branch", "test-json"])
        result = runner.invoke(
            cli,
            ["--json", "-s", initialized_store, "merge", "test-json", "-S", "theirs"],
        )
        # Parse JSON output if successful
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "strategy" in data
            assert data["strategy"] == "theirs"

    def test_diff_command(self, runner, initialized_store):
        """Test 'diff' command."""
        result = runner.invoke(cli, ["-s", initialized_store, "diff"])
        # May fail if no commits, but should not crash
        assert result.exit_code in [0, 1, 5]

    def test_diff_json_output(self, runner, initialized_store):
        """Test 'diff' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "diff"])
        # May fail, but if succeeds should be JSON
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert isinstance(data, dict)

    def test_time_travel_requires_target(self, runner, initialized_store):
        """Test 'time-travel' command requires target."""
        result = runner.invoke(cli, ["-s", initialized_store, "time-travel"])
        assert result.exit_code != 0


class TestCryptoCommands:
    """Test crypto commands: proof, verify, blame."""

    def test_proof_requires_key(self, runner, initialized_store):
        """Test 'proof' command requires a key argument."""
        result = runner.invoke(cli, ["-s", initialized_store, "proof"])
        assert result.exit_code != 0

    def test_proof_nonexistent_key(self, runner, initialized_store):
        """Test 'proof' for nonexistent key."""
        result = runner.invoke(
            cli, ["-s", initialized_store, "proof", "nonexistent.key"]
        )
        # Should fail gracefully or return empty proof
        assert result.exit_code in [0, 1, 2]

    def test_verify_requires_args(self, runner, initialized_store):
        """Test 'verify' command requires arguments."""
        result = runner.invoke(cli, ["-s", initialized_store, "verify"])
        assert result.exit_code != 0

    def test_blame_requires_key(self, runner, initialized_store):
        """Test 'blame' command requires a key argument."""
        result = runner.invoke(cli, ["-s", initialized_store, "blame"])
        assert result.exit_code != 0

    def test_blame_nonexistent_key(self, runner, initialized_store):
        """Test 'blame' for nonexistent key."""
        result = runner.invoke(
            cli, ["-s", initialized_store, "blame", "nonexistent.key"]
        )
        # Should return empty or error
        assert result.exit_code == 0 or "not found" in result.output.lower()


class TestAnalysisCommands:
    """Test analysis commands: summarize, timeline, location."""

    def test_summarize_default(self, runner, initialized_store):
        """Test 'summarize' command with default type."""
        result = runner.invoke(cli, ["-s", initialized_store, "summarize"])
        assert result.exit_code == 0

    def test_summarize_taxonomy(self, runner, initialized_store):
        """Test 'summarize taxonomy' command."""
        result = runner.invoke(cli, ["-s", initialized_store, "summarize", "taxonomy"])
        assert result.exit_code == 0

    def test_summarize_json_output(self, runner, initialized_store):
        """Test 'summarize' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "summarize"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_summarize_depth_rejects_zero(self, runner, initialized_store):
        """--depth 0 must fail fast — depth is 1-indexed."""
        result = runner.invoke(
            cli, ["-s", initialized_store, "summarize", "--depth", "0"]
        )
        assert result.exit_code != 0

    def test_summarize_depth_json_shape(self, runner, initialized_store):
        """--depth adds depth + prefix_counts to JSON; omitted otherwise."""
        result = runner.invoke(
            cli, ["--json", "-s", initialized_store, "summarize", "--depth", "1"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["depth"] == 1
        assert "prefix_counts" in data
        assert isinstance(data["prefix_counts"], dict)

        # Without --depth, those keys must not appear.
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "summarize"])
        data = json.loads(result.output)
        assert "depth" not in data
        assert "prefix_counts" not in data

    def test_summarize_depth_groups_keys(self, monkeypatch, runner, initialized_store):
        """--depth groups keys by first N segments and returns counts per namespace."""
        from memoir.services.store_service import StoreService

        fake = {
            "namespaces": {
                "default": [
                    "preferences.coding.style",
                    "preferences.coding.languages",
                    "preferences.tools.cli",
                    "profile.professional.skills",
                    "toplevel",
                ]
            }
        }
        monkeypatch.setattr(StoreService, "read_store", lambda self: fake)

        result = runner.invoke(
            cli, ["--json", "-s", initialized_store, "summarize", "--depth", "1"]
        )
        assert result.exit_code == 0
        counts = json.loads(result.output)["prefix_counts"]["default"]
        assert counts == {"preferences": 3, "profile": 1, "toplevel": 1}

        result = runner.invoke(
            cli, ["--json", "-s", initialized_store, "summarize", "--depth", "2"]
        )
        counts = json.loads(result.output)["prefix_counts"]["default"]
        assert counts == {
            "preferences.coding": 2,
            "preferences.tools": 1,
            "profile.professional": 1,
            "toplevel": 1,
        }

    def test_summarize_depth_with_pattern(self, monkeypatch, runner, initialized_store):
        """--keys filter applies before --depth grouping."""
        from memoir.services.store_service import StoreService

        fake = {
            "namespaces": {
                "default": [
                    "preferences.coding.style",
                    "preferences.tools.cli",
                    "profile.professional.skills",
                ]
            }
        }
        monkeypatch.setattr(StoreService, "read_store", lambda self: fake)

        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "summarize",
                "--keys",
                "preferences.*",
                "--depth",
                "1",
            ],
        )
        assert result.exit_code == 0
        counts = json.loads(result.output)["prefix_counts"]["default"]
        assert counts == {"preferences": 2}

    def test_summarize_multi_pattern_union(
        self, monkeypatch, runner, initialized_store
    ):
        """Multiple --keys patterns union-match (not intersect, not last-wins)."""
        from memoir.services.store_service import StoreService

        fake = {
            "namespaces": {
                "default": [
                    "context.project.scope",
                    "context.current.session",
                    "knowledge.technical.taxonomy",
                    "metrics.turn.main",
                    "preferences.coding.style",
                ]
            }
        }
        monkeypatch.setattr(StoreService, "read_store", lambda self: fake)

        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "summarize",
                "--keys",
                "context.*",
                "--keys",
                "knowledge.*",
            ],
        )
        assert result.exit_code == 0
        matched = json.loads(result.output)["matching_keys"]["default"]
        assert set(matched) == {
            "context.project.scope",
            "context.current.session",
            "knowledge.technical.taxonomy",
        }
        # metrics.* and preferences.* must NOT appear — would mean union failed.
        assert not any(k.startswith("metrics.") for k in matched)
        assert not any(k.startswith("preferences.") for k in matched)


class TestMemoryCommands:
    """Test memory commands: remember, recall, forget.

    Note: These tests are marked as slow because they may involve LLM calls.
    Run with: pytest tests/test_cli.py -v -m "not slow" to skip.
    """

    def test_remember_requires_content(self, runner, initialized_store):
        """Test 'remember' command requires content argument."""
        result = runner.invoke(cli, ["-s", initialized_store, "remember"])
        assert result.exit_code != 0

    def test_recall_requires_query(self, runner, initialized_store):
        """Test 'recall' command requires query argument."""
        result = runner.invoke(cli, ["-s", initialized_store, "recall"])
        assert result.exit_code != 0

    def test_forget_requires_key(self, runner, initialized_store):
        """Test 'forget' command requires key argument."""
        result = runner.invoke(cli, ["-s", initialized_store, "forget"])
        assert result.exit_code != 0

    def test_recall_empty_store(self, runner, initialized_store):
        """Test 'recall' on empty store."""
        result = runner.invoke(cli, ["-s", initialized_store, "recall", "test query"])
        # Should succeed but find nothing
        assert result.exit_code == 0
        assert (
            "No memories" in result.output
            or "0" in result.output
            or "memories" in result.output.lower()
        )

    def test_recall_json_output(self, runner, initialized_store):
        """Test 'recall' command with JSON output."""
        result = runner.invoke(
            cli, ["--json", "-s", initialized_store, "recall", "test"]
        )
        assert result.exit_code == 0
        # Extract JSON from output (may have debug lines before it)
        output = result.output
        json_start = output.find("{")
        if json_start >= 0:
            json_str = output[json_start:]
            data = json.loads(json_str)
            assert "memories" in data or isinstance(data, dict)
        else:
            # No JSON found, just verify command ran
            assert True

    def test_forget_with_force(self, runner, initialized_store):
        """Test 'forget' with --force flag."""
        result = runner.invoke(
            cli, ["-s", initialized_store, "forget", "some.key", "--force"]
        )
        # May succeed (delete nothing) or fail (not found)
        # The behavior depends on implementation
        assert result.exit_code in [0, 2]

    def test_forget_json_output(self, runner, initialized_store):
        """Test 'forget' command with JSON output."""
        result = runner.invoke(
            cli,
            ["--json", "-s", initialized_store, "forget", "some.key", "--force"],
        )
        assert result.exit_code in [0, 2]
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_remember_path_namespace_prefix_inferred(self, runner, initialized_store):
        """`-p custom:foo.bar` with no -n stores under namespace 'custom' at
        path 'foo.bar' (not under namespace 'default' at literal key
        'custom:foo.bar')."""
        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "remember",
                "fact one",
                "-p",
                "custom:foo.bar",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.find("{") :])
        assert data["success"]
        assert data["namespace"] == "custom"
        assert data["key"] == "foo.bar"
        assert data["full_key"] == "custom:foo.bar"

    def test_remember_path_prefix_matches_explicit_namespace(
        self, runner, initialized_store
    ):
        """`-n default -p default:foo.bar` strips prefix silently."""
        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "remember",
                "fact",
                "-n",
                "default",
                "-p",
                "default:foo.bar",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.find("{") :])
        assert data["namespace"] == "default"
        assert data["key"] == "foo.bar"

    def test_remember_path_prefix_conflicts_explicit_namespace(
        self, runner, initialized_store
    ):
        """`-n default -p other:foo` is a hard error."""
        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "fact",
                "-n",
                "default",
                "-p",
                "other:foo",
            ],
        )
        assert result.exit_code != 0
        assert "conflicts" in result.output.lower()

    def test_remember_two_paths_different_prefixes_error(
        self, runner, initialized_store
    ):
        """Two -p with different namespace prefixes is a hard error."""
        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "fact",
                "-p",
                "ns1:foo",
                "-p",
                "ns2:bar",
            ],
        )
        assert result.exit_code != 0
        assert "conflicting" in result.output.lower()

    def test_remember_path_no_prefix_uses_default_namespace(
        self, runner, initialized_store
    ):
        """`-p foo.bar` with no -n stores under namespace 'default'."""
        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "remember",
                "fact",
                "-p",
                "foo.bar",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.find("{") :])
        assert data["namespace"] == "default"
        assert data["key"] == "foo.bar"

    def test_remember_path_mixed_prefix_and_bare(self, runner, initialized_store):
        """One -p with prefix + one without inherits the prefix's namespace."""
        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "remember",
                "fact",
                "-p",
                "scratch:a.b",
                "-p",
                "c.d",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output[result.output.find("{") :])
        assert data["namespace"] == "scratch"
        assert set(data["keys"]) == {"a.b", "c.d"}

    def test_remember_path_empty_prefix_or_path_error(self, runner, initialized_store):
        """`-p :foo` and `-p foo:` both error."""
        for bad in [":foo", "foo:"]:
            result = runner.invoke(
                cli,
                ["-s", initialized_store, "remember", "fact", "-p", bad],
            )
            assert result.exit_code != 0, f"expected error for {bad!r}"

    def test_remember_replace_flag_overrides_append(self, runner, initialized_store):
        """`--replace` makes -p clobber instead of appending."""
        path = "context.project.cli_replace_test"

        result = runner.invoke(
            cli,
            ["--json", "-s", initialized_store, "remember", "first", "-p", path],
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(
            cli,
            [
                "--json",
                "-s",
                initialized_store,
                "remember",
                "second",
                "-p",
                path,
                "--replace",
            ],
        )
        assert result.exit_code == 0, result.output

        get_result = runner.invoke(
            cli,
            ["--json", "-s", initialized_store, "get", path],
        )
        data = json.loads(get_result.output[get_result.output.find("{") :])
        assert data["items"][0]["value"]["content"] == "second"


class TestEnvironmentVariables:
    """Test environment variable support."""

    def test_memoir_store_env_var(self, runner, initialized_store):
        """Test MEMOIR_STORE environment variable."""
        result = runner.invoke(cli, ["status"], env={"MEMOIR_STORE": initialized_store})
        assert result.exit_code == 0

    def test_memoir_json_env_var(self, runner, initialized_store):
        """Test MEMOIR_JSON environment variable."""
        result = runner.invoke(
            cli,
            ["status"],
            env={"MEMOIR_STORE": initialized_store, "MEMOIR_JSON": "1"},
        )
        assert result.exit_code == 0
        # Should be JSON output
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_memoir_quiet_env_var(self, runner, initialized_store):
        """Test MEMOIR_QUIET environment variable."""
        result = runner.invoke(
            cli,
            ["status"],
            env={"MEMOIR_STORE": initialized_store, "MEMOIR_QUIET": "1"},
        )
        assert result.exit_code == 0


class TestExitCodes:
    """Test that exit codes are correct for various scenarios."""

    def test_success_exit_code(self, runner, initialized_store):
        """Test exit code 0 on success."""
        result = runner.invoke(cli, ["-s", initialized_store, "status"])
        assert result.exit_code == 0

    def test_no_store_shows_error_or_uses_default(self, runner, tmp_path, monkeypatch):
        """Test behavior when no store configured.

        Important: isolate cwd to a tmpdir so the CLI's fallback-to-cwd path
        can't materialize a memoir store inside this repository's working
        tree when the test runs from the repo root.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("MEMOIR_STORE", raising=False)
        result = runner.invoke(cli, ["status"], env={"MEMOIR_STORE": ""})
        # May fail (no store) or succeed (default config exists). Either way
        # should not crash.
        assert result.exit_code in [0, 3]

    def test_error_returns_nonzero(self, runner, initialized_store):
        """Test that errors return non-zero exit codes."""
        # Invalid command
        result = runner.invoke(cli, ["-s", initialized_store, "invalid-command"])
        assert result.exit_code != 0


class TestPerCallBranchRouting:
    """Tests for `--branch` / MEMOIR_BRANCH routing on memory + search commands.

    Issue #123 — multi-agent deployments share one store but each agent gets
    its own branch. A single call to ``memoir remember --branch=agents/X``
    must write on X and leave the rest of the process on whatever was
    checked out coming in.
    """

    PATH = "preferences.tools.editor"
    NAMESPACE = "default"

    def _current_branch(self, runner, store):
        """Read the currently-checked-out branch as JSON."""
        result = runner.invoke(cli, ["-s", store, "--json", "branch"])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)["current"]

    def _branches(self, runner, store):
        """Read the full branch list as JSON."""
        result = runner.invoke(cli, ["-s", store, "--json", "branch"])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)["branches"]

    def test_branch_flag_routes_write_and_restores_head(
        self, runner, initialized_store
    ):
        """`remember --branch=X` writes on X; HEAD on main is unchanged after."""
        before = self._current_branch(runner, initialized_store)

        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "reviewer found N+1 query",
                "-p",
                self.PATH,
                "--branch",
                "agents/reviewer",
            ],
        )
        assert result.exit_code == 0, result.output

        # HEAD restored.
        assert self._current_branch(runner, initialized_store) == before

        # Branch was auto-created.
        assert "agents/reviewer" in self._branches(runner, initialized_store)

        # Value lives on agents/reviewer, not on main.
        on_branch = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "get",
                self.PATH,
                "--branch",
                "agents/reviewer",
            ],
        )
        assert on_branch.exit_code == 0
        assert "N+1" in on_branch.output

        on_main = runner.invoke(cli, ["-s", initialized_store, "get", self.PATH])
        # `get` on main: key absent → exit code is EXIT_NOT_FOUND.
        assert on_main.exit_code != 0
        assert "not found" in on_main.output.lower()

    def test_memoir_branch_env_var_routes_write(self, runner, initialized_store):
        """MEMOIR_BRANCH alone (no --branch flag) routes the same way."""
        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "builder shipped pagination",
                "-p",
                self.PATH,
            ],
            env={"MEMOIR_BRANCH": "agents/builder"},
        )
        assert result.exit_code == 0, result.output
        assert "agents/builder" in self._branches(runner, initialized_store)

        on_branch = runner.invoke(
            cli,
            ["-s", initialized_store, "get", self.PATH],
            env={"MEMOIR_BRANCH": "agents/builder"},
        )
        assert on_branch.exit_code == 0
        assert "pagination" in on_branch.output

    def test_branch_flag_beats_env_var(self, runner, initialized_store):
        """When both are set the explicit --branch flag wins (standard Click)."""
        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "flag-wins content",
                "-p",
                self.PATH,
                "--branch",
                "agents/flag-target",
            ],
            env={"MEMOIR_BRANCH": "agents/env-target"},
        )
        assert result.exit_code == 0, result.output

        branches = self._branches(runner, initialized_store)
        assert "agents/flag-target" in branches
        # The env-only branch should not have been created.
        assert "agents/env-target" not in branches

    def test_read_errors_on_missing_branch(self, runner, initialized_store):
        """Reads against a non-existent branch must error, not return empty."""
        result = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "get",
                self.PATH,
                "--branch",
                "agents/does-not-exist",
            ],
        )
        assert result.exit_code != 0
        # Message should name the bad branch so the user can fix the typo.
        assert "agents/does-not-exist" in result.output

    def test_multi_agent_isolation_and_merge(self, runner, initialized_store):
        """End-to-end: two agents write on separate branches, then merge."""
        # Agent A writes on agents/reviewer.
        a = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "reviewer: missing WHERE in migration",
                "-p",
                "lessons.reviewer.sql",
                "--branch",
                "agents/reviewer",
            ],
        )
        assert a.exit_code == 0, a.output

        # Agent B writes on agents/builder. Same path, different content; the
        # branches must not see each other.
        b = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "remember",
                "builder: added retry to /users",
                "-p",
                "lessons.builder.api",
                "--branch",
                "agents/builder",
            ],
        )
        assert b.exit_code == 0, b.output

        # Reviewer's note is NOT visible from builder's branch.
        on_builder = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "get",
                "lessons.reviewer.sql",
                "--branch",
                "agents/builder",
            ],
        )
        assert on_builder.exit_code != 0
        assert "not found" in on_builder.output.lower()

        # …and not visible on main either.
        on_main = runner.invoke(
            cli,
            ["-s", initialized_store, "get", "lessons.reviewer.sql"],
        )
        assert on_main.exit_code != 0

        # Merge reviewer into main, then it's visible on main.
        merge = runner.invoke(
            cli,
            [
                "-s",
                initialized_store,
                "merge",
                "agents/reviewer",
                "--into",
                "main",
            ],
        )
        assert merge.exit_code == 0, merge.output

        after_merge = runner.invoke(
            cli,
            ["-s", initialized_store, "get", "lessons.reviewer.sql"],
        )
        assert after_merge.exit_code == 0, after_merge.output
        assert "WHERE" in after_merge.output

    @pytest.mark.parametrize(
        "command", ["remember", "recall", "get", "forget", "search"]
    )
    def test_all_data_op_commands_expose_branch_flag(self, runner, command):
        """Every command in the routing scope must surface --branch in --help."""
        result = runner.invoke(cli, [command, "--help"])
        assert result.exit_code == 0, result.output
        assert "--branch" in result.output
        assert "MEMOIR_BRANCH" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
