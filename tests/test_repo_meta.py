# SPDX-License-Identifier: Apache-2.0
"""
Code-repo metadata reported to memoir-cloud (issue #164).

Unit tests for the collector (`memoir.services.repo_meta`) plus integration
through `memoir remote add` / `memoir push` against the fake gateway.

Run with: pytest tests/test_repo_meta.py -v
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from memoir.cli.main import cli
from memoir.services import repo_meta
from tests.fake_cloud import API_KEY, HANDLE, FakeCloud

ADDRESS = f"{HANDLE}/demo"


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _make_repo(
    path: Path, origin: str | None = "git@github.com:zhangfengcdt/memoir.git"
):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(
        path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x.io",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c1",
    )
    if origin:
        _git(path, "remote", "add", "origin", origin)
    return path


def _slug(path: Path) -> str:
    return str(path.resolve()).replace("/", "-").replace(".", "-")


@pytest.fixture
def home(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="memoir_repometa_")).resolve()
    monkeypatch.setenv("HOME", str(root))
    (root / ".memoir").mkdir()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def offline(monkeypatch):
    """No GitHub calls unless a test opts in."""

    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", boom)


# --------------------------------------------------------------------------
# URL normalisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "git@github.com:zhangfengcdt/memoir.git",
            "https://github.com/zhangfengcdt/memoir",
        ),
        (
            "https://github.com/zhangfengcdt/memoir.git",
            "https://github.com/zhangfengcdt/memoir",
        ),
        ("https://user:tok@github.com/o/r", "https://github.com/o/r"),
        ("ssh://git@gitlab.com:2222/group/sub/r.git", "https://gitlab.com/group/sub/r"),
        ("https://GitHub.com/o/r/", "https://github.com/o/r"),
        ("/srv/git/r.git", None),
        ("file:///srv/git/r.git", None),
        ("", None),
    ],
)
def test_normalize_remote_url(url, expected):
    assert repo_meta.normalize_remote_url(url) == expected


# --------------------------------------------------------------------------
# Store → code repo
# --------------------------------------------------------------------------


class TestResolve:
    def test_slug_maps_back_to_repo(self, home):
        repo = _make_repo(home / "code" / "memoir")
        store = home / ".memoir" / _slug(repo)
        store.mkdir()
        assert repo_meta.resolve_code_repo(store) == repo

    def test_dashes_in_directory_names(self, home):
        """`memoir-cloud` and `memoir/cloud` share a slug; the existing one wins."""
        repo = _make_repo(home / "code" / "memoir-cloud")
        (home / "code" / "memoir").mkdir()  # a decoy prefix
        store = home / ".memoir" / _slug(repo)
        store.mkdir()
        assert repo_meta.resolve_code_repo(store) == repo

    def test_dots_in_directory_names(self, home):
        repo = _make_repo(home / "code" / "site.io")
        store = home / ".memoir" / _slug(repo)
        store.mkdir()
        assert repo_meta.resolve_code_repo(store) == repo

    def test_store_outside_memoir_home_or_without_repo(self, home):
        assert repo_meta.resolve_code_repo(home / "elsewhere") is None
        plain = home / "code" / "not-a-repo"
        plain.mkdir(parents=True)
        store = home / ".memoir" / _slug(plain)
        store.mkdir()
        assert repo_meta.resolve_code_repo(store) is None


# --------------------------------------------------------------------------
# Field collection
# --------------------------------------------------------------------------


class TestFields:
    def test_git_local_fields(self, home):
        repo = _make_repo(home / "code" / "memoir")
        _git(repo, "checkout", "-q", "-b", "feat/x")
        fields = repo_meta.git_local_fields(repo)
        assert fields == {
            "url": "https://github.com/zhangfengcdt/memoir",
            "host": "github",
            "owner": "zhangfengcdt",
            "name": "memoir",
            "root": "memoir",
            "default_branch": "main",
            "head_branch": "feat/x",
            "head_commit": _git(repo, "rev-parse", "HEAD"),
        }

    def test_default_branch_from_origin_head(self, home):
        repo = _make_repo(home / "code" / "r")
        _git(repo, "branch", "-m", "main", "trunk")
        _git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        _git(
            repo,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/remotes/origin/trunk",
        )
        assert repo_meta.git_local_fields(repo)["default_branch"] == "trunk"

    def test_no_origin_means_no_metadata(self, home):
        repo = _make_repo(home / "code" / "r", origin=None)
        assert repo_meta.git_local_fields(repo) is None

    def test_github_fields(self, monkeypatch):
        seen = {}

        def fake_get(url, headers, timeout):
            seen.update(url=url, headers=headers, timeout=timeout)
            return httpx.Response(
                200,
                json={
                    "description": "d" * 1500,
                    "topics": [f"t{i}" for i in range(25)],
                    "language": "Python",
                    "visibility": "public",
                    "stargazers_count": 12,
                    "homepage": "https://example.com",
                    "secret_field": "ignored",
                },
            )

        monkeypatch.setattr(httpx, "get", fake_get)
        monkeypatch.setattr(repo_meta, "_gh_token", lambda: "gho_test")
        fields = repo_meta.github_fields("zhangfengcdt", "memoir")
        assert seen["url"] == "https://api.github.com/repos/zhangfengcdt/memoir"
        assert seen["headers"]["Authorization"] == "Bearer gho_test"
        assert seen["headers"]["Accept"] == "application/vnd.github+json"
        assert seen["timeout"] == 2.0
        assert len(fields["description"]) == 1000
        assert len(fields["topics"]) == 20
        assert fields["language"] == "Python"
        assert fields["stars"] == 12
        assert fields["visibility"] == "public"
        assert fields["homepage"] == "https://example.com"
        assert "secret_field" not in fields
        assert fields["fetched_at"].endswith("+00:00")

    @pytest.mark.parametrize("status", [403, 404, 500])
    def test_github_failure_omits_fields(self, monkeypatch, status):
        monkeypatch.setattr(
            httpx, "get", lambda *a, **k: httpx.Response(status, json={})
        )
        monkeypatch.setattr(repo_meta, "_gh_token", lambda: None)
        assert repo_meta.github_fields("o", "r") == {}

    def test_offline_omits_fields(self, offline, monkeypatch):
        monkeypatch.setattr(repo_meta, "_gh_token", lambda: None)
        assert repo_meta.github_fields("o", "r") == {}

    def test_fingerprint_ignores_fetched_at(self):
        a = {
            "url": "https://x/o/r",
            "stars": 1,
            "fetched_at": "2026-01-01T00:00:00+00:00",
        }
        b = {**a, "fetched_at": "2026-02-02T00:00:00+00:00"}
        assert repo_meta.fingerprint(a) == repo_meta.fingerprint(b)
        assert repo_meta.fingerprint(a) != repo_meta.fingerprint({**a, "stars": 2})


# --------------------------------------------------------------------------
# Integration: remote add / push send it, best-effort
# --------------------------------------------------------------------------


@pytest.fixture
def cloud(home):
    with FakeCloud(repos_root=home / "repos") as fake:
        (home / "repos").mkdir(exist_ok=True)
        fake.state.create_store("demo")
        yield fake


@pytest.fixture
def env(cloud, home):
    return {"MEMOIR_API_KEY": API_KEY, "MEMOIR_CLOUD_URL": cloud.url, "HOME": str(home)}


def _plugin_store(runner, home, repo: Path) -> Path:
    """A store at ~/.memoir/<slug of repo>, as the Claude Code plugin creates it."""
    store = home / ".memoir" / _slug(repo)
    res = runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
    assert res.exit_code == 0, res.output
    res = runner.invoke(
        cli,
        ["-s", str(store), "remember", "-p", "workflow.x", "y"],
        catch_exceptions=False,
    )
    assert res.exit_code == 0, res.output
    return store


def _patches(cloud):
    return [r for r in cloud.state.requests if r.method == "PATCH"]


class TestIntegration:
    def test_remote_add_and_push_send_metadata_once(self, home, cloud, env, offline):
        runner = CliRunner()
        repo = _make_repo(home / "code" / "memoir")
        store = _plugin_store(runner, home, repo)

        res = runner.invoke(cli, ["-s", str(store), "remote", "add", ADDRESS], env=env)
        assert res.exit_code == 0, res.output
        assert len(_patches(cloud)) == 1
        assert _patches(cloud)[0].path == f"/stores/by-name/{ADDRESS}"
        sent = cloud.state.repo_meta[cloud.state.lookup(HANDLE, "demo")["id"]]
        assert sent["url"] == "https://github.com/zhangfengcdt/memoir"
        assert sent["default_branch"] == "main"
        assert sent["head_commit"] == _git(repo, "rev-parse", "HEAD")
        # offline: only the git-local fields
        assert "description" not in sent
        assert "fetched_at" not in sent

        res = runner.invoke(cli, ["-s", str(store), "push"], env=env)
        assert res.exit_code == 0, res.output
        assert len(_patches(cloud)) == 1  # unchanged → not resent

        _git(
            repo,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@x.io",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "c2",
        )
        runner.invoke(cli, ["-s", str(store), "remember", "-p", "workflow.z", "w"])
        res = runner.invoke(cli, ["-s", str(store), "push"], env=env)
        assert res.exit_code == 0, res.output
        assert len(_patches(cloud)) == 2  # head_commit moved → resent
        sent = cloud.state.repo_meta[cloud.state.lookup(HANDLE, "demo")["id"]]
        assert sent["head_commit"] == _git(repo, "rev-parse", "HEAD")

        record = store / ".git" / "memoir-cloud" / "repo-meta-origin"
        assert json.loads(record.read_text())["head_commit"] == sent["head_commit"]
        assert API_KEY not in record.read_text()

    def test_push_create_sends_metadata(self, home, cloud, env, offline):
        runner = CliRunner()
        repo = _make_repo(home / "code" / "memoir")
        store = _plugin_store(runner, home, repo)
        res = runner.invoke(
            cli, ["-s", str(store), "push", "--create", "fresh"], env=env
        )
        assert res.exit_code == 0, res.output
        assert [r.path for r in _patches(cloud)] == [f"/stores/by-name/{HANDLE}/fresh"]

    def test_online_adds_github_fields(self, home, cloud, env, monkeypatch):
        monkeypatch.setattr(repo_meta, "_gh_token", lambda: None)
        monkeypatch.setattr(
            httpx,
            "get",
            lambda *a, **k: httpx.Response(
                200,
                json={
                    "description": "memory for agents",
                    "topics": ["memory"],
                    "language": "Python",
                    "stargazers_count": 7,
                },
            ),
        )
        runner = CliRunner()
        store = _plugin_store(runner, home, _make_repo(home / "code" / "memoir"))
        res = runner.invoke(cli, ["-s", str(store), "remote", "add", ADDRESS], env=env)
        assert res.exit_code == 0, res.output
        sent = cloud.state.repo_meta[cloud.state.lookup(HANDLE, "demo")["id"]]
        assert sent["description"] == "memory for agents"
        assert sent["topics"] == ["memory"]
        assert sent["language"] == "Python"
        assert sent["stars"] == 7
        assert "fetched_at" in sent

    def test_store_without_code_repo_sends_nothing(self, home, cloud, env, offline):
        runner = CliRunner()
        store = home / "plain-store"
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        runner.invoke(cli, ["-s", str(store), "remember", "-p", "workflow.x", "y"])
        assert (
            runner.invoke(
                cli, ["-s", str(store), "remote", "add", ADDRESS], env=env
            ).exit_code
            == 0
        )
        assert runner.invoke(cli, ["-s", str(store), "push"], env=env).exit_code == 0
        assert _patches(cloud) == []

    def test_cloud_failure_never_fails_the_verb(self, home, cloud, env, offline):
        cloud.state.patch_status = 500
        runner = CliRunner()
        store = _plugin_store(runner, home, _make_repo(home / "code" / "memoir"))
        res = runner.invoke(cli, ["-s", str(store), "remote", "add", ADDRESS], env=env)
        assert res.exit_code == 0, res.output
        res = runner.invoke(cli, ["-s", str(store), "push"], env=env)
        assert res.exit_code == 0, res.output
        # not recorded as sent, so the next push retries
        assert not (store / ".git" / "memoir-cloud" / "repo-meta-origin").exists()
        assert len(_patches(cloud)) >= 2
