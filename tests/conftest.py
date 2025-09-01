"""
Pytest configuration and fixtures for UI testing.
"""

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def output_config():
    """Configure output directories for test artifacts."""
    # Get base output directory from environment or use default
    base_output_dir = os.getenv("TEST_OUTPUT_DIR", "/tmp/memoir_ui_test")
    base_path = Path(base_output_dir)

    # Create directories
    screenshots_dir = base_path / "screenshots"
    videos_dir = base_path / "videos"

    # Clean and recreate directories
    if base_path.exists():
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    return {
        "base_dir": str(base_path),
        "screenshots_dir": str(screenshots_dir),
        "videos_dir": str(videos_dir),
    }


@pytest.fixture
def delete_output_dir(output_config):
    """Fixture that can be used to clean up output after tests."""
    return output_config
    # Cleanup is handled by output_config fixture
