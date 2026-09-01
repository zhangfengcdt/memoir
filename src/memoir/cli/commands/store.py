# SPDX-License-Identifier: Apache-2.0
"""
Store commands for memoir CLI.

Commands: new, status, refresh, store-path, ensure-store

Note: `memoir connect` and `--connect` were removed. Memoir does not persist
a global default store; pick one each invocation via -s, MEMOIR_STORE, or by
running from inside the store directory.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_GIT_FAILED,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("path")
@click.option(
    "--backend",
    type=click.Choice(["git", "file"], case_sensitive=False),
    default=None,
    help=(
        "Storage backend for prollytree nodes. Default: file (gc-safe). "
        "Use git only for tooling-compatibility reasons; "
        "set MEMOIR_PROLLY_BACKEND for env-level override."
    ),
)
@click.option(
    "--taxonomy-builtin",
    is_flag=True,
    default=False,
    help="Initialize with builtin taxonomy (classification examples, descriptions, presets)",
)
@click.option(
    "-t",
    "--taxonomy",
    "taxonomy_paths",
    multiple=True,
    type=click.Path(exists=True),
    help="External taxonomy markdown file(s) to load",
)
@pass_context
def new(
    ctx: MemoirContext,
    path: str,
    backend: str | None,
    taxonomy_builtin: bool,
    taxonomy_paths: tuple,
):
    """Create a new memory store.

    INPUT: Path where the store should be created (will create directory).
    OUTPUT: Confirmation with store path and an export hint.

    Creates a git-initialized memory store at PATH. To use it on subsequent
    commands, either pass `-s PATH`, set `MEMOIR_STORE=PATH` in your shell,
    or `cd` into the store directory.

    Optionally initialize with taxonomy data for classification:
      --taxonomy-builtin loads the builtin taxonomy (~215 examples)
      -t/--taxonomy loads external markdown taxonomy files

    \b
    Examples:
      memoir new /tmp/my-agent-memory
      memoir new ~/memories --taxonomy-builtin
      memoir new ~/memories --taxonomy-builtin -t custom.md

    \b
    JSON output includes: path, success, taxonomy_loaded
    """
    from memoir.services.store_service import StoreService

    service = StoreService()
    result = service.create_store(path, backend=backend)

    if not result.success:
        ctx.error(result.error or "Failed to create store", EXIT_GIT_FAILED)
        return

    taxonomy_result = None

    # Initialize taxonomy if requested
    if taxonomy_builtin or taxonomy_paths:
        from memoir.taxonomy.loader import TaxonomyLoader

        try:
            # Re-open the store for taxonomy loading
            from memoir.store.prolly_adapter import ProllyTreeStore

            store = ProllyTreeStore(result.path)
            loader = TaxonomyLoader(store)
            taxonomy_result = loader.init_store(
                include_builtin=taxonomy_builtin,
                external_paths=list(taxonomy_paths),
            )
            ctx.info(f"Loaded taxonomy: {taxonomy_result}")
        except Exception as e:
            ctx.warn(f"Failed to initialize taxonomy: {e}")

    output_data = {"path": result.path}
    if taxonomy_result:
        output_data["taxonomy_loaded"] = taxonomy_result

    ctx.success(f"Created store at {result.path}", output_data)
    if not ctx.json_output:
        ctx.info(f"To use this store: export MEMOIR_STORE={result.path}")


@click.command()
@pass_context
def status(ctx: MemoirContext):
    """Show status of the connected memory store.

    INPUT: None (uses connected store).
    OUTPUT: Store info including path, branch, memory count, namespaces.

    Use this to verify connection and check store health before operations.

    \b
    Examples:
      memoir status
      memoir status --json

    \b
    JSON output includes: path, initialized, branch, commit_count, memory_count, namespaces
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.store_service import StoreService

    service = StoreService(ctx.store_path)
    info = service.get_status()

    if ctx.json_output:
        ctx.output(info.to_dict())
    else:
        click.echo(f"Store: {info.path}")
        click.echo(
            f"Status: {'Initialized' if info.initialized else 'Not initialized'}"
        )
        if info.branch:
            click.echo(f"Branch: {info.branch}")
        if info.commit_count is not None:
            click.echo(f"Commits: {info.commit_count}")
        if info.memory_count is not None:
            click.echo(f"Memories: {info.memory_count}")
        if info.namespaces:
            click.echo(f"Namespaces: {', '.join(info.namespaces)}")


@click.command()
@pass_context
def refresh(ctx: MemoirContext):
    """Refresh the memory store.

    Re-reads store data and updates internal caches.

    \b
    Examples:
      memoir refresh
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.store_service import StoreService

    try:
        service = StoreService(ctx.store_path)
        data = service.read_store()

        if ctx.json_output:
            ctx.output({"success": True, "data": data})
        else:
            memory_count = data.get("statistics", {}).get("total_keys", 0)
            ns_count = data.get("statistics", {}).get("namespace_count", 0)
            ctx.success(f"Refreshed: {memory_count} memories in {ns_count} namespaces")
    except Exception as e:
        ctx.error(f"Failed to refresh: {e}", EXIT_ERROR)


def _main_worktree_root() -> str | None:
    """Absolute path of the repo's primary worktree, or None if the current
    directory isn't inside a git working tree.

    Linked worktrees of the same repository collapse onto one result so
    that `store-path` resolves every worktree of a repo to the same store —
    a shared store per linked worktree would otherwise fragment a single
    project's branch/merge history across N stores.

    Fast path: compare `git rev-parse --git-dir` against `--git-common-dir`.
    They're equal outside of a linked worktree (or in a repo with none), in
    which case `--show-toplevel` is authoritative. Otherwise, parse
    `git worktree list --porcelain`, whose first `worktree <path>` line is
    always the main worktree (git >= 2.7). Bare repos report `(bare)` for
    that path, which isn't a usable root, so fall back to `--show-toplevel`
    (which itself resolves to nothing outside a working tree; callers drop
    to cwd in that case).
    """

    def _show_toplevel() -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
        )
        return result.stdout.strip() or None if result.returncode == 0 else None

    try:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        common_dir = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    git_dir_abs = str(Path(git_dir).resolve()) if Path(git_dir).is_dir() else git_dir
    common_dir_abs = (
        str(Path(common_dir).resolve()) if Path(common_dir).is_dir() else common_dir
    )
    if git_dir_abs == common_dir_abs:
        return _show_toplevel()

    first_worktree = None
    listing = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True
    )
    for line in listing.stdout.splitlines():
        if line.startswith("worktree "):
            first_worktree = line[len("worktree ") :]
            break

    if not first_worktree or first_worktree == "(bare)":
        return _show_toplevel()

    return first_worktree


@click.command("store-path")
@click.argument("project_dir", required=False)
@click.option(
    "--print-git-root",
    is_flag=True,
    help="Print only the repo's main-worktree root (nothing if not in a git "
    "tree) and exit. Used internally to keep worktree-aware resolution in "
    "one place; most callers want the plain form instead.",
)
def store_path(project_dir: str | None, print_git_root: bool):
    """Derive the per-project memoir store path for PROJECT_DIR.

    INPUT: Optional PROJECT_DIR. Defaults to the current repo's main
    worktree root, or the current directory if not inside a git repo.
    OUTPUT: $HOME/.memoir/<slug>, where <slug> is the absolute project path
    with every '/' and '.' replaced by '-'.

    A per-project store (rather than a per-project namespace inside one
    shared store) keeps memoir's git operations — branching, time-travel,
    merge — scoped to a single project; a shared store would entangle
    unrelated projects' histories together.

    \b
    Examples:
      memoir store-path                    # from the current project
      memoir store-path /path/to/project
      memoir store-path --print-git-root   # just the git root, or nothing
    """
    if print_git_root:
        root = _main_worktree_root()
        if root:
            click.echo(root)
        return

    target = project_dir or _main_worktree_root() or os.getcwd()
    resolved = str(Path(target).expanduser().resolve())
    slug = resolved.replace("/", "-").replace(".", "-")
    click.echo(str(Path.home() / ".memoir" / slug))


def _ensure_store(path: str) -> bool:
    """Idempotently create `path` as a memoir store with the builtin
    taxonomy if it doesn't already exist.

    Returns True if this call created the store, False if it already
    existed. Mirrors `memoir new <path> --taxonomy-builtin`, but runs the
    taxonomy install from a scratch git-initialized temp directory rather
    than the caller's actual working directory: that step operates against
    the new store's git backend and needs the process to be inside *some*
    git working tree, which a non-git project folder doesn't guarantee.
    """
    store_dir = Path(path).expanduser()
    if (store_dir / ".git").exists():
        return False

    from memoir.services.store_service import StoreService
    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.taxonomy.loader import TaxonomyLoader

    store_dir.parent.mkdir(parents=True, exist_ok=True)

    scratch = tempfile.mkdtemp(prefix="memoir-scratch.")
    previous_cwd = os.getcwd()
    try:
        subprocess.run(["git", "init", "-q", scratch], capture_output=True)
        os.chdir(scratch)
        service = StoreService()
        result = service.create_store(str(store_dir), backend=None)
        if not result.success:
            raise RuntimeError(result.error or f"failed to create store at {store_dir}")
        store = ProllyTreeStore(result.path)
        TaxonomyLoader(store).init_store(include_builtin=True, external_paths=[])
    finally:
        os.chdir(previous_cwd)
        shutil.rmtree(scratch, ignore_errors=True)

    return True


@click.command("ensure-store")
@click.argument("path")
@pass_context
def ensure_store(ctx: MemoirContext, path: str):
    """Idempotently create a memory store with the builtin taxonomy.

    INPUT: Path where the store should exist.
    OUTPUT: Confirmation; exits 0 whether the store already existed or was
    just created here.

    Safe to call on every invocation of a wrapping hook or skill — an
    existing store is left untouched. This is the single source of truth
    for store bootstrapping shared by every host plugin, so a user who
    installs memoir mid-session (after SessionStart already ran) doesn't
    get stuck with every command failing "Store not found".

    \b
    Examples:
      memoir ensure-store ~/.memoir/-Users-feng-project
    """
    try:
        created = _ensure_store(path)
    except Exception as e:
        ctx.error(f"Failed to create store at {path}: {e}", EXIT_GIT_FAILED)
        return

    if created:
        ctx.success(f"Created store at {path}", {"path": path, "created": True})
    else:
        ctx.success(f"Store already exists at {path}", {"path": path, "created": False})
