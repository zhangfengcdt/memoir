"""
Tests for the `memoir store-path` and `memoir ensure-store` CLI commands.

Run with: pytest tests/test_store_path.py -v
"""

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from memoir.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _expected_store_path(project_dir: str) -> str:
    resolved = str(Path(project_dir).resolve())
    slug = resolved.replace("/", "-").replace(".", "-")
    return str(Path.home() / ".memoir" / slug)


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class TestStorePath:
    def test_non_git_directory_uses_cwd(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["store-path"])
        assert result.exit_code == 0
        assert result.output.strip() == _expected_store_path(str(tmp_path))

    def test_explicit_project_dir_argument(self, runner, tmp_path):
        target = tmp_path / "some-project"
        target.mkdir()
        result = runner.invoke(cli, ["store-path", str(target)])
        assert result.exit_code == 0
        assert result.output.strip() == _expected_store_path(str(target))

    def test_git_repo_resolves_to_toplevel(self, runner, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-q", cwd=repo)
        nested = repo / "src" / "nested"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        result = runner.invoke(cli, ["store-path"])
        assert result.exit_code == 0
        assert result.output.strip() == _expected_store_path(str(repo))

    def test_print_git_root_outside_repo_prints_nothing(
        self, runner, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["store-path", "--print-git-root"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_print_git_root_inside_repo(self, runner, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-q", cwd=repo)
        monkeypatch.chdir(repo)
        result = runner.invoke(cli, ["store-path", "--print-git-root"])
        assert result.exit_code == 0
        assert Path(result.output.strip()).resolve() == repo.resolve()

    def test_linked_worktree_shares_main_worktree_store(
        self, runner, tmp_path, monkeypatch
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-q", cwd=repo)
        (repo / "README.md").write_text("x")
        _git("add", ".", cwd=repo)
        _git(
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "-m",
            "initial",
            cwd=repo,
        )
        worktree = tmp_path / "worktree"
        _git("worktree", "add", "-q", "-b", "wt-branch", str(worktree), cwd=repo)

        monkeypatch.chdir(worktree)
        result = runner.invoke(cli, ["store-path"])
        assert result.exit_code == 0
        assert result.output.strip() == _expected_store_path(str(repo))


class TestEnsureStore:
    def test_creates_store_when_missing(self, runner, tmp_path):
        target = tmp_path / "new-store"
        result = runner.invoke(cli, ["--json", "ensure-store", str(target)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["created"] is True
        assert (target / ".git").exists()

    def test_idempotent_on_existing_store(self, runner, tmp_path):
        target = tmp_path / "existing-store"
        create = runner.invoke(cli, ["new", str(target)])
        assert create.exit_code == 0

        result = runner.invoke(cli, ["--json", "ensure-store", str(target)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["created"] is False

    def test_works_from_non_git_cwd(self, runner, tmp_path, monkeypatch):
        # Regression check for the scratch-dir workaround: taxonomy install
        # must succeed even when the caller's cwd isn't inside a git repo.
        plain_dir = tmp_path / "not-a-repo"
        plain_dir.mkdir()
        monkeypatch.chdir(plain_dir)

        target = tmp_path / "store-from-non-git-cwd"
        result = runner.invoke(cli, ["ensure-store", str(target)])
        assert result.exit_code == 0
        assert (target / ".git").exists()

    def test_restores_original_cwd(self, runner, tmp_path, monkeypatch):
        plain_dir = tmp_path / "caller-cwd"
        plain_dir.mkdir()
        monkeypatch.chdir(plain_dir)

        target = tmp_path / "store-cwd-check"
        result = runner.invoke(cli, ["ensure-store", str(target)])
        assert result.exit_code == 0
        assert Path.cwd().resolve() == plain_dir.resolve()
