#!/usr/bin/env python3
"""
Script to analyze labeling results across all extracted data files.
Counts cppcheck issues found in all JSON files.
"""

import json
from collections import defaultdict
from pathlib import Path


def analyze_labels(data_dir: str = "extracted_data"):
    """
    Analyzes all JSON files in the extracted_data directory
    and counts cppcheck issues.
    """
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"Error: Directory {data_dir} does not exist")
        return

    # Counters
    total_files = 0
    files_with_labels = 0

    cppcheck_total = 0

    cppcheck_issues = defaultdict(int)

    groups_stats = {"memory_management": 0, "invalid_access": 0, "uninitialized": 0, "concurrency": 0, "logic_error": 0, "resource_leak": 0, "security_portability": 0, "code_quality_performance": 0}

    # Process all JSON files
    json_files = list(data_path.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {data_dir}")
        return

    print(f"Analyzing {len(json_files)} files...\n")

    for json_file in json_files:
        total_files += 1

        try:
            with open(json_file, "r") as f:
                data = json.load(f)

            labels = data.get("labels", {})

            if not labels:
                continue

            files_with_labels += 1

            # Count cppcheck issues (now a list)
            cppcheck = labels.get("cppcheck", [])
            if isinstance(cppcheck, list):
                for issue_type in cppcheck:
                    cppcheck_issues[issue_type] += 1
                cppcheck_total += len(cppcheck)
            elif isinstance(cppcheck, dict):
                # Support old format
                for issue_type, count in cppcheck.items():
                    cppcheck_issues[issue_type] += count
                    cppcheck_total += count

            # Count group flags
            groups = labels.get("groups", {})
            for group_name, is_flagged in groups.items():
                if is_flagged:
                    groups_stats[group_name] += 1
        except Exception as e:
            print(f"Error processing {json_file.name}: {e}")

    # Print results
    print("=" * 60)
    print("LABEL ANALYSIS RESULTS")
    print("=" * 60)
    print(f"\nTotal files processed: {total_files}")
    print(f"Files with labels: {files_with_labels}")
    print(f"Files without labels: {total_files - files_with_labels}")

    print(f"\n{'=' * 60}")
    print("CPPCHECK RESULTS")
    print("=" * 60)
    print(f"Total cppcheck issues found: {cppcheck_total}")

    if cppcheck_issues:
        print("\nTop cppcheck issues:")
        sorted_cppcheck = sorted(cppcheck_issues.items(), key=lambda x: x[1], reverse=True)
        for issue_type, count in sorted_cppcheck[:10]:
            print(f"  {issue_type:40} {count:5} issues")
    else:
        print("  No cppcheck issues found")

    print(f"\n{'=' * 60}")
    print("HIGH-LEVEL CATEGORY GROUPS")
    print("=" * 60)
    for group_name, count in sorted(groups_stats.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / files_with_labels * 100) if files_with_labels > 0 else 0
        print(f"  {group_name:25} {count:5} files ({percentage:5.1f}%)")

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Total unique issues detected: {cppcheck_total}")
    print(f"Unique cppcheck issue types: {len(cppcheck_issues)}")


if __name__ == "__main__":
    import sys

    data_dir = sys.argv[1] if len(sys.argv) > 1 else "extracted_data"
    analyze_labels(data_dir)
