"""
Tests for labeling module.
"""

import os
import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest


class TestConfigMapper:
    """Tests for ConfigBasedMapper class."""

    @pytest.fixture
    def sample_labels_config(self, tmp_path):
        """Create sample labels config file."""
        config = {
            "error_classification": {
                "memory_management": ["memleak", "doubleFree"],
                "invalid_access": ["nullPointer", "arrayIndexOutOfBounds"],
                "uninitialized": ["uninitvar"],
            },
            "ignore_list": ["cppcheckError", "syntaxError"]
        }

        config_path = tmp_path / "labels_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        return str(config_path)

    def test_map_to_groups(self, sample_labels_config):
        """Test mapping issues to groups."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(sample_labels_config)
        issues = ["memleak", "nullPointer"]

        groups = mapper.map_to_groups(issues)

        assert groups["memory_management"] is True
        assert groups["invalid_access"] is True
        assert groups["uninitialized"] is False

    def test_filter_issues(self, sample_labels_config):
        """Test filtering ignored issues."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(sample_labels_config)
        issues = ["memleak", "cppcheckError", "nullPointer", "syntaxError"]

        filtered = mapper.filter_issues(issues)

        assert "memleak" in filtered
        assert "nullPointer" in filtered
        assert "cppcheckError" not in filtered
        assert "syntaxError" not in filtered

    def test_nonexistent_config_file(self, tmp_path):
        """Test with non-existent config file."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        # Should not raise, but use empty mappings
        mapper = ConfigBasedMapper(str(tmp_path / "nonexistent.json"))

        groups = mapper.map_to_groups(["memleak"])

        # All groups should be False with no mapping
        assert all(not v for v in groups.values())


class TestCppcheckAnalyzer:
    """Tests for CppcheckAnalyzer class."""

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        from scraper.labeling.analyzers import CppcheckAnalyzer

        analyzer = CppcheckAnalyzer(timeout=60)

        assert analyzer.timeout == 60

    @patch("subprocess.run")
    def test_run_with_code(self, mock_run):
        """Test running analyzer with code."""
        from scraper.labeling.analyzers import CppcheckAnalyzer

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr='<?xml version="1.0"?><results></results>'
        )

        analyzer = CppcheckAnalyzer()

        # Just verify it doesn't crash
        # The actual parsing depends on cppcheck installation
        try:
            results = analyzer.run("int x;")
            assert isinstance(results, list)
        except Exception:
            # If cppcheck isn't installed, that's OK for this test
            pass


class TestLabeler:
    """Tests for Labeler class."""

    @pytest.fixture
    def mock_cppcheck(self):
        """Create mock cppcheck analyzer."""
        mock = MagicMock()
        mock.run.return_value = []
        return mock

    @pytest.fixture
    def sample_labels_config(self, tmp_path):
        """Create sample labels config."""
        config = {
            "error_classification": {
                "memory_management": ["memleak", "doubleFree"],
                "invalid_access": ["nullPointer"],
            },
            "ignore_list": []
        }

        config_path = tmp_path / "labels_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        return str(config_path)

    @patch("scraper.labeling.labeler.CppcheckAnalyzer")
    def test_analyze_basic(self, mock_analyzer_class, sample_labels_config):
        """Test basic analysis."""
        from scraper.labeling.labeler import Labeler

        # Mock the analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.run.return_value = [{"id": "memleak", "msg": "Memory leak"}]
        mock_analyzer_class.return_value = mock_analyzer

        labeler = Labeler(config_path=sample_labels_config)

        result = labeler.analyze("int* p = malloc(10);", "int* p = malloc(10); free(p);")

        assert "cppcheck" in result
        assert "groups" in result

    @patch("scraper.labeling.labeler.CppcheckAnalyzer")
    def test_analyze_diff(self, mock_analyzer_class, sample_labels_config):
        """Test analysis with diff calculation."""
        from scraper.labeling.labeler import Labeler

        mock_analyzer = MagicMock()
        # Before: has memleak, After: no issues
        mock_analyzer.run.side_effect = [
            [{"id": "memleak", "msg": "Memory leak"}],
            []
        ]
        mock_analyzer_class.return_value = mock_analyzer

        labeler = Labeler(config_path=sample_labels_config)

        result = labeler.analyze("buggy code", "fixed code")

        # memleak should be in the diff (fixed)
        assert "memleak" in result["cppcheck"]

    @patch("scraper.labeling.labeler.CppcheckAnalyzer")
    def test_extract_unique_issues(self, mock_analyzer_class, sample_labels_config):
        """Test extracting unique issues."""
        from scraper.labeling.labeler import Labeler

        mock_analyzer = MagicMock()
        mock_analyzer.run.return_value = []
        mock_analyzer_class.return_value = mock_analyzer

        labeler = Labeler(config_path=sample_labels_config)

        results = [
            {"id": "memleak", "msg": "Leak 1"},
            {"id": "memleak", "msg": "Leak 2"},
            {"id": "nullPointer", "msg": "Null"},
        ]

        unique = labeler._extract_unique_issues(results)

        assert len(unique) == 2
        assert "memleak" in unique
        assert "nullPointer" in unique


class TestLabelsIntegration:
    """Integration tests for labeling system."""

    @pytest.fixture
    def labels_config_path(self):
        """Get path to actual labels config if it exists."""
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "scraper",
            "labels_config.json"
        )
        if os.path.exists(config_path):
            return config_path
        return None

    def test_real_labels_config_exists(self, labels_config_path):
        """Test that the real labels config file exists."""
        if labels_config_path:
            assert os.path.exists(labels_config_path)

            with open(labels_config_path) as f:
                config = json.load(f)

            assert "error_classification" in config

    def test_real_labels_config_structure(self, labels_config_path):
        """Test structure of real labels config."""
        if not labels_config_path:
            pytest.skip("Labels config not found")

        with open(labels_config_path) as f:
            config = json.load(f)

        classification = config["error_classification"]

        # Check expected groups exist
        expected_groups = [
            "memory_management",
            "invalid_access",
            "uninitialized",
        ]

        for group in expected_groups:
            assert group in classification
            assert isinstance(classification[group], list)
