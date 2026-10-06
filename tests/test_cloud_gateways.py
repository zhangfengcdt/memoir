# SPDX-License-Identifier: Apache-2.0
"""
Per-gateway credentials and named remotes (issue #170).

Two fake gateways stand in for production and staging, each accepting only
its own key, so a request carrying the wrong key fails loudly and every
request's Authorization header can be audited.

Run with: pytest tests/test_cloud_gateways.py -v
"""

import json
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from memoir.cli.main import cli
from memoir.services import cloud_auth, sync_service
from tests.fake_cloud import HANDLE, FakeCloud

PROD_KEY = "mck_prod_secret_key"
STAGING_KEY = "mck_staging_secret_key"


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def home(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="memoir_gw_")).resolve()
    monkeypatch.setenv("HOME", str(root))
    for var in ("MEMOIR_API_KEY", "MEMOIR_CLOUD_URL", "MEMOIR_STORE"):
        monkeypatch.delenv(var, raising=False)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def clouds(home):
    (home / "prod").mkdir()
    (home / "staging").mkdir()
    with (
        FakeCloud(repos_root=home / "prod") as prod,
        FakeCloud(repos_root=home / "staging") as staging,
    ):
        prod.state.api_key = PROD_KEY
        staging.state.api_key = STAGING_KEY
        prod.state.create_store("demo")
        staging.state.create_store("demo")
        yield prod, staging


@pytest.fixture
def runner():
    return CliRunner()


def _store(runner, path: Path) -> Path:
    assert runner.invoke(cli, ["new", str(path)], catch_exceptions=False).exit_code == 0
    res = runner.invoke(cli, ["-s", str(path), "remember", "-p", "workflow.x", "y"])
    assert res.exit_code == 0, res.output
    return path


def _keys_seen(cloud) -> set[str]:
    return {
        r.headers.get("Authorization", "").removeprefix("Bearer ")
        for r in cloud.state.requests
        if r.headers.get("Authorization")
    }


# --------------------------------------------------------------------------
# Part 1: per-gateway credentials
# --------------------------------------------------------------------------


class TestCredentials:
    def test_normalize_gateway(self):
        n = cloud_auth.normalize_gateway
        assert n("HTTPS://Gw.Example/") == "https://gw.example"
        assert n("https://gw.example/some/path") == "https://gw.example"
        assert n("http://127.0.0.1:8080") == "http://127.0.0.1:8080"

    def test_two_logins_coexist(self, home):
        cloud_auth.save("https://prod.example", PROD_KEY, "feng")
        cloud_auth.save("https://staging.example/", STAGING_KEY, "feng-s")
        data = cloud_auth.load_all()
        assert data["default"] == "https://prod.example"  # first login
        assert set(data["gateways"]) == {
            "https://prod.example",
            "https://staging.example",
        }
        assert sync_service.api_key("https://prod.example") == PROD_KEY
        assert sync_service.api_key("https://staging.example") == STAGING_KEY
        assert sync_service.api_key("https://other.example") == ""
        assert stat.S_IMODE(cloud_auth.config_path().stat().st_mode) == 0o600

    def test_make_default(self, home):
        cloud_auth.save("https://prod.example", PROD_KEY, "feng")
        cloud_auth.save(
            "https://staging.example", STAGING_KEY, "feng", make_default=True
        )
        assert cloud_auth.default_gateway() == "https://staging.example"
        assert sync_service.resolve_gateway() == "https://staging.example"

    def test_migration_from_single_login_format(self, home):
        cloud_auth.config_dir().mkdir(parents=True)
        cloud_auth.config_path().write_text(
            json.dumps(
                {
                    "gateway": "https://prod.example/",
                    "api_key": PROD_KEY,
                    "handle": "feng",
                }
            )
        )
        data = cloud_auth.load_all()
        assert data == {
            "default": "https://prod.example",
            "gateways": {
                "https://prod.example": {"api_key": PROD_KEY, "handle": "feng"}
            },
        }
        assert sync_service.api_key("https://prod.example") == PROD_KEY
        # the next save rewrites it in the new shape, keeping the old entry
        cloud_auth.save("https://staging.example", STAGING_KEY, "feng")
        on_disk = json.loads(cloud_auth.config_path().read_text())
        assert on_disk["default"] == "https://prod.example"
        assert set(on_disk["gateways"]) == {
            "https://prod.example",
            "https://staging.example",
        }

    def test_env_key_still_wins(self, home, monkeypatch):
        cloud_auth.save("https://staging.example", STAGING_KEY, "feng")
        monkeypatch.setenv("MEMOIR_API_KEY", "mck_env")
        assert sync_service.api_key("https://staging.example") == "mck_env"
        assert sync_service.api_key("https://prod.example") == "mck_env"

    def test_only_env_key_behaves_as_before_169(self, home, monkeypatch):
        """Acceptance 4: MEMOIR_API_KEY and no cloud.json."""
        monkeypatch.setenv("MEMOIR_API_KEY", "mck_env")
        assert not cloud_auth.config_path().exists()
        assert sync_service.cloud_enabled() is True
        assert sync_service.resolve_gateway() == sync_service.DEFAULT_GATEWAY
        assert sync_service.api_key("https://anything.example") == "mck_env"


class TestLoginCommands:
    def test_status_lists_both_and_marks_default(self, runner, clouds):
        prod, staging = clouds
        for cloud, key in ((prod, PROD_KEY), (staging, STAGING_KEY)):
            res = runner.invoke(
                cli,
                ["login", "--url", cloud.url, "--with-key"],
                input=key,
                catch_exceptions=False,
            )
            assert res.exit_code == 0, res.output
        res = runner.invoke(cli, ["login", "--status"], catch_exceptions=False)
        lines = res.output.splitlines()
        assert lines[0] == f"* {prod.url}  as {HANDLE}"
        assert lines[1] == f"  {staging.url}  as {HANDLE}"
        assert PROD_KEY not in res.output
        assert STAGING_KEY not in res.output
        data = json.loads(runner.invoke(cli, ["--json", "login", "--status"]).output)
        assert data["default"] == prod.url
        assert {g["gateway"] for g in data["gateways"]} == {prod.url, staging.url}

    def test_login_default_flag(self, runner, clouds):
        prod, staging = clouds
        runner.invoke(cli, ["login", "--url", prod.url, "--with-key"], input=PROD_KEY)
        res = runner.invoke(
            cli,
            ["login", "--url", staging.url, "--with-key", "--default"],
            input=STAGING_KEY,
        )
        assert "(default)" in res.output
        assert cloud_auth.default_gateway() == staging.url

    def test_logout_one_keeps_the_other(self, runner, clouds):
        prod, staging = clouds
        cloud_auth.save(prod.url, PROD_KEY, HANDLE)
        cloud_auth.save(staging.url, STAGING_KEY, HANDLE)
        res = runner.invoke(
            cli, ["logout", "--url", staging.url], catch_exceptions=False
        )
        assert res.exit_code == 0, res.output
        assert f"logged out of {staging.url} (key revoked)" in res.output
        assert staging.state.revoked_keys == [STAGING_KEY]
        assert prod.state.revoked_keys == []
        assert cloud_auth.entry(staging.url) is None
        assert cloud_auth.entry(prod.url)["api_key"] == PROD_KEY
        res = runner.invoke(
            cli, ["logout", "--url", staging.url], catch_exceptions=False
        )
        assert "not logged in" in res.output

    def test_logout_all(self, runner, clouds):
        prod, staging = clouds
        cloud_auth.save(prod.url, PROD_KEY, HANDLE)
        cloud_auth.save(staging.url, STAGING_KEY, HANDLE)
        res = runner.invoke(cli, ["logout", "--all"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        assert prod.state.revoked_keys == [PROD_KEY]
        assert staging.state.revoked_keys == [STAGING_KEY]
        assert not cloud_auth.config_path().exists()

    def test_removing_the_default_promotes_another(self, home):
        cloud_auth.save("https://prod.example", PROD_KEY, "feng")
        cloud_auth.save("https://staging.example", STAGING_KEY, "feng")
        cloud_auth.remove("https://prod.example")
        assert cloud_auth.default_gateway() == "https://staging.example"

    def test_staging_login_is_not_sent_to_a_production_origin(
        self, runner, clouds, home
    ):
        prod, staging = clouds
        cloud_auth.save(staging.url, STAGING_KEY, HANDLE)
        store = _store(runner, home / "s")
        _git(store, "remote", "add", "origin", f"{prod.url}/{HANDLE}/demo")
        res = runner.invoke(cli, ["-s", str(store), "push"])
        assert res.exit_code == 1
        assert (
            f"not logged in to {prod.url}: run `memoir login --url {prod.url}`"
            in res.output
        )
        assert prod.state.requests == []  # no request at all


# --------------------------------------------------------------------------
# Part 2: named remotes
# --------------------------------------------------------------------------


@pytest.fixture
def both(runner, clouds, home):
    """A store with `origin` on prod and `staging` on staging, logged in to both."""
    prod, staging = clouds
    cloud_auth.save(prod.url, PROD_KEY, HANDLE)
    cloud_auth.save(staging.url, STAGING_KEY, HANDLE)
    store = _store(runner, home / "store")
    res = runner.invoke(
        cli, ["-s", str(store), "remote", "add", f"{HANDLE}/demo", "--url", prod.url]
    )
    assert res.exit_code == 0, res.output
    res = runner.invoke(
        cli,
        [
            "-s",
            str(store),
            "remote",
            "add",
            f"{HANDLE}/demo",
            "--name",
            "staging",
            "--url",
            staging.url,
        ],
    )
    assert res.exit_code == 0, res.output
    assert "staging: " in res.output
    return prod, staging, store


class TestNamedRemotes:
    def test_push_each_remote_with_its_own_key(self, runner, both):
        prod, staging, store = both
        res = runner.invoke(cli, ["-s", str(store), "push"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        res = runner.invoke(
            cli,
            ["-s", str(store), "push", "--remote", "staging"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert _keys_seen(prod) == {PROD_KEY}
        assert _keys_seen(staging) == {STAGING_KEY}
        tip = _git(store, "rev-parse", "main")
        assert _git(prod.state.repo_for(HANDLE, "demo"), "rev-parse", "main") == tip
        assert _git(staging.state.repo_for(HANDLE, "demo"), "rev-parse", "main") == tip
        mc = store / ".git" / "memoir-cloud"
        assert (mc / "pushed-origin").exists()
        assert (mc / "pushed-staging").exists()

    def test_records_are_per_remote(self, runner, both):
        _prod, _staging, store = both
        runner.invoke(cli, ["-s", str(store), "push"], catch_exceptions=False)
        mc = store / ".git" / "memoir-cloud"
        before = (mc / "pushed-origin").read_text()
        res = runner.invoke(
            cli,
            ["-s", str(store), "fetch", "--remote", "staging"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert (mc / "pushed-origin").read_text() == before
        # staging's refs live under refs/remotes/staging/
        runner.invoke(
            cli,
            ["-s", str(store), "push", "--remote", "staging"],
            catch_exceptions=False,
        )
        runner.invoke(
            cli,
            ["-s", str(store), "fetch", "--remote", "staging"],
            catch_exceptions=False,
        )
        refs = _git(
            store, "for-each-ref", "--format=%(refname)", "refs/remotes/"
        ).split()
        assert "refs/remotes/staging/main" in refs
        specs = _git(store, "config", "--get-all", "remote.staging.fetch")
        assert "+refs/cloud/*:refs/remotes/staging/cloud/*" in specs

    def test_pull_from_one_remote(self, runner, both, home):
        prod, staging, store = both
        runner.invoke(
            cli,
            ["-s", str(store), "push", "--remote", "staging"],
            catch_exceptions=False,
        )
        other = _store(runner, home / "other")
        _git(other, "remote", "add", "staging", f"{staging.url}/{HANDLE}/demo")
        prod_before = len(prod.state.requests)
        res = runner.invoke(
            cli,
            ["-s", str(other), "pull", "--remote", "staging", "--force"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert _git(other, "rev-parse", "main") == _git(store, "rev-parse", "main")
        assert len(prod.state.requests) == prod_before  # production untouched

    def test_list_show_remove(self, runner, both):
        prod, staging, store = both
        res = runner.invoke(
            cli, ["-s", str(store), "--json", "remote", "list"], catch_exceptions=False
        )
        rows = json.loads(res.output)["remotes"]
        assert [r["name"] for r in rows] == ["origin", "staging"]
        assert {r["gateway"] for r in rows} == {prod.url, staging.url}
        assert all(r["logged_in"] for r in rows)
        res = runner.invoke(
            cli, ["-s", str(store), "remote", "show", "staging"], catch_exceptions=False
        )
        assert "staging:" in res.output
        assert staging.url in res.output
        res = runner.invoke(
            cli,
            ["-s", str(store), "remote", "remove", "staging"],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert "removed cloud remote staging" in res.output
        assert _git(store, "remote") == "origin"

    def test_list_marks_gateways_without_a_login(self, runner, both):
        _prod, staging, store = both
        cloud_auth.remove(staging.url)
        res = runner.invoke(
            cli, ["-s", str(store), "remote", "list"], catch_exceptions=False
        )
        assert "(logged in)" in res.output
        assert "(not logged in)" in res.output
        # and the staging push fails locally while origin still works
        res = runner.invoke(cli, ["-s", str(store), "push", "--remote", "staging"])
        assert res.exit_code == 1
        assert f"not logged in to {staging.url}" in res.output
        staging_requests = len(staging.state.requests)
        res = runner.invoke(cli, ["-s", str(store), "push"], catch_exceptions=False)
        assert res.exit_code == 0, res.output
        assert len(staging.state.requests) == staging_requests

    def test_status_lists_every_remote(self, runner, both):
        prod, staging, store = both
        res = runner.invoke(cli, ["-s", str(store), "status"], catch_exceptions=False)
        assert f"origin: {HANDLE}/demo @ {prod.url}" in res.output
        assert f"staging: {HANDLE}/demo @ {staging.url}" in res.output
        data = json.loads(
            runner.invoke(cli, ["-s", str(store), "--json", "status"]).output
        )
        assert data["origin"] == f"{HANDLE}/demo"
        assert [r["name"] for r in data["remotes"]] == ["origin", "staging"]

    def test_unknown_remote_and_bad_name(self, runner, both):
        _prod, _staging, store = both
        res = runner.invoke(cli, ["-s", str(store), "push", "--remote", "nope"])
        assert res.exit_code == 1
        assert "no remote named 'nope'" in res.output
        res = runner.invoke(cli, ["-s", str(store), "push", "--remote", "bad name"])
        assert res.exit_code == 1
        assert "not a valid remote name" in res.output

    def test_push_create_under_a_named_remote(self, runner, clouds, home):
        _prod, staging = clouds
        cloud_auth.save(staging.url, STAGING_KEY, HANDLE)
        store = _store(runner, home / "fresh")
        res = runner.invoke(
            cli,
            [
                "-s",
                str(store),
                "push",
                "--create",
                "newstore",
                "--url",
                staging.url,
                "--remote",
                "staging",
            ],
            catch_exceptions=False,
        )
        assert res.exit_code == 0, res.output
        assert _git(store, "remote") == "staging"
        assert staging.state.lookup(HANDLE, "newstore") is not None
