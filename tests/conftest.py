#!/usr/bin/env python3
"""
Pytest configuration for Memoir UI testing with Playwright.
"""

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context with single video recording and custom output."""

    # Get output directory from environment or use default
    output_dir = os.environ.get("TEST_OUTPUT_DIR", "tests/ui/output")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    return {
        **browser_context_args,
        "record_video_dir": str(output_path / "videos"),
        "record_video_size": {"width": 1920, "height": 1080},  # Full HD resolution
        "viewport": {"width": 1920, "height": 1080},  # Set browser viewport to match
    }


@pytest.fixture(scope="session")
def playwright():
    """Start Playwright."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright):
    """Launch browser with video recording enabled."""
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def browser_context(browser, browser_context_args):
    """Create a single browser context for all tests."""
    context = browser.new_context(**browser_context_args)
    yield context
    context.close()


@pytest.fixture(scope="session")
def page(browser_context):
    """Create a single page for all tests to share - continuous video recording."""
    page = browser_context.new_page()
    yield page
    page.close()


def pytest_configure(config):
    """Configure output directories based on environment variables."""
    output_dir = os.environ.get("TEST_OUTPUT_DIR", "tests/ui/output")
    screenshots_dir = Path(output_dir) / "screenshots"
    videos_dir = Path(output_dir) / "videos"

    # Ensure directories exist
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Store paths for use in tests
    config.screenshots_dir = str(screenshots_dir)
    config.videos_dir = str(videos_dir)


def pytest_sessionfinish(session, exitstatus):
    """Rename video file after all tests complete."""
    output_dir = os.environ.get("TEST_OUTPUT_DIR", "tests/ui/output")
    videos_dir = Path(output_dir) / "videos"

    # Find the video file (should be only one now)
    video_files = list(videos_dir.glob("*.webm"))
    if video_files:
        video_file = video_files[0]
        new_name = videos_dir / "memoir_ui_tests_full_session.webm"
        if new_name.exists():
            new_name.unlink()  # Remove existing file
        video_file.rename(new_name)
        print(f"📹 Renamed video to: {new_name.name}")


@pytest.fixture(scope="session")
def output_config(request):
    """Provide output directory configuration to tests."""
    return {
        "screenshots_dir": request.config.screenshots_dir,
        "videos_dir": request.config.videos_dir,
    }
