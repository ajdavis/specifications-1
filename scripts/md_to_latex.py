#!/usr/bin/env python3
"""
Convert Markdown to LaTeX in a basic, straightforward way.
Uses mistune for parsing Markdown.
"""

import argparse
import re
import mistune


class LaTeXRenderer(mistune.HTMLRenderer):
    """Custom renderer that outputs LaTeX instead of HTML."""

    def __init__(self, min_heading_level=1):
        super().__init__()
        # The minimum heading level found in the document
        # This will be mapped to \section{}
        self.min_heading_level = min_heading_level

    def text(self, text):
        # Escape LaTeX special characters
        return escape_latex(text)

    def emphasis(self, text):
        return f"\\textit{{{text}}}"

    def strong(self, text):
        return f"\\textbf{{{text}}}"

    def link(self, text, url, title=None):
        if url.startswith("#"):
            # Internal link - just use the text
            return text
        return f"\\href{{{escape_latex_url(url)}}}{{{text}}}"

    def image(self, text, url, title=None):
        return f"\\includegraphics{{{url}}}"

    def codespan(self, text):
        # Use \texttt for inline code, escape underscores specially
        escaped = text.replace("\\", "\\textbackslash{}")
        escaped = escaped.replace("_", "\\_")
        escaped = escaped.replace("{", "\\{")
        escaped = escaped.replace("}", "\\}")
        escaped = escaped.replace("$", "\\$")
        escaped = escaped.replace("%", "\\%")
        escaped = escaped.replace("&", "\\&")
        escaped = escaped.replace("#", "\\#")
        return f"\\texttt{{{escaped}}}"

    def paragraph(self, text):
        return f"{text}\n\n"

    def heading(self, text, level, **attrs):
        # Map heading levels: min_heading_level -> section, etc.
        adjusted_level = level - self.min_heading_level
        if adjusted_level == 0:
            return f"\\section{{{text}}}\n\n"
        elif adjusted_level == 1:
            return f"\\subsection{{{text}}}\n\n"
        elif adjusted_level == 2:
            return f"\\subsubsection{{{text}}}\n\n"
        elif adjusted_level == 3:
            return f"\\paragraph{{{text}}}\n\n"
        else:
            return f"\\subparagraph{{{text}}}\n\n"

    def block_code(self, code, info=None):
        lang = info or ""
        # Use verbatim for simple code blocks
        return f"\\begin{{verbatim}}\n{code}\\end{{verbatim}}\n\n"

    def block_quote(self, text):
        return f"\\begin{{quote}}\n{text}\\end{{quote}}\n\n"

    def list(self, text, ordered, **attrs):
        env = "enumerate" if ordered else "itemize"
        return f"\\begin{{{env}}}\n{text}\\end{{{env}}}\n\n"

    def list_item(self, text, **attrs):
        return f"\\item {text.strip()}\n"

    def thematic_break(self):
        return "\\hrulefill\n\n"

    def linebreak(self):
        return "\\\\\n"

    def table(self, text):
        # Count columns from the header row
        # This is a simplified approach
        return f"\\begin{{tabular}}{{|l|l|l|}}\n\\hline\n{text}\\hline\n\\end{{tabular}}\n\n"

    def table_head(self, text):
        return f"{text}\\hline\n"

    def table_body(self, text):
        return text

    def table_row(self, text):
        # Remove trailing ' & ' and add line break
        text = text.rstrip(" & ")
        return f"{text} \\\\\n"

    def table_cell(self, text, is_head=False, **attrs):
        if is_head:
            return f"\\textbf{{{text}}} & "
        return f"{text} & "


def escape_latex(text):
    """Escape LaTeX special characters in text."""
    # Order matters - backslash first
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("$", "\\$"),
        ("%", "\\%"),
        ("&", "\\&"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("^", "\\^{}"),
        ("~", "\\~{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    # Convert Unicode curly quotes to LaTeX quotes
    # U+201C LEFT DOUBLE QUOTATION MARK -> ``
    # U+201D RIGHT DOUBLE QUOTATION MARK -> ''
    # U+2018 LEFT SINGLE QUOTATION MARK -> `
    # U+2019 RIGHT SINGLE QUOTATION MARK -> '
    text = text.replace("\u201c", "``")  # "
    text = text.replace("\u201d", "''")  # "
    text = text.replace("\u2018", "`")   # '
    text = text.replace("\u2019", "'")   # '

    # Convert straight double quotes to LaTeX curly quotes
    # Alternate between opening (``) and closing ('')
    result = []
    in_quote = False
    for char in text:
        if char == '"':
            if in_quote:
                result.append("''")
            else:
                result.append("``")
            in_quote = not in_quote
        else:
            result.append(char)
    text = "".join(result)

    return text


def escape_latex_url(url):
    """Escape URLs for LaTeX href."""
    # URLs need special handling - mainly escape % and #
    url = url.replace("%", "\\%")
    url = url.replace("#", "\\#")
    url = url.replace("_", "\\_")
    return url


def find_min_heading_level(markdown_text):
    """Find the minimum heading level used in the document."""
    heading_pattern = re.compile(r"^(#{1,6})\s", re.MULTILINE)
    matches = heading_pattern.findall(markdown_text)
    if matches:
        return min(len(h) for h in matches)
    return 1


def convert_markdown_to_latex(markdown_text):
    """Convert Markdown text to LaTeX."""
    # Find minimum heading level to map to \section
    min_level = find_min_heading_level(markdown_text)

    # Create renderer and parser
    renderer = LaTeXRenderer(min_heading_level=min_level)
    md = mistune.create_markdown(renderer=renderer)

    # Parse and render
    latex_body = md(markdown_text)

    return latex_body


def create_latex_document(body, title=None):
    """Wrap LaTeX body in a complete document."""
    preamble = r"""\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage{hyperref}
\usepackage{graphicx}

"""
    if title:
        preamble += f"\\title{{{escape_latex(title)}}}\n"
        preamble += "\\date{}\n"

    document = preamble
    document += "\\begin{document}\n\n"

    if title:
        document += "\\maketitle\n\n"

    document += body
    document += "\\end{document}\n"

    return document


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown to LaTeX"
    )
    parser.add_argument(
        "input",
        help="Input Markdown file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output LaTeX file (default: stdout)"
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Create a standalone LaTeX document with preamble"
    )
    parser.add_argument(
        "--title",
        help="Document title (for standalone mode)"
    )

    args = parser.parse_args()

    # Read input file
    with open(args.input, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    # Convert to LaTeX
    latex_body = convert_markdown_to_latex(markdown_text)

    # Optionally wrap in document
    if args.standalone:
        latex_output = create_latex_document(latex_body, title=args.title)
    else:
        latex_output = latex_body

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(latex_output)
        print(f"Written to {args.output}")
    else:
        print(latex_output)


if __name__ == "__main__":
    main()
