"""
Main Labeler class that orchestrates code analysis.
"""

from typing import Dict, List, Optional

from .analyzers import CppcheckAnalyzer
from .config_mapper import ConfigBasedMapper


class Labeler:
    """
    Coordinates static analysis tools and produces structured labels
    matching the fastapi_app.models.Labels schema.
    """

    def __init__(self, timeout: int = 30, config_path: str = None, temp_dir: Optional[str] = None):
        """
        Initialize labeler with analyzers.

        Args:
            timeout: Maximum time in seconds for each analyzer
            config_path: Path to labels_config.json (optional)
            temp_dir: Directory for temporary files (e.g., RAM disk for performance)
        """
        import os

        self.cppcheck = CppcheckAnalyzer(timeout=timeout, temp_dir=temp_dir)
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "..", "labels_config.json")
        self.mapper = ConfigBasedMapper(config_path)

    def analyze(self, code_buggy: str, code_fixed: str = None) -> Dict:
        """
        Analyzes code and produces labels.

        Args:
            code_buggy: Buggy/original code to analyze
            code_fixed: Fixed code to compare against

        Returns:
            Dict matching fastapi_app.models.Labels structure:
            {
                "cppcheck": ["issue_id1", "issue_id2", ...],  # Issues fixed (present in original, not in fixed)
                "groups": {
                    "memory_management": bool,
                    "invalid_access": bool,
                    "uninitialized": bool,
                    "concurrency": bool,
                    "logic_error": bool,
                    "resource_leak": bool,
                    "security_portability": bool,
                    "code_quality_performance": bool
                }
            }
        """
        # Analyze the buggy code (before fix)
        cppcheck_results_before = self.cppcheck.run(code_buggy)
        issues_before = self._extract_unique_issues(cppcheck_results_before)

        # If fixed code provided, analyze it too and compute diff
        if code_fixed:
            cppcheck_results_after = self.cppcheck.run(code_fixed)
            issues_after = self._extract_unique_issues(cppcheck_results_after)

            # Keep only issues that were fixed (present in before, not in after)
            issues_before_set = set(issues_before)
            issues_after_set = set(issues_after)
            fixed_issues = sorted(list(issues_before_set - issues_after_set))

            cppcheck_labels = fixed_issues
        else:
            # If no fixed code, return all issues from buggy code
            cppcheck_labels = issues_before

        # Filter out ignored issues
        cppcheck_labels = self.mapper.filter_issues(cppcheck_labels)

        # Map to high-level groups using config-based mapper
        groups = self.mapper.map_to_groups(cppcheck_labels)

        return {"cppcheck": cppcheck_labels, "groups": groups}

    def _extract_unique_issues(self, results: list) -> List[str]:
        """
        Extract unique issue type names from analyzer results.

        Args:
            results: List of issue dicts from analyzer

        Returns:
            List of unique issue IDs (sorted for consistency)
        """
        issue_types = set()
        for issue in results:
            issue_type = issue.get("id", "unknown")
            if issue_type and issue_type != "unknown":
                issue_types.add(issue_type)
        return sorted(list(issue_types))
