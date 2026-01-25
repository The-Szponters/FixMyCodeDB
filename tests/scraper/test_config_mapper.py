"""
Unit tests for scraper/labeling/config_mapper.py
Tests configuration-based label mapping.
"""
import pytest
import json


class TestConfigBasedMapper:
    """Tests for ConfigBasedMapper class."""

    @pytest.fixture
    def mock_config_path(self, tmp_path):
        """Create a mock labels_config.json file."""
        config = {
            "error_classification": {
                "memory_management": ["memleak", "deallocuse", "doubleFree"],
                "invalid_access": ["nullPointer", "arrayIndexOutOfBounds"],
                "uninitialized": ["uninitvar", "uninitMemberVar"],
                "concurrency": ["raceCondition", "deadlock"],
                "logic_error": ["duplicateBreak", "unreachableCode"],
                "resource_leak": ["resourceLeak", "fdLeak"],
                "security_portability": ["bufferAccessOutOfBounds"],
                "code_quality_performance": ["unusedVariable", "constParameter"],
            },
            "ignore_list": ["syntaxError", "preprocessorError", "checkersReport"],
        }
        config_path = tmp_path / "labels_config.json"
        config_path.write_text(json.dumps(config))
        return str(config_path)

    def test_mapper_init(self, mock_config_path):
        """Test mapper initialization."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        assert mapper.error_classification is not None
        assert mapper.ignore_set is not None
        assert "syntaxError" in mapper.ignore_set

    def test_filter_issues_removes_ignored(self, mock_config_path):
        """Test filter_issues removes ignored issues."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        issues = ["nullPointer", "syntaxError", "memleak", "preprocessorError"]
        filtered = mapper.filter_issues(issues)

        assert "nullPointer" in filtered
        assert "memleak" in filtered
        assert "syntaxError" not in filtered
        assert "preprocessorError" not in filtered

    def test_filter_issues_empty_list(self, mock_config_path):
        """Test filter_issues with empty list."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        filtered = mapper.filter_issues([])

        assert filtered == []

    def test_filter_issues_all_ignored(self, mock_config_path):
        """Test filter_issues when all are ignored."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        issues = ["syntaxError", "preprocessorError", "checkersReport"]
        filtered = mapper.filter_issues(issues)

        assert filtered == []

    def test_map_to_groups_single_category(self, mock_config_path):
        """Test mapping single issue to group."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        groups = mapper.map_to_groups(["nullPointer"])

        assert groups["invalid_access"] is True
        assert groups["memory_management"] is False
        assert groups["uninitialized"] is False

    def test_map_to_groups_multiple_categories(self, mock_config_path):
        """Test mapping multiple issues to multiple groups."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        groups = mapper.map_to_groups(["nullPointer", "memleak", "raceCondition"])

        assert groups["invalid_access"] is True
        assert groups["memory_management"] is True
        assert groups["concurrency"] is True
        assert groups["uninitialized"] is False

    def test_map_to_groups_all_false_when_empty(self, mock_config_path):
        """Test all groups are False when no issues."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        groups = mapper.map_to_groups([])

        assert all(v is False for v in groups.values())
        assert len(groups) == 8

    def test_map_to_groups_unknown_issue(self, mock_config_path):
        """Test unknown issues don't affect groups."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        groups = mapper.map_to_groups(["unknownIssue"])

        assert all(v is False for v in groups.values())

    def test_issue_to_category_mapping(self, mock_config_path):
        """Test issue_to_category reverse mapping."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        assert mapper.issue_to_category["nullPointer"] == "invalid_access"
        assert mapper.issue_to_category["memleak"] == "memory_management"
        assert mapper.issue_to_category["raceCondition"] == "concurrency"
        assert mapper.issue_to_category["unusedVariable"] == "code_quality_performance"

    def test_map_to_groups_ignores_filtered_issues(self, mock_config_path):
        """Test map_to_groups ignores issues in ignore set."""
        from scraper.labeling.config_mapper import ConfigBasedMapper

        mapper = ConfigBasedMapper(mock_config_path)

        # Even if we pass ignored issues, they shouldn't affect groups
        groups = mapper.map_to_groups(["syntaxError", "nullPointer"])

        assert groups["invalid_access"] is True
        # syntaxError is in ignore list, shouldn't map to anything
