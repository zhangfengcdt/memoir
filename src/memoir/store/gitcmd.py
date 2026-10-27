# SPDX-License-Identifier: Apache-2.0
"""Single git invocation helper for the store layer (review #9a).

``node_gc`` and ``repo_mode`` each had their own wrapper and this PR added a
third that omitted ``encoding="utf-8"``; git always emits UTF-8, so decoding
with the locale encoding breaks non-ASCII refs. All three share this one.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def run_git(cwd: str | Path, *args: str, timeout: float | None = None):
    """Run ``git -C <cwd> <args>`` and decode the output as UTF-8.

    ``check=False``: a non-zero exit is reported through the return code, so
    callers can tell a failure apart from an empty result.
    """
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )
