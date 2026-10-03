# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync tests: memoir remote / push / pull / fetch / clone.

Cloud stores are addressed GitHub-style as ``<owner>/<store>``. The chunk,
auth, and store endpoints are served by ``tests/fake_cloud.py``; the git half
goes through the real ``git`` binary against ``git http-backend``, so push /
fetch / pull / clone and non-fast-forward rejection are exercised end to end
without a network.

Run with: pytest tests/test_cloud_sync.py -v
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from memoir.cli.main import EXIT_NON_FF, cli
from memoir.services import sync_service
from memoir.services.base import ServiceError
from memoir.services.sync_service import (
    CloudClient,
    CloudError,
    SyncService,
    parse_address,
    parse_remote_url,
)
from tests.fake_cloud import API_KEY, HANDLE, OTHER_HANDLE, FakeCloud

ADDRESS = f"{HANDLE}/demo"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def tmp_root():
    root = tempfile.mkdtemp(prefix="memoir_cloud_sync_")
    yield Path(root)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def cloud(tmp_root):
    repos = tmp_root / "repos"
    repos.mkdir()
    with FakeCloud(repos_root=repos) as fake:
        fake.state.create_store("demo")
        yield fake


@pytest.fixture
def env(cloud):
    """Env for CliRunner: key set, gateway pointed at the fake."""
    return {"MEMOIR_API_KEY": API_KEY, "MEMOIR_CLOUD_URL": cloud.url}


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, args, env=None, input=None):
    return runner.invoke(cli, args, env=env, input=input, catch_exceptions=False)


@pytest.fixture
def store(tmp_root, runner):
    """A local store with one memory committed."""
    path = tmp_root / "store"
    res = _invoke(runner, ["new", str(path)])
    assert res.exit_code == 0, res.output
    _remember(runner, path, "workflow.coding.style", "use black")
    return path


def _remember(runner, path, key, content):
    res = _invoke(runner, ["-s", str(path), "remember", "-p", key, content])
    assert res.exit_code == 0, res.output


@pytest.fixture
def linked_store(store, runner, env):
    res = _invoke(runner, ["-s", str(store), "remote", "add", ADDRESS], env=env)
    assert res.exit_code == 0, res.output
    return store


def _nodes(path: Path) -> set[str]:
    nodes = path / ".git" / "prolly" / "nodes" / "files"
    return {p.name for p in nodes.iterdir() if sync_service.CHUNK_HASH_RE.match(p.name)}


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _assert_no_ids(text: str) -> None:
    assert "str_" not in text, text


# --------------------------------------------------------------------------
# gating
# --------------------------------------------------------------------------


class TestGating:
    @pytest.mark.parametrize(
        "args",
        [
            ["remote", "add", ADDRESS],
            ["remote", "show"],
            ["remote", "remove"],
            ["push"],
            ["pull"],
            ["fetch"],
        ],
    )
    def test_commands_require_key(self, runner, store, args, monkeypatch):
        monkeypatch.delenv("MEMOIR_API_KEY", raising=False)
        res = runner.invoke(cli, ["-s", str(store), *args])
        assert res.exit_code == 1
        assert "requires MEMOIR_API_KEY (PRO)" in res.output

    def test_clone_requires_key(self, runner, tmp_root, monkeypatch):
        monkeypatch.delenv("MEMOIR_API_KEY", raising=False)
        res = runner.invoke(cli, ["clone", ADDRESS, str(tmp_root / "x")])
        assert res.exit_code == 1
        assert "requires MEMOIR_API_KEY (PRO)" in res.output

    def test_existing_commands_unaffected(self, runner, store, monkeypatch):
        monkeypatch.delenv("MEMOIR_API_KEY", raising=False)
        res = runner.invoke(cli, ["-s", str(store), "status"])
        assert res.exit_code == 0
        assert "Initialized" in res.output
        assert "origin" not in res.output

    def test_cloud_enabled_helper(self, monkeypatch):
        monkeypatch.delenv("MEMOIR_API_KEY", raising=False)
        assert sync_service.cloud_enabled() is False
        monkeypatch.setenv("MEMOIR_API_KEY", "   ")
        assert sync_service.cloud_enabled() is False
        monkeypatch.setenv("MEMOIR_API_KEY", "k")
        assert sync_service.cloud_enabled() is True

    def test_machine_readable_lists_cloud_group_and_exit_code(self, runner):
        res = runner.invoke(cli, ["--machine-readable"])
        data = json.loads(res.output)
        assert data["exit_codes"]["6"] == "non_fast_forward"
        assert {c["name"] for c in data["commands"]["cloud"]} == {
            "remote",
            "push",
            "pull",
            "fetch",
            "clone",
        }
        assert "MEMOIR_API_KEY" in data["env_vars"]
        assert "MEMOIR_CLOUD_URL" in data["env_vars"]

    @pytest.mark.parametrize(
        "args",
        [["remote", "add", ADDRESS], ["push"], ["fetch"], ["pull"]],
    )
    def test_no_handle_tells_user_to_choose_one(
        self, runner, linked_store, cloud, env, args
    ):
        """Acceptance 5: every cloud command points at $GW/app when handle is null."""
        cloud.state.handle = None
        res = runner.invoke(
            cli,
            (
                ["-s", str(linked_store), *args, "--force"]
                if args[0] == "remote"
                else ["-s", str(linked_store), *args]
            ),
            env=env,
        )
        assert res.exit_code == 1
        assert f"{cloud.url}/app" in res.output
        assert "handle" in res.output

    def test_no_handle_clone(self, runner, cloud, env, tmp_root):
        cloud.state.handle = None
        res = runner.invoke(cli, ["clone", ADDRESS, str(tmp_root / "c")], env=env)
        assert res.exit_code == 1
        assert f"{cloud.url}/app" in res.output


# --------------------------------------------------------------------------
# addresses
# --------------------------------------------------------------------------


class TestAddresses:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("feng-zhang/demo", ("feng-zhang", "demo")),
            ("  feng-zhang/demo.v2 ", ("feng-zhang", "demo.v2")),
            ("https://gw.example/feng-zhang/demo", ("feng-zhang", "demo")),
            ("https://gw.example/feng-zhang/demo/", ("feng-zhang", "demo")),
            ("https://gw.example/feng-zhang/demo.git", ("feng-zhang", "demo")),
        ],
    )
    def test_parse_valid(self, text, expected):
        assert parse_address(text) == expected

    @pytest.mark.parametrize(
        ("text", "fragment"),
        [
            ("demo", "expected <owner>/<store>"),
            ("a/b/c", "expected <owner>/<store>"),
            ("feng-zhang/My Store", "store names are 1-100 letters"),
            ("feng-zhang/.hidden", "store names are"),
            ("feng-zhang/demo.git", "store names are"),
            ("-bad/demo", "handles are"),
            ("bad--handle/demo", "handles are"),
            ("under_score/demo", "handles are"),
            ("str_MKD2ZN-OOxq6ACtrrtJk_A", "<owner>/<store>"),
            ("https://gw.example/sync/str_abc", "<owner>/<store>"),
        ],
    )
    def test_parse_invalid(self, text, fragment):
        with pytest.raises(ServiceError) as exc:
            parse_address(text)
        assert fragment in exc.value.message

    def test_parse_remote_url(self):
        assert parse_remote_url("https://g.example/feng-zhang/demo") == (
            "https://g.example",
            "feng-zhang",
            "demo",
        )
        assert parse_remote_url("http://127.0.0.1:5/prefix/x/y") == (
            "http://127.0.0.1:5/prefix",
            "x",
            "y",
        )
        with pytest.raises(ServiceError) as exc:
            parse_remote_url("https://g.example/sync/str_x")
        assert "legacy" in exc.value.message

    def test_store_id_rejected_before_any_request(self, runner, tmp_root, cloud, env):
        """Acceptance 3."""
        res = runner.invoke(
            cli, ["clone", "str_MKD2ZN-OOxq6ACtrrtJk_A", str(tmp_root / "c")], env=env
        )
        assert res.exit_code == 1
        assert "<owner>/<store>" in res.output
        assert cloud.state.requests == []
        assert not (tmp_root / "c").exists()


# --------------------------------------------------------------------------
# remote
# --------------------------------------------------------------------------


class TestRemote:
    def test_add_resolves_then_sets_origin(self, runner, store, cloud, env):
        res = _invoke(runner, ["-s", str(store), "remote", "add", ADDRESS], env=env)
        assert res.exit_code == 0, res.output
        assert f"origin: {ADDRESS}" in res.output
        _assert_no_ids(res.output)
        assert cloud.state.paths("GET") == [
            "/auth/whoami",
            f"/stores/by-name/{HANDLE}/demo",
        ]
        assert _git(store, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"
        fetch_specs = _git(store, "config", "--get-all", "remote.origin.fetch")
        assert "+refs/cloud/*:refs/remotes/origin/cloud/*" in fetch_specs

    def test_add_accepts_full_url(self, runner, store, cloud, env):
        res = _invoke(
            runner,
            ["-s", str(store), "remote", "add", f"{cloud.url}/{ADDRESS}"],
            env=env,
        )
        assert res.exit_code == 0, res.output
        assert _git(store, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"

    def test_add_unknown_or_not_owned(self, runner, store, cloud, env):
        cloud.state.create_store("theirs", owner_handle=OTHER_HANDLE)
        for address in (f"{HANDLE}/nope", f"{OTHER_HANDLE}/theirs"):
            res = runner.invoke(
                cli, ["-s", str(store), "remote", "add", address], env=env
            )
            assert res.exit_code == 1
            assert f"store {address} not found (or you don't own it)" in res.output
        assert _git(store, "remote") == ""

    def test_add_bad_key(self, runner, store, env):
        res = runner.invoke(
            cli,
            ["-s", str(store), "remote", "add", ADDRESS],
            env={**env, "MEMOIR_API_KEY": "wrong"},
        )
        assert res.exit_code == 1
        assert "not signed in: set MEMOIR_API_KEY" in res.output

    def test_add_twice_requires_force(self, runner, linked_store, env, cloud):
        cloud.state.create_store("other")
        res = runner.invoke(
            cli, ["-s", str(linked_store), "remote", "add", f"{HANDLE}/other"], env=env
        )
        assert res.exit_code == 1
        assert "--force" in res.output
        assert ADDRESS in res.output
        res = _invoke(
            runner,
            ["-s", str(linked_store), "remote", "add", f"{HANDLE}/other", "--force"],
            env=env,
        )
        assert res.exit_code == 0
        assert _git(linked_store, "remote", "get-url", "origin").endswith("/other")

    def test_add_without_argument_defaults_and_confirms(
        self, runner, tmp_root, cloud, env
    ):
        path = tmp_root / "demo"  # directory name == store name
        _invoke(runner, ["new", str(path)])
        res = _invoke(runner, ["-s", str(path), "remote", "add"], env=env, input="y\n")
        assert res.exit_code == 0, res.output
        assert f"Link this store to {ADDRESS}?" in res.output
        assert _git(path, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"

    def test_add_without_argument_declined(self, runner, tmp_root, cloud, env):
        path = tmp_root / "demo"
        _invoke(runner, ["new", str(path)])
        res = runner.invoke(
            cli, ["-s", str(path), "remote", "add"], env=env, input="n\n"
        )
        assert res.exit_code == 1
        assert _git(path, "remote") == ""

    def test_add_without_argument_bad_dirname(self, runner, tmp_root, cloud, env):
        path = tmp_root / "My Store"
        _invoke(runner, ["new", str(path)])
        res = runner.invoke(
            cli, ["-s", str(path), "remote", "add"], env=env, input="y\n"
        )
        assert res.exit_code == 1
        assert "not usable as a store name" in res.output

    def test_add_without_argument_json_requires_address(self, runner, store, env):
        res = runner.invoke(cli, ["-s", str(store), "--json", "remote", "add"], env=env)
        assert res.exit_code == 1
        assert "required" in res.output

    def test_show_and_remove(self, runner, linked_store, env, cloud):
        res = _invoke(
            runner, ["-s", str(linked_store), "--json", "remote", "show"], env=env
        )
        data = json.loads(res.output)
        assert data["origin"] == ADDRESS
        assert data["gateway"] == cloud.url
        assert data["branch"] == "main"
        assert data["store"]["name"] == "demo"
        assert data["store"]["owner_handle"] == HANDLE
        assert "id" not in data["store"]
        _assert_no_ids(res.output)

        res = _invoke(runner, ["-s", str(linked_store), "remote", "show"], env=env)
        assert f"origin:   {ADDRESS}" in res.output
        _assert_no_ids(res.output)

        res = _invoke(runner, ["-s", str(linked_store), "remote", "remove"], env=env)
        assert res.exit_code == 0
        assert ADDRESS in res.output
        assert "origin" not in _git(linked_store, "remote")

    def test_show_without_remote(self, runner, store, env):
        res = runner.invoke(cli, ["-s", str(store), "remote", "show"], env=env)
        assert res.exit_code == 1
        assert "no cloud remote configured" in res.output

    def test_status_shows_origin(self, runner, linked_store, store, env):
        """Acceptance 6."""
        res = _invoke(runner, ["-s", str(linked_store), "status"])
        assert f"origin: {ADDRESS}" in res.output
        res = _invoke(runner, ["-s", str(linked_store), "--json", "status"])
        assert json.loads(res.output)["origin"] == ADDRESS


# --------------------------------------------------------------------------
# push
# --------------------------------------------------------------------------


class TestPush:
    def test_push_uploads_chunks_then_pushes_git(
        self, runner, linked_store, cloud, env
    ):
        local = _nodes(linked_store)
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["pushed"] is True
        assert data["branch"] == "main"
        assert data["origin"] == ADDRESS
        assert data["chunks_uploaded"] == len(local)
        assert data["chunks_present"] == 0
        _assert_no_ids(res.output)

        server_chunks = cloud.state.chunks_for(HANDLE, "demo")
        assert set(server_chunks) == local
        for h in local:
            assert (
                server_chunks[h]
                == (linked_store / ".git/prolly/nodes/files" / h).read_bytes()
            )

        # Address-based routes only, and every PUT precedes receive-pack.
        paths = cloud.state.paths()
        assert all(not p.startswith("/sync/") for p in paths)
        last_put = max(i for i, p in enumerate(paths) if f"/{ADDRESS}/chunks/" in p)
        receive = paths.index(f"/{ADDRESS}/git-receive-pack")
        assert last_put < receive

        bare = cloud.state.repo_for(HANDLE, "demo")
        assert _git(bare, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )

    def test_second_push_is_incremental(self, runner, linked_store, cloud, env):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        before = len(cloud.state.chunks_for(HANDLE, "demo"))
        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        data = json.loads(res.output)
        assert data["chunks_present"] == before
        assert data["chunks_uploaded"] == len(_nodes(linked_store)) - before
        assert data["chunks_uploaded"] >= 1

    def test_failed_chunk_upload_never_pushes_git(
        self, runner, linked_store, cloud, env
    ):
        victim = sorted(_nodes(linked_store))[0]
        cloud.state.fail_puts.add(victim)
        res = runner.invoke(cli, ["-s", str(linked_store), "push"], env=env)
        assert res.exit_code == 1
        assert "500" in res.output
        assert not any(
            "git-receive-pack" in p or "info/refs" in p for p in cloud.state.paths()
        )
        assert _git(cloud.state.repo_for(HANDLE, "demo"), "for-each-ref") == ""

    def test_transient_5xx_is_retried(self, runner, linked_store, cloud, env):
        victim = sorted(_nodes(linked_store))[0]
        cloud.state.flaky_puts.add(victim)
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        puts = [p for p in cloud.state.paths("PUT") if p.endswith(victim)]
        assert len(puts) == 2

    def test_push_refuses_cloud_branch(self, runner, linked_store, env, cloud):
        _git(linked_store, "branch", "cloud/feature/x")
        before = len(cloud.state.requests)
        res = runner.invoke(
            cli,
            ["-s", str(linked_store), "push", "--branch", "cloud/feature/x"],
            env=env,
        )
        assert res.exit_code == 1
        assert "cloud-owned" in res.output
        assert len(cloud.state.requests) == before

    def test_push_missing_branch(self, runner, linked_store, env):
        res = runner.invoke(
            cli, ["-s", str(linked_store), "push", "--branch", "nope"], env=env
        )
        assert res.exit_code == 2

    def test_push_bad_key_stops_before_git(self, runner, linked_store, env, cloud):
        res = runner.invoke(
            cli,
            ["-s", str(linked_store), "push"],
            env={**env, "MEMOIR_API_KEY": "wrong"},
        )
        assert res.exit_code == 1
        assert "not signed in: set MEMOIR_API_KEY" in res.output
        assert all("git-" not in p for p in cloud.state.paths())

    def test_push_without_remote(self, runner, store, env):
        res = runner.invoke(cli, ["-s", str(store), "push"], env=env)
        assert res.exit_code == 1
        assert "push --create" in res.output


class TestPushCreate:
    def test_create_links_and_pushes(self, runner, store, cloud, env):
        res = _invoke(
            runner, ["-s", str(store), "--json", "push", "--create", "fresh"], env=env
        )
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["origin"] == f"{HANDLE}/fresh"
        assert data["pushed"] is True
        _assert_no_ids(res.output)
        assert (
            _git(store, "remote", "get-url", "origin") == f"{cloud.url}/{HANDLE}/fresh"
        )
        created = [
            r
            for r in cloud.state.requests
            if r.method == "POST" and r.path == "/stores"
        ]
        assert json.loads(created[0].body) == {"name": "fresh"}
        assert _git(cloud.state.repo_for(HANDLE, "fresh"), "rev-parse", "main") == _git(
            store, "rev-parse", "main"
        )

    def test_create_bad_name_fails_locally(self, runner, store, cloud, env):
        """Acceptance 4a: no request is made."""
        res = runner.invoke(
            cli, ["-s", str(store), "push", "--create", "Bad Name"], env=env
        )
        assert res.exit_code == 1
        assert "store names are" in res.output
        assert cloud.state.requests == []
        assert _git(store, "remote") == ""

    def test_create_duplicate_reports_409(self, runner, store, cloud, env):
        """Acceptance 4b."""
        res = runner.invoke(
            cli, ["-s", str(store), "push", "--create", "demo"], env=env
        )
        assert res.exit_code == 1
        assert "store name already exists" in res.output
        assert f"memoir remote add {HANDLE}/demo" in res.output
        assert _git(store, "remote") == ""

    def test_create_when_already_linked(self, runner, linked_store, env):
        res = runner.invoke(
            cli, ["-s", str(linked_store), "push", "--create", "x"], env=env
        )
        assert res.exit_code == 1
        assert f"already linked to {ADDRESS}" in res.output


# --------------------------------------------------------------------------
# fetch / pull / clone / non-FF
# --------------------------------------------------------------------------


class TestRoundTrip:
    def test_clone_round_trips_memories(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        """Acceptance 1 + 7."""
        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        dest = tmp_root / "clone"
        res = _invoke(runner, ["--json", "clone", ADDRESS, str(dest)], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["origin"] == ADDRESS
        assert data["chunks_downloaded"] == len(_nodes(linked_store))
        assert data["branch"] == "main"
        _assert_no_ids(res.output)

        assert (dest / ".git" / "memoir-backend").read_text().strip() == "file"
        assert _git(dest, "remote") == "origin"
        assert _git(dest, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"
        assert "+refs/cloud/*" in _git(
            dest, "config", "--get-all", "remote.origin.fetch"
        )
        assert _nodes(dest) == _nodes(linked_store)

        res = _invoke(runner, ["-s", str(dest), "status"])
        assert "Memories: 2" in res.output
        assert f"origin: {ADDRESS}" in res.output
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.gates"])
        assert "run tests" in res.output
        assert SyncService(str(dest)).root_hash() in _nodes(dest)

    def test_clone_prints_address_in_human_mode(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        res = _invoke(runner, ["clone", ADDRESS, str(tmp_root / "c")], env=env)
        assert f"origin: {ADDRESS}" in res.output
        _assert_no_ids(res.output)

    def test_clone_default_path_is_store_name(
        self, runner, linked_store, cloud, env, tmp_root, monkeypatch
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        monkeypatch.chdir(tmp_root)
        res = _invoke(runner, ["clone", ADDRESS], env=env)
        assert res.exit_code == 0, res.output
        assert (tmp_root / "demo" / ".git" / "memoir-backend").exists()

    def test_clone_not_found_leaves_nothing_behind(self, runner, cloud, env, tmp_root):
        """Acceptance 2."""
        dest = tmp_root / "nope"
        res = runner.invoke(
            cli, ["clone", f"{HANDLE}/does-not-exist", str(dest)], env=env
        )
        assert res.exit_code == 1
        assert (
            f"store {HANDLE}/does-not-exist not found (or you don't own it)"
            in res.output
        )
        assert not dest.exists()
        assert all("git" not in p for p in cloud.state.paths())

    def test_clone_into_nonempty_dir_fails(self, runner, env, tmp_root):
        dest = tmp_root / "busy"
        dest.mkdir()
        (dest / "x").write_text("x")
        res = runner.invoke(cli, ["clone", ADDRESS, str(dest)], env=env)
        assert res.exit_code == 1
        assert "not empty" in res.output

    def test_clone_bad_key(self, runner, env, tmp_root):
        res = runner.invoke(
            cli,
            ["clone", ADDRESS, str(tmp_root / "c")],
            env={**env, "MEMOIR_API_KEY": "bad"},
        )
        assert res.exit_code == 1
        assert "not signed in: set MEMOIR_API_KEY" in res.output

    def test_fetch_pull_fast_forwards_clone(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", ADDRESS, str(dest)], env=env)

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        new_tip = _git(linked_store, "rev-parse", "main")

        res = _invoke(runner, ["-s", str(dest), "--json", "fetch"], env=env)
        data = json.loads(res.output)
        assert data["origin"] == ADDRESS
        assert data["chunks_downloaded"] >= 1
        assert "origin/main" in data["remote_refs"]
        assert _git(dest, "rev-parse", "main") != new_tip

        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        data = json.loads(res.output)
        assert data["created"] is False
        assert _git(dest, "rev-parse", "main") == new_tip
        assert new_tip.startswith(data["tip"])

        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.gates"])
        assert "run tests" in res.output

    def test_pull_creates_missing_branch(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", ADDRESS, str(dest)], env=env)

        _git(linked_store, "branch", "experiments")
        _invoke(
            runner,
            ["-s", str(linked_store), "push", "--branch", "experiments"],
            env=env,
        )

        res = _invoke(
            runner,
            ["-s", str(dest), "--json", "pull", "--branch", "experiments"],
            env=env,
        )
        data = json.loads(res.output)
        assert data["created"] is True
        assert _git(dest, "rev-parse", "experiments") == _git(
            linked_store, "rev-parse", "main"
        )

    def test_pull_unknown_branch(self, runner, linked_store, env):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        res = runner.invoke(
            cli, ["-s", str(linked_store), "pull", "--branch", "ghost"], env=env
        )
        assert res.exit_code == 2

    def test_non_ff_push_rejected_then_pull_then_push(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", ADDRESS, str(dest)], env=env)

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        res = runner.invoke(cli, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "run `memoir pull`" in res.output

        res = _invoke(runner, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == 0, res.output
        _remember(runner, dest, "workflow.x", "from clone")
        res = _invoke(runner, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == 0, res.output
        assert _git(cloud.state.repo_for(HANDLE, "demo"), "rev-parse", "main") == _git(
            dest, "rev-parse", "main"
        )

    def test_diverged_pull_rejected(self, runner, linked_store, cloud, env, tmp_root):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", ADDRESS, str(dest)], env=env)

        _remember(runner, linked_store, "workflow.a", "one")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        _remember(runner, dest, "workflow.b", "two")

        res = runner.invoke(cli, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "diverged" in res.output

    def test_fetch_downloads_atomically_and_paginates(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        for i in range(4):
            _remember(runner, linked_store, f"workflow.k{i}", f"v{i}")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        cloud.state.page_size = 2

        dest = tmp_root / "clone"
        res = _invoke(runner, ["--json", "clone", ADDRESS, str(dest)], env=env)
        assert res.exit_code == 0, res.output
        server_chunks = cloud.state.chunks_for(HANDLE, "demo")
        total = len(server_chunks)
        assert json.loads(res.output)["chunks_downloaded"] == total
        listings = [
            p for p in cloud.state.paths("GET") if p.startswith(f"/{ADDRESS}/chunks?")
        ]
        assert len(listings) == -(-total // 2) + (1 if total % 2 == 0 else 0)
        assert _nodes(dest) == set(server_chunks)
        assert not list((dest / ".git/prolly/nodes/files").glob("*.partial.*"))


# --------------------------------------------------------------------------
# key hygiene
# --------------------------------------------------------------------------


class TestKeyHygiene:
    def test_key_never_persisted_or_printed(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        outputs = []
        outputs.append(
            _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env).output
        )
        outputs.append(
            _invoke(
                runner, ["-s", str(linked_store), "--json", "remote", "show"], env=env
            ).output
        )
        dest = tmp_root / "clone"
        outputs.append(
            _invoke(runner, ["--json", "clone", ADDRESS, str(dest)], env=env).output
        )
        outputs.append(
            _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env).output
        )

        for out in outputs:
            assert API_KEY not in out
            _assert_no_ids(out)
        for path in (linked_store, dest):
            for f in (path / ".git").rglob("*"):
                if f.is_file() and f.suffix != ".pack" and f.stat().st_size < 1_000_000:
                    assert API_KEY not in f.read_bytes().decode("latin-1"), f
            assert "str_" not in (path / ".git" / "config").read_text()

        assert cloud.state.requests
        for req in cloud.state.requests:
            assert req.headers.get("Authorization") == f"Bearer {API_KEY}"

    def test_git_error_output_is_redacted(self, runner, linked_store, env, monkeypatch):
        service = SyncService(str(linked_store))
        service._key = API_KEY

        class Fake:
            returncode = 128
            stdout = ""
            stderr = f"fatal: header 'Authorization: Bearer {API_KEY}' rejected"

        monkeypatch.setattr(sync_service.subprocess, "run", lambda *a, **k: Fake())
        with pytest.raises(ServiceError) as exc:
            service._git(["push", "origin"])
        assert API_KEY not in exc.value.message
        assert "***" in exc.value.message


# --------------------------------------------------------------------------
# chunk protocol unit tests (CloudClient)
# --------------------------------------------------------------------------


class TestCloudClient:
    def test_negotiate_batches_of_500(self, cloud):
        hashes = [f"{i:064x}" for i in range(1201)]
        with CloudClient(cloud.url, API_KEY) as client:
            missing = client.missing_on_server(ADDRESS, hashes)
        assert missing == hashes
        negotiates = [r for r in cloud.state.requests if r.path.endswith("/negotiate")]
        sizes = [len(json.loads(r.body)["have"]) for r in negotiates]
        assert sizes == [500, 500, 201]

    def test_put_is_idempotent(self, cloud):
        h = "a" * 64
        with CloudClient(cloud.url, API_KEY) as client:
            assert client.put_chunk(ADDRESS, h, b"data") is True
            assert client.put_chunk(ADDRESS, h, b"data") is False
            assert client.get_chunk(ADDRESS, h) == b"data"

    def test_404_is_not_retried(self, cloud):
        with (
            CloudClient(cloud.url, API_KEY) as client,
            pytest.raises(CloudError) as exc,
        ):
            client.get_chunk(ADDRESS, "b" * 64)
        assert exc.value.status == 404
        gets = [p for p in cloud.state.paths("GET") if p.endswith("b" * 64)]
        assert len(gets) == 1

    def test_create_store_422_surfaces_server_text(self, cloud):
        with (
            CloudClient(cloud.url, API_KEY) as client,
            pytest.raises(CloudError) as exc,
        ):
            client.create_store("Bad Name")
        assert exc.value.status == 422
        assert "store names are" in exc.value.message
        assert "Value error" not in exc.value.message

    def test_connection_error_surfaces_as_cloud_error(self, tmp_root):
        with (
            CloudClient("http://127.0.0.1:9", API_KEY) as client,
            pytest.raises(CloudError) as exc,
        ):
            client.whoami()
        assert API_KEY not in exc.value.message

    def test_local_chunks_ignores_config_and_partials(self, store):
        nodes = store / ".git" / "prolly" / "nodes" / "files"
        (nodes / "config_tree_config").write_text("{}")
        (nodes / f"{'c' * 64}.partial.123").write_bytes(b"x")
        local = SyncService(str(store)).local_chunks()
        assert "config_tree_config" not in local
        assert not any(".partial." in h for h in local)
        assert all(sync_service.CHUNK_HASH_RE.match(h) for h in local)

    def test_resolve_gateway_precedence(self, monkeypatch):
        monkeypatch.delenv("MEMOIR_CLOUD_URL", raising=False)
        assert sync_service.resolve_gateway() == sync_service.DEFAULT_GATEWAY
        monkeypatch.setenv("MEMOIR_CLOUD_URL", "https://env.example/")
        assert sync_service.resolve_gateway() == "https://env.example"
        assert (
            sync_service.resolve_gateway("https://flag.example/")
            == "https://flag.example"
        )
        assert os.environ["MEMOIR_CLOUD_URL"]
