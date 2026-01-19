"""
Unit tests for scraper/labeling/labeler.py
Tests labeling functionality with mocked analyzers.
"""
import pytest
from unittest.mock import MagicMock, patch
import json
import tempfile
import os


class TestLabeler:
    """Tests for Labeler class."""

    @pytest.fixture
    def mock_labels_config(self, tmp_path):
        """Create a mock labels_config.json file."""
        config = {
            "error_classification": {
                "memory_management": ["memleak", "deallocuse"],
                "invalid_access": ["nullPointer", "arrayIndexOutOfBounds"],
                "uninitialized": ["uninitvar", "uninitMemberVar"],
                "concurrency": ["raceCondition"],
                "logic_error": ["duplicateBreak", "unreachableCode"],
                "resource_leak": ["resourceLeak"],
                "security_portability": ["bufferAccessOutOfBounds"],
                "code_quality_performance": ["unusedVariable", "constParameter"],
            },
            "ignore_list": ["syntaxError", "preprocessorError"],
        }
        config_path = tmp_path / "labels_config.json"
        config_path.write_text(json.dumps(config))
        return str(config_path)

    def test_labeler_init(self, mock_labels_config):
        """Test Labeler initialization."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer:
            mock_analyzer.return_value = MagicMock()

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)

            assert labeler.cppcheck is not None
            assert labeler.mapper is not None

    def test_analyze_with_issues(self, mock_labels_config):
        """Test analyze finds issues in buggy code."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer = MagicMock()
            mock_analyzer.run.return_value = [
                {"id": "nullPointer"},
                {"id": "memleak"},
            ]
            mock_analyzer_class.return_value = mock_analyzer

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)
            result = labeler.analyze("int main() { int *p; *p = 1; }")

            assert "cppcheck" in result
            assert "groups" in result
            assert "nullPointer" in result["cppcheck"]
            assert "memleak" in result["cppcheck"]

    def test_analyze_with_fixed_code(self, mock_labels_config):
        """Test analyze compares buggy and fixed code."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer = MagicMock()
            # Buggy code has two issues
            # Fixed code has one issue
            call_count = [0]

            def run_side_effect(code):
                call_count[0] += 1
                if call_count[0] == 1:
                    return [{"id": "nullPointer"}, {"id": "memleak"}]
                return [{"id": "memleak"}]  # nullPointer was fixed

            mock_analyzer.run.side_effect = run_side_effect
            mock_analyzer_class.return_value = mock_analyzer

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)
            result = labeler.analyze("buggy code", "fixed code")

            # Only nullPointer should be in result (it was fixed)
            assert "nullPointer" in result["cppcheck"]
            assert "memleak" not in result["cppcheck"]

    def test_analyze_no_issues(self, mock_labels_config):
        """Test analyze with clean code."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer = MagicMock()
            mock_analyzer.run.return_value = []
            mock_analyzer_class.return_value = mock_analyzer

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)
            result = labeler.analyze("int main() { return 0; }")

            assert result["cppcheck"] == []

    def test_analyze_filters_ignored_issues(self, mock_labels_config):
        """Test analyze filters out ignored issues."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer = MagicMock()
            mock_analyzer.run.return_value = [
                {"id": "syntaxError"},  # Should be filtered
                {"id": "nullPointer"},  # Should remain
            ]
            mock_analyzer_class.return_value = mock_analyzer

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)
            result = labeler.analyze("buggy code")

            assert "syntaxError" not in result["cppcheck"]
            assert "nullPointer" in result["cppcheck"]

    def test_analyze_maps_to_groups(self, mock_labels_config):
        """Test analyze maps issues to groups correctly."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer = MagicMock()
            mock_analyzer.run.return_value = [
                {"id": "nullPointer"},
                {"id": "memleak"},
            ]
            mock_analyzer_class.return_value = mock_analyzer

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)
            result = labeler.analyze("buggy code")

            assert result["groups"]["invalid_access"] is True
            assert result["groups"]["memory_management"] is True
            assert result["groups"]["concurrency"] is False

    def test_extract_unique_issues(self, mock_labels_config):
        """Test _extract_unique_issues extracts unique IDs."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            mock_analyzer_class.return_value = MagicMock()

            from scraper.labeling.labeler import Labeler

            labeler = Labeler(timeout=30, config_path=mock_labels_config)

            results = [
                {"id": "nullPointer"},
                {"id": "nullPointer"},  # Duplicate
                {"id": "memleak"},
                {"id": "unknown"},  # Should be filtered
            ]

            unique = labeler._extract_unique_issues(results)

            assert len(unique) == 2
            assert "nullPointer" in unique
            assert "memleak" in unique
            assert "unknown" not in unique

    def test_labeler_with_temp_dir(self, mock_labels_config, tmp_path):
        """Test Labeler passes temp_dir to analyzer."""
        with patch('scraper.labeling.labeler.CppcheckAnalyzer') as mock_analyzer_class:
            from scraper.labeling.labeler import Labeler

            labeler = Labeler(
                timeout=30,
                config_path=mock_labels_config,
                temp_dir=str(tmp_path)
            )

            mock_analyzer_class.assert_called_once_with(
                timeout=30,
                temp_dir=str(tmp_path)
            )
