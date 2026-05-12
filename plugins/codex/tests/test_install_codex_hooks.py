import json
import os
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PLUGIN_ROOT / "scripts" / "install-codex-hooks.sh"


def _run_installer(hooks_file: Path, tmp_path: Path, mode: str = "install") -> None:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(tmp_path / "codex-home")
    env["CODEX_HOOKS_FILE"] = str(hooks_file)
    env["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    subprocess.run(
        ["bash", str(INSTALLER), mode],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _backup_names(hooks_file: Path) -> list[str]:
    return sorted(p.name for p in hooks_file.parent.glob(f"{hooks_file.name}.bak-*"))


def test_install_is_idempotent_and_does_not_accumulate_backups(tmp_path: Path) -> None:
    hooks_file = tmp_path / "hooks.json"

    _run_installer(hooks_file, tmp_path)
    first = hooks_file.read_text()
    assert _backup_names(hooks_file) == []

    _run_installer(hooks_file, tmp_path)
    assert hooks_file.read_text() == first
    assert _backup_names(hooks_file) == []


def test_install_strips_legacy_memoir_codex_hooks(tmp_path: Path) -> None:
    hooks_file = tmp_path / "hooks.json"
    old_command = (
        "bash /old/memoir-codex/hooks/session-start.sh "
        "# memoir-codex managed hook: SessionStart"
    )
    hooks_file.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": old_command,
                                    "statusMessage": "Loading Memoir context",
                                },
                                {
                                    "type": "command",
                                    "command": "bash /keep/other-plugin.sh",
                                    "statusMessage": "Other plugin",
                                },
                            ]
                        }
                    ]
                }
            }
        )
        + "\n"
    )

    _run_installer(hooks_file, tmp_path)

    text = hooks_file.read_text()
    assert "memoir-codex managed hook" not in text
    assert "/memoir-codex/" not in text
    assert "memoir managed hook" in text
    assert "bash /keep/other-plugin.sh" in text
    assert len(_backup_names(hooks_file)) == 1


def test_install_keeps_only_three_latest_backups(tmp_path: Path) -> None:
    hooks_file = tmp_path / "hooks.json"
    hooks_file.write_text('{"hooks": {}}\n')
    for i in range(5):
        (tmp_path / f"hooks.json.bak-20250101-00000{i}").write_text("{}\n")

    _run_installer(hooks_file, tmp_path)

    backups = _backup_names(hooks_file)
    assert len(backups) == 3
    assert "hooks.json.bak-20250101-000000" not in backups
    assert "hooks.json.bak-20250101-000001" not in backups
