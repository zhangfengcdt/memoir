"""
CLI Executor - Execute memoir CLI commands and return results.

This module provides a clean interface for executing memoir CLI commands
programmatically, capturing output and errors for use in agent simulations.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CLIResult:
    """Result from executing a memoir CLI command."""

    success: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str
    data: Optional[dict[str, Any]] = None
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def json_output(self) -> Optional[dict[str, Any]]:
        """Parse stdout as JSON if possible."""
        if self.data:
            return self.data
        try:
            return json.loads(self.stdout)
        except (json.JSONDecodeError, TypeError):
            return None


class CLIExecutor:
    """
    Execute memoir CLI commands and capture results.

    This executor wraps the memoir CLI, always using --json flag
    for machine-readable output suitable for agent consumption.

    Example:
        executor = CLIExecutor("/path/to/store")

        # Store a memory
        result = executor.remember("User prefers dark mode")
        if result.success:
            print(f"Stored at: {result.data['key']}")

        # Recall memories
        result = executor.recall("user preferences")
        for memory in result.data.get('memories', []):
            print(f"  {memory['path']}: {memory['content']}")
    """

    def __init__(
        self,
        store_path: str,
        timeout: float = 30.0,
        env: Optional[dict[str, str]] = None,
    ):
        """
        Initialize CLI executor.

        Args:
            store_path: Path to memoir store directory
            timeout: Command timeout in seconds
            env: Additional environment variables
        """
        self.store_path = str(Path(store_path).expanduser().resolve())
        self.timeout = timeout
        self._env = os.environ.copy()
        self._env["MEMOIR_STORE"] = self.store_path
        self._env["MEMOIR_JSON"] = "1"  # Always use JSON output
        if env:
            self._env.update(env)

    def _execute(
        self,
        args: list[str],
        input_data: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> CLIResult:
        """
        Execute a memoir CLI command.

        Args:
            args: Command arguments (without 'memoir' prefix)
            input_data: Optional stdin input
            timeout: Override default timeout

        Returns:
            CLIResult with command output
        """
        cmd = ["memoir", "--json", *args]
        cmd_str = " ".join(cmd)

        logger.debug(f"Executing: {cmd_str}")
        start_time = time.time()

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                env=self._env,
                input=input_data,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Parse JSON output
            data = None
            if process.stdout:
                import contextlib

                with contextlib.suppress(json.JSONDecodeError):
                    data = json.loads(process.stdout)

            success = process.returncode == 0
            error = None
            if not success and data:
                error = data.get("error")
            elif not success and process.stderr:
                error = process.stderr.strip()

            return CLIResult(
                success=success,
                command=cmd_str,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                data=data,
                duration_ms=duration_ms,
                error=error,
            )

        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=self.timeout * 1000,
                error=f"Command timed out after {self.timeout}s",
            )

        except FileNotFoundError:
            return CLIResult(
                success=False,
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr="",
                error="memoir CLI not found. Ensure it's installed and in PATH.",
            )

        except Exception as e:
            return CLIResult(
                success=False,
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                error=str(e),
            )

    # ==========================================================================
    # Store Commands
    # ==========================================================================

    def new(self, path: Optional[str] = None) -> CLIResult:
        """
        Create a new memoir store.

        Args:
            path: Store path (uses configured path if not specified)

        Returns:
            CLIResult with creation status
        """
        store = path or self.store_path
        return self._execute(["new", store])

    def status(self) -> CLIResult:
        """
        Get store status.

        Returns:
            CLIResult with store status info
        """
        return self._execute(["status"])

    def connect(self, path: Optional[str] = None) -> CLIResult:
        """
        Connect to a memoir store.

        Args:
            path: Store path (uses configured path if not specified)

        Returns:
            CLIResult with connection status
        """
        store = path or self.store_path
        return self._execute(["connect", store])

    # ==========================================================================
    # Memory Commands
    # ==========================================================================

    def remember(
        self,
        content: str,
        namespace: Optional[str] = None,
    ) -> CLIResult:
        """
        Store a memory.

        Args:
            content: Content to store
            namespace: Namespace for the memory

        Returns:
            CLIResult with classification and storage info
        """
        args = ["remember", content]
        if namespace:
            args.extend(["--namespace", namespace])
        return self._execute(args)

    def recall(
        self,
        query: str,
        limit: int = 10,
        namespace: Optional[str] = None,
    ) -> CLIResult:
        """
        Search memories.

        Args:
            query: Natural language search query
            limit: Maximum results
            namespace: Namespace to search

        Returns:
            CLIResult with matching memories
        """
        args = ["recall", query, "--limit", str(limit)]
        if namespace:
            args.extend(["--namespace", namespace])
        return self._execute(args)

    def forget(
        self,
        key: str,
        namespace: Optional[str] = None,
    ) -> CLIResult:
        """
        Delete a memory.

        Args:
            key: Memory path/key to delete
            namespace: Namespace containing the memory

        Returns:
            CLIResult with deletion status
        """
        args = ["forget", key]
        if namespace:
            args.extend(["--namespace", namespace])
        return self._execute(args)

    def get(
        self,
        path: str,
        namespace: Optional[str] = None,
    ) -> CLIResult:
        """
        Get a memory by exact path (cheap, no LLM).

        Note: This uses recall with the path as query for now.
        A dedicated 'get' command would be more efficient.

        Args:
            path: Exact memory path
            namespace: Namespace

        Returns:
            CLIResult with memory content
        """
        # Use recall with limit=1 for path lookup
        args = ["recall", path, "--limit", "1"]
        if namespace:
            args.extend(["--namespace", namespace])
        return self._execute(args)

    # ==========================================================================
    # Branch Commands
    # ==========================================================================

    def branch(self, list_branches: bool = True) -> CLIResult:
        """
        List branches.

        Args:
            list_branches: List all branches

        Returns:
            CLIResult with branch list
        """
        return self._execute(["branch"])

    def checkout(
        self,
        branch_name: str,
        create_if_missing: bool = False,
    ) -> CLIResult:
        """
        Checkout a branch.

        Args:
            branch_name: Branch to checkout
            create_if_missing: Create branch if it doesn't exist

        Returns:
            CLIResult with checkout status
        """
        args = ["checkout", branch_name]
        if create_if_missing:
            args.append("--create-if-missing")
        return self._execute(args)

    def merge(self, source_branch: str) -> CLIResult:
        """
        Merge a branch into current branch.

        Args:
            source_branch: Branch to merge from

        Returns:
            CLIResult with merge status
        """
        return self._execute(["merge", source_branch])

    def commits(self, limit: int = 10) -> CLIResult:
        """
        List recent commits.

        Args:
            limit: Maximum commits to show

        Returns:
            CLIResult with commit history
        """
        return self._execute(["commits", "--limit", str(limit)])

    # ==========================================================================
    # Crypto Commands
    # ==========================================================================

    def proof(self, path: str) -> CLIResult:
        """
        Generate cryptographic proof for a memory path.

        Args:
            path: Memory path to generate proof for

        Returns:
            CLIResult with proof data
        """
        return self._execute(["proof", path])

    def verify(self, proof_json: str) -> CLIResult:
        """
        Verify a cryptographic proof.

        Args:
            proof_json: JSON proof to verify

        Returns:
            CLIResult with verification status
        """
        return self._execute(["verify"], input_data=proof_json)

    # ==========================================================================
    # Batch Operations (for hooks)
    # ==========================================================================

    def batch_remember(
        self,
        contents: list[str],
        namespace: Optional[str] = None,
    ) -> list[CLIResult]:
        """
        Store multiple memories.

        Args:
            contents: List of contents to store
            namespace: Namespace for all memories

        Returns:
            List of CLIResults
        """
        results = []
        for content in contents:
            result = self.remember(content, namespace)
            results.append(result)
        return results

    def batch_recall(
        self,
        queries: list[str],
        limit: int = 5,
        namespace: Optional[str] = None,
    ) -> dict[str, CLIResult]:
        """
        Search with multiple queries.

        Args:
            queries: List of search queries
            limit: Max results per query
            namespace: Namespace to search

        Returns:
            Dict mapping query to CLIResult
        """
        results = {}
        for query in queries:
            result = self.recall(query, limit, namespace)
            results[query] = result
        return results

    # ==========================================================================
    # Help Commands
    # ==========================================================================

    def help(self, command: Optional[str] = None) -> CLIResult:
        """
        Get help for memoir CLI or a specific command.

        Args:
            command: Optional command name (e.g., "remember", "recall")
                    If None, returns general memoir help.

        Returns:
            CLIResult with help text in stdout
        """
        args = [command, "--help"] if command else ["--help"]

        # Don't use --json for help output
        cmd = ["memoir", *args]
        cmd_str = " ".join(cmd)

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, "MEMOIR_STORE": self.store_path},
            )
            duration_ms = (time.time() - start_time) * 1000

            return CLIResult(
                success=result.returncode == 0,
                command=cmd_str,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                data={"help_text": result.stdout},
            )
        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr="",
                error="Command timed out",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return CLIResult(
                success=False,
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr="",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )


# Convenience function for quick execution
def execute_memoir(
    command: str,
    store_path: str,
    *args: str,
    **kwargs: str,
) -> CLIResult:
    """
    Quick execution of a memoir command.

    Args:
        command: Command name (remember, recall, etc.)
        store_path: Path to memoir store
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        CLIResult

    Example:
        result = execute_memoir("remember", "/path/store", "User prefers dark mode")
    """
    executor = CLIExecutor(store_path)
    method = getattr(executor, command, None)
    if method is None:
        return CLIResult(
            success=False,
            command=command,
            exit_code=-1,
            stdout="",
            stderr="",
            error=f"Unknown command: {command}",
        )
    return method(*args, **kwargs)
