#!/usr/bin/env python3
"""
Count non-comment, non-whitespace lines in Unified Test Format (UTF) YAML files
across the git history of the MongoDB specifications repository.

This script samples at most one commit per ISO week, identifies UTF files by
checking for the required `schemaVersion` field, and outputs a CSV suitable
for charting corpus growth over time.

Usage:
    python scripts/count_utf_lines.py [--output FILE] [--repo-path PATH]

Output CSV columns:
    commit_hash, date, iso_week, num_files, total_lines
"""

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import ReusedAnchorWarning

# Version for traceability in output
SCRIPT_VERSION = "1.4.0"

# Regex to validate schemaVersion format: X.Y or X.Y.Z
SCHEMA_VERSION_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")

# Directories to skip (contain test fixtures for the format itself, not real tests)
SKIP_DIRS = {"unified-test-format"}


def log_verbose(message: str, verbose: bool) -> None:
    """Log a verbose message to stderr if verbose mode is enabled."""
    if verbose:
        print(f"[VERBOSE] {message}", file=sys.stderr)


def get_all_commits_with_dates(repo_path: Path) -> list[tuple[str, str]]:
    """
    Get all commits with their ISO dates, oldest first.

    Returns list of (commit_hash, iso_date) tuples.
    """
    result = subprocess.run(
        ["git", "log", "--format=%H %aI", "--reverse"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))
    return commits


def get_iso_week(iso_date: str) -> str:
    """
    Extract ISO week string (YYYY-WNN) from an ISO date.
    """
    # Parse ISO date: 2020-11-06T10:30:00-05:00
    date_str = iso_date

    # Handle timezone offset in ISO format
    if "+" in date_str or date_str.count("-") > 2:
        # Remove timezone for parsing
        if "+" in date_str:
            date_str = date_str.split("+")[0]
        elif date_str.count("-") > 2:
            # Find the last hyphen that's part of timezone
            # Format: 2020-11-06T10:30:00-05:00
            if "T" in date_str:
                date_part, time_part = date_str.split("T")
                if "-" in time_part:
                    time_part = time_part.rsplit("-", 1)[0]
                date_str = f"{date_part}T{time_part}"

    # Remove any trailing Z
    date_str = date_str.rstrip("Z")

    # Parse the datetime
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        # Fallback: just use the date portion
        dt = datetime.fromisoformat(iso_date[:10])

    # Get ISO calendar week
    iso_cal = dt.isocalendar()
    return f"{iso_cal[0]}-W{iso_cal[1]:02d}"


def sample_weekly_commits(
    commits: list[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    """
    Sample at most one commit per ISO week (the first commit of each week).

    Returns list of (commit_hash, iso_date, iso_week) tuples.
    """
    weekly_commits = {}  # iso_week -> (commit_hash, iso_date)

    for commit_hash, iso_date in commits:
        iso_week = get_iso_week(iso_date)
        if iso_week not in weekly_commits:
            weekly_commits[iso_week] = (commit_hash, iso_date)

    # Sort by ISO week for deterministic output
    result = []
    for iso_week in sorted(weekly_commits.keys()):
        commit_hash, iso_date = weekly_commits[iso_week]
        result.append((commit_hash, iso_date, iso_week))

    return result


def find_yml_files(repo_path: Path) -> list[Path]:
    """
    Find all .yml files in the repository, sorted for reproducibility.
    """
    yml_files = sorted(repo_path.rglob("*.yml"))
    # Also check for .yaml extension
    yaml_files = sorted(repo_path.rglob("*.yaml"))
    return sorted(set(yml_files + yaml_files))


def is_utf_file(file_path: Path, verbose: bool = False) -> bool:
    """
    Check if a YAML file is a Unified Test Format file.

    UTF files are identified by:
    - Having a `schemaVersion` field at root level matching X.Y or X.Y.Z
    - Having `tests` and `description` fields at root level
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    with open(file_path, "r", encoding="utf-8") as f:
        # Suppress ReusedAnchorWarning - duplicate anchors are valid in YAML 1.2
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=ReusedAnchorWarning)
            content = yaml.load(f)

    if not isinstance(content, dict):
        log_verbose(f"  Not a dict: {file_path}", verbose)
        return False

    # Check for schemaVersion (required, unique to UTF)
    schema_version = content.get("schemaVersion")
    if schema_version is None:
        log_verbose(f"  No schemaVersion: {file_path}", verbose)
        return False

    if not SCHEMA_VERSION_PATTERN.match(str(schema_version)):
        log_verbose(f"  Invalid schemaVersion '{schema_version}': {file_path}", verbose)
        return False

    # Check for required fields
    if "tests" not in content:
        log_verbose(f"  No 'tests' field: {file_path}", verbose)
        return False
    if "description" not in content:
        log_verbose(f"  No 'description' field: {file_path}", verbose)
        return False

    log_verbose(f"  IS UTF (schemaVersion={schema_version}): {file_path}", verbose)
    return True


def count_non_comment_lines(file_path: Path) -> int:
    """
    Count non-empty, non-comment lines in a file.

    Excludes:
    - Empty lines (after stripping whitespace)
    - Lines starting with # (comments)
    """
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def process_commit(
    source_repo: Path,
    work_repo: Path,
    commit_hash: str,
    verbose: bool = False,
    max_files: int | None = None,
) -> tuple[int, int]:
    """
    Checkout a commit and count UTF files and lines.

    Returns (num_files, total_lines).
    
    If max_files is set, stops after processing that many UTF files.
    """
    # Checkout the commit
    subprocess.run(
        ["git", "checkout", "--force", "--quiet", commit_hash],
        cwd=work_repo,
        check=True,
        capture_output=True,
    )

    # Find and process UTF files
    yml_files = find_yml_files(work_repo)
    log_verbose(f"Found {len(yml_files)} YAML files in commit", verbose)

    num_files = 0
    total_lines = 0

    for yml_file in yml_files:
        # Skip files in .git directory or in SKIP_DIRS
        if ".git" in yml_file.parts:
            continue
        if any(skip_dir in yml_file.parts for skip_dir in SKIP_DIRS):
            continue

        log_verbose(f"Checking: {yml_file.relative_to(work_repo)}", verbose)
        
        if is_utf_file(yml_file, verbose=verbose):
            lines = count_non_comment_lines(yml_file)
            log_verbose(f"  Line count: {lines}", verbose)
            num_files += 1
            total_lines += lines
            
            if max_files is not None and num_files >= max_files:
                log_verbose(f"Stopping after {max_files} UTF file(s) (--max-files-per-commit)", verbose)
                return num_files, total_lines

    return num_files, total_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count UTF YAML file lines across git history"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output CSV file path (default: stdout)",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        default=".",
        help="Path to the specifications repository (default: current directory)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary directory after completion (for debugging)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output showing file-by-file decisions",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=None,
        help="Maximum number of commits to process (default: all)",
    )
    parser.add_argument(
        "--max-files-per-commit",
        type=int,
        default=None,
        help="Maximum UTF files to process per commit (default: all)",
    )
    parser.add_argument(
        "--overwrite-results",
        action="store_true",
        help="Overwrite existing CSV instead of skipping already-processed commits",
    )
    args = parser.parse_args()

    verbose = args.verbose
    source_repo = Path(args.repo_path).resolve()
    start_time = time.time()

    if not (source_repo / ".git").exists():
        print(f"Error: {source_repo} is not a git repository", file=sys.stderr)
        sys.exit(1)

    print(f"Source repository: {source_repo}", file=sys.stderr)

    # Get all commits
    print("Fetching commit history...", file=sys.stderr)
    all_commits = get_all_commits_with_dates(source_repo)
    print(f"Found {len(all_commits)} total commits", file=sys.stderr)

    # Sample weekly commits
    weekly_commits = sample_weekly_commits(all_commits)
    print(f"Sampled {len(weekly_commits)} weekly commits", file=sys.stderr)

    # Apply --max-commits limit (take from the end for recent commits)
    if args.max_commits is not None:
        weekly_commits = weekly_commits[-args.max_commits:]
        print(f"Limited to {len(weekly_commits)} commits (--max-commits)", file=sys.stderr)

    # Load existing results if output file exists (incremental mode)
    existing_results = {}  # iso_week -> result dict
    if args.output and Path(args.output).exists() and not args.overwrite_results:
        with open(args.output, "r") as f:
            # Skip comment lines
            reader = csv.DictReader(
                line for line in f if not line.startswith("#")
            )
            for row in reader:
                row["num_files"] = int(row["num_files"])
                row["total_lines"] = int(row["total_lines"])
                existing_results[row["iso_week"]] = row
        print(f"Loaded {len(existing_results)} existing results from {args.output}", file=sys.stderr)

    # Filter out already-processed commits
    commits_to_process = [
        (h, d, w) for h, d, w in weekly_commits if w not in existing_results
    ]
    if len(commits_to_process) < len(weekly_commits):
        print(
            f"Skipping {len(weekly_commits) - len(commits_to_process)} already-processed commits",
            file=sys.stderr,
        )

    # If nothing to process, just report and exit
    if not commits_to_process:
        print("No new commits to process", file=sys.stderr)
        # Still print summary from existing results
        results = sorted(existing_results.values(), key=lambda r: r["iso_week"])
        utf_results = [r for r in results if r["num_files"] > 0]
        if utf_results:
            print(
                f"First UTF files appeared: {utf_results[0]['iso_week']} "
                f"({utf_results[0]['num_files']} files, {utf_results[0]['total_lines']} lines)",
                file=sys.stderr,
            )
            print(
                f"Latest sample: {utf_results[-1]['iso_week']} "
                f"({utf_results[-1]['num_files']} files, {utf_results[-1]['total_lines']} lines)",
                file=sys.stderr,
            )
        return

    # Create temporary directory and clone repo
    temp_dir = tempfile.mkdtemp(prefix="utf_count_")
    work_repo = Path(temp_dir) / "repo"

    print(f"Working directory: {temp_dir}", file=sys.stderr)

    try:
        # Clone the repository (local clone is fast)
        print("Cloning repository to temp directory...", file=sys.stderr)
        subprocess.run(
            ["git", "clone", "--quiet", str(source_repo), str(work_repo)],
            check=True,
            capture_output=True,
        )

        # Process each weekly commit
        results = []

        for i, (commit_hash, iso_date, iso_week) in enumerate(commits_to_process):
            # Progress indicator
            if (i + 1) % 50 == 0 or i == 0:
                print(
                    f"Processing commit {i + 1}/{len(commits_to_process)} "
                    f"({iso_week})...",
                    file=sys.stderr,
                )

            num_files, total_lines = process_commit(
                source_repo, work_repo, commit_hash,
                verbose=verbose,
                max_files=args.max_files_per_commit,
            )

            results.append(
                {
                    "commit_hash": commit_hash,
                    "date": iso_date[:10],  # Just the date portion
                    "iso_week": iso_week,
                    "num_files": num_files,
                    "total_lines": total_lines,
                }
            )

        # Merge new results with existing results
        for result in results:
            existing_results[result["iso_week"]] = result
        
        # Sort all results by iso_week
        all_results = sorted(existing_results.values(), key=lambda r: r["iso_week"])

        # Write output
        output_file = (
            open(args.output, "w", newline="") if args.output else sys.stdout
        )

        try:
            # Write header comment
            if args.output:
                output_file.write(
                    f"# Generated by count_utf_lines.py v{SCRIPT_VERSION}\n"
                )
                output_file.write(f"# Source: {source_repo}\n")

            writer = csv.DictWriter(
                output_file,
                fieldnames=[
                    "commit_hash",
                    "date",
                    "iso_week",
                    "num_files",
                    "total_lines",
                ],
            )
            writer.writeheader()
            writer.writerows(all_results)
        finally:
            if args.output:
                output_file.close()

        print(f"Processed {len(results)} new commits, {len(all_results)} total weekly samples", file=sys.stderr)

        # Summary statistics
        utf_results = [r for r in all_results if r["num_files"] > 0]
        if utf_results:
            first_utf = utf_results[0]
            last_utf = utf_results[-1]
            print(
                f"First UTF files appeared: {first_utf['iso_week']} "
                f"({first_utf['num_files']} files, {first_utf['total_lines']} lines)",
                file=sys.stderr,
            )
            print(
                f"Latest sample: {last_utf['iso_week']} "
                f"({last_utf['num_files']} files, {last_utf['total_lines']} lines)",
                file=sys.stderr,
            )
        else:
            print("No UTF files found in any commit", file=sys.stderr)

        elapsed = time.time() - start_time
        print(f"Elapsed time: {elapsed:.1f}s", file=sys.stderr)

    finally:
        if args.keep_temp:
            print(f"Keeping temp directory: {temp_dir}", file=sys.stderr)
        else:
            print("Cleaning up temp directory...", file=sys.stderr)
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
