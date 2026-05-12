"""Load plugin prompt templates and substitute their dynamic placeholders.

The harness uses the SAME prompt files the plugin uses in production — no
duplicated copies that would drift. Today the only prompt with a template
file is ``stop_capture`` (used by ``hooks/stop.sh``); add new ones here as
they get extracted.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Repo layout — this file lives at:
#   plugins/codex/tests/prompt-harness/prompts.py
# So the plugin root is two parents up.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PLUGIN_ROOT / "hooks" / "prompts"
CACHE_FILENAME = "plugin-stop-taxonomy-prompt-cache"

# Fresh, isolated memoir store for harness runs. Init is idempotent — only
# happens the first time. Living under /tmp keeps it out of the user's real
# ~/.memoir/, so test runs never pollute or depend on production state.
TMP_STORE_DIR = Path("/tmp/memoir-prompt-tests/_store")


# Hard-coded fallback used by stop.sh when the store has no taxonomy snippet
# available. Keep this in sync with the fallback in hooks/stop.sh so the
# harness reflects what production would emit at the same moment.
_TAXONOMY_FALLBACK = """\
CATEGORIES (top-level + common second levels — pick a sensible third level yourself):
  profile.{personal,professional}: identity, demographics, occupation, education, skills, location, etc.
  preferences.{coding,tools,work,food,hobbies,entertainment}: editors, languages, frameworks, AI models, work style, etc.
  workflow.{coding,devops}: testing, branching, review, deployment, versioning, etc.
  context.project.{stack,repository,infrastructure,database,cicd,standards}
  relationships.{family,friends,professional}: manager, mentees, colleagues, etc.
  goals.{career,education,projects,financial}
  experience: past work, milestones, decisions
  knowledge.technical: languages, tools the user knows
  behavior.work: schedule, habits
  routine.daily: standups, ceremonies"""


@dataclass
class AssembledPrompt:
    name: str
    system_prompt: str
    template_path: Path
    taxonomy_source: str  # "store: <path>", "fallback", or "none"


def list_prompts() -> list[str]:
    """Names of all prompt templates available in the plugin."""
    if not PROMPTS_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.tmpl"))


def _ensure_temp_store() -> str | None:
    """Initialise an isolated memoir store under TMP_STORE_DIR with the builtin
    taxonomy. Idempotent — only runs ``memoir new`` the first time. Returns the
    store path on success, or None if memoir CLI is unavailable / init fails.
    """
    if (TMP_STORE_DIR / ".git").is_dir():
        return str(TMP_STORE_DIR)
    if not shutil.which("memoir"):
        return None
    TMP_STORE_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        res = subprocess.run(
            [
                "memoir", "new", str(TMP_STORE_DIR),
                "--taxonomy-builtin",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0 and (TMP_STORE_DIR / ".git").is_dir():
            return str(TMP_STORE_DIR)
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _resolve_store(store: str | None) -> str | None:
    """Resolve which memoir store the harness should use for the taxonomy.

    Priority:
      1. ``store`` arg (explicit override — most often a real store you want
         to test against, e.g. for diagnosing prod-specific failures).
      2. $MEMOIR_STORE env var.
      3. A fresh, isolated temp store under ``/tmp/memoir-prompt-tests/_store/``
         with the builtin taxonomy — this is the default so test runs are
         reproducible and don't depend on the user's real ~/.memoir/ state.
    Returns None only if memoir CLI isn't installed at all.
    """
    if store and (Path(store) / ".git").is_dir():
        return store
    env_store = os.environ.get("MEMOIR_STORE")
    if env_store and (Path(env_store) / ".git").is_dir():
        return env_store
    return _ensure_temp_store()


def _load_taxonomy_block(store: str | None) -> tuple[str, str]:
    """Return ``(block, source_label)``.

    Mirrors the production order of preference in ``hooks/stop.sh`` +
    ``hooks/common.sh::read_stop_prompt_cache``:

      1. Cached snippet at ``<store>/.git/plugin-stop-taxonomy-prompt-cache``
         (this is what the live Stop hook reads — exact production parity).
      2. Fresh ``memoir -s <store> taxonomy prompt-snippet`` if the cache
         is missing/empty but the CLI is available.
      3. Hardcoded fallback (same one ``stop.sh`` ships).

    The store itself is auto-resolved via ``_resolve_store`` so users don't
    have to remember ``--store`` for the common case.
    """
    resolved = _resolve_store(store)

    if resolved:
        cache = Path(resolved) / ".git" / CACHE_FILENAME
        if cache.is_file():
            text = cache.read_text().strip()
            if text:
                return text, f"cache: {cache}"

        if shutil.which("memoir"):
            try:
                res = subprocess.run(
                    ["memoir", "-s", resolved, "taxonomy", "prompt-snippet"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                snippet = (res.stdout or "").strip()
                if snippet:
                    return snippet, f"memoir-cli: {resolved}"
            except (subprocess.SubprocessError, OSError):
                pass

    return _TAXONOMY_FALLBACK, "fallback"


def assemble(name: str, store: str | None = None) -> AssembledPrompt:
    """Return the system prompt named ``name`` with placeholders substituted.

    Raises FileNotFoundError if the template doesn't exist. Raises ValueError
    if a known placeholder is missing from the template (catches drift).
    """
    template_path = PROMPTS_DIR / f"{name}.tmpl"
    if not template_path.is_file():
        available = ", ".join(list_prompts()) or "(none)"
        raise FileNotFoundError(
            f"prompt template not found: {template_path}\n"
            f"  available prompts: {available}"
        )
    template = template_path.read_text()

    # Per-prompt placeholder substitutions. Add new prompts here.
    if name == "stop_capture":
        if "${TAXONOMY_BLOCK}" not in template:
            raise ValueError(
                f"{template_path} is missing the ${{TAXONOMY_BLOCK}} "
                f"placeholder — out of sync with hooks/stop.sh."
            )
        taxonomy_block, source = _load_taxonomy_block(store)
        system_prompt = template.replace("${TAXONOMY_BLOCK}", taxonomy_block)
        return AssembledPrompt(
            name=name,
            system_prompt=system_prompt,
            template_path=template_path,
            taxonomy_source=source,
        )

    # Default: no placeholders to substitute, return verbatim.
    return AssembledPrompt(
        name=name,
        system_prompt=template,
        template_path=template_path,
        taxonomy_source="none",
    )
