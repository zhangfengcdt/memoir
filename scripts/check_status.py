#!/usr/bin/env python3
"""
Status check script for LangMem-ProllyTree CI pipeline.
Runs comprehensive checks and reports the overall health of the project.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class StatusChecker:
    """Comprehensive status checker for the project."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.results = {}
        self.start_time = time.time()

    def run_command(self, cmd: list[str], timeout: int = 60) -> tuple[bool, str, str]:
        """Run a command and return success status, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)

    def check_dependencies(self) -> dict[str, Any]:
        """Check if all dependencies are installed."""
        print("🔍 Checking dependencies...")

        checks = {
            "python_version": self._check_python_version(),
            "pip_install": self._check_pip_install(),
            "dev_dependencies": self._check_dev_dependencies(),
        }

        return {
            "status": all(check["success"] for check in checks.values()),
            "checks": checks,
        }

    def _check_python_version(self) -> dict[str, Any]:
        """Check Python version compatibility."""
        success, stdout, stderr = self.run_command([sys.executable, "--version"])

        if success:
            version = stdout.strip().split()[1]
            major, minor = map(int, version.split(".")[:2])
            compatible = major >= 3 and minor >= 9

            return {
                "success": compatible,
                "version": version,
                "message": f"Python {version}"
                + ("" if compatible else " (requires >= 3.9)"),
            }

        return {
            "success": False,
            "version": "unknown",
            "message": f"Failed to get Python version: {stderr}",
        }

    def _check_pip_install(self) -> dict[str, Any]:
        """Check if package can be installed."""
        success, stdout, stderr = self.run_command(
            [sys.executable, "-m", "pip", "install", "-e", "."]
        )

        return {
            "success": success,
            "message": (
                "Package installation successful"
                if success
                else f"Installation failed: {stderr}"
            ),
        }

    def _check_dev_dependencies(self) -> dict[str, Any]:
        """Check if dev dependencies are available."""
        tools = ["pytest", "black", "ruff", "mypy", "bandit"]
        results = {}

        for tool in tools:
            success, _, _ = self.run_command([sys.executable, "-m", tool, "--version"])
            results[tool] = success

        all_available = all(results.values())

        return {
            "success": all_available,
            "tools": results,
            "message": (
                "All dev tools available"
                if all_available
                else f"Missing tools: {[k for k, v in results.items() if not v]}"
            ),
        }

    def check_code_quality(self) -> dict[str, Any]:
        """Run code quality checks."""
        print("✨ Running code quality checks...")

        checks = {
            "formatting": self._check_formatting(),
            "linting": self._check_linting(),
            "type_checking": self._check_type_checking(),
            "security": self._check_security(),
        }

        return {
            "status": all(check["success"] for check in checks.values()),
            "checks": checks,
        }

    def _check_formatting(self) -> dict[str, Any]:
        """Check code formatting with Black and isort."""
        black_success, black_out, black_err = self.run_command(
            [sys.executable, "-m", "black", "--check", "src/", "tests/", "examples/"]
        )

        isort_success, isort_out, isort_err = self.run_command(
            [
                sys.executable,
                "-m",
                "isort",
                "--check-only",
                "src/",
                "tests/",
                "examples/",
            ]
        )

        success = black_success and isort_success

        return {
            "success": success,
            "black": black_success,
            "isort": isort_success,
            "message": (
                "Code formatting OK" if success else "Code formatting issues found"
            ),
        }

    def _check_linting(self) -> dict[str, Any]:
        """Check linting with Ruff."""
        success, stdout, stderr = self.run_command(
            [sys.executable, "-m", "ruff", "check", "src/", "tests/", "examples/"]
        )

        return {
            "success": success,
            "message": (
                "No linting issues" if success else f"Linting issues found: {stderr}"
            ),
        }

    def _check_type_checking(self) -> dict[str, Any]:
        """Check type annotations with MyPy."""
        success, stdout, stderr = self.run_command(
            [
                sys.executable,
                "-m",
                "mypy",
                "src/langmem_prollytree",
                "--ignore-missing-imports",
            ]
        )

        return {
            "success": success,
            "message": (
                "Type checking passed" if success else f"Type errors found: {stderr}"
            ),
        }

    def _check_security(self) -> dict[str, Any]:
        """Run security checks with Bandit."""
        bandit_success, bandit_out, bandit_err = self.run_command(
            [sys.executable, "-m", "bandit", "-r", "src/"]
        )

        # Safety check is optional as it may fail due to network issues
        safety_success, safety_out, safety_err = self.run_command(
            [sys.executable, "-m", "safety", "check"], timeout=30
        )

        return {
            "success": bandit_success,
            "bandit": bandit_success,
            "safety": safety_success,
            "message": (
                "Security checks passed"
                if bandit_success
                else f"Security issues found: {bandit_err}"
            ),
        }

    def check_tests(self) -> dict[str, Any]:
        """Run test suite."""
        print("🧪 Running tests...")

        # Run tests with coverage
        success, stdout, stderr = self.run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-v",
                "--cov=langmem_prollytree",
                "--cov-report=term-missing",
            ]
        )

        # Extract coverage percentage if available
        coverage_percent = None
        if "TOTAL" in stdout:
            try:
                total_line = [line for line in stdout.split("\n") if "TOTAL" in line][
                    -1
                ]
                coverage_percent = int(total_line.split()[-1].rstrip("%"))
            except Exception:
                pass

        return {
            "success": success,
            "coverage": coverage_percent,
            "message": f"Tests {'passed' if success else 'failed'}"
            + (f" with {coverage_percent}% coverage" if coverage_percent else ""),
            "output": stdout if success else stderr,
        }

    def check_examples(self) -> dict[str, Any]:
        """Check that examples run without errors."""
        print("📖 Testing examples...")

        examples = [("basic_usage.py", 30), ("langgraph_integration.py", 30)]

        results = {}
        for example, timeout in examples:
            success, stdout, stderr = self.run_command(
                [sys.executable, f"examples/{example}"], timeout=timeout
            )

            results[example] = {
                "success": success,
                "message": "Ran successfully" if success else f"Failed: {stderr}",
            }

        all_success = all(result["success"] for result in results.values())

        return {
            "status": all_success,
            "examples": results,
            "message": (
                "All examples run successfully"
                if all_success
                else "Some examples failed"
            ),
        }

    def check_performance(self) -> dict[str, Any]:
        """Run performance benchmarks."""
        print("⚡ Running performance benchmarks...")

        # Run a quick benchmark
        success, stdout, stderr = self.run_command(
            [sys.executable, "examples/performance_benchmark.py"], timeout=120
        )

        # Try to extract performance metrics
        metrics = {}
        if success and stdout:
            try:
                # Look for performance numbers in output
                lines = stdout.split("\n")
                for line in lines:
                    if "Average search time:" in line:
                        metrics["search_time_ms"] = float(
                            line.split(":")[1].strip().rstrip("ms")
                        )
                    elif "Average storage time:" in line:
                        metrics["storage_time_ms"] = float(
                            line.split(":")[1].strip().rstrip("ms")
                        )
                    elif "Average classification time:" in line:
                        metrics["classification_time_ms"] = float(
                            line.split(":")[1].strip().rstrip("ms")
                        )
            except Exception:
                pass

        # Check if performance targets are met
        performance_ok = (
            metrics.get("search_time_ms", 999) < 10
            and metrics.get("storage_time_ms", 999) < 50
            and metrics.get("classification_time_ms", 999) < 10
        )

        return {
            "success": success and performance_ok,
            "metrics": metrics,
            "targets_met": performance_ok,
            "message": (
                "Performance benchmarks completed"
                if success
                else f"Benchmark failed: {stderr}"
            ),
        }

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive status report."""
        total_time = time.time() - self.start_time

        # Run all checks
        dependency_status = self.check_dependencies()
        code_quality_status = self.check_code_quality()
        test_status = self.check_tests()
        example_status = self.check_examples()
        performance_status = self.check_performance()

        # Overall status
        all_checks = [
            dependency_status["status"],
            code_quality_status["status"],
            test_status["success"],
            example_status["status"],
            performance_status["success"],
        ]

        overall_success = all(all_checks)

        report = {
            "timestamp": time.time(),
            "duration_seconds": total_time,
            "overall_status": "PASS" if overall_success else "FAIL",
            "checks": {
                "dependencies": dependency_status,
                "code_quality": code_quality_status,
                "tests": test_status,
                "examples": example_status,
                "performance": performance_status,
            },
        }

        return report

    def print_summary(self, report: dict[str, Any]):
        """Print a human-readable summary."""
        print("\n" + "=" * 60)
        print("LANGMEM-PROLLYTREE STATUS REPORT")
        print("=" * 60)

        status_icon = "✅" if report["overall_status"] == "PASS" else "❌"
        print(f"\n{status_icon} Overall Status: {report['overall_status']}")
        print(f"⏱️  Total Time: {report['duration_seconds']:.1f}s")

        # Dependencies
        deps = report["checks"]["dependencies"]
        deps_icon = "✅" if deps["status"] else "❌"
        print(f"\n{deps_icon} Dependencies: {'OK' if deps['status'] else 'FAIL'}")

        # Code Quality
        quality = report["checks"]["code_quality"]
        quality_icon = "✅" if quality["status"] else "❌"
        print(f"{quality_icon} Code Quality: {'OK' if quality['status'] else 'FAIL'}")
        if not quality["status"]:
            for check_name, check_result in quality["checks"].items():
                if not check_result["success"]:
                    print(f"  ⚠️  {check_name}: {check_result['message']}")

        # Tests
        tests = report["checks"]["tests"]
        tests_icon = "✅" if tests["success"] else "❌"
        print(f"{tests_icon} Tests: {tests['message']}")

        # Examples
        examples = report["checks"]["examples"]
        examples_icon = "✅" if examples["status"] else "❌"
        print(f"{examples_icon} Examples: {examples['message']}")

        # Performance
        perf = report["checks"]["performance"]
        perf_icon = "✅" if perf["success"] else "❌"
        print(f"{perf_icon} Performance: {perf['message']}")

        if perf["success"] and perf.get("metrics"):
            metrics = perf["metrics"]
            print(f"  📊 Search: {metrics.get('search_time_ms', 'N/A')}ms")
            print(f"  📊 Storage: {metrics.get('storage_time_ms', 'N/A')}ms")
            print(
                f"  📊 Classification: {metrics.get('classification_time_ms', 'N/A')}ms"
            )

        print("\n" + "=" * 60)

        if report["overall_status"] == "PASS":
            print("🎉 All checks passed! Project is ready for production.")
            print("🚀 Performance targets achieved:")
            print("   • Sub-10ms search latency")
            print("   • Sub-50ms storage latency")
            print("   • Sub-10ms classification latency")
        else:
            print("⚠️  Some checks failed. See details above.")
            print("💡 Run 'make ci' to fix issues locally.")

        print("=" * 60)


def main():
    """Run the status checker."""
    checker = StatusChecker()

    print("🔍 Starting LangMem-ProllyTree status check...")
    print("This may take a few minutes...\n")

    try:
        report = checker.generate_report()
        checker.print_summary(report)

        # Save detailed report
        report_file = checker.project_root / "status_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 Detailed report saved to: {report_file}")

        # Exit with appropriate code
        sys.exit(0 if report["overall_status"] == "PASS" else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Status check interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Status check failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
