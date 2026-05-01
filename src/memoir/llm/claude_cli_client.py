# SPDX-License-Identifier: Apache-2.0
"""
Claude CLI backend — a drop-in replacement for LiteLLMWrapper that invokes
the `claude` command-line interface instead of making direct provider API calls.

When memoir is used alongside Claude Code, this backend lets every LLM call
(classification, path selection, metadata extraction) inherit Claude Code's
own auth — subscription OAuth or API key, whichever the user is logged in
with — so no separate OPENAI_API_KEY / ANTHROPIC_API_KEY is needed.

Activation:
    export MEMOIR_LLM_BACKEND=claude-cli

Same public interface as LiteLLMWrapper: .invoke() / .ainvoke() returning
a response object with .content and .usage attributes. All 12 existing
call sites in the codebase work unchanged.

Tradeoffs vs LiteLLM:
- Pros: no API key management, rides Claude Code auth (incl. subscription).
- Cons: each call spawns a Node subprocess — cold-start is in seconds, not
  ms. Typical end-to-end latency for a short classification prompt:
    - OAuth + MCP discovery + CLAUDE.md load (unoptimized):  ~13s cold
    - --strict-mcp-config with empty --mcp-config:           ~5s cold
    - --bare (requires ANTHROPIC_API_KEY):                   ~1.7s cold
    - LiteLLM direct-API backend, same prompt:               ~1-1.5s
  No direct cache-stat access, only Claude models (no GPT/Gemini/Ollama).
  If you have an API key, prefer the LiteLLM backend.

Implementation notes:
- System prompt (the cacheable [STATIC_SECTION_START]...[STATIC_SECTION_END]
  block) is passed via --system-prompt; dynamic content goes on stdin.
  Claude Code handles prompt caching internally when using --system-prompt,
  so we get roughly the same cache benefits as LiteLLM's ephemeral caching.
- `claude` subprocess is invoked with CLAUDECODE= and MEMOIR_NO_CAPTURE=1 to
  prevent recursion when memoir is called from within a Claude Code session
  whose plugin would otherwise fire hooks on the child `claude` call.
- MCP discovery is suppressed via --strict-mcp-config + an empty --mcp-config
  JSON string. Memoir's LLM calls are pure text completions that never need
  MCP tools, and MCP startup on the outer user's environment can add 5-10s
  per subprocess on setups with many configured servers.
- When ANTHROPIC_API_KEY is set, --bare is also added: skips hooks, LSP,
  plugin sync, CLAUDE.md auto-discovery, and keychain reads, saving another
  ~3s of cold start. --bare forces ANTHROPIC_API_KEY-only auth (OAuth and
  keychain are skipped), so it's conditional on the env var being present.
"""

import asyncio
import logging
import os
import shutil
import subprocess
from typing import Any, ClassVar

from memoir.llm.litellm_client import LiteLLMResponse

logger = logging.getLogger(__name__)


class ClaudeCLIError(RuntimeError):
    """Raised when the claude CLI is missing, misconfigured, or returns non-zero."""


class ClaudeCLIWrapper:
    """
    LLM client that shells out to `claude -p` instead of calling provider APIs.

    Interface-compatible with LiteLLMWrapper:
        - .invoke(prompt) -> LiteLLMResponse
        - .ainvoke(prompt) -> LiteLLMResponse  (async)
        - .get_cache_stats() -> dict  (reports zeros — claude CLI doesn't expose them)

    Model names: accepts memoir's usual names (e.g. "claude-haiku-4-5"), the
    short aliases claude CLI understands (haiku/sonnet/opus), or full model IDs.
    Rejects non-Claude models (gpt-*, gemini/*, ollama/*) with a clear error.
    """

    # Models this backend can handle. Non-Claude models must stay on LiteLLM.
    SUPPORTED_MARKERS: ClassVar[list[str]] = ["haiku", "sonnet", "opus", "claude"]

    # Default subprocess timeout (seconds). Classification tasks are short.
    DEFAULT_TIMEOUT = 60

    # Empty MCP config passed on every call together with --strict-mcp-config
    # to suppress the outer environment's MCP server discovery. See module
    # docstring for why this matters (5-10s savings on typical setups).
    _EMPTY_MCP_CONFIG_JSON: ClassVar[str] = '{"mcpServers":{}}'

    def __init__(
        self,
        model: str = "haiku",
        temperature: float = 0,  # accepted for interface parity; claude CLI ignores
        max_tokens: int = 500,  # accepted for interface parity; claude CLI ignores
        base_url: str | None = None,  # accepted for interface parity
        api_key: str | None = None,  # accepted for interface parity
        enable_prompt_cache: bool = True,  # claude CLI caches internally
        debug_cache: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.model = self._normalize_model(model)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_prompt_cache = enable_prompt_cache
        self._debug_cache = debug_cache
        self._timeout = timeout

        # Cache-stat shape matches LiteLLMWrapper so callers don't branch.
        # claude CLI doesn't expose per-call cache tokens; values stay 0.
        self.cache_stats = {
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "total_requests": 0,
            "cached_requests": 0,
        }

        # Fail fast if the CLI isn't available — better than a cryptic subprocess error.
        self._claude_path = shutil.which("claude")
        if not self._claude_path:
            raise ClaudeCLIError(
                "claude CLI not found on PATH. Install Claude Code from "
                "https://claude.com/claude-code or set MEMOIR_LLM_BACKEND=litellm "
                "to use direct provider API calls instead."
            )

    @staticmethod
    def _normalize_model(model: str) -> str:
        """Strip any LiteLLM provider prefix; reject non-Claude models."""
        # LiteLLM uses "anthropic/claude-haiku-4-5"; claude CLI wants "claude-haiku-4-5".
        if model.startswith("anthropic/"):
            model = model[len("anthropic/") :]
        model_lower = model.lower()
        if not any(m in model_lower for m in ClaudeCLIWrapper.SUPPORTED_MARKERS):
            raise ClaudeCLIError(
                f"Model {model!r} is not a Claude model — the claude-cli backend "
                "only supports Claude models. Set MEMOIR_LLM_MODEL to a Claude "
                "model (e.g. 'claude-haiku-4-5') or switch to the litellm backend."
            )
        return model

    def _split_prompt(self, prompt: str) -> tuple[str | None, str]:
        """
        Split a classification prompt into (system, user) parts using the same
        [STATIC_SECTION_END] marker LiteLLMWrapper uses.

        Returns (system_part, user_part). If no marker, system is None and the
        full prompt goes to user.
        """
        marker = "[STATIC_SECTION_END]"
        if marker in prompt:
            end = prompt.find(marker) + len(marker)
            return prompt[:end], prompt[end:].lstrip()
        return None, prompt

    def _build_argv(self, system_prompt: str | None) -> list[str]:
        argv = [
            self._claude_path,
            "-p",
            "--model",
            self.model,
            "--no-session-persistence",
            "--no-chrome",
            "--strict-mcp-config",
            "--mcp-config",
            self._EMPTY_MCP_CONFIG_JSON,
        ]
        if os.getenv("ANTHROPIC_API_KEY"):
            argv.append("--bare")
        if system_prompt:
            argv += ["--system-prompt", system_prompt]
        return argv

    def _build_env(self) -> dict:
        """
        Child environment: blank CLAUDECODE so the spawned claude doesn't think
        it's running inside Claude Code, and MEMOIR_NO_CAPTURE to stop the
        memoir plugin's Stop hook (if installed) from recursively firing on
        this child turn.
        """
        env = os.environ.copy()
        env["CLAUDECODE"] = ""
        env["MEMOIR_NO_CAPTURE"] = "1"
        return env

    def _coerce_prompt(self, prompt: Any) -> str:
        """Normalize arbitrary prompt inputs (str, list-of-messages) into a single string."""
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, list):
            # LangChain-style [{"role": ..., "content": ...}] — flatten
            parts = []
            for msg in prompt:
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Multi-part content — join text blocks
                        content = "\n".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in content
                        )
                    parts.append(f"[{role}]: {content}")
                else:
                    parts.append(str(msg))
            return "\n".join(parts)
        return str(prompt)

    # --- sync / async public methods ---

    def invoke(self, prompt: Any) -> LiteLLMResponse:
        prompt_str = self._coerce_prompt(prompt)
        system, user = self._split_prompt(prompt_str)
        argv = self._build_argv(system)

        try:
            result = subprocess.run(
                argv,
                input=user,
                capture_output=True,
                text=True,
                env=self._build_env(),
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeCLIError(f"claude CLI timed out after {self._timeout}s") from e

        if result.returncode != 0:
            raise ClaudeCLIError(
                f"claude CLI exited {result.returncode}: {result.stderr.strip()[:500]}"
            )

        self.cache_stats["total_requests"] += 1
        return LiteLLMResponse(content=result.stdout.strip(), usage={})

    async def ainvoke(self, prompt: Any) -> LiteLLMResponse:
        prompt_str = self._coerce_prompt(prompt)
        system, user = self._split_prompt(prompt_str)
        argv = self._build_argv(system)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_env(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=user.encode("utf-8")),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise ClaudeCLIError(f"claude CLI timed out after {self._timeout}s") from e

        if proc.returncode != 0:
            raise ClaudeCLIError(
                f"claude CLI exited {proc.returncode}: "
                f"{stderr.decode('utf-8', errors='replace').strip()[:500]}"
            )

        self.cache_stats["total_requests"] += 1
        return LiteLLMResponse(
            content=stdout.decode("utf-8", errors="replace").strip(), usage={}
        )

    def get_cache_stats(self) -> dict:
        """Same shape as LiteLLMWrapper.get_cache_stats() — values are zero because
        claude CLI doesn't report per-call cache activity back to the caller."""
        stats = self.cache_stats.copy()
        stats["cache_hit_rate"] = 0.0
        stats["estimated_token_savings"] = 0
        stats["note"] = (
            "claude-cli backend: cache activity happens inside Claude Code and "
            "is not exposed to callers. total_requests is the only meaningful stat."
        )
        return stats
