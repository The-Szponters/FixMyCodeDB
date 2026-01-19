"""
Unit tests for scraper/labeling/analyzers.py
Tests analyzer wrappers with mocked subprocesses.
"""
import pytest
from unittest.mock import MagicMock, patch
import subprocess


class TestCppcheckAnalyzer:
    """Tests for CppcheckAnalyzer class."""

    def test_init_finds_cppcheck(self):
        """Test analyzer finds cppcheck in PATH."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/cppcheck"

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)

            assert analyzer.cppcheck_path == "/usr/bin/cppcheck"
            assert analyzer.timeout == 30

    def test_init_cppcheck_not_found(self):
        """Test analyzer raises when cppcheck not found."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = None

            from scraper.labeling.analyzers import CppcheckAnalyzer

            with pytest.raises(RuntimeError, match="cppcheck not found"):
                CppcheckAnalyzer(timeout=30)

    def test_init_with_temp_dir(self):
        """Test analyzer accepts temp_dir parameter."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/cppcheck"

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30, temp_dir="/dev/shm")

            assert analyzer.temp_dir == "/dev/shm"

    def test_run_empty_code(self):
        """Test run with empty code returns empty list."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/cppcheck"

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("")

            assert result == []

    def test_run_whitespace_only(self):
        """Test run with whitespace-only code returns empty list."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/cppcheck"

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("   \n\t  ")

            assert result == []

    def test_run_finds_issues(self, tmp_path):
        """Test run finds and parses issues."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which, \
             patch('scraper.labeling.analyzers.subprocess.run') as mock_run, \
             patch('scraper.labeling.analyzers.tempfile.NamedTemporaryFile') as mock_tempfile, \
             patch('scraper.labeling.analyzers.Path') as mock_path:

            mock_which.return_value = "/usr/bin/cppcheck"

            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.cpp")
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_file

            mock_result = MagicMock()
            mock_result.stderr = "/tmp/test.cpp:5:10: error: Null pointer dereference [nullPointer]\n"
            mock_run.return_value = mock_result

            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("int main() { int *p; *p = 1; }")

            assert len(result) == 1
            assert result[0]["id"] == "nullPointer"

    def test_run_filters_suppressed_issues(self, tmp_path):
        """Test run filters out suppressed issues."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which, \
             patch('scraper.labeling.analyzers.subprocess.run') as mock_run, \
             patch('scraper.labeling.analyzers.tempfile.NamedTemporaryFile') as mock_tempfile, \
             patch('scraper.labeling.analyzers.Path') as mock_path:

            mock_which.return_value = "/usr/bin/cppcheck"

            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.cpp")
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_file

            mock_result = MagicMock()
            mock_result.stderr = """
/tmp/test.cpp:1:0: information: Missing include [missingInclude]
/tmp/test.cpp:5:10: error: Null pointer [nullPointer]
"""
            mock_run.return_value = mock_result

            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("int main() {}")

            # missingInclude should be filtered
            issue_ids = [r["id"] for r in result]
            assert "missingInclude" not in issue_ids
            assert "nullPointer" in issue_ids

    def test_run_handles_timeout(self, tmp_path):
        """Test run handles subprocess timeout."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which, \
             patch('scraper.labeling.analyzers.subprocess.run') as mock_run, \
             patch('scraper.labeling.analyzers.tempfile.NamedTemporaryFile') as mock_tempfile, \
             patch('scraper.labeling.analyzers.Path') as mock_path:

            mock_which.return_value = "/usr/bin/cppcheck"

            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.cpp")
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_file

            mock_run.side_effect = subprocess.TimeoutExpired("cppcheck", 30)

            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("int main() {}")

            assert result == []

    def test_run_handles_file_not_found(self, tmp_path):
        """Test run handles cppcheck not found at runtime."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which, \
             patch('scraper.labeling.analyzers.subprocess.run') as mock_run, \
             patch('scraper.labeling.analyzers.tempfile.NamedTemporaryFile') as mock_tempfile, \
             patch('scraper.labeling.analyzers.Path') as mock_path:

            mock_which.return_value = "/usr/bin/cppcheck"

            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.cpp")
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_file

            mock_run.side_effect = FileNotFoundError()

            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("int main() {}")

            assert result == []

    def test_run_no_issues_found(self, tmp_path):
        """Test run with clean code."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which, \
             patch('scraper.labeling.analyzers.subprocess.run') as mock_run, \
             patch('scraper.labeling.analyzers.tempfile.NamedTemporaryFile') as mock_tempfile, \
             patch('scraper.labeling.analyzers.Path') as mock_path:

            mock_which.return_value = "/usr/bin/cppcheck"

            mock_file = MagicMock()
            mock_file.name = str(tmp_path / "test.cpp")
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_tempfile.return_value = mock_file

            mock_result = MagicMock()
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            from scraper.labeling.analyzers import CppcheckAnalyzer

            analyzer = CppcheckAnalyzer(timeout=30)
            result = analyzer.run("int main() { return 0; }")

            assert result == []


class TestClangTidyAnalyzer:
    """Tests for ClangTidyAnalyzer class."""

    def test_init_finds_clang_tidy(self):
        """Test analyzer finds clang-tidy in PATH."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/clang-tidy"

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            analyzer = ClangTidyAnalyzer(timeout=30)

            assert analyzer.clang_tidy_path == "/usr/bin/clang-tidy"

    def test_init_clang_tidy_not_found(self):
        """Test analyzer raises when clang-tidy not found."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = None

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            with pytest.raises(RuntimeError, match="clang-tidy not found"):
                ClangTidyAnalyzer(timeout=30)

    def test_run_empty_code(self):
        """Test run with empty code."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/clang-tidy"

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            analyzer = ClangTidyAnalyzer(timeout=30)
            result = analyzer.run("")

            assert result == []

    def test_parse_clang_output_warning(self):
        """Test parsing clang-tidy warning output."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/clang-tidy"

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            analyzer = ClangTidyAnalyzer(timeout=30)

            output = "/tmp/test.cpp:5:10: warning: some warning [check-name]"
            result = analyzer._parse_clang_output(output)

            assert len(result) == 1
            assert result[0]["id"] == "check-name"

    def test_parse_clang_output_multiple(self):
        """Test parsing multiple warnings."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/clang-tidy"

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            analyzer = ClangTidyAnalyzer(timeout=30)

            output = """
/tmp/test.cpp:5:10: warning: warning 1 [check-1]
/tmp/test.cpp:10:5: error: error 1 [check-2]
"""
            result = analyzer._parse_clang_output(output)

            assert len(result) == 2
            ids = [r["id"] for r in result]
            assert "check-1" in ids
            assert "check-2" in ids

    def test_parse_clang_output_generic_warning(self):
        """Test parsing warning without check name."""
        with patch('scraper.labeling.analyzers.shutil.which') as mock_which:
            mock_which.return_value = "/usr/bin/clang-tidy"

            from scraper.labeling.analyzers import ClangTidyAnalyzer

            analyzer = ClangTidyAnalyzer(timeout=30)

            output = "/tmp/test.cpp:5:10: warning: some generic warning"
            result = analyzer._parse_clang_output(output)

            assert len(result) == 1
            assert result[0]["id"] == "generic-warning"
