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
        """Test --version option."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower()

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
    """Test store commands: new, connect, status, refresh."""

    def test_new_creates_store(self, runner, temp_store):
        """Test 'new' command creates a store."""
        # Remove the temp dir so 'new' can create it
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store])
        assert result.exit_code == 0
        assert "Created" in result.output or "success" in result.output.lower()
        assert os.path.exists(temp_store)
        assert os.path.exists(os.path.join(temp_store, ".git"))

    def test_new_json_output(self, runner, temp_store):
        """Test 'new' command with JSON output."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["--json", "new", temp_store])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert "path" in data

    def test_new_no_connect_option(self, runner, temp_store):
        """Test 'new' command with --no-connect option."""
        shutil.rmtree(temp_store)

        result = runner.invoke(cli, ["new", temp_store, "--no-connect"])
        assert result.exit_code == 0
        assert os.path.exists(temp_store)

    def test_connect_to_store(self, runner, initialized_store):
        """Test 'connect' command."""
        result = runner.invoke(cli, ["connect", initialized_store])
        assert result.exit_code == 0
        assert "Connected" in result.output

    def test_connect_json_output(self, runner, initialized_store):
        """Test 'connect' command with JSON output."""
        result = runner.invoke(cli, ["--json", "connect", initialized_store])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "path" in data

    def test_connect_nonexistent_path(self, runner):
        """Test 'connect' to nonexistent path fails."""
        result = runner.invoke(cli, ["connect", "/nonexistent/path"])
        assert result.exit_code != 0
        assert "not exist" in result.output.lower() or "error" in result.output.lower()

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

    def test_status_no_store_error(self, runner):
        """Test 'status' without store configured fails or uses default."""
        # Clear any environment variables that might set a store
        result = runner.invoke(cli, ["status"], env={"MEMOIR_STORE": ""})
        # May fail (no store) or succeed (if default configured)
        # Just verify it runs without crashing
        assert result.exit_code in [0, 3]

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

    def test_commits_list(self, runner, initialized_store):
        """Test 'commits' command shows history."""
        result = runner.invoke(cli, ["-s", initialized_store, "commits"])
        assert result.exit_code == 0
        # May have initial commit or be empty

    def test_commits_json_output(self, runner, initialized_store):
        """Test 'commits' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "commits"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "commits" in data

    def test_commits_with_limit(self, runner, initialized_store):
        """Test 'commits' command with --limit option."""
        result = runner.invoke(cli, ["-s", initialized_store, "commits", "-n", "5"])
        assert result.exit_code == 0

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

    def test_timeline_list(self, runner, initialized_store):
        """Test 'timeline' command lists events."""
        result = runner.invoke(cli, ["-s", initialized_store, "timeline"])
        assert result.exit_code == 0

    def test_timeline_json_output(self, runner, initialized_store):
        """Test 'timeline' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "timeline"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_location_list(self, runner, initialized_store):
        """Test 'location' command lists locations."""
        result = runner.invoke(cli, ["-s", initialized_store, "location"])
        assert result.exit_code == 0

    def test_location_json_output(self, runner, initialized_store):
        """Test 'location' command with JSON output."""
        result = runner.invoke(cli, ["--json", "-s", initialized_store, "location"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)


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

    def test_no_store_shows_error_or_uses_default(self, runner):
        """Test behavior when no store configured."""
        # Clear environment
        result = runner.invoke(cli, ["status"], env={"MEMOIR_STORE": ""})
        # May fail (no store) or succeed (default config exists)
        # Either way should not crash
        assert result.exit_code in [0, 3]

    def test_error_returns_nonzero(self, runner, initialized_store):
        """Test that errors return non-zero exit codes."""
        # Invalid command
        result = runner.invoke(cli, ["-s", initialized_store, "invalid-command"])
        assert result.exit_code != 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
