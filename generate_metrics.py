#!/usr/bin/env python3
"""
Generate repository metrics report.

Calculates:
- Total File Count (source files)
- Lines of Code (LOC)
- Number of Unit Tests
- Code Coverage Percentage

Usage:
    python generate_metrics.py [--run-tests] [--output FORMAT]

Options:
    --run-tests     Run pytest to get actual coverage (requires pytest-cov)
    --output        Output format: text, json, or markdown (default: text)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# File extensions to count as source files
SOURCE_EXTENSIONS = {'.py', '.yaml', '.yml', '.sh', '.js', 'Dockerfile'}

# Patterns to exclude from counting
EXCLUDE_PATTERNS = {
    '.md', '.txt', '.pdf', '.png', '.jpg', '.jpeg', '.gif',
    '.drawio', '.gitignore', '.dockerignore', 'LICENSE'
}

# Directories to exclude
EXCLUDE_DIRS = {
    '.git', '__pycache__', 'venv', '.venv', 'node_modules',
    '.mypy_cache', '.pytest_cache', 'eggs', '*.egg-info'
}


def is_excluded_dir(path: Path) -> bool:
    """Check if path contains an excluded directory."""
    parts = path.parts
    for exclude in EXCLUDE_DIRS:
        if exclude.startswith('*'):
            # Pattern match
            suffix = exclude[1:]
            if any(part.endswith(suffix) for part in parts):
                return True
        elif exclude in parts:
            return True
    return False


def is_source_file(path: Path) -> bool:
    """Check if file should be counted as a source file."""
    if is_excluded_dir(path):
        return False

    name = path.name
    suffix = path.suffix

    # Check excluded patterns
    if suffix in EXCLUDE_PATTERNS or name in EXCLUDE_PATTERNS:
        return False

    # Check for Dockerfile (no extension)
    if name == 'Dockerfile':
        return True

    # Check source extensions
    if suffix in SOURCE_EXTENSIONS:
        return True

    return False


def count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f if line.strip())
    except (IOError, OSError):
        return 0


def find_source_files(root_dir: Path) -> List[Path]:
    """Find all source files in the repository."""
    source_files = []

    for path in root_dir.rglob('*'):
        if path.is_file() and is_source_file(path):
            source_files.append(path)

    return source_files


def count_test_functions(test_dir: Path) -> Tuple[int, List[str]]:
    """Count pytest test functions in test files."""
    test_count = 0
    test_names = []

    test_pattern = re.compile(r'^\s*def\s+(test_\w+)\s*\(', re.MULTILINE)
    class_pattern = re.compile(r'^\s*class\s+(Test\w+)', re.MULTILINE)

    for test_file in test_dir.rglob('test_*.py'):
        if is_excluded_dir(test_file):
            continue

        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Count test functions
            matches = test_pattern.findall(content)
            test_count += len(matches)
            test_names.extend(matches)

            # Also count test classes (for reference)
            class_matches = class_pattern.findall(content)
            test_names.extend([f"class:{cls}" for cls in class_matches])

        except (IOError, OSError):
            continue

    return test_count, test_names


def run_pytest_coverage(root_dir: Path) -> Tuple[float, str]:
    """Run pytest with coverage and return coverage percentage."""
    try:
        result = subprocess.run(
            [
                sys.executable, '-m', 'pytest',
                'tests/',
                '--cov=cli',
                '--cov=fastapi_app',
                '--cov=scraper',
                '--cov-report=term-missing',
                '--cov-report=json',
                '-q'
            ],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=300
        )

        # Try to parse coverage from JSON report
        coverage_json = root_dir / 'coverage.json'
        if coverage_json.exists():
            with open(coverage_json) as f:
                cov_data = json.load(f)
            coverage_pct = cov_data.get('totals', {}).get('percent_covered', 0.0)
            return coverage_pct, result.stdout + result.stderr

        # Fall back to parsing terminal output
        output = result.stdout + result.stderr
        coverage_match = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', output)
        if coverage_match:
            return float(coverage_match.group(1)), output

        return 0.0, output

    except subprocess.TimeoutExpired:
        return 0.0, "Test execution timed out"
    except FileNotFoundError:
        return 0.0, "pytest not found. Install with: pip install pytest pytest-cov"
    except Exception as e:
        return 0.0, f"Error running tests: {e}"


def generate_report(root_dir: Path, run_tests: bool = False) -> Dict:
    """Generate the complete metrics report."""
    metrics = {
        'repository': root_dir.name,
        'source_files': [],
        'total_file_count': 0,
        'total_loc': 0,
        'test_count': 0,
        'coverage_percent': 0.0,
        'test_output': ''
    }

    # Find and count source files
    source_files = find_source_files(root_dir)
    metrics['total_file_count'] = len(source_files)

    # Count lines of code
    for file_path in source_files:
        loc = count_lines(file_path)
        rel_path = file_path.relative_to(root_dir)
        metrics['source_files'].append({
            'path': str(rel_path),
            'loc': loc
        })
        metrics['total_loc'] += loc

    # Count test functions
    tests_dir = root_dir / 'tests'
    if tests_dir.exists():
        test_count, test_names = count_test_functions(tests_dir)
        metrics['test_count'] = test_count
        metrics['test_names'] = test_names

    # Run coverage if requested
    if run_tests:
        coverage, output = run_pytest_coverage(root_dir)
        metrics['coverage_percent'] = coverage
        metrics['test_output'] = output

    return metrics


def format_text(metrics: Dict) -> str:
    """Format metrics as plain text."""
    lines = [
        "=" * 60,
        f"Repository Metrics: {metrics['repository']}",
        "=" * 60,
        "",
        f"📁 Total File Count:     {metrics['total_file_count']}",
        f"📝 Lines of Code (LOC):  {metrics['total_loc']}",
        f"🧪 Number of Unit Tests: {metrics['test_count']}",
        f"📊 Code Coverage:        {metrics['coverage_percent']:.1f}%",
        "",
        "-" * 60,
        "Files by Directory:",
        "-" * 60,
    ]

    # Group files by directory
    by_dir: Dict[str, List[Dict]] = {}
    for f in metrics['source_files']:
        dir_name = str(Path(f['path']).parent)
        if dir_name not in by_dir:
            by_dir[dir_name] = []
        by_dir[dir_name].append(f)

    for dir_name in sorted(by_dir.keys()):
        files = by_dir[dir_name]
        dir_loc = sum(f['loc'] for f in files)
        lines.append(f"\n{dir_name}/ ({len(files)} files, {dir_loc} LOC)")
        for f in sorted(files, key=lambda x: x['path']):
            lines.append(f"  - {Path(f['path']).name}: {f['loc']} LOC")

    lines.extend([
        "",
        "=" * 60,
    ])

    if metrics.get('test_output'):
        lines.extend([
            "",
            "Test Output:",
            "-" * 60,
            metrics['test_output'][:2000]  # Limit output length
        ])

    return "\n".join(lines)


def format_markdown(metrics: Dict) -> str:
    """Format metrics as Markdown."""
    lines = [
        f"# Repository Metrics: {metrics['repository']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| 📁 Total File Count | {metrics['total_file_count']} |",
        f"| 📝 Lines of Code (LOC) | {metrics['total_loc']} |",
        f"| 🧪 Number of Unit Tests | {metrics['test_count']} |",
        f"| 📊 Code Coverage | {metrics['coverage_percent']:.1f}% |",
        "",
        "## Files by Directory",
        "",
    ]

    # Group files by directory
    by_dir: Dict[str, List[Dict]] = {}
    for f in metrics['source_files']:
        dir_name = str(Path(f['path']).parent)
        if dir_name not in by_dir:
            by_dir[dir_name] = []
        by_dir[dir_name].append(f)

    for dir_name in sorted(by_dir.keys()):
        files = by_dir[dir_name]
        dir_loc = sum(f['loc'] for f in files)
        lines.append(f"### `{dir_name}/` ({len(files)} files, {dir_loc} LOC)")
        lines.append("")
        for f in sorted(files, key=lambda x: x['path']):
            lines.append(f"- `{Path(f['path']).name}`: {f['loc']} LOC")
        lines.append("")

    return "\n".join(lines)


def format_json(metrics: Dict) -> str:
    """Format metrics as JSON."""
    # Remove verbose test output for JSON
    output = {k: v for k, v in metrics.items() if k != 'test_output'}
    return json.dumps(output, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Generate repository metrics report')
    parser.add_argument(
        '--run-tests',
        action='store_true',
        help='Run pytest to get actual coverage'
    )
    parser.add_argument(
        '--output',
        choices=['text', 'json', 'markdown'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--root',
        type=Path,
        default=Path.cwd(),
        help='Repository root directory'
    )

    args = parser.parse_args()

    # Generate report
    metrics = generate_report(args.root, run_tests=args.run_tests)

    # Format output
    if args.output == 'json':
        print(format_json(metrics))
    elif args.output == 'markdown':
        print(format_markdown(metrics))
    else:
        print(format_text(metrics))


if __name__ == '__main__':
    main()
