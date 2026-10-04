# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync tests: memoir remote / push / pull / fetch.

Cloud stores are addressed GitHub-style as ``<owner>/<store>``. The chunk,
auth, and store endpoints are served by ``tests/fake_cloud.py``; the git half
goes through the real ``git`` binary against ``git http-backend``, so push /
fetch / pull and non-fast-forward rejection are exercised end to end
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


def _second_machine(runner, env, path: Path, address: str = ADDRESS) -> Path:
    """What a second machine looks like: a store that already exists (the
    plugin creates it, and the first command opens it, so it already has
    prollytree's initial commit), then `remote add` + `pull`."""
    res = _invoke(runner, ["new", str(path)])
    assert res.exit_code == 0, res.output
    res = _invoke(runner, ["-s", str(path), "status"])  # opens → initial commit
    assert res.exit_code == 0, res.output
    assert _git(path, "rev-list", "--count", "HEAD") == "1"
    res = _invoke(runner, ["-s", str(path), "remote", "add", address], env=env)
    assert res.exit_code == 0, res.output
    res = _invoke(runner, ["-s", str(path), "--json", "pull"], env=env)
    assert res.exit_code == 0, res.output
    return path


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

    def test_store_id_rejected_before_any_request(self, runner, store, cloud, env):
        """Acceptance 3."""
        res = runner.invoke(
            cli,
            ["-s", str(store), "remote", "add", "str_MKD2ZN-OOxq6ACtrrtJk_A"],
            env=env,
        )
        assert res.exit_code == 1
        assert "<owner>/<store>" in res.output
        assert cloud.state.requests == []
        assert _git(store, "remote") == ""


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

    def test_add_without_argument_defaults_to_cwd_name(
        self, runner, tmp_root, cloud, env, monkeypatch
    ):
        """The proposed name is the project directory (cwd), not the store
        directory: plugin stores live under ~/.memoir/<path-slug>."""
        project = tmp_root / "demo"
        project.mkdir()
        monkeypatch.chdir(project)
        store = tmp_root / "-Users-me-demo"  # a plugin-style store slug
        _invoke(runner, ["new", str(store)])
        res = _invoke(runner, ["-s", str(store), "remote", "add"], env=env, input="y\n")
        assert res.exit_code == 0, res.output
        assert f"Link this store to {ADDRESS}?" in res.output
        assert _git(store, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"

    def test_add_without_argument_declined(
        self, runner, tmp_root, cloud, env, monkeypatch
    ):
        project = tmp_root / "demo"
        project.mkdir()
        monkeypatch.chdir(project)
        store = tmp_root / "s"
        _invoke(runner, ["new", str(store)])
        res = runner.invoke(
            cli, ["-s", str(store), "remote", "add"], env=env, input="n\n"
        )
        assert res.exit_code == 1
        assert _git(store, "remote") == ""

    def test_add_without_argument_bad_dirname(
        self, runner, tmp_root, cloud, env, monkeypatch
    ):
        project = tmp_root / "My Store"
        project.mkdir()
        monkeypatch.chdir(project)
        store = tmp_root / "s"
        _invoke(runner, ["new", str(store)])
        res = runner.invoke(
            cli, ["-s", str(store), "remote", "add"], env=env, input="y\n"
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
        assert data["seconds"] >= 0
        _assert_no_ids(res.output)

        server_chunks = cloud.state.chunks_for(HANDLE, "demo")
        assert set(server_chunks) == local
        for h in local:
            assert (
                server_chunks[h]
                == (linked_store / ".git/prolly/nodes/files" / h).read_bytes()
            )

        # Address-based routes only; uploads go through the batch endpoint,
        # and every batch precedes receive-pack.
        paths = cloud.state.paths()
        assert all(not p.startswith("/sync/") for p in paths)
        assert not cloud.state.paths("PUT")
        batches = [i for i, p in enumerate(paths) if p == f"/{ADDRESS}/chunks/batch"]
        assert len(batches) == 1  # a small store fits one batch
        receive = paths.index(f"/{ADDRESS}/git-receive-pack")
        assert max(batches) < receive

        # The server-confirmed set is recorded for the next push.
        record = linked_store / ".git" / "memoir-cloud" / "pushed-origin"
        assert set(record.read_text().split()) == local

        bare = cloud.state.repo_for(HANDLE, "demo")
        assert _git(bare, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )

    def test_second_push_is_incremental_without_negotiate(
        self, runner, linked_store, cloud, env
    ):
        """Acceptance 2: with the pushed record, a no-op push makes zero
        negotiate and zero batch requests; a push with one new memory makes
        one batch and still no negotiate."""
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        before = len(cloud.state.chunks_for(HANDLE, "demo"))
        cloud.state.requests.clear()

        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        data = json.loads(res.output)
        assert data["chunks_uploaded"] == 0
        assert data["chunks_present"] == before
        posts = cloud.state.paths("POST")
        assert not [
            p for p in posts if p.endswith("/negotiate") or p.endswith("/batch")
        ]

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        cloud.state.requests.clear()
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        data = json.loads(res.output)
        assert data["chunks_present"] == before
        assert data["chunks_uploaded"] == len(_nodes(linked_store)) - before >= 1
        posts = cloud.state.paths("POST")
        assert len([p for p in posts if p.endswith("/batch")]) == 1
        assert not [p for p in posts if p.endswith("/negotiate")]
        record = linked_store / ".git" / "memoir-cloud" / "pushed-origin"
        assert set(record.read_text().split()) == _nodes(linked_store)

    def test_push_without_record_negotiates_once(
        self, runner, linked_store, cloud, env
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        (linked_store / ".git" / "memoir-cloud" / "pushed-origin").unlink()
        cloud.state.requests.clear()
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert json.loads(res.output)["chunks_uploaded"] == 0
        posts = cloud.state.paths("POST")
        assert len([p for p in posts if p.endswith("/negotiate")]) == 1
        assert not [p for p in posts if p.endswith("/batch")]

    def test_failed_chunk_upload_never_pushes_git(
        self, runner, linked_store, cloud, env, monkeypatch
    ):
        """Acceptance 5: persistent 502 → retried, then surfaced; no git push."""
        monkeypatch.setattr(sync_service, "BATCH_BACKOFF", (0.01, 0.01, 0.01))
        cloud.state.batch_fail_502 = -1
        res = runner.invoke(cli, ["-s", str(linked_store), "push"], env=env)
        assert res.exit_code == 1
        assert "object store unavailable, retry later" in res.output
        assert not any(
            "git-receive-pack" in p or "info/refs" in p for p in cloud.state.paths()
        )
        assert _git(cloud.state.repo_for(HANDLE, "demo"), "for-each-ref") == ""
        assert not (linked_store / ".git" / "memoir-cloud" / "pushed-origin").exists()

    def test_transient_502_is_retried(
        self, runner, linked_store, cloud, env, monkeypatch
    ):
        monkeypatch.setattr(sync_service, "BATCH_BACKOFF", (0.01, 0.01, 0.01))
        cloud.state.batch_fail_502 = 1
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        assert len([p for p in cloud.state.paths("POST") if p.endswith("/batch")]) == 2
        assert json.loads(res.output)["chunks_uploaded"] == len(_nodes(linked_store))

    def test_413_splits_the_batch(self, runner, linked_store, cloud, env):
        cloud.state.batch_max_parts = 1
        n = len(_nodes(linked_store))
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        assert json.loads(res.output)["chunks_uploaded"] == n
        assert set(cloud.state.chunks_for(HANDLE, "demo")) == _nodes(linked_store)
        batch_posts = [p for p in cloud.state.paths("POST") if p.endswith("/batch")]
        assert len(batch_posts) >= n  # one 413 per split, then one per chunk

    def test_rejected_chunk_fails_push_before_git(
        self, runner, linked_store, cloud, env
    ):
        victim = sorted(_nodes(linked_store))[0]
        cloud.state.reject_hashes.add(victim)
        res = runner.invoke(cli, ["-s", str(linked_store), "push"], env=env)
        assert res.exit_code == 1
        assert "rejected 1 chunk" in res.output
        assert victim[:12] in res.output
        assert "injected" in res.output
        assert not any("git-receive-pack" in p for p in cloud.state.paths())
        # the other chunks did land and are recorded, so a fixed retry is cheap
        assert set(cloud.state.chunks_for(HANDLE, "demo")) == _nodes(linked_store) - {
            victim
        }

    def test_resume_after_interrupted_push(
        self, runner, linked_store, cloud, env, monkeypatch
    ):
        """Acceptance 3: a push cut off after some batches resumes; earlier
        chunks come back as `existing`, never re-stored."""
        for i in range(3):
            _remember(runner, linked_store, f"workflow.k{i}", f"v{i}")
        monkeypatch.setattr(sync_service, "BATCH_MAX_PARTS", 2)
        monkeypatch.setattr(sync_service, "BATCH_WORKERS", 1)
        monkeypatch.setattr(sync_service, "BATCH_BACKOFF", (0.01, 0.01, 0.01))
        cloud.state.batch_fail_after_ok = 1
        res = runner.invoke(cli, ["-s", str(linked_store), "push"], env=env)
        assert res.exit_code == 1
        assert "object store unavailable" in res.output
        landed = set(cloud.state.chunks_for(HANDLE, "demo"))
        assert 0 < len(landed) < len(_nodes(linked_store))
        assert not any("git-receive-pack" in p for p in cloud.state.paths())

        cloud.state.batch_fail_after_ok = None
        cloud.state.requests.clear()
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["chunks_present"] >= len(landed)
        assert set(cloud.state.chunks_for(HANDLE, "demo")) == _nodes(linked_store)
        assert _git(cloud.state.repo_for(HANDLE, "demo"), "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )

    def test_missing_chunk_on_git_push_falls_back_to_negotiate(
        self, runner, linked_store, cloud, env, monkeypatch
    ):
        """A stale pushed record (e.g. copied from another machine) claims the
        server has chunks it lacks: the server rejects the ref with
        `missing chunk`, the client negotiates everything and retries."""
        record = linked_store / ".git" / "memoir-cloud"
        record.mkdir()
        (record / "pushed-origin").write_text(
            "".join(f"{h}\n" for h in _nodes(linked_store))
        )

        real_git = SyncService._git
        state = {"pushes": 0}

        def fake_git(self, args, **kw):
            if args[:1] == ["push"]:
                state["pushes"] += 1
                if state["pushes"] == 1:
                    return subprocess.CompletedProcess(
                        args,
                        1,
                        "",
                        "! [remote rejected] main -> main (missing chunk abc)",
                    )
            return real_git(self, args, **kw)

        monkeypatch.setattr(SyncService, "_git", fake_git)
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["chunks_uploaded"] == len(_nodes(linked_store))
        posts = cloud.state.paths("POST")
        assert len([p for p in posts if p.endswith("/negotiate")]) == 1
        assert state["pushes"] == 2
        assert set(cloud.state.chunks_for(HANDLE, "demo")) == _nodes(linked_store)

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
# fetch / pull / non-FF
# --------------------------------------------------------------------------


class TestRoundTrip:
    def test_second_machine_remote_add_pull_round_trips(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        """Acceptance 1 + 7, plugin-style: the local store already exists and
        has been opened (initial commit) before it is linked and pulled."""
        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        dest = tmp_root / "desktop"
        _invoke(runner, ["new", str(dest)])
        _invoke(runner, ["-s", str(dest), "status"])
        assert _git(dest, "rev-list", "--count", "HEAD") == "1"  # pristine
        already_local = _nodes(dest)  # the empty-tree root from the initial commit

        res = _invoke(runner, ["-s", str(dest), "remote", "add", ADDRESS], env=env)
        assert f"origin: {ADDRESS}" in res.output
        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["origin"] == ADDRESS
        assert data["created"] is True  # adopted the cloud history
        assert data["chunks_downloaded"] == len(_nodes(linked_store) - already_local)
        _assert_no_ids(res.output)

        assert _git(dest, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )
        assert _git(dest, "remote", "get-url", "origin") == f"{cloud.url}/{ADDRESS}"
        assert "+refs/cloud/*" in _git(
            dest, "config", "--get-all", "remote.origin.fetch"
        )
        assert _nodes(dest) >= _nodes(linked_store)

        res = _invoke(runner, ["-s", str(dest), "status"])
        assert "Memories: 2" in res.output
        assert f"origin: {ADDRESS}" in res.output
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.gates"])
        assert "run tests" in res.output
        assert SyncService(str(dest)).root_hash() in _nodes(dest)

    def test_pull_into_unopened_new_store(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        """`memoir new` without any open leaves HEAD unborn, named by git's
        default branch (whatever it is); pull means `main` and checks it out."""
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "fresh"
        _invoke(runner, ["new", str(dest)])
        _git(dest, "symbolic-ref", "HEAD", "refs/heads/master")  # CI-style default
        _invoke(runner, ["-s", str(dest), "remote", "add", ADDRESS], env=env)
        res = runner.invoke(cli, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == 2
        assert "no memories yet" in res.output
        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["created"] is True
        assert data["branch"] == "main"
        assert _git(dest, "symbolic-ref", "--short", "HEAD") == "main"
        assert _git(dest, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.style"])
        assert "use black" in res.output

    def test_pull_into_store_with_own_memories_is_refused_cleanly(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        """Not pristine (has a real memory) + a cloud history it never saw →
        exit 6 with the adopt-the-cloud hint, never a raw git error; local
        history untouched."""
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "busy"
        _invoke(runner, ["new", str(dest)])
        _remember(runner, dest, "workflow.local", "mine")
        _invoke(runner, ["-s", str(dest), "remote", "add", ADDRESS], env=env)
        res = runner.invoke(cli, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "diverged" in res.output
        assert "memoir pull --force --branch main" in res.output
        assert "fatal" not in res.output
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.local"])
        assert "mine" in res.output

    def test_pull_force_replaces_local_branch(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        """--force: local main := cloud main; previous tip reported and kept
        under refs/memoir/backup/main; local-only memory gone, cloud memory in."""
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "busy"
        _invoke(runner, ["new", str(dest)])
        _remember(runner, dest, "workflow.local", "mine")
        old_tip = _git(dest, "rev-parse", "main")
        _invoke(runner, ["-s", str(dest), "remote", "add", ADDRESS], env=env)

        res = _invoke(runner, ["-s", str(dest), "--json", "pull", "--force"], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["forced"] is True
        assert data["created"] is False
        assert old_tip.startswith(data["previous_tip"])
        assert "replaced main (was" in data["message"]
        _assert_no_ids(res.output)

        assert _git(dest, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.style"])
        assert "use black" in res.output
        res = runner.invoke(cli, ["-s", str(dest), "get", "workflow.local"])
        assert "mine" not in res.output
        # the old tip is parked under a hidden ref for recovery (prollytree
        # commits bypass git's reflog, so this is the only handle on it)
        assert data["backup_ref"] == "refs/memoir/backup/main"
        assert _git(dest, "rev-parse", "refs/memoir/backup/main") == old_tip
        assert "backup" not in _git(dest, "branch", "--list")
        _git(dest, "branch", "recovered", "refs/memoir/backup/main")
        assert _git(dest, "rev-parse", "recovered") == old_tip
        assert SyncService(str(dest)).root_hash() in _nodes(dest)

        # A plain pull afterwards is a no-op fast-forward.
        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        assert json.loads(res.output)["forced"] is False

    def test_pull_force_non_current_branch(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = _second_machine(runner, env, tmp_root / "desktop")
        # desktop diverges on a side branch that also exists on the cloud
        _git(linked_store, "branch", "side")
        _invoke(runner, ["-s", str(linked_store), "push", "--branch", "side"], env=env)
        _git(dest, "branch", "side")
        _git(dest, "commit", "-q", "--allow-empty", "-m", "local side work")
        _git(dest, "branch", "-f", "side", "HEAD")
        _git(dest, "reset", "-q", "--hard", "HEAD~1")

        res = runner.invoke(cli, ["-s", str(dest), "pull", "--branch", "side"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "--force --branch side" in res.output
        res = _invoke(
            runner,
            ["-s", str(dest), "--json", "pull", "--branch", "side", "--force"],
            env=env,
        )
        assert json.loads(res.output)["forced"] is True
        assert _git(dest, "rev-parse", "side") == _git(
            linked_store, "rev-parse", "side"
        )
        assert _git(dest, "symbolic-ref", "--short", "HEAD") == "main"  # untouched

    def test_diverged_pull_force_after_both_sides_commit(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = _second_machine(runner, env, tmp_root / "desktop")
        _remember(runner, linked_store, "workflow.a", "one")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        _remember(runner, dest, "workflow.b", "two")

        res = runner.invoke(cli, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == EXIT_NON_FF
        res = _invoke(runner, ["-s", str(dest), "pull", "--force"], env=env)
        assert res.exit_code == 0, res.output
        assert "replaced main" in res.output
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.a"])
        assert "one" in res.output
        res = runner.invoke(cli, ["-s", str(dest), "get", "workflow.b"])
        assert "two" not in res.output

    def test_pull_bad_key(self, runner, linked_store, env):
        res = runner.invoke(
            cli, ["-s", str(linked_store), "pull"], env={**env, "MEMOIR_API_KEY": "bad"}
        )
        assert res.exit_code == 1
        assert "not signed in: set MEMOIR_API_KEY" in res.output

    def test_fetch_pull_fast_forwards_second_machine(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = _second_machine(runner, env, tmp_root / "desktop")

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        new_tip = _git(linked_store, "rev-parse", "main")

        res = _invoke(runner, ["-s", str(dest), "--json", "fetch"], env=env)
        data = json.loads(res.output)
        assert data["origin"] == ADDRESS
        assert data["chunks_downloaded"] >= 1
        assert "origin/main" in data["remote_refs"]
        assert _git(dest, "rev-parse", "main") != new_tip
        # downloaded chunks are known to be on the server: recorded as pushed
        record = set((dest / ".git/memoir-cloud/pushed-origin").read_text().split())
        assert record >= set(cloud.state.chunks_for(HANDLE, "demo"))

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
        dest = _second_machine(runner, env, tmp_root / "desktop")

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
        dest = _second_machine(runner, env, tmp_root / "desktop")

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        res = runner.invoke(cli, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "run `memoir pull`" in res.output

        res = _invoke(runner, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == 0, res.output
        _remember(runner, dest, "workflow.x", "from desktop")
        res = _invoke(runner, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == 0, res.output
        assert _git(cloud.state.repo_for(HANDLE, "demo"), "rev-parse", "main") == _git(
            dest, "rev-parse", "main"
        )

    def test_diverged_pull_rejected(self, runner, linked_store, cloud, env, tmp_root):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = _second_machine(runner, env, tmp_root / "desktop")

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

        dest = tmp_root / "desktop"
        _invoke(runner, ["new", str(dest)])
        _invoke(runner, ["-s", str(dest), "remote", "add", ADDRESS], env=env)
        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        assert res.exit_code == 0, res.output
        server_chunks = cloud.state.chunks_for(HANDLE, "demo")
        total = len(server_chunks)
        assert json.loads(res.output)["chunks_downloaded"] == total
        listings = [
            p for p in cloud.state.paths("GET") if p.startswith(f"/{ADDRESS}/chunks?")
        ]
        assert len(listings) == -(-total // 2) + (1 if total % 2 == 0 else 0)
        assert _nodes(dest) >= set(server_chunks)
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
        dest = _second_machine(runner, env, tmp_root / "desktop")
        outputs.append(
            _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env).output
        )
        outputs.append(_invoke(runner, ["-s", str(dest), "--json", "status"]).output)

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
    def test_negotiate_batches_of_1000(self, cloud):
        hashes = [f"{i:064x}" for i in range(1201)]
        with CloudClient(cloud.url, API_KEY) as client:
            missing = client.missing_on_server(ADDRESS, hashes)
        assert missing == hashes
        negotiates = [r for r in cloud.state.requests if r.path.endswith("/negotiate")]
        sizes = [len(json.loads(r.body)["have"]) for r in negotiates]
        assert sizes == [1000, 201]

    def test_upload_batch_reports_stored_existing_rejected(self, cloud):
        a, b = "a" * 64, "b" * 64
        with CloudClient(cloud.url, API_KEY) as client:
            client.put_chunk(ADDRESS, a, b"old")
            cloud.state.reject_hashes.add("c" * 64)
            body = client.upload_batch(
                ADDRESS, [(a, b"old"), (b, b"new"), ("c" * 64, b"x")]
            )
        assert body["existing"] == [a]
        assert body["stored"] == [b]
        assert body["rejected"] == {"c" * 64: "injected"}
        assert cloud.state.chunks_for(HANDLE, "demo")[b] == b"new"

    def test_upload_batch_502_retried_then_unavailable(self, cloud, monkeypatch):
        monkeypatch.setattr(sync_service, "BATCH_BACKOFF", (0.01, 0.01, 0.01))
        cloud.state.batch_fail_502 = -1
        with (
            CloudClient(cloud.url, API_KEY) as client,
            pytest.raises(CloudError) as exc,
        ):
            client.upload_batch(ADDRESS, [("d" * 64, b"x")])
        assert "object store unavailable, retry later" in exc.value.message
        assert len([p for p in cloud.state.paths("POST") if p.endswith("/batch")]) == 4

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
