from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
    _, raw, _ = text.split("---", 2)
    data = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        assert sep, f"{path} frontmatter line must be key/value: {line!r}"
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        data[key.strip()] = value
    return data


def test_skill_metadata_is_codex_loadable() -> None:
    skills = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
    assert skills

    names = set()
    for skill in skills:
        data = _frontmatter(skill)
        name = data.get("name")
        description = data.get("description")

        assert isinstance(name, str) and name, f"{skill} missing name"
        assert name == skill.parent.name, f"{skill} name should match folder"
        assert name not in names, f"duplicate skill name: {name}"
        names.add(name)

        assert isinstance(description, str) and description, f"{skill} missing description"
        assert len(description) <= 1024, f"{skill} description exceeds Codex limit"


def test_codex_command_replacement_skills_exist() -> None:
    skill_dirs = {p.name for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir()}
    assert {
        "memory-recall",
        "memoir-onboard",
        "memoir-remember",
        "memoir-status",
        "memoir-ui",
    } <= skill_dirs
