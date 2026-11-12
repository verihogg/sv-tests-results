#!/usr/bin/env python3
"""Build a simple HTML table of warning constructs and example tests."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from sv_tests_unsupported_report import (
    CSS,
    Test,
    detect_report_root,
    die,
    key_label_html,
    link_href,
    load_tests,
    split_key,
)

EXTRA_CSS = """
#constructs-table td:first-child { width: 38%; }
#constructs-table td:last-child { overflow-wrap: anywhere; }
#constructs-table td a {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}
"""


def choose_examples(tests: list[Test]) -> dict[str, Test]:
    examples: dict[str, Test] = {}
    for test in tests:
        if test.status != "warning" or not test.keys:
            continue
        for key in test.keys:
            current = examples.get(key)
            if current is None or (
                len(test.keys),
                test.name.lower(),
            ) < (
                len(current.keys),
                current.name.lower(),
            ):
                examples[key] = test
    return examples


def render_table(examples: dict[str, Test], root: Path, output_dir: Path) -> str:
    rows = []
    for key in sorted(examples, key=lambda item: (split_key(item)[1].lower(), item)):
        test = examples[key]
        if test.testpath:
            href = link_href(root / test.testpath, output_dir)
            example = f'<a href="{html.escape(href)}">{html.escape(test.name)}</a>'
        else:
            example = '<span class="muted">—</span>'
        rows.append(f"<tr><td>{key_label_html(key)}</td><td>{example}</td></tr>")
    return (
        "<section>"
        '<p class="lead">One example test for each construct that produces '
        "a warning. The link opens the test source.</p>"
        '<table class="plain" id="constructs-table">'
        "<thead><tr><th>Construct</th><th>Example code</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
        "</section>"
    )


def render_page(examples: dict[str, Test], root: Path, output: Path) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>VerihoggFormat — warning constructs</title>\n"
        f"<style>{CSS}{EXTRA_CSS}</style>\n</head>\n<body>\n"
        "<header>"
        "<h1>VerihoggFormat: warning constructs</h1>"
        f'<p class="meta">{len(examples)} constructs · '
        '<a href="unsupported.html">Full report</a></p>'
        "</header>\n<main>\n"
        + render_table(examples, root, output.parent)
        + "\n</main>\n</body>\n</html>\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTML table of VerihoggFormat warning constructs and example tests."
    )
    parser.add_argument(
        "--report",
        required=True,
        type=Path,
        help="report directory: sv-tests/out, sv-tests/out/report, or "
        "tests_reports/<name>",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output HTML path (default: <report>/constructs.html)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not print the summary line",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = detect_report_root(args.report)
    output = (args.output or (root / "constructs.html")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    tests = load_tests(root)
    if not tests:
        die(f"No VerihoggFormat tests found in {root}")

    examples = choose_examples(tests)
    if not examples:
        die(f"No warning constructs found in {root}")

    output.write_text(render_page(examples, root, output), encoding="utf-8")

    if not args.quiet:
        print(
            f"Report: {output} ({len(examples)} warning constructs)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
