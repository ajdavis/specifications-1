# Scripts for use with Drivers specifications repository

## migrate_to_md

Use this file to automate the process of converting a specification from rst to GitHub Flavored Markdown.

The goal of the script is to do most of the work, including updating relative links to the new document from other
files. Note that all known features will translate, including explicit cross-reference markers (e.g. `.. _foo`) which
are translated to a `<div id="foo">`. It will also create a new changelog entry with today's date marking the
conversion.

### Prerequisites

```bash
brew install pandoc
brew install pre-commit
brew install python # or get python through your preferred channel
pre-commit install
```

### Usage

- Run the script as:

```bash
python3 scripts/migrate_to_md.py "source/<path_to_rst_file>"
```

- Address any errors that were printed during the run.

- Ensure that the generated markdown file is properly formatted.

- Ensure that the links in the new file are working, by running `pre-commit run markdown-link-check` and addressing
    failures until that passes.

- Remove the rst file using `git rm`.

- Create a PR. When you commit the changes, the `mdformat` `pre-commit` hook will update the formatting as appropriate.

## generate_index

Use this file to generate the top level Markdown index file. It is independent to be used as a pre-commit hook.

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
