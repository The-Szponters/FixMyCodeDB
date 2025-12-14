"""
Analyzers for static code analysis tools (cppcheck, clang-tidy).
"""

import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from typing import Dict, List


class CppcheckAnalyzer:
    """Wrapper for cppcheck static analyzer."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def run(self, code: str) -> List[Dict]:
        """
        Analyzes C++ code using cppcheck.

        Args:
            code: Source code string to analyze

        Returns:
            List of issues found, each as dict with 'id' and other metadata
        """
        if not code.strip():
            return []

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Run cppcheck with text output (JSON template doesn't work properly)
            result = subprocess.run(  # nosec B603, B607
                [self.cppcheck_path, "--enable=all", "--inline-suppr", "--suppress=missingInclude", "--suppress=missingIncludeSystem", "--suppress=unmatchedSuppression", temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            # Parse text output from stderr (cppcheck outputs to stderr)
            if result.stderr:
                print(f"[DEBUG] Cppcheck full output:\n{result.stderr}")

            issues = []
            import re

            for line in result.stderr.splitlines():
                # Parse text format: "/path/file.cpp:line:col: severity: message [issueId]"
                # Example: /tmp/test.cpp:1:16: error: syntax error [syntaxError]
                match = re.search(r"\[(\w+)\]", line)
                if match:
                    issue_id = match.group(1)
                    # Filter out suppressed and informational issues
                    if issue_id not in ["missingInclude", "missingIncludeSystem", "unmatchedSuppression", "checkersReport", "normalCheckLevelMaxBranches"]:
                        # Create a minimal issue dict for compatibility
                        issues.append({"id": issue_id})
                        print(f"[DEBUG] Cppcheck found: {issue_id}")

            if not issues:
                print("[DEBUG] Cppcheck found no issues")

            return issues

        except subprocess.TimeoutExpired:
            print(f"[!] Cppcheck timeout after {self.timeout}s")
            return []
        except FileNotFoundError:
            print("[!] Cppcheck not found - skipping analysis")
            return []
        except Exception as e:
            print(f"[!] Cppcheck error: {e}")
            return []
        finally:
            Path(temp_file).unlink(missing_ok=True)


class ClangTidyAnalyzer:
    """Wrapper for clang-tidy static analyzer."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.clang_tidy_path = shutil.which("clang-tidy")
        if not self.clang_tidy_path:
            raise RuntimeError("clang-tidy not found in PATH")

    def run(self, code: str) -> List[Dict]:
        """
        Analyzes C++ code using clang-tidy.

        Args:
            code: Source code string to analyze

        Returns:
            List of warnings found, each as dict with 'id' and 'message'
        """
        if not code.strip():
            return []

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Run clang-tidy
            result = subprocess.run(  # nosec B603, B607
                [self.clang_tidy_path, temp_file, "--", "-std=c++17", "-Wno-everything", "-ferror-limit=0"],  # Suppress compiler warnings  # Don't stop on errors
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            # Parse output
            if result.stdout:
                print(f"[DEBUG] Clang-tidy output:\n{result.stdout[:500]}...")
            if result.stderr:
                print(f"[DEBUG] Clang-tidy stderr:\n{result.stderr[:500]}...")

            warnings = self._parse_clang_output(result.stdout)
            return warnings

        except subprocess.TimeoutExpired:
            print(f"[!] Clang-tidy timeout after {self.timeout}s")
            return []
        except FileNotFoundError:
            print("[!] Clang-tidy not found - skipping analysis")
            return []
        except Exception as e:
            print(f"[!] Clang-tidy error: {e}")
            return []
        finally:
            Path(temp_file).unlink(missing_ok=True)

    def _parse_clang_output(self, output: str) -> List[Dict]:
        """Parse clang-tidy text output into structured issues."""
        issues = []

        for line in output.splitlines():
            # Skip lines about missing includes/headers
            if "fatal error:" in line and ("file not found" in line or "no such file" in line):
                continue
            if "'#include' file not found" in line:
                continue

            if "warning:" in line or "error:" in line:
                # Extract check name from brackets [check-name]
                if "[" in line and "]" in line:
                    start = line.rfind("[")
                    end = line.rfind("]")
                    check_name = line[start + 1 : end]

                    # Extract message
                    warning_pos = line.find("warning:")
                    error_pos = line.find("error:")
                    msg_start = max(warning_pos, error_pos)

                    if msg_start != -1:
                        message = line[msg_start:start].strip()
                        issues.append({"id": check_name, "message": message})
                else:
                    # Generic warning without check name
                    if "warning:" in line:
                        msg = line.split("warning:")[1].strip()
                        issues.append({"id": "generic-warning", "message": msg})

        return issues
