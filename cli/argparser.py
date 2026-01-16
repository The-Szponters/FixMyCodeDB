"""
CLI argument parser module.
Provides argparse-based command-line interface for one-liner execution.
"""

import argparse
import sys
from typing import List, Optional


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="fixmycodedb",
        description="FixMyCodeDB - C++ Bug Dataset Collector and Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start interactive mode (default)
  python cli/main.py

  # Scan repositories from config file
  python cli/main.py --scan --config config.json

  # Scan in parallel mode
  python cli/main.py --scan --parallel --config config.json

  # Scan a single repository
  python cli/main.py --scan --repo-url https://github.com/user/repo

  # Export data to JSON
  python cli/main.py --export json --output data.json

  # Export data to CSV
  python cli/main.py --export csv --output data.csv

  # Manual labeling
  python cli/main.py --label-manual --id <record_id> --set-label "memory-leak"

  # Query entries
  python cli/main.py --query --limit 50 --has-memory-management
        """,
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Start interactive command loop (default if no args)"
    )
    mode_group.add_argument(
        "--scan",
        action="store_true",
        help="Run repository scanning"
    )
    mode_group.add_argument(
        "--export",
        choices=["json", "csv"],
        metavar="FORMAT",
        help="Export data to file (json or csv)"
    )
    mode_group.add_argument(
        "--label-manual",
        action="store_true",
        help="Manually label a specific record"
    )
    mode_group.add_argument(
        "--query",
        action="store_true",
        help="Query and display entries from database"
    )
    mode_group.add_argument(
        "--import-data",
        action="store_true",
        help="Import data from database with filters"
    )

    # Scan options
    scan_group = parser.add_argument_group("Scan Options")
    scan_group.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to scraper config file (default: config.json)"
    )
    scan_group.add_argument(
        "--repo-url",
        type=str,
        help="Single repository URL to scan (overrides config)"
    )
    scan_group.add_argument(
        "--parallel",
        action="store_true",
        help="Use parallel scanning mode"
    )
    scan_group.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel workers (default: 4)"
    )
    scan_group.add_argument(
        "--target-count",
        type=int,
        default=100,
        help="Target record count per repository (default: 100)"
    )

    # Export options
    export_group = parser.add_argument_group("Export Options")
    export_group.add_argument(
        "-o", "--output",
        type=str,
        help="Output file path for export"
    )

    # Labeling options
    label_group = parser.add_argument_group("Labeling Options")
    label_group.add_argument(
        "--id",
        type=str,
        help="Record ID to label"
    )
    label_group.add_argument(
        "--set-label",
        type=str,
        help="Label to set (e.g., 'memory-leak', 'null-pointer')"
    )
    label_group.add_argument(
        "--remove-label",
        type=str,
        help="Label to remove from record"
    )

    # Query/Filter options
    filter_group = parser.add_argument_group("Query/Filter Options")
    filter_group.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of results (default: 100)"
    )
    filter_group.add_argument(
        "--repo-filter",
        type=str,
        help="Filter by repository URL"
    )
    filter_group.add_argument(
        "--commit-hash",
        type=str,
        help="Filter by commit hash"
    )
    filter_group.add_argument(
        "--code-hash",
        type=str,
        help="Filter by code hash"
    )
    filter_group.add_argument(
        "--has-memory-management",
        action="store_true",
        help="Filter entries with memory management issues"
    )
    filter_group.add_argument(
        "--has-invalid-access",
        action="store_true",
        help="Filter entries with invalid access issues"
    )
    filter_group.add_argument(
        "--has-uninitialized",
        action="store_true",
        help="Filter entries with uninitialized variable issues"
    )
    filter_group.add_argument(
        "--has-concurrency",
        action="store_true",
        help="Filter entries with concurrency issues"
    )
    filter_group.add_argument(
        "--has-logic-error",
        action="store_true",
        help="Filter entries with logic errors"
    )
    filter_group.add_argument(
        "--has-resource-leak",
        action="store_true",
        help="Filter entries with resource leaks"
    )

    # General options
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Skip Docker infrastructure management"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="FastAPI server URL (default: http://localhost:8000)"
    )

    return parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: List of arguments to parse (defaults to sys.argv)

    Returns:
        Parsed argument namespace
    """
    parser = create_parser()
    return parser.parse_args(args)


def has_action_args(args: argparse.Namespace) -> bool:
    """
    Check if any action arguments were provided.

    Args:
        args: Parsed argument namespace

    Returns:
        True if user specified an action, False for interactive mode
    """
    action_flags = [
        args.scan,
        args.export is not None,
        args.label_manual,
        args.query,
        args.import_data,
    ]
    return any(action_flags)


def build_filter_dict(args: argparse.Namespace) -> dict:
    """
    Build a MongoDB filter dictionary from parsed arguments.

    Args:
        args: Parsed argument namespace

    Returns:
        Filter dictionary for database queries
    """
    filter_dict = {}

    if args.repo_filter:
        filter_dict["repo.url"] = args.repo_filter

    if args.commit_hash:
        filter_dict["repo.commit_hash"] = args.commit_hash

    if args.code_hash:
        filter_dict["code_hash"] = args.code_hash

    # Boolean label filters
    bool_filters = {
        "has_memory_management": ("labels.groups.memory_management", args.has_memory_management if hasattr(args, 'has_memory_management') else False),
        "has_invalid_access": ("labels.groups.invalid_access", args.has_invalid_access if hasattr(args, 'has_invalid_access') else False),
        "has_uninitialized": ("labels.groups.uninitialized", args.has_uninitialized if hasattr(args, 'has_uninitialized') else False),
        "has_concurrency": ("labels.groups.concurrency", args.has_concurrency if hasattr(args, 'has_concurrency') else False),
        "has_logic_error": ("labels.groups.logic_error", args.has_logic_error if hasattr(args, 'has_logic_error') else False),
        "has_resource_leak": ("labels.groups.resource_leak", args.has_resource_leak if hasattr(args, 'has_resource_leak') else False),
    }

    for key, (db_key, value) in bool_filters.items():
        if value:
            filter_dict[db_key] = True

    return filter_dict
