# SPDX-License-Identifier: Apache-2.0
"""Subprocess bridge to the memoir CLI for the Hermes memory provider.

The provider never imports memoir in-process. It shells out to the `memoir`
CLI with `--json`, which keeps the plugin dependency-free (stdlib only) and
lets prollytree self-resolve concurrent writes — so capture can be
fire-and-forget with no locking.

Conventions ported from the Codex plugin's shell bridge
(`plugins/codex/scripts/{resolve-memoir-cli,ensure-store}.sh`):

  * CLI resolution: `memoir` on PATH wins (any version the user installed);
    otherwise fall back to a *pinned* `uvx --from memoir-ai==<pin> memoir`,
    then `uv tool run`. The resolved argv is cached for the process.
  * Store creation runs `memoir new --taxonomy-builtin` from a throwaway
    git-init'd scratch dir, because the builtin-taxonomy install needs the
    calling cwd to be inside a git work tree (a Hermes home generally
    isn't).
  * Every call has a timeout and degrades gracefully — methods return
    `(ok, payload)` tuples and never raise, because the Hermes tool-handler
    contract forbids exceptions from `handle_tool_call`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any

# Pinned memoir-ai version for the uvx / uv-tool-run fallbacks. A `memoir`
# already on PATH always wins and is used unpinned (we trust the user's
# install). Bump deliberately after verifying a new release works with this
# provider. Mirrors MEMOIR_AI_PIN in the Codex plugin's resolver.
MEMOIR_AI_PIN = "0.2.2"

INSTALL_HINT = (
    "memoir CLI not found. Install one of: `pip install memoir-ai`, "
    "`pipx install memoir-ai`, `uv tool install memoir-ai`, or install `uv` "
    "for a transparent uvx fallback."
)

_DEFAULT_TIMEOUT = 15
_STORE_CREATE_TIMEOUT = 60


class MemoirBridge:
    """Thin, resilient wrapper around the memoir CLI for one store."""

    def __init__(
        self,
        store_path: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.store_path = store_path
        # The host-selected LLM model memoir should use for extraction /
        # classification. Mutable so the provider can track mid-session model
        # switches (on_turn_start). None → memoir's own default.
        self.model = model
        # Optional custom provider endpoint (LLM gateway/proxy). None → the
        # provider's default endpoint (e.g. api.anthropic.com).
        self.base_url = base_url
        self._argv: list[str] | None = None
        self._resolved = False

    # -- environment ---------------------------------------------------------

    def _build_env(self) -> dict:
        """Subprocess env for every memoir call.

        Forces memoir's ``litellm`` (direct provider API) backend so it NEVER
        shells out to the `claude` CLI — a Hermes host has its own configured
        provider + credentials, and a typical Hermes box has no `claude`
        binary. The provider's credentials are inherited from the Hermes
        process env. ``MEMOIR_LLM_MODEL`` carries the host-selected model so
        capture/classification use it rather than memoir's built-in default.
        ``MEMOIR_LLM_BASE_URL``, when configured, points memoir at a custom
        provider endpoint (e.g. an LLM gateway/proxy) so it can share the
        host's routing instead of calling the provider directly.
        """
        env = os.environ.copy()
        env["MEMOIR_LLM_BACKEND"] = "litellm"
        if self.model:
            env["MEMOIR_LLM_MODEL"] = self.model
        if self.base_url:
            env["MEMOIR_LLM_BASE_URL"] = self.base_url
        return env

    # -- CLI resolution ------------------------------------------------------

    def _cli(self) -> list[str] | None:
        """Return the base argv to invoke memoir, or None if unavailable.

        Resolved once and cached. Preference: PATH `memoir` (unpinned) →
        pinned `uvx` → pinned `uv tool run`.
        """
        if self._resolved:
            return self._argv
        self._resolved = True
        if shutil.which("memoir"):
            self._argv = ["memoir"]
        elif shutil.which("uvx"):
            self._argv = ["uvx", "--from", f"memoir-ai=={MEMOIR_AI_PIN}", "memoir"]
        elif shutil.which("uv"):
            self._argv = [
                "uv",
                "tool",
                "run",
                "--from",
                f"memoir-ai=={MEMOIR_AI_PIN}",
                "memoir",
            ]
        else:
            self._argv = None
        return self._argv

    def available(self) -> bool:
        """True if a memoir CLI invocation is resolvable. No network/subprocess."""
        return self._cli() is not None

    # -- Core invocation -----------------------------------------------------

    def run(
        self,
        args: list[str],
        *,
        stdin: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        json_out: bool = True,
    ) -> tuple[bool, Any]:
        """Invoke `memoir [--json] -s <store> <args...>`.

        Returns ``(ok, payload)``. On success with ``json_out`` the payload is
        the parsed JSON (falling back to ``{"raw": <stdout>}`` if it isn't
        JSON); otherwise raw stdout text. On failure the payload is
        ``{"error": <message>}``. Never raises.
        """
        base = self._cli()
        if base is None:
            return False, {"error": INSTALL_HINT}

        cmd = list(base)
        if json_out:
            cmd.append("--json")
        cmd += ["-s", self.store_path, *args]

        try:
            proc = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._build_env(),
            )
        except subprocess.TimeoutExpired:
            return False, {"error": f"memoir timed out after {timeout}s"}
        except Exception as e:  # pragma: no cover - defensive
            return False, {"error": f"memoir invocation failed: {e}"}

        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip()[:500]
            return False, {"error": msg or f"memoir exited {proc.returncode}"}

        if not json_out:
            return True, proc.stdout

        out = (proc.stdout or "").strip()
        if not out:
            return True, {}
        try:
            return True, json.loads(out)
        except (ValueError, TypeError):
            return True, {"raw": proc.stdout}

    # -- Store lifecycle -----------------------------------------------------

    def ensure_store(self) -> bool:
        """Idempotently create the store with the builtin taxonomy.

        No-op (returns True) if the store already exists. Returns False if the
        CLI is unavailable or creation fails.
        """
        if os.path.isdir(os.path.join(self.store_path, ".git")):
            return True
        base = self._cli()
        if base is None:
            return False

        parent = os.path.dirname(self.store_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # `memoir new --taxonomy-builtin` installs the taxonomy against the
        # store's git backend, which requires the *calling* cwd to be inside a
        # git work tree. A Hermes home generally isn't, so run from a
        # throwaway git-init'd scratch dir (mirrors ensure-store.sh).
        scratch = tempfile.mkdtemp(prefix="memoir-scratch.")
        try:
            subprocess.run(
                ["git", "init", "-q", scratch],
                capture_output=True,
                timeout=_DEFAULT_TIMEOUT,
            )
            proc = subprocess.run(
                [*base, "new", self.store_path, "--taxonomy-builtin"],
                cwd=scratch,
                capture_output=True,
                text=True,
                timeout=_STORE_CREATE_TIMEOUT,
                env=self._build_env(),
            )
            return proc.returncode == 0
        except Exception:
            return False
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # -- Convenience wrappers ------------------------------------------------

    def capture(
        self, transcript: str, *, profile: str = "assistant"
    ) -> tuple[bool, Any]:
        """Run `memoir capture --profile <profile>` over a turn transcript."""
        return self.run(
            ["capture", "--profile", profile],
            stdin=transcript,
            timeout=_DEFAULT_TIMEOUT,
        )

    def get(self, keys: list[str], *, namespace: str = "default") -> tuple[bool, Any]:
        """Fast direct lookup of keys via `memoir get` (no LLM)."""
        if not keys:
            return True, {"items": []}
        return self.run(["get", *keys, "-n", namespace])

    def recall(
        self, *, namespace: str = "default", max_keys: int = 50
    ) -> tuple[bool, Any]:
        """Fetch stored memories via summarize→get (no LLM, fast, reliable).

        Lists the namespace's 3-level keys with ``summarize --depth 3`` (the
        recall-skill convention), drops machine-generated ``metrics.*`` keys,
        then batch-`get`s them. memoir's semantic `recall` is intentionally
        avoided here: it costs an LLM round-trip (multi-second via the
        claude-cli fallback) and adds nothing for the small profile-style
        stores a personal assistant accumulates.
        """
        ok, summ = self.summarize(depth=3, namespace=namespace)
        if not ok:
            # A brand-new store has no `default` namespace until the first
            # write — summarize reports "Namespace 'default' not found". For a
            # read that just means "nothing stored yet", not an error.
            err = summ.get("error", "") if isinstance(summ, dict) else ""
            if "not found" in str(err).lower():
                return True, {"items": []}
            return ok, summ
        prefix: dict = {}
        if isinstance(summ, dict):
            prefix = (summ.get("prefix_counts") or {}).get(namespace, {}) or {}
        keys = [k for k in prefix if not k.startswith("metrics.")]
        return self.get(keys[:max_keys], namespace=namespace)

    def remember(
        self, content: str, *, path: str | None = None, replace: bool = False
    ) -> tuple[bool, Any]:
        """Store a fact via `memoir remember` (pre-classified if ``path`` given)."""
        args = ["remember", content]
        if path:
            args += ["-p", path]
        if replace:
            args.append("--replace")
        return self.run(args)

    def status(self) -> tuple[bool, Any]:
        """Store status via `memoir status`."""
        return self.run(["status"])

    def summarize(self, depth: int = 3, namespace: str = "default") -> tuple[bool, Any]:
        """Taxonomy/overview summary via `memoir summarize`."""
        return self.run(["summarize", "--depth", str(depth), "-n", namespace])
