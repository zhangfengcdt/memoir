# SPDX-License-Identifier: Apache-2.0
"""
`memoir login` / `logout`, key + gateway resolution, and repo mode (#168).

The conftest points XDG_CONFIG_HOME at an empty directory per test, so the
developer's real ~/.config/memoir/cloud.json is never read or written.

Run with: pytest tests/test_cloud_login.py -v
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from memoir.cli.main import EXIT_NO_STORE, cli
from memoir.services import cloud_auth, sync_service
from memoir.store import repo_mode
from tests.fake_cloud import API_KEY, HANDLE, FakeCloud


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def home(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="memoir_login_")).resolve()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.delenv("MEMOIR_API_KEY", raising=False)
    monkeypatch.delenv("MEMOIR_CLOUD_URL", raising=False)
    monkeypatch.delenv("MEMOIR_STORE", raising=False)
    (root / ".memoir").mkdir()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def cloud(home):
    (home / "repos").mkdir()
    with FakeCloud(repos_root=home / "repos") as fake:
        yield fake


@pytest.fixture
def runner():
    return CliRunner()


def _repo(path: Path) -> Path:
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
    _git(path, "remote", "add", "origin", f"git@github.com:someone/{path.name}.git")
    return path


def _login(cloud):
    cloud_auth.save(cloud.url, API_KEY, HANDLE)


# --------------------------------------------------------------------------
# config file + resolution
# --------------------------------------------------------------------------


class TestConfig:
    def test_save_is_private_and_round_trips(self, home):
        path = cloud_auth.save("https://gw.example", "mck_secret", "feng")
        assert path == Path(os.environ["XDG_CONFIG_HOME"]) / "memoir" / "cloud.json"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert json.loads(path.read_text()) == {
            "gateway": "https://gw.example",
            "api_key": "mck_secret",
            "handle": "feng",
        }
        assert cloud_auth.saved_key() == "mck_secret"
        assert cloud_auth.saved_gateway() == "https://gw.example"
        assert cloud_auth.delete() is True
        assert cloud_auth.load() is None
        assert cloud_auth.delete() is False

    def test_unreadable_file_is_ignored(self, home):
        cloud_auth.config_dir().mkdir(parents=True)
        cloud_auth.config_path().write_text("{not json")
        assert cloud_auth.load() is None
        assert sync_service.cloud_enabled() is False

    def test_key_precedence(self, home, monkeypatch):
        assert sync_service.api_key() == ""
        cloud_auth.save("https://gw.example", "mck_file", "feng")
        assert sync_service.api_key() == "mck_file"
        assert sync_service.cloud_enabled() is True
        monkeypatch.setenv("MEMOIR_API_KEY", "mck_env")
        assert sync_service.api_key() == "mck_env"  # env wins

    def test_gateway_precedence(self, home, monkeypatch):
        assert sync_service.resolve_gateway() == sync_service.DEFAULT_GATEWAY
        cloud_auth.save("https://login.example/", "k", "h")
        assert sync_service.resolve_gateway() == "https://login.example"
        monkeypatch.setenv("MEMOIR_CLOUD_URL", "https://env.example")
        assert sync_service.resolve_gateway() == "https://env.example"
        assert (
            sync_service.resolve_gateway("https://flag.example")
            == "https://flag.example"
        )

    def test_redaction_covers_the_saved_key(self, home):
        cloud_auth.save("https://gw.example", "mck_file_secret", "feng")
        assert "mck_file_secret" not in sync_service.redact("boom mck_file_secret boom")


# --------------------------------------------------------------------------
# memoir login / logout
# --------------------------------------------------------------------------


class TestLogin:
    def test_device_login_saves_key(self, runner, cloud, monkeypatch):
        opened = []
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
        res = runner.invoke(cli, ["login", "--url", cloud.url], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        assert "ABCD-EFGH" in res.output
        assert f"logged in to {cloud.url} as {HANDLE}" in res.output
        assert API_KEY not in res.output
        assert opened == ["http://fake/cli/login?code=ABCD-EFGH"]
        assert cloud.state.login_starts[0]["client_name"]
        saved = cloud_auth.load()
        assert saved == {"gateway": cloud.url, "api_key": API_KEY, "handle": HANDLE}
        assert stat.S_IMODE(cloud_auth.config_path().stat().st_mode) == 0o600

    def test_no_browser_and_json(self, runner, cloud, monkeypatch):
        opened = []
        monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
        res = runner.invoke(
            cli,
            ["--json", "login", "--url", cloud.url, "--no-browser"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert opened == []
        data = json.loads(res.stdout)
        assert data["handle"] == HANDLE
        assert data["gateway"] == cloud.url
        assert API_KEY not in res.output

    @pytest.mark.parametrize(
        ("outcome", "fragment"), [("denied", "denied"), ("expired", "expired")]
    )
    def test_denied_or_expired(self, runner, cloud, outcome, fragment, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: None)
        cloud.state.login_outcome = outcome
        res = runner.invoke(cli, ["login", "--url", cloud.url])
        assert res.exit_code == 1
        assert fragment in res.output
        assert cloud_auth.load() is None

    def test_with_key_from_stdin(self, runner, cloud):
        res = runner.invoke(
            cli,
            ["login", "--url", cloud.url, "--with-key"],
            input=f"{API_KEY}\n",
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert cloud_auth.load()["handle"] == HANDLE
        assert API_KEY not in res.output

    def test_with_bad_key(self, runner, cloud):
        res = runner.invoke(
            cli, ["login", "--url", cloud.url, "--with-key"], input="mck_wrong\n"
        )
        assert res.exit_code == 1
        assert "not signed in" in res.output
        assert "mck_wrong" not in res.output
        assert cloud_auth.load() is None

    def test_logout_revokes_and_removes(self, runner, cloud):
        _login(cloud)
        res = runner.invoke(cli, ["logout"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        assert "key revoked" in res.output
        assert cloud.state.revoked_keys == [API_KEY]
        assert cloud_auth.load() is None
        res = runner.invoke(cli, ["logout"], catch_exceptions=False)
        assert "not logged in" in res.output

    def test_logout_offline_still_removes(self, runner, home):
        cloud_auth.save("http://127.0.0.1:9", API_KEY, HANDLE)
        res = runner.invoke(cli, ["logout"], catch_exceptions=False)
        assert res.exit_code == 0
        assert "revoke it on the keys page" in res.output
        assert cloud_auth.load() is None

    def test_cloud_commands_use_the_saved_login(self, runner, cloud, home):
        """No MEMOIR_API_KEY, no MEMOIR_CLOUD_URL: the login supplies both."""
        cloud.state.create_store("demo")
        _login(cloud)
        store = home / "store"
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        res = runner.invoke(
            cli,
            ["-s", str(store), "remote", "add", f"{HANDLE}/demo"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert (
            _git(store, "remote", "get-url", "origin") == f"{cloud.url}/{HANDLE}/demo"
        )
        assert API_KEY not in (store / ".git" / "config").read_text()

    def test_without_login_the_hint_says_login(self, runner, home):
        res = runner.invoke(cli, ["-s", str(home), "push"])
        assert res.exit_code == 1
        assert "memoir login" in res.output


# --------------------------------------------------------------------------
# repo mode
# --------------------------------------------------------------------------


class TestRepoModeDetection:
    def test_store_is_the_plugins_slug(self, home):
        repo = _repo(home / "code" / "my.app-x")
        (repo / "sub").mkdir()
        rc = repo_mode.detect(repo / "sub", home=home)
        assert rc is not None
        assert rc.root == repo
        assert rc.name == "my.app-x"
        assert rc.store == home / ".memoir" / str(repo).replace("/", "-").replace(
            ".", "-"
        )

    def test_matches_derive_store_path_sh(self, home):
        repo = _repo(home / "code" / "proj.x")
        script = (
            Path(__file__).resolve().parents[1]
            / "plugins/claude-code/scripts/derive-store-path.sh"
        )
        out = subprocess.run(
            ["bash", str(script)],
            cwd=repo,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(home)},
        ).stdout.strip()
        assert Path(out) == repo_mode.detect(repo, home=home).store

    def test_linked_worktree_uses_the_main_repo(self, home):
        repo = _repo(home / "code" / "main-repo")
        wt = home / "code" / "wt"
        _git(repo, "worktree", "add", "-q", str(wt), "-b", "feat")
        rc = repo_mode.detect(wt, home=home)
        assert rc.root == repo

    def test_not_in_a_repo_or_inside_a_store(self, home, runner):
        plain = home / "plain"
        plain.mkdir()
        assert repo_mode.detect(plain, home=home) is None
        store = home / "a-store"
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        assert repo_mode.detect(store, home=home) is None


class TestRepoModeCLI:
    def test_push_create_defaults_to_the_repo_name(
        self, runner, cloud, home, monkeypatch
    ):
        """Acceptance 2: in a repo whose plugin store exists, `memoir push
        --create` is the whole command."""
        _login(cloud)
        repo = _repo(home / "code" / "sedona-db")
        store = repo_mode.store_for_repo(repo, home)
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        runner.invoke(
            cli,
            ["-s", str(store), "remember", "-p", "workflow.x", "y"],
            catch_exceptions=False,
        )
        monkeypatch.chdir(repo)
        res = runner.invoke(cli, ["push", "--create"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        first = res.output.splitlines()[0]
        assert first == f"store: {repo_mode.display(store, home)} (repo sedona-db)"
        assert f"pushed main to {HANDLE}/sedona-db" in res.output
        assert cloud.state.lookup(HANDLE, "sedona-db") is not None

    def test_remote_add_and_pull_create_the_store(
        self, runner, cloud, home, monkeypatch
    ):
        """Acceptance 3: a fresh clone with no store."""
        _login(cloud)
        # The cloud store, pushed from elsewhere.
        src = home / "elsewhere"
        runner.invoke(cli, ["new", str(src)], catch_exceptions=False)
        runner.invoke(
            cli,
            ["-s", str(src), "remember", "-p", "workflow.shared", "from cloud"],
            catch_exceptions=False,
        )
        res = runner.invoke(
            cli, ["-s", str(src), "push", "--create", "proj"], catch_exceptions=False
        )
        assert res.exit_code == 0, res.output

        repo = _repo(home / "code" / "proj")
        store = repo_mode.store_for_repo(repo, home)
        assert not store.exists()
        monkeypatch.chdir(repo)
        res = runner.invoke(
            cli, ["remote", "add", f"{HANDLE}/proj"], catch_exceptions=False
        )
        assert res.exit_code == 0, res.output
        assert store.exists()
        assert "created" in res.output
        res = runner.invoke(cli, ["pull"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        res = runner.invoke(cli, ["get", "workflow.shared"], catch_exceptions=False)
        assert "from cloud" in res.output
        # the same store the plugin would use
        assert store == repo_mode.detect(repo, home=home).store

    def test_remote_add_proposes_handle_slash_repo_name(
        self, runner, cloud, home, monkeypatch
    ):
        _login(cloud)
        cloud.state.create_store("proj2")
        repo = _repo(home / "code" / "proj2")
        monkeypatch.chdir(repo)
        res = runner.invoke(cli, ["remote", "add"], input="y\n", catch_exceptions=False)
        assert res.exit_code == 0, res.output
        assert f"Link this store to {HANDLE}/proj2?" in res.output

    def test_other_commands_error_with_a_hint_when_no_store(
        self, runner, cloud, home, monkeypatch
    ):
        _login(cloud)
        repo = _repo(home / "code" / "nostore")
        monkeypatch.chdir(repo)
        res = runner.invoke(cli, ["push"])
        assert res.exit_code == EXIT_NO_STORE
        assert "memoir remote add" in res.output
        assert not repo_mode.store_for_repo(repo, home).exists()

    def test_explicit_store_and_env_are_unchanged(self, runner, home, monkeypatch):
        """Acceptance 5: -s / MEMOIR_STORE win over repo mode."""
        repo = _repo(home / "code" / "proj3")
        other = home / "other-store"
        runner.invoke(cli, ["new", str(other)], catch_exceptions=False)
        runner.invoke(
            cli,
            ["-s", str(other), "remember", "-p", "workflow.o", "other"],
            catch_exceptions=False,
        )
        monkeypatch.chdir(repo)
        res = runner.invoke(
            cli, ["-s", str(other), "get", "workflow.o"], catch_exceptions=False
        )
        assert "other" in res.output
        res = runner.invoke(
            cli,
            ["get", "workflow.o"],
            env={"MEMOIR_STORE": str(other)},
            catch_exceptions=False,
        )
        assert "other" in res.output
        assert not repo_mode.store_for_repo(repo, home).exists()

    def test_inside_a_store_directory_is_unchanged(self, runner, home, monkeypatch):
        store = home / "plain-store"
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        runner.invoke(
            cli,
            ["-s", str(store), "remember", "-p", "workflow.p", "here"],
            catch_exceptions=False,
        )
        monkeypatch.chdir(store)
        res = runner.invoke(cli, ["get", "workflow.p"], catch_exceptions=False)
        assert "here" in res.output

    def test_repo_flag(self, runner, home, monkeypatch):
        repo = _repo(home / "code" / "proj4")
        store = repo_mode.store_for_repo(repo, home)
        runner.invoke(cli, ["new", str(store)], catch_exceptions=False)
        runner.invoke(
            cli,
            ["-s", str(store), "remember", "-p", "workflow.r", "repo store"],
            catch_exceptions=False,
        )
        monkeypatch.chdir(repo)
        # --repo beats MEMOIR_STORE
        res = runner.invoke(
            cli,
            ["--repo", "get", "workflow.r"],
            env={"MEMOIR_STORE": str(home / "x")},
            catch_exceptions=False,
        )
        assert "repo store" in res.output
        # but not together with -s
        res = runner.invoke(cli, ["--repo", "-s", str(store), "status"])
        assert res.exit_code != 0
        assert "not both" in res.output
        # and not outside a repo
        plain = home / "plain2"
        plain.mkdir()
        monkeypatch.chdir(plain)
        res = runner.invoke(cli, ["--repo", "status"])
        assert res.exit_code == EXIT_NO_STORE
