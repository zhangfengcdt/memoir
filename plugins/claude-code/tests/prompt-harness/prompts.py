"""Load plugin prompt templates and substitute their dynamic placeholders.

The harness uses the SAME prompt files the plugin uses in production — no
duplicated copies that would drift. Today the only prompt with a template
file is ``stop_capture`` (used by ``hooks/stop.sh``); add new ones here as
they get extracted.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Repo layout — this file lives at:
#   plugins/claude-code/tests/prompt-harness/prompts.py
# So the plugin root is two parents up.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = PLUGIN_ROOT / "hooks" / "prompts"


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


def _load_taxonomy_block(store: str | None) -> tuple[str, str]:
    """Return ``(block, source_label)``.

    Tries `memoir taxonomy prompt-snippet` against ``store`` if provided and
    the CLI is on PATH; falls back to the hardcoded category sheet otherwise.
    Mirrors the logic in hooks/common.sh::write_stop_prompt_cache + stop.sh's
    fallback.
    """
    if store and shutil.which("memoir"):
        try:
            res = subprocess.run(
                ["memoir", "-s", store, "taxonomy", "prompt-snippet"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            snippet = (res.stdout or "").strip()
            if snippet:
                return snippet, f"store: {store}"
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
