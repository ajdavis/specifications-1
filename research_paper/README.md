# Data for our research paper about the Unified Test Format

## count_utf_lines

Count lines of YAML in Unified Test Format (UTF) files across the git history and generate a chart showing corpus growth over time.

UTF files are identified by regex, looking for the `schemaVersion` field which is required and unique to UTF files. This avoids YAML parsing errors on older files with non-standard syntax.

### Prerequisites

```bash
pip install -r scripts/requirements.txt
```

### Usage

```bash
python3 scripts/count_utf_lines.py --output scripts/utf_growth.csv
```

This will:
1. Analyze git history, sampling one commit per ISO week
2. Identify UTF files by detecting `schemaVersion` field via regex
3. Count lines (non-comment, non-empty) for each UTF file
4. Save results to the CSV file (incrementally - skips already-processed commits)
5. Generate a PDF chart at `scripts/count_utf_lines.pdf`

## md_to_latex.py

Markdown to LaTeX converter.
