# SPDX-License-Identifier: Apache-2.0
"""
Code-repo metadata for memoir-cloud (issue #164).

When a memoir store is the memory store of a code repo, memoir-cloud can show
that repo GitHub-style (link, description, language, topics). This module
collects the metadata; ``SyncService`` sends it with
``PATCH /stores/by-name/<owner>/<store>`` on ``remote add`` and after every
successful ``push``.

Everything here is best-effort: any failure yields fewer fields (or ``None``
when there is no code repo at all), never an exception. Nothing is written to
the store's ProllyTree; the metadata is not a memory.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_TIMEOUT = 2.0
GIT_TIMEOUT = 5.0
MAX_DESCRIPTION = 1000
MAX_TOPICS = 20


# --------------------------------------------------------------------------
# Which code repo does a store belong to?
# --------------------------------------------------------------------------


def resolve_code_repo(store_path: str | Path, home: Path | None = None) -> Path | None:
    """Return the code repo a store maps to, or ``None``.

    Plugin-created stores live at ``~/.memoir/<slug>``, where the slug is the
    repo's absolute path with ``/`` and ``.`` replaced by ``-``. Because a
    ``-`` in the slug may stand for ``/``, ``.`` or a literal ``-``, the slug
    is resolved against the filesystem one character class at a time
    (``/Users/me/memoir-cloud`` and ``/Users/me/memoir/cloud`` produce the
    same slug; whichever exists wins, deepest real directory first). The
    result must be a directory with a ``.git`` entry.
    """
    home = home or Path.home()
    try:
        store = Path(store_path).expanduser().resolve()
        rel = store.relative_to((home / ".memoir").resolve())
    except (OSError, ValueError):
        return None
    slug = str(rel)
    if not slug.startswith("-") or "/" in slug:
        return None
    found = _walk_slug(Path("/"), slug[1:])
    if found is not None and (found / ".git").exists():
        return found
    return None


def _walk_slug(base: Path, rest: str) -> Path | None:
    """Depth-first match of ``rest`` (a dash-joined path) under ``base``.

    At each step, try every existing child of ``base`` whose name, with ``.``
    and ``-`` mapped to ``-``, is a prefix of ``rest`` ending at a ``-`` or at
    the end. Longest names first, so ``memoir-cloud`` beats ``memoir`` when
    both exist and both fit.
    """
    if not rest:
        return base
    try:
        children = [c for c in base.iterdir() if c.is_dir()]
    except OSError:
        return None
    candidates = []
    for child in children:
        key = child.name.replace(".", "-")
        if rest == key or rest.startswith(key + "-"):
            candidates.append((len(key), child))
    for _, child in sorted(candidates, key=lambda t: -t[0]):
        key_len = len(child.name)
        remainder = rest[key_len + 1 :] if len(rest) > key_len else ""
        found = _walk_slug(child, remainder)
        if found is not None:
            return found
    return None


# --------------------------------------------------------------------------
# Git-local fields (no network)
# --------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>.+)$")


def normalize_remote_url(url: str) -> str | None:
    """``git@github.com:o/r.git`` / ``ssh://…`` / ``https://…`` → ``https://host/o/r``.

    Credentials and ports are dropped. Returns ``None`` for anything that
    doesn't look like a hosted remote (local paths, ``file://``).
    """
    url = url.strip()
    if not url:
        return None
    if "://" in url:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https", "ssh", "git", "git+ssh"):
            return None
        host, path = parts.hostname, parts.path
    else:
        m = _SCP_LIKE.match(url)
        if not m or m.group("host").startswith((".", "/")):
            return None
        host, path = m.group("host"), m.group("path")
    if not host:
        return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if not path:
        return None
    return f"https://{host.lower()}/{path}"


def git_local_fields(repo: Path) -> dict[str, Any] | None:
    """The fields that need only the local clone. ``None`` without a usable origin."""
    origin = _git(repo, "remote", "get-url", "origin")
    url = normalize_remote_url(origin) if origin else None
    if not url:
        return None
    parts = urlsplit(url)
    host_name = parts.hostname or ""
    segments = [s for s in parts.path.split("/") if s]
    fields: dict[str, Any] = {
        "url": url,
        "host": host_name.split(".")[0] if host_name else None,
        "root": repo.name,
    }
    if len(segments) == 2:
        fields["owner"], fields["name"] = segments

    default = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if default and default.startswith("origin/"):
        fields["default_branch"] = default[len("origin/") :]
    elif _git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/main"):
        fields["default_branch"] = "main"

    head_branch = _git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    if head_branch:
        fields["head_branch"] = head_branch
    head_commit = _git(repo, "rev-parse", "HEAD")
    if head_commit and re.fullmatch(r"[0-9a-f]{40}", head_commit):
        fields["head_commit"] = head_commit
    return {k: v for k, v in fields.items() if v is not None}


# --------------------------------------------------------------------------
# GitHub fields (network, best-effort)
# --------------------------------------------------------------------------


def _gh_token() -> str | None:
    if not shutil.which("gh"):
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=GITHUB_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip()
    return token if result.returncode == 0 and token else None


def github_fields(owner: str, name: str) -> dict[str, Any]:
    """Description, topics, language, … from the GitHub API, or ``{}`` on any failure."""
    import httpx

    headers = {"Accept": "application/vnd.github+json"}
    token = _gh_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{name}",
            headers=headers,
            timeout=GITHUB_TIMEOUT,
        )
    except httpx.HTTPError as e:
        logger.debug("github metadata fetch failed: %s", e)
        return {}
    if resp.status_code != 200:
        logger.debug("github metadata fetch → %s", resp.status_code)
        return {}
    try:
        data = resp.json()
    except ValueError:
        return {}
    fields: dict[str, Any] = {}
    if isinstance(data.get("description"), str) and data["description"]:
        fields["description"] = data["description"][:MAX_DESCRIPTION]
    topics = data.get("topics")
    if isinstance(topics, list):
        fields["topics"] = [t for t in topics if isinstance(t, str)][:MAX_TOPICS]
    if isinstance(data.get("language"), str):
        fields["language"] = data["language"]
    if isinstance(data.get("visibility"), str):
        fields["visibility"] = data["visibility"]
    if isinstance(data.get("stargazers_count"), int) and data["stargazers_count"] >= 0:
        fields["stars"] = data["stargazers_count"]
    if isinstance(data.get("homepage"), str) and data["homepage"]:
        fields["homepage"] = data["homepage"]
    if fields:
        fields["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return fields


# --------------------------------------------------------------------------
# Assemble + change detection
# --------------------------------------------------------------------------


def collect(store_path: str | Path, *, online: bool = True) -> dict[str, Any] | None:
    """The ``repo`` document for a store, or ``None`` when it maps to no code repo."""
    repo = resolve_code_repo(store_path)
    if repo is None:
        return None
    fields = git_local_fields(repo)
    if fields is None:
        return None
    if (
        online
        and fields.get("host") == "github"
        and "owner" in fields
        and "name" in fields
    ):
        fields.update(github_fields(fields["owner"], fields["name"]))
    return fields


def fingerprint(doc: dict[str, Any]) -> str:
    """Stable JSON for change detection; ``fetched_at`` changes on every fetch
    and is not a change in itself, so it is left out."""
    return json.dumps(
        {k: v for k, v in doc.items() if k != "fetched_at"},
        sort_keys=True,
        ensure_ascii=False,
    )


def last_sent_path(store_path: str | Path, remote: str) -> Path:
    return Path(store_path) / ".git" / "memoir-cloud" / f"repo-meta-{remote}"


def unchanged(store_path: str | Path, remote: str, doc: dict[str, Any]) -> bool:
    try:
        return last_sent_path(store_path, remote).read_text() == fingerprint(doc)
    except OSError:
        return False


def record_sent(store_path: str | Path, remote: str, doc: dict[str, Any]) -> None:
    path = last_sent_path(store_path, remote)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(fingerprint(doc))
    os.replace(tmp, path)
