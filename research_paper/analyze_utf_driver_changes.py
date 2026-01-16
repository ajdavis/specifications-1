#!/usr/bin/env python3
"""
Analyze code changes for Unified Test Format migration across MongoDB drivers.

This script:
1. Clones each driver repository to a temp directory
2. Searches git history for commits referencing Jira ticket IDs
3. Measures net lines of test runner code added/removed (excluding YAML, JSON, etc.)
4. Outputs results to CSV
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Driver:
    name: str
    repo_url: str
    code_extensions: tuple[str, ...]
    ticket_ids: list[str] = field(default_factory=list)


# Define all drivers with their configurations
DRIVERS = [
    Driver(
        name="C Driver",
        repo_url="https://github.com/mongodb/mongo-c-driver.git",
        code_extensions=(".c", ".h"),
        ticket_ids=[
            "CDRIVER-3967",  # Epic
            "CDRIVER-3959",  # Convert GridFS spec tests
            "CDRIVER-3960",  # Convert CRUD v2 spec tests
        ],
    ),
    Driver(
        name="C++ Driver",
        repo_url="https://github.com/mongodb/mongo-cxx-driver.git",
        code_extensions=(".cpp", ".hpp", ".hh", ".h", ".cxx"),
        ticket_ids=[
            "CXX-2236",  # Epic
            "CXX-2228",  # Convert GridFS spec tests
            "CXX-2229",  # Convert CRUD v2 spec tests
        ],
    ),
    Driver(
        name="C# Driver",
        repo_url="https://github.com/mongodb/mongo-csharp-driver.git",
        code_extensions=(".cs",),
        ticket_ids=[
            "CSHARP-3620",  # Epic
            "CSHARP-3587",  # Convert GridFS spec tests
            "CSHARP-3592",  # Convert CRUD v2 spec tests
            "CSHARP-3678",  # Convert transactions spec tests
            "CSHARP-4052",  # Convert sessions spec tests
            "CSHARP-4984",  # Convert retryable writes spec tests
            "CSHARP-4989",  # Convert retryable reads spec tests
            "CSHARP-4999",  # Migrate Atlas Data Lake tests
            "CSHARP-5000",  # Convert read/write concern spec tests
        ],
    ),
    Driver(
        name="Go Driver",
        repo_url="https://github.com/mongodb/mongo-go-driver.git",
        code_extensions=(".go",),
        ticket_ids=[
            "GODRIVER-1983",  # Epic
            "GODRIVER-1969",  # Convert GridFS spec tests
            "GODRIVER-1970",  # Convert CRUD v2 spec tests
            "GODRIVER-1986",  # Convert change stream spec tests
            "GODRIVER-2309",  # Convert sessions spec tests
            "GODRIVER-2434",  # Convert APM spec tests
            "GODRIVER-2466",  # Convert SDAM integration spec tests
        ],
    ),
    Driver(
        name="Java Driver",
        repo_url="https://github.com/mongodb/mongo-java-driver.git",
        code_extensions=(".java",),
        ticket_ids=[
            "JAVA-4120",  # Epic
            "JAVA-4109",  # Convert GridFS spec tests
            "JAVA-4110",  # Convert CRUD v2 spec tests
            "JAVA-5343",  # Convert CRUD v1 spec tests
            "JAVA-5344",  # Convert retryable reads spec tests
            "JAVA-5354",  # Migrate Atlas Data Lake tests
            "JAVA-5355",  # Convert write concern operation spec tests
            "JAVA-5363",  # Use mapReduce command name
        ],
    ),
    Driver(
        name="Node.js Driver",
        repo_url="https://github.com/mongodb/node-mongodb-native.git",
        code_extensions=(".js", ".ts"),
        ticket_ids=[
            "NODE-3237",  # Epic
            "NODE-3211",  # Convert GridFS spec tests
            "NODE-3213",  # Convert CRUD v2 spec tests
            "NODE-3248",  # Convert change stream spec tests
            "NODE-3299",  # Convert transactions spec tests
            "NODE-5975",  # Convert retryable writes spec tests
            "NODE-5976",  # Convert CRUD v1 spec tests
            "NODE-5984",  # Convert retryable reads spec tests
            "NODE-6004",  # Migrate Atlas Data Lake tests
            "NODE-6005",  # Convert read/write concern spec tests
        ],
    ),
    Driver(
        name="PHP Driver",
        repo_url="https://github.com/mongodb/mongo-php-library.git",
        code_extensions=(".php",),
        ticket_ids=[
            "PHPLIB-1289",  # Epic
            "PHPLIB-644",  # Convert GridFS spec tests
            "PHPLIB-645",  # Convert CRUD v2 spec tests
            "PHPLIB-652",  # Convert change stream spec tests
            "PHPLIB-788",  # Convert sessions spec tests
            "PHPLIB-879",  # Convert APM spec tests
            "PHPLIB-1392",  # Convert transactions spec tests
            "PHPLIB-1402",  # Convert retryable writes spec tests
            "PHPLIB-1403",  # Convert CRUD v1 spec tests
            "PHPLIB-1404",  # Convert retryable reads spec tests
            "PHPLIB-1408",  # Migrate Atlas Data Lake tests
            "PHPLIB-1409",  # Convert read/write concern spec tests
        ],
    ),
    Driver(
        name="Python Driver",
        repo_url="https://github.com/mongodb/mongo-python-driver.git",
        code_extensions=(".py",),
        ticket_ids=[
            "PYTHON-2664",  # Epic (also covers MOTOR-1197)
            "PYTHON-2650",  # Convert GridFS spec tests
            "PYTHON-2651",  # Convert CRUD v2 spec tests
            "PYTHON-2683",  # Convert change stream spec tests
            "PYTHON-2723",  # Convert transactions spec tests
            "PYTHON-4249",  # Convert retryable reads spec tests
            "PYTHON-4266",  # Migrate Atlas Data Lake tests
            "PYTHON-4267",  # Convert read/write concern spec tests
        ],
    ),
    Driver(
        name="Ruby Driver",
        repo_url="https://github.com/mongodb/mongo-ruby-driver.git",
        code_extensions=(".rb",),
        ticket_ids=[
            "RUBY-3336",  # Epic (no visible child tickets)
        ],
    ),
    Driver(
        name="Rust Driver",
        repo_url="https://github.com/mongodb/mongo-rust-driver.git",
        code_extensions=(".rs",),
        ticket_ids=[
            "RUST-758",  # Epic
            "RUST-749",  # Convert CRUD v2 spec tests
            "RUST-767",  # Convert change stream spec tests
            "RUST-817",  # Convert transactions spec tests
            "RUST-1878",  # Migrate Atlas Data Lake tests
        ],
    ),
]


def clone_repo(repo_url: str, dest_dir: str) -> bool:
    """Clone a git repository to the destination directory."""
    try:
        subprocess.run(
            ["git", "clone", "--bare", repo_url, dest_dir],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error cloning {repo_url}: {e.stderr}")
        return False


def find_commits_for_tickets(repo_dir: str, ticket_ids: list[str]) -> set[str]:
    """Find all unique commit SHAs that reference any of the ticket IDs."""
    commits = set()
    for ticket_id in ticket_ids:
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--format=%H", f"--grep={ticket_id}"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            for sha in result.stdout.strip().split("\n"):
                if sha:
                    commits.add(sha)
        except subprocess.CalledProcessError:
            pass
    return commits


def analyze_commit(
    repo_dir: str, sha: str, code_extensions: tuple[str, ...]
) -> tuple[int, int]:
    """
    Analyze a commit and return (lines_added, lines_removed) for code files only.
    """
    try:
        result = subprocess.run(
            ["git", "show", "--numstat", "--format=", sha],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return 0, 0

    lines_added = 0
    lines_removed = 0

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue

        added, removed, filepath = parts

        # Skip binary files (shown as "-")
        if added == "-" or removed == "-":
            continue

        # Check if this is a code file we care about
        if not filepath.endswith(code_extensions):
            continue

        lines_added += int(added)
        lines_removed += int(removed)

    return lines_added, lines_removed


def analyze_driver(driver: Driver, temp_dir: str) -> dict:
    """Analyze all UTF-related commits for a driver."""
    repo_dir = os.path.join(temp_dir, driver.name.replace(" ", "_").replace("#", "sharp"))

    print(f"\nAnalyzing {driver.name}...")
    print(f"  Cloning {driver.repo_url}...")

    if not clone_repo(driver.repo_url, repo_dir):
        return {
            "driver": driver.name,
            "repo": driver.repo_url,
            "num_commits": 0,
            "lines_added": 0,
            "lines_removed": 0,
            "net_change": 0,
            "error": "Failed to clone repository",
        }

    print(f"  Searching for commits matching {len(driver.ticket_ids)} ticket IDs...")
    commits = find_commits_for_tickets(repo_dir, driver.ticket_ids)
    print(f"  Found {len(commits)} unique commits")

    total_added = 0
    total_removed = 0

    for sha in commits:
        added, removed = analyze_commit(repo_dir, sha, driver.code_extensions)
        total_added += added
        total_removed += removed

    net_change = total_added - total_removed

    print(f"  Code changes: +{total_added} -{total_removed} (net: {net_change:+d})")

    return {
        "driver": driver.name,
        "repo": driver.repo_url,
        "num_commits": len(commits),
        "lines_added": total_added,
        "lines_removed": total_removed,
        "net_change": net_change,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze UTF migration code changes across MongoDB drivers"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="utf_driver_code_changes.csv",
        help="Output CSV file path (default: utf_driver_code_changes.csv)",
    )
    parser.add_argument(
        "--keep-repos",
        action="store_true",
        help="Keep cloned repositories after analysis (for debugging)",
    )
    parser.add_argument(
        "--temp-dir",
        help="Use a specific temp directory instead of creating one",
    )
    args = parser.parse_args()

    # Create temp directory
    if args.temp_dir:
        temp_dir = args.temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        cleanup = False
    else:
        temp_dir = tempfile.mkdtemp(prefix="utf_analysis_")
        cleanup = not args.keep_repos

    print(f"Using temp directory: {temp_dir}")

    results = []
    try:
        for driver in DRIVERS:
            result = analyze_driver(driver, temp_dir)
            results.append(result)
    finally:
        if cleanup:
            print(f"\nCleaning up temp directory...")
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"\nRepositories kept in: {temp_dir}")

    # Write results to CSV
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    fieldnames = [
        "driver",
        "repo",
        "num_commits",
        "lines_added",
        "lines_removed",
        "net_change",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults written to: {output_path}")

    # Print summary table
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Driver':<20} {'Commits':>10} {'Added':>12} {'Removed':>12} {'Net':>12}")
    print("-" * 80)

    total_commits = 0
    total_added = 0
    total_removed = 0

    for r in results:
        print(
            f"{r['driver']:<20} {r['num_commits']:>10} {r['lines_added']:>12} "
            f"{r['lines_removed']:>12} {r['net_change']:>+12}"
        )
        total_commits += r["num_commits"]
        total_added += r["lines_added"]
        total_removed += r["lines_removed"]

    print("-" * 80)
    total_net = total_added - total_removed
    print(
        f"{'TOTAL':<20} {total_commits:>10} {total_added:>12} "
        f"{total_removed:>12} {total_net:>+12}"
    )


if __name__ == "__main__":
    main()
