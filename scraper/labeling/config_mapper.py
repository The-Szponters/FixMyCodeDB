"""
Config-based mapper for cppcheck issues to label categories.
"""

import json
from typing import Dict, List


class ConfigBasedMapper:
    """Maps cppcheck issue IDs to high-level categories using labels_config.json."""

    def __init__(self, config_path: str):
        """
        Initialize mapper with configuration file.

        Args:
            config_path: Path to labels_config.json
        """
        with open(config_path, "r") as f:
            config = json.load(f)

        self.error_classification = config["error_classification"]
        self.ignore_set = set(config["ignore_list"])

        # Build reverse mapping: issue_id -> category_name
        self.issue_to_category: Dict[str, str] = {}
        for category, issues in self.error_classification.items():
            for issue_id in issues:
                self.issue_to_category[issue_id] = category

    def filter_issues(self, issues: List[str]) -> List[str]:
        """
        Filter out issues that should be ignored.

        Args:
            issues: List of cppcheck issue IDs

        Returns:
            Filtered list of issues
        """
        return [issue for issue in issues if issue not in self.ignore_set]

    def map_to_groups(self, cppcheck_issues: List[str]) -> Dict[str, bool]:
        """
        Map cppcheck issues to high-level category flags.

        Args:
            cppcheck_issues: List of cppcheck issue IDs (already filtered)

        Returns:
            Dict with 8 category flags:
            {
                "memory_management": bool,
                "invalid_access": bool,
                "uninitialized": bool,
                "concurrency": bool,
                "logic_error": bool,
                "resource_leak": bool,
                "security_portability": bool,
                "code_quality_performance": bool
            }
        """
        # Initialize all categories as False
        groups = {
            "memory_management": False,
            "invalid_access": False,
            "uninitialized": False,
            "concurrency": False,
            "logic_error": False,
            "resource_leak": False,
            "security_portability": False,
            "code_quality_performance": False,
        }

        # Set flags based on detected issues
        for issue_id in cppcheck_issues:
            # Skip ignored issues
            if issue_id in self.ignore_set:
                continue

            # Look up category for this issue
            category = self.issue_to_category.get(issue_id)
            if category and category in groups:
                groups[category] = True

        return groups
