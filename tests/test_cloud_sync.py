# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync tests: memoir remote / push / pull / fetch / clone.

The chunk and auth endpoints are served by ``tests/fake_cloud.py``; the git
half goes through the real ``git`` binary against ``git http-backend``, so
push / fetch / pull / clone and non-fast-forward rejection are exercised
end to end without a network.

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
    parse_remote_url,
)
from tests.fake_cloud import API_KEY, FakeCloud

STORE_ID = "str_test0001"


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
        fake.state.create_store(STORE_ID, "test store")
        yield fake


@pytest.fixture
def env(cloud):
    """Env for CliRunner: key set, gateway pointed at the fake."""
    return {"MEMORY_API_KEY": API_KEY, "MEMOIR_CLOUD_URL": cloud.url}


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, args, env=None):
    return runner.invoke(cli, args, env=env, catch_exceptions=False)


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
    res = _invoke(runner, ["-s", str(store), "remote", "add", STORE_ID], env=env)
    assert res.exit_code == 0, res.output
    return store


def _nodes(path: Path) -> set[str]:
    nodes = path / ".git" / "prolly" / "nodes" / "files"
    return {p.name for p in nodes.iterdir() if sync_service.CHUNK_HASH_RE.match(p.name)}


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


# --------------------------------------------------------------------------
# gating
# --------------------------------------------------------------------------


class TestGating:
    @pytest.mark.parametrize(
        "args",
        [
            ["remote", "add", STORE_ID],
            ["remote", "show"],
            ["remote", "remove"],
            ["push"],
            ["pull"],
            ["fetch"],
        ],
    )
    def test_commands_require_key(self, runner, store, args, monkeypatch):
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
        res = runner.invoke(cli, ["-s", str(store), *args])
        assert res.exit_code == 1
        assert "requires MEMORY_API_KEY (PRO)" in res.output

    def test_clone_requires_key(self, runner, tmp_root, monkeypatch):
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
        res = runner.invoke(cli, ["clone", STORE_ID, str(tmp_root / "x")])
        assert res.exit_code == 1
        assert "requires MEMORY_API_KEY (PRO)" in res.output

    def test_existing_commands_unaffected(self, runner, store, monkeypatch):
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
        res = runner.invoke(cli, ["-s", str(store), "status"])
        assert res.exit_code == 0
        assert "Initialized" in res.output

    def test_cloud_enabled_helper(self, monkeypatch):
        monkeypatch.delenv("MEMORY_API_KEY", raising=False)
        assert sync_service.cloud_enabled() is False
        monkeypatch.setenv("MEMORY_API_KEY", "   ")
        assert sync_service.cloud_enabled() is False
        monkeypatch.setenv("MEMORY_API_KEY", "k")
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
        assert "MEMORY_API_KEY" in data["env_vars"]
        assert "MEMOIR_CLOUD_URL" in data["env_vars"]


# --------------------------------------------------------------------------
# remote
# --------------------------------------------------------------------------


class TestRemote:
    def test_add_verifies_key_and_store(self, runner, store, cloud, env):
        res = _invoke(runner, ["-s", str(store), "remote", "add", STORE_ID], env=env)
        assert res.exit_code == 0, res.output
        assert cloud.state.paths("GET")[:2] == ["/auth/whoami", f"/stores/{STORE_ID}"]
        assert _git(store, "remote", "get-url", "memoir-cloud") == (
            f"{cloud.url}/sync/{STORE_ID}"
        )
        fetch_specs = _git(store, "config", "--get-all", "remote.memoir-cloud.fetch")
        assert "+refs/cloud/*:refs/remotes/memoir-cloud/cloud/*" in fetch_specs

    def test_add_unknown_store(self, runner, store, env):
        res = runner.invoke(
            cli, ["-s", str(store), "remote", "add", "str_nope"], env=env
        )
        assert res.exit_code == 1
        assert "404" in res.output

    def test_add_bad_key(self, runner, store, env):
        res = runner.invoke(
            cli,
            ["-s", str(store), "remote", "add", STORE_ID],
            env={**env, "MEMORY_API_KEY": "wrong"},
        )
        assert res.exit_code == 1
        assert "MEMORY_API_KEY is missing or invalid" in res.output

    def test_add_twice_requires_force(self, runner, linked_store, env, cloud):
        cloud.state.create_store("str_other")
        res = runner.invoke(
            cli, ["-s", str(linked_store), "remote", "add", "str_other"], env=env
        )
        assert res.exit_code == 1
        assert "--force" in res.output
        res = _invoke(
            runner,
            ["-s", str(linked_store), "remote", "add", "str_other", "--force"],
            env=env,
        )
        assert res.exit_code == 0
        assert _git(linked_store, "remote", "get-url", "memoir-cloud").endswith(
            "str_other"
        )

    def test_add_create(self, runner, store, cloud, env):
        res = _invoke(
            runner,
            [
                "-s",
                str(store),
                "--json",
                "remote",
                "add",
                "--create",
                "--name",
                "laptop",
            ],
            env=env,
        )
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["store"]["name"] == "laptop"
        assert data["store_id"] in cloud.state.stores
        assert _git(store, "remote", "get-url", "memoir-cloud").endswith(
            data["store_id"]
        )

    def test_add_create_defaults_name_to_basename(self, runner, store, cloud, env):
        res = _invoke(
            runner, ["-s", str(store), "--json", "remote", "add", "--create"], env=env
        )
        assert json.loads(res.output)["store"]["name"] == store.name

    def test_show_and_remove(self, runner, linked_store, env, cloud):
        res = _invoke(
            runner, ["-s", str(linked_store), "--json", "remote", "show"], env=env
        )
        data = json.loads(res.output)
        assert data == {
            "gateway": cloud.url,
            "store_id": STORE_ID,
            "branch": "main",
            "store": cloud.state.stores[STORE_ID],
        }
        res = _invoke(runner, ["-s", str(linked_store), "remote", "show"], env=env)
        assert f"Store id: {STORE_ID}" in res.output

        res = _invoke(runner, ["-s", str(linked_store), "remote", "remove"], env=env)
        assert res.exit_code == 0
        assert "memoir-cloud" not in _git(linked_store, "remote")

    def test_show_without_remote(self, runner, store, env):
        res = runner.invoke(cli, ["-s", str(store), "remote", "show"], env=env)
        assert res.exit_code == 1
        assert "no cloud remote configured" in res.output

    def test_parse_remote_url(self):
        assert parse_remote_url("https://g.example/sync/str_x") == (
            "https://g.example",
            "str_x",
        )
        with pytest.raises(ServiceError):
            parse_remote_url("https://g.example/other/str_x")


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
        assert data["chunks_uploaded"] == len(local)
        assert data["chunks_present"] == 0

        assert set(cloud.state.chunks[STORE_ID]) == local
        for h in local:
            assert (
                cloud.state.chunks[STORE_ID][h]
                == (linked_store / ".git/prolly/nodes/files" / h).read_bytes()
            )

        # Ordering: every PUT precedes receive-pack.
        paths = cloud.state.paths()
        last_put = max(
            i for i, p in enumerate(paths) if "/chunks/" in p and p.count("/") == 4
        )
        receive = paths.index(f"/sync/{STORE_ID}/git-receive-pack")
        assert last_put < receive

        # Git half really landed in the bare repo.
        bare = cloud.state.repos_root / STORE_ID
        assert _git(bare, "rev-parse", "main") == _git(
            linked_store, "rev-parse", "main"
        )

    def test_second_push_is_incremental(self, runner, linked_store, cloud, env):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        before = len(cloud.state.chunks[STORE_ID])
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
        assert "git-receive-pack" not in " ".join(cloud.state.paths())
        assert "info/refs" not in " ".join(cloud.state.paths())
        bare = cloud.state.repos_root / STORE_ID
        assert _git(bare, "for-each-ref") == ""

    def test_transient_5xx_is_retried(self, runner, linked_store, cloud, env):
        victim = sorted(_nodes(linked_store))[0]
        cloud.state.flaky_puts.add(victim)
        res = _invoke(runner, ["-s", str(linked_store), "--json", "push"], env=env)
        assert res.exit_code == 0, res.output
        puts = [p for p in cloud.state.paths("PUT") if p.endswith(victim)]
        assert len(puts) == 2
        assert json.loads(res.output)["pushed"] is True

    def test_push_refuses_cloud_branch(self, runner, linked_store, env, cloud):
        _git(linked_store, "branch", "cloud/feature/x")
        res = runner.invoke(
            cli,
            ["-s", str(linked_store), "push", "--branch", "cloud/feature/x"],
            env=env,
        )
        assert res.exit_code == 1
        assert "cloud-owned" in res.output
        assert not [p for p in cloud.state.paths() if p.startswith("/sync/")]

    def test_push_missing_branch(self, runner, linked_store, env):
        res = runner.invoke(
            cli, ["-s", str(linked_store), "push", "--branch", "nope"], env=env
        )
        assert res.exit_code == 2

    def test_push_bad_key_stops_before_git(self, runner, linked_store, env, cloud):
        res = runner.invoke(
            cli,
            ["-s", str(linked_store), "push"],
            env={**env, "MEMORY_API_KEY": "wrong"},
        )
        assert res.exit_code == 1
        assert "MEMORY_API_KEY is missing or invalid" in res.output
        assert all("git-" not in p for p in cloud.state.paths())


# --------------------------------------------------------------------------
# fetch / pull / clone / non-FF
# --------------------------------------------------------------------------


class TestRoundTrip:
    def test_clone_round_trips_memories(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        dest = tmp_root / "clone"
        res = _invoke(runner, ["--json", "clone", STORE_ID, str(dest)], env=env)
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["chunks_downloaded"] == len(_nodes(linked_store))
        assert data["branch"] == "main"

        # It is a real memoir store: backend lock, remote name, refspecs.
        assert (dest / ".git" / "memoir-backend").read_text().strip() == "file"
        assert _git(dest, "remote") == "memoir-cloud"
        assert "+refs/cloud/*" in _git(
            dest, "config", "--get-all", "remote.memoir-cloud.fetch"
        )
        assert _nodes(dest) == _nodes(linked_store)

        res = _invoke(runner, ["-s", str(dest), "status"])
        assert res.exit_code == 0
        assert "Memories: 2" in res.output
        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.gates"])
        assert "run tests" in res.output

        # Root chunk check passes: the tracked root is present in the clone.
        root = SyncService(str(dest)).root_hash()
        assert root in _nodes(dest)

    def test_clone_into_nonempty_dir_fails(self, runner, env, tmp_root):
        dest = tmp_root / "busy"
        dest.mkdir()
        (dest / "x").write_text("x")
        res = runner.invoke(cli, ["clone", STORE_ID, str(dest)], env=env)
        assert res.exit_code == 1
        assert "not empty" in res.output

    def test_clone_bad_key(self, runner, env, tmp_root):
        res = runner.invoke(
            cli,
            ["clone", STORE_ID, str(tmp_root / "c")],
            env={**env, "MEMORY_API_KEY": "bad"},
        )
        assert res.exit_code == 1
        assert "MEMORY_API_KEY is missing or invalid" in res.output
        assert "bad" not in res.output.replace("MEMORY_API_KEY", "")

    def test_fetch_pull_fast_forwards_clone(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", STORE_ID, str(dest)], env=env)

        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        new_tip = _git(linked_store, "rev-parse", "main")

        res = _invoke(runner, ["-s", str(dest), "--json", "fetch"], env=env)
        data = json.loads(res.output)
        assert data["chunks_downloaded"] >= 1
        assert "memoir-cloud/main" in data["remote_refs"]
        # fetch does not move the local branch
        assert _git(dest, "rev-parse", "main") != new_tip

        res = _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env)
        data = json.loads(res.output)
        assert data["created"] is False
        assert _git(dest, "rev-parse", "main") == new_tip
        assert data["tip"] == new_tip[: len(data["tip"])]

        res = _invoke(runner, ["-s", str(dest), "get", "workflow.coding.gates"])
        assert "run tests" in res.output

    def test_pull_creates_missing_branch(
        self, runner, linked_store, cloud, env, tmp_root
    ):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", STORE_ID, str(dest)], env=env)

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
        """Acceptance 2: stale clone → push exit 6 → pull → push succeeds."""
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", STORE_ID, str(dest)], env=env)

        # Cloud moves ahead via the original store.
        _remember(runner, linked_store, "workflow.coding.gates", "run tests")
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)

        # Stale clone pushes nothing new → rejected.
        res = runner.invoke(cli, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == EXIT_NON_FF
        assert "run `memoir pull`" in res.output

        res = _invoke(runner, ["-s", str(dest), "pull"], env=env)
        assert res.exit_code == 0, res.output
        _remember(runner, dest, "workflow.x", "from clone")
        res = _invoke(runner, ["-s", str(dest), "push"], env=env)
        assert res.exit_code == 0, res.output
        assert _git(cloud.state.repos_root / STORE_ID, "rev-parse", "main") == _git(
            dest, "rev-parse", "main"
        )

    def test_diverged_pull_rejected(self, runner, linked_store, cloud, env, tmp_root):
        _invoke(runner, ["-s", str(linked_store), "push"], env=env)
        dest = tmp_root / "clone"
        _invoke(runner, ["clone", STORE_ID, str(dest)], env=env)

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
        res = _invoke(runner, ["--json", "clone", STORE_ID, str(dest)], env=env)
        assert res.exit_code == 0, res.output
        total = len(cloud.state.chunks[STORE_ID])
        assert json.loads(res.output)["chunks_downloaded"] == total
        listings = [
            p
            for p in cloud.state.paths("GET")
            if p.startswith(f"/sync/{STORE_ID}/chunks?")
        ]
        assert len(listings) == -(-total // 2) + (1 if total % 2 == 0 else 0)
        assert _nodes(dest) == set(cloud.state.chunks[STORE_ID])
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
            _invoke(runner, ["--json", "clone", STORE_ID, str(dest)], env=env).output
        )
        outputs.append(
            _invoke(runner, ["-s", str(dest), "--json", "pull"], env=env).output
        )

        for out in outputs:
            assert API_KEY not in out
        for path in (linked_store, dest):
            for f in (path / ".git").rglob("*"):
                if f.is_file() and f.suffix != ".pack" and f.stat().st_size < 1_000_000:
                    assert API_KEY not in f.read_bytes().decode("latin-1"), f

        # ...but the bearer header did reach the server on every request.
        assert cloud.state.requests
        for req in cloud.state.requests:
            assert req.headers.get("Authorization") == f"Bearer {API_KEY}"

    def test_git_error_output_is_redacted(self, runner, linked_store, env, monkeypatch):
        service = SyncService(str(linked_store))
        monkeypatch.setenv("MEMORY_API_KEY", API_KEY)
        service._key = API_KEY

        class Fake:
            returncode = 128
            stdout = ""
            stderr = f"fatal: header 'Authorization: Bearer {API_KEY}' rejected"

        monkeypatch.setattr(sync_service.subprocess, "run", lambda *a, **k: Fake())
        with pytest.raises(ServiceError) as exc:
            service._git(["push", "memoir-cloud"])
        assert API_KEY not in exc.value.message
        assert "***" in exc.value.message


# --------------------------------------------------------------------------
# chunk protocol unit tests (CloudClient)
# --------------------------------------------------------------------------


class TestCloudClient:
    def test_negotiate_batches_of_500(self, cloud):
        hashes = [f"{i:064x}" for i in range(1201)]
        with CloudClient(cloud.url, API_KEY) as client:
            missing = client.missing_on_server(STORE_ID, hashes)
        assert missing == hashes
        negotiates = [r for r in cloud.state.requests if r.path.endswith("/negotiate")]
        sizes = [len(json.loads(r.body)["have"]) for r in negotiates]
        assert sizes == [500, 500, 201]

    def test_put_is_idempotent(self, cloud):
        h = "a" * 64
        with CloudClient(cloud.url, API_KEY) as client:
            assert client.put_chunk(STORE_ID, h, b"data") is True
            assert client.put_chunk(STORE_ID, h, b"data") is False
            assert client.get_chunk(STORE_ID, h) == b"data"

    def test_404_and_403_are_not_retried(self, cloud):
        with (
            CloudClient(cloud.url, API_KEY) as client,
            pytest.raises(CloudError) as exc,
        ):
            client.get_chunk(STORE_ID, "b" * 64)
        assert exc.value.status == 404
        gets = [p for p in cloud.state.paths("GET") if p.endswith("b" * 64)]
        assert len(gets) == 1

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
        assert os.environ["MEMOIR_CLOUD_URL"]  # env untouched
