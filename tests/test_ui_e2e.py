#!/usr/bin/env python3
"""
End-to-end UI tests for Memoir with video recording and screenshots.
Run with: pytest tests/test_ui_e2e.py -v
Set custom output with: TEST_OUTPUT_DIR=/path/to/output pytest tests/test_ui_e2e.py -v
"""

import subprocess
import time
import uuid
from pathlib import Path

import pytest

# Temporarily skip all e2e tests - requires running server and Playwright browsers
pytestmark = pytest.mark.skip(reason="E2E tests temporarily disabled - requires server and Playwright setup")


@pytest.fixture(scope="session")
def server():
    """Start the Memoir UI server for testing."""
    # Start server in background
    server_process = subprocess.Popen(
        ["python", "-m", "src.memoir.ui.server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to start
    time.sleep(3)

    yield server_process

    # Cleanup
    server_process.terminate()
    server_process.wait()


def test_ui_loads_successfully(server, page, output_config):
    """Test that the UI loads without errors."""
    screenshots_dir = Path(output_config["screenshots_dir"])

    # Navigate to UI
    page.goto("http://localhost:8080")

    # Wait for the page to load
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Take screenshot
    page.screenshot(path=str(screenshots_dir / "01_initial_load.png"), full_page=True)

    # Verify basic elements exist
    assert page.locator("#memoryInput").is_visible()
    assert page.locator(".memoir-logo").is_visible()
    assert page.locator(".view-toggle").is_visible()


def test_demo_command(server, page, output_config):
    """Test the demo command functionality."""
    screenshots_dir = Path(output_config["screenshots_dir"])

    page.goto("http://localhost:8080")
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Execute demo command
    page.fill("#memoryInput", "/demo")
    page.press("#memoryInput", "Enter")

    # Wait a bit for demo to load
    page.wait_for_timeout(2000)

    # Take screenshot
    page.screenshot(path=str(screenshots_dir / "02_demo_loaded.png"), full_page=True)

    # Verify tree structure is visible
    assert page.locator(".tree-node").count() > 0


def test_view_switching(server, page, output_config):
    """Test switching between different views."""
    screenshots_dir = Path(output_config["screenshots_dir"])

    page.goto("http://localhost:8080")
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Load demo first
    page.fill("#memoryInput", "/demo")
    page.press("#memoryInput", "Enter")
    page.wait_for_timeout(1000)

    # Test Graph view
    page.click('[data-view="graph"]')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshots_dir / "03_graph_view.png"), full_page=True)
    assert page.locator("#graphView").is_visible()

    # Test Timeline view
    page.click('[data-view="timeline"]')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshots_dir / "04_timeline_view.png"), full_page=True)
    assert page.locator("#timelineView").is_visible()

    # Test Places view
    page.click('[data-view="places"]')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshots_dir / "05_places_view.png"), full_page=True)
    assert page.locator("#placesView").is_visible()

    # Return to Tree view
    page.click('[data-view="tree"]')
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshots_dir / "06_tree_view.png"), full_page=True)
    assert page.locator("#treeView").is_visible()


def test_theme_toggle(server, page, output_config):
    """Test theme switching functionality."""
    screenshots_dir = Path(output_config["screenshots_dir"])

    page.goto("http://localhost:8080")
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Take screenshot in dark theme
    page.screenshot(path=str(screenshots_dir / "07_dark_theme.png"), full_page=True)

    # Toggle to light theme
    page.click(".theme-toggle")
    page.wait_for_timeout(500)

    # Take screenshot in light theme
    page.screenshot(path=str(screenshots_dir / "08_light_theme.png"), full_page=True)

    # Verify theme changed (check data attribute)
    theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme == "light"

    # Switch back to dark theme for consistency
    page.click(".theme-toggle")
    page.wait_for_timeout(500)

    # Verify back to dark theme
    theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme == "dark"


def test_help_command(server, page, output_config):
    """Test the help command."""
    screenshots_dir = Path(output_config["screenshots_dir"])

    page.goto("http://localhost:8080")
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Execute help command
    page.fill("#memoryInput", "/help")
    page.press("#memoryInput", "Enter")
    page.wait_for_timeout(1000)

    page.screenshot(path=str(screenshots_dir / "09_help_command.png"), full_page=True)


def test_memory_workflow_sequence(server, page, output_config):
    """Test the complete memory workflow: /new → /remember → /recall → /demo → /recall → /summarize"""
    screenshots_dir = Path(output_config["screenshots_dir"])

    page.goto("http://localhost:8080")
    page.wait_for_selector("#memoryInput", timeout=10000)

    # Step 1: Create new memory store with random name
    random_store_name = f"memoir_test_{uuid.uuid4().hex[:8]}"
    store_path = f"/tmp/{random_store_name}"
    page.fill("#memoryInput", f"/new {store_path}")
    page.press("#memoryInput", "Enter")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(screenshots_dir / "10_new_store.png"), full_page=True)

    # Step 2: Remember several things
    memories = [
        "My name is John Smith, and I am 29 years old",
        "I have a background in computer science and software engineering",
        "I learned Python today and built a web scraper",
    ]

    for i, memory in enumerate(memories, 1):
        page.fill("#memoryInput", f"/remember {memory}")
        page.press("#memoryInput", "Enter")
        if i == 1:  # Take screenshot of first remember and wait for completion
            # Wait for remember processing to complete (shows progress modal)
            page.wait_for_timeout(3000)  # Wait for processing to start/complete
            page.screenshot(
                path=str(screenshots_dir / "11_remember_command.png"), full_page=True
            )
        else:
            page.wait_for_timeout(2500)  # Wait for each memory to be processed

    # Step 3: Test recall
    page.fill("#memoryInput", "/recall what is my name?")
    page.press("#memoryInput", "Enter")
    # Wait for recall processing (may show modal or notification)
    page.wait_for_timeout(5000)  # Wait for AI processing
    page.screenshot(
        path=str(screenshots_dir / "12_recall_before_demo.png"), full_page=True
    )

    # Close any modal that might be open
    page.wait_for_timeout(1000)  # Wait for modal to fully appear
    try:
        page.click(".recall-modal-close", timeout=2000)
        page.wait_for_timeout(500)  # Wait for close animation
    except Exception:
        try:
            page.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            # Try clicking backdrop to close
            import contextlib

            with contextlib.suppress(Exception):
                page.click("body", timeout=500)

    # Step 4: Load demo
    page.fill("#memoryInput", "/demo")
    page.press("#memoryInput", "Enter")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(screenshots_dir / "13_demo_loaded.png"), full_page=True)

    # Step 5: Final recall test
    page.fill("#memoryInput", "/recall what is my education background?")
    page.press("#memoryInput", "Enter")
    # Wait for recall processing (may show modal or notification)
    page.wait_for_timeout(5000)  # Wait for AI processing
    page.screenshot(path=str(screenshots_dir / "14_final_recall.png"), full_page=True)

    # Close any modal that might be open
    page.wait_for_timeout(1000)  # Wait for modal to fully appear
    try:
        page.click(".recall-modal-close", timeout=2000)
        page.wait_for_timeout(500)  # Wait for close animation
    except Exception:
        try:
            page.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            # Try clicking backdrop to close
            import contextlib

            with contextlib.suppress(Exception):
                page.click("body", timeout=500)

    # Step 6: Test summarize command
    page.fill("#memoryInput", "/summarize")
    page.press("#memoryInput", "Enter")
    # Wait for summarize processing (may show modal or notification)
    page.wait_for_timeout(6000)  # Wait for AI processing
    page.screenshot(path=str(screenshots_dir / "15_summarize_all.png"), full_page=True)

    # Close any modal that might be open
    page.wait_for_timeout(1000)  # Wait for modal to fully appear
    try:
        page.click(".summary-modal-close", timeout=2000)
        page.wait_for_timeout(500)  # Wait for close animation
    except Exception:
        try:
            page.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            # Try clicking backdrop to close
            import contextlib

            with contextlib.suppress(Exception):
                page.click("body", timeout=500)

    # Test specific summary type
    page.fill("#memoryInput", "/summarize taxonomy")
    page.press("#memoryInput", "Enter")
    # Wait for taxonomy summarize processing
    page.wait_for_timeout(6000)  # Wait for AI processing
    page.screenshot(
        path=str(screenshots_dir / "16_summarize_taxonomy.png"), full_page=True
    )

    # Close final modal
    page.wait_for_timeout(1000)  # Wait for modal to fully appear
    try:
        page.click(".summary-modal-close", timeout=2000)
        page.wait_for_timeout(500)  # Wait for close animation
    except Exception:
        try:
            page.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            # Try clicking backdrop to close
            import contextlib

            with contextlib.suppress(Exception):
                page.click("body", timeout=500)

    # Verify the UI is still responsive
    assert page.locator("#memoryInput").is_visible()


if __name__ == "__main__":
    # Direct run for development
    pytest.main([__file__, "-v"])
