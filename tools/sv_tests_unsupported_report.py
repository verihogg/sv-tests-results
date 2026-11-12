#!/usr/bin/env python3
"""Build an HTML report of unsupported constructs from sv-tests results.

Only VerihoggFormat results are analysed. The script accepts any report
directory produced by sv-tests (a run directory, its report/ subdirectory, or
a tests_reports/<name> directory) and understands both the old per-warning log
format and the new grouped-summary format.
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TOOL = "VerihoggFormat"

STATUS_BY_CODE = {
    0: "failed",
    1: "passed",
    2: "warning",
    3: "negative-pass",
    4: "unverified",
}

STATUS_LABEL = {
    "passed": "passed",
    "warning": "warning",
    "failed": "failed",
    "unverified": "unverified",
    "negative-pass": "negative-pass",
    "unknown": "unknown",
}

STATUS_ORDER = {
    "warning": 0,
    "failed": 1,
    "passed": 2,
    "negative-pass": 3,
    "unverified": 4,
    "unknown": 5,
}

CATEGORY_LABEL = {
    "token": "Token",
    "construct": "Construct",
    "annotation": "Annotation",
    "other": "Other",
}

TOKEN_SYMBOLS = {
    "DoublePlus": "++",
    "DoubleMinus": "--",
    "PlusColon": "+:",
    "MinusColon": "-:",
    "DoubleColon": "::",
    "Dollar": "$",
    "OrKeyword": "or",
    "AndKeyword": "and",
    "XorKeyword": "xor",
    "DefaultKeyword": "default",
    "ReturnKeyword": "return",
    "AutomaticKeyword": "automatic",
    "TypeKeyword": "type",
    "InsideKeyword": "inside",
    "ExtendsKeyword": "extends",
    "VarKeyword": "var",
    "BreakKeyword": "break",
    "TimeKeyword": "time",
    "ProgramKeyword": "program",
    "EndProgramKeyword": "endprogram",
    "ExpectKeyword": "expect",
    "MinusArrow": "->",
    "OrEqualsArrow": "=>",
    "PackageKeyword": "package",
    "EndPackageKeyword": "endpackage",
    "ImportKeyword": "import",
    "ExportKeyword": "export",
    "StaticKeyword": "static",
    "InterfaceKeyword": "interface",
    "EndInterfaceKeyword": "endinterface",
    "ImplementsKeyword": "implements",
    "NewKeyword": "new",
}

ANNOTATION_LABELS = {
    "unmatched closing bracket": "Unmatched closing bracket",
    "unclosed bracket before statement end": "Unclosed bracket before statement end",
    "based literal wildcard is not supported": "Based literal wildcard is not supported",
    "conditional operator has no matching colon": "Conditional operator has no matching colon",
}

ANNOTATION_HINTS = ("bracket", "wildcard", "no matching colon")

OTHER_LABELS = {
    "macro-line-number": "Macro line number",
    "incompatible-conditional-branches": "Incompatible conditional branches",
    "invalid-annotation": "Invalid annotation",
    "unsupported-construct": "Unsupported construct",
}

CONFIG_ENTRY_RE = re.compile(r'\["([^"]*)","([^"]*)",(\d+),"([^"]*)","([^"]*)"\]')
NEW_MARKER = "The formatter does not support these constructs yet"
NEW_ENTRY_RE = re.compile(
    r"^  - (.+?)\s{2,}(\d+) occurrences?,\s+first at (.+)$", re.MULTILINE
)
OLD_WARN_RE = re.compile(
    r"^Warning in .*?: (.*?)(?:; original [a-z ]+)?"
    r" \[([a-z][a-z0-9-]*)\]\s*$",
    re.MULTILINE,
)
CONSTRUCT_RE = re.compile(r"unsupported SystemVerilog construct '([^']*)'")
TOKEN_RE = re.compile(
    r"cannot annotate SystemVerilog line \(unsupported token kind (\w+)\)"
)
ANNOT_RE = re.compile(r"cannot annotate SystemVerilog line \((.*)\)")
SCRIPT_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
TAG_RE = re.compile(r"(?s)<[^>]+>")


@dataclass
class Test:
    name: str
    code: int
    logpath: str
    testpath: str
    status: str = "unknown"
    description: str = ""
    group: str = ""
    tags: set[str] = field(default_factory=set)
    keys: Counter = field(default_factory=Counter)
    unparsed: bool = False
    logfile: Path | None = None


def die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def normalize_status(value: str | None) -> str:
    value = (value or "").strip()
    return value.removeprefix("test-")


def strip_html(text: str) -> str:
    text = SCRIPT_RE.sub("", text)
    text = TAG_RE.sub("\n", text)
    return html.unescape(text)


def detect_report_root(path: Path) -> Path:
    if not path.exists():
        die(f"Path does not exist: {path}")
    candidates = [path, path / "report"]
    for candidate in candidates:
        if (candidate / "results" / "verihoggformat").is_dir():
            return candidate.resolve()
    die(f"No results/verihoggformat directory found in {path} or {path / 'report'}")
    return path


def load_csv(root: Path) -> dict[str, dict[str, str]]:
    path = root / "report.csv"
    rows: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            name = row.get("TestName")
            if name:
                rows[name] = row
    return rows


def load_tests(root: Path) -> list[Test]:
    config_dir = root / "results" / "verihoggformat"
    tests: dict[str, Test] = {}
    for config in sorted(config_dir.glob("*.config.js")):
        tag = config.name[: -len(".config.js")]
        text = config.read_text(encoding="utf-8", errors="replace")
        for description, name, code, logpath, testpath in CONFIG_ENTRY_RE.findall(text):
            logpath = logpath.strip()
            if not logpath:
                continue
            test = tests.get(logpath)
            if test is None:
                test = Test(
                    name=name,
                    code=int(code),
                    logpath=logpath,
                    testpath=testpath,
                )
                tests[logpath] = test
            test.tags.add(tag)
            if not test.description and description:
                test.description = description

    csv_rows = load_csv(root)
    for test in tests.values():
        row = csv_rows.get(test.name)
        if row:
            test.group = (row.get("Group") or "").strip()
            test.status = normalize_status(row.get("Status")) or STATUS_BY_CODE.get(
                test.code, "unknown"
            )
            test.tags.update((row.get("Tags") or "").split())
        else:
            test.status = STATUS_BY_CODE.get(test.code, "unknown")

        text, logfile = read_log(root, test.logpath)
        if text is None:
            test.unparsed = test.status == "warning"
            continue
        test.logfile = logfile
        test.keys, test.unparsed = parse_log(text)

    return list(tests.values())


def read_log(root: Path, logpath: str) -> tuple[str | None, Path | None]:
    relative = logpath.removeprefix("logs/")
    plain_relative = relative.removesuffix(".html")
    candidates = [
        root / logpath,
        root / "logs" / (plain_relative + ".html"),
        root / "logs" / plain_relative,
        root / "report" / "logs" / (plain_relative + ".html"),
        root.parent / "logs" / plain_relative,
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if candidate.name.endswith(".html"):
            text = strip_html(text)
        return text, candidate
    return None, None


def classify_old(message: str, code: str) -> tuple[str, str]:
    match = CONSTRUCT_RE.search(message)
    if match:
        return "construct", match.group(1)
    match = TOKEN_RE.search(message)
    if match:
        return "token", match.group(1)
    match = ANNOT_RE.search(message)
    if match:
        return "annotation", match.group(1)
    return "other", code


def classify_new(key: str) -> tuple[str, str]:
    match = re.fullmatch(r"unsupported token kind (.+)", key)
    if match:
        return "token", match.group(1)
    if key in OTHER_LABELS:
        return "other", key
    if key in ANNOTATION_LABELS or any(hint in key for hint in ANNOTATION_HINTS):
        return "annotation", key
    return "construct", key


def parse_log(text: str) -> tuple[Counter, bool]:
    keys: Counter = Counter()
    if NEW_MARKER in text:
        for match in NEW_ENTRY_RE.finditer(text):
            key = match.group(1).strip()
            count = int(match.group(2))
            category, value = classify_new(key)
            keys[f"{category}:{value}"] += count
        return keys, False

    matched = False
    for match in OLD_WARN_RE.finditer(text):
        matched = True
        category, value = classify_old(match.group(1), match.group(2))
        keys[f"{category}:{value}"] += 1
    unparsed = not matched and "Warning" in text
    return keys, unparsed


def split_key(key: str) -> tuple[str, str]:
    category, _, value = key.partition(":")
    return category, value


def greedy_order(
    priority_tests: list[Test], stats: dict[str, dict]
) -> list[tuple[str, int]]:
    remaining = {
        id(test): (test, set(test.keys)) for test in priority_tests if test.keys
    }
    done: set[str] = set()
    order: list[tuple[str, int]] = []

    while remaining:
        gain: Counter = Counter()
        for _, keys in remaining.values():
            rest = keys - done
            if len(rest) == 1:
                gain[next(iter(rest))] += 1

        if gain:
            key = max(
                gain,
                key=lambda item: (
                    gain[item],
                    stats.get(item, {}).get("occ", 0),
                    item,
                ),
            )
            newly = gain[key]
        else:
            frequency: Counter = Counter()
            for _, keys in remaining.values():
                for key in keys - done:
                    frequency[key] += 1
            if not frequency:
                break
            key = max(
                frequency,
                key=lambda item: (
                    frequency[item],
                    stats.get(item, {}).get("occ", 0),
                    item,
                ),
            )
            newly = 0

        order.append((key, newly))
        done.add(key)
        remaining = {
            test_id: (test, keys)
            for test_id, (test, keys) in remaining.items()
            if not keys.issubset(done)
        }

    return order


def build_stats(tests: list[Test], include_failed: bool) -> dict:
    priority_statuses = {"warning"}
    if include_failed:
        priority_statuses.add("failed")
    priority_tests = [test for test in tests if test.status in priority_statuses]

    stats: dict[str, dict] = {}
    for test in tests:
        for key, count in test.keys.items():
            entry = stats.setdefault(key, {"occ": 0, "tests": set(), "first": None})
            entry["occ"] += count
            entry["tests"].add(test.logpath)
            current = entry["first"]
            if current is None or (
                test.status in priority_statuses
                and current.status not in priority_statuses
            ):
                entry["first"] = test

    solo: Counter = Counter()
    for test in priority_tests:
        if len(test.keys) == 1:
            solo[next(iter(test.keys))] += 1

    order = greedy_order(priority_tests, stats)
    rank: dict[str, dict] = {}
    cumulative = 0
    for position, (key, newly) in enumerate(order, start=1):
        cumulative += newly
        rank[key] = {
            "rank": position,
            "newly": newly,
            "cumulative": cumulative,
        }

    status_counts = Counter(test.status for test in tests)
    group_counts: Counter = Counter()
    group_warning: Counter = Counter()
    for test in tests:
        group = test.group or "main"
        group_counts[group] += 1
        if test.status == "warning":
            group_warning[group] += 1

    parsed_priority = sum(1 for test in priority_tests if test.keys)
    unparsed_priority = sum(1 for test in priority_tests if not test.keys)
    total_occurrences = sum(entry["occ"] for entry in stats.values())

    return {
        "tests": tests,
        "priority_tests": priority_tests,
        "stats": stats,
        "solo": solo,
        "rank": rank,
        "cumulative": cumulative,
        "status_counts": status_counts,
        "group_counts": group_counts,
        "group_warning": group_warning,
        "parsed_priority": parsed_priority,
        "unparsed_priority": unparsed_priority,
        "total_occurrences": total_occurrences,
    }


def key_label_html(key: str) -> str:
    category, value = split_key(key)
    escaped = html.escape(value)
    if category == "token":
        symbol = TOKEN_SYMBOLS.get(value)
        if symbol:
            return (
                f"<code>{html.escape(symbol)}</code> "
                f'<span class="muted">{escaped}</span>'
            )
        return f"<code>{escaped}</code>"
    return f"<code>{escaped}</code>"


def key_search_text(key: str) -> str:
    category, value = split_key(key)
    parts = [category, value]
    if category == "annotation":
        label = ANNOTATION_LABELS.get(value)
        if label:
            parts.append(label)
    elif category == "other":
        parts.append(OTHER_LABELS.get(value, value))
    elif category == "token":
        symbol = TOKEN_SYMBOLS.get(value)
        if symbol:
            parts.append(symbol)
    return " ".join(parts)


def link_href(target: Path | None, output_dir: Path) -> str:
    if target is None:
        return ""
    try:
        return os.path.relpath(target.resolve(), output_dir).replace(os.sep, "/")
    except ValueError:
        return str(target)


def status_badge(status: str) -> str:
    label = STATUS_LABEL.get(status, status)
    return (
        f'<span class="badge badge-{html.escape(status)}">{html.escape(label)}</span>'
    )


def render_cards(data: dict) -> str:
    total = len(data["tests"])
    counts = data["status_counts"]
    passed = counts.get("passed", 0)
    warning = counts.get("warning", 0)
    failed = counts.get("failed", 0)
    unverified = counts.get("unverified", 0)
    negative = counts.get("negative-pass", 0)
    causes = len(data["stats"])

    def percent(value: int) -> str:
        return f"{value / total * 100:.1f}%" if total else "0.0%"

    cards = [
        ("", str(total), "Total tests", ""),
        ("green", str(passed), "Passed", percent(passed)),
        ("yellow", str(warning), "Warning", percent(warning)),
        ("red", str(failed), "Failed", percent(failed)),
        ("gray", str(unverified), "Unverified", percent(unverified)),
        ("blue", str(negative), "Negative pass", percent(negative)),
        ("", str(data["total_occurrences"]), "Warning occurrences", ""),
        ("", str(causes), "Unique causes", ""),
    ]
    parts = ['<section class="cards">']
    for css, value, label, extra in cards:
        extra_html = f'<span class="pct">{html.escape(extra)}</span>' if extra else ""
        class_name = f"card {css}".strip()
        parts.append(
            f'<div class="{class_name}">'
            f'<div class="value">{html.escape(value)}{extra_html}</div>'
            f'<div class="label">{html.escape(label)}</div>'
            "</div>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def render_group_table(data: dict) -> str:
    if not data["group_counts"]:
        return ""
    rows = []
    for group, count in sorted(
        data["group_counts"].items(), key=lambda item: (-item[1], item[0])
    ):
        label = "main" if group == "main" else group
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(label)}</code></td>"
            f'<td class="num">{count}</td>'
            f'<td class="num">{data["group_warning"].get(group, 0)}</td>'
            "</tr>"
        )
    return (
        "<section>"
        "<h2>By test suite</h2>"
        '<p class="lead">Suite is the sv-tests <code>results_group</code>: '
        "<code>main</code> = tests from the SV Tests repository, "
        "<code>cores</code> = generated tests for third-party cores, "
        "<code>imported</code> = imported third-party test suites. "
        "Tests without a group are shown as <code>main</code>.</p>"
        '<table class="plain">'
        "<thead><tr><th>Suite</th><th>Tests</th><th>Warnings</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table></section>"
    )


def render_greedy(data: dict, top: int) -> str:
    order = sorted(data["rank"].items(), key=lambda item: item[1]["rank"])
    if top > 0:
        order = order[:top]
    total = data["parsed_priority"] or 1
    rows = []
    for key, info in order:
        category, _ = split_key(key)
        percent = info["cumulative"] / total * 100
        rows.append(
            "<tr>"
            f'<td class="num">{info["rank"]}</td>'
            f"<td>{key_label_html(key)}</td>"
            f'<td class="muted">{html.escape(CATEGORY_LABEL.get(category, category))}</td>'
            f'<td class="num">{data["stats"][key]["occ"]}</td>'
            f'<td class="num">{len(data["stats"][key]["tests"])}</td>'
            f'<td class="num">+{info["newly"]}</td>'
            '<td class="num wide">'
            f'{info["cumulative"]} <span class="muted">/ {data["parsed_priority"]}</span>'
            f'<div class="bar"><span style="width:{percent:.2f}%"></span></div>'
            "</td>"
            "</tr>"
        )
    hint = ""
    if top > 0 and len(data["rank"]) > top:
        hint = (
            f'<p class="hint">Showing the first {top} of {len(data["rank"])}. '
            "Run with <code>--top 0</code> to show all.</p>"
        )
    return (
        "<section>"
        "<h2>What to fix first</h2>"
        '<p class="lead">Causes are ordered greedily: at each step the cause '
        "that would close the most still-open warning tests is chosen. "
        "Coverage is cumulative. See "
        '<a href="#how-to-read">How to read this report</a>.</p>'
        + hint
        + '<table class="plain sortable" id="greedy-table">'
        "<thead><tr>"
        '<th class="num">#</th><th>Cause</th><th>Category</th>'
        '<th class="num">Occurrences</th><th class="num">Tests</th>'
        '<th class="num">Newly clean (sim.)</th>'
        '<th class="num">Cumulative</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
    )


def render_causes(data: dict, root: Path, output_dir: Path) -> str:
    ordered = sorted(
        data["stats"].items(),
        key=lambda item: (-item[1]["occ"], item[0]),
    )
    rows = []
    for key, entry in ordered:
        category, value = split_key(key)
        solo = data["solo"].get(key, 0)
        rank = data["rank"].get(key, {}).get("rank", "")
        first = entry["first"]
        example = ""
        if first is not None:
            log_target = first.logfile or (root / first.logpath)
            log_href = link_href(log_target, output_dir)
            test_href = (
                link_href(root / first.testpath, output_dir) if first.testpath else ""
            )
            links = []
            if log_href:
                links.append(f'<a href="{html.escape(log_href)}">log</a>')
            if test_href:
                links.append(f'<a href="{html.escape(test_href)}">test</a>')
            example = (
                f'<span class="muted">{html.escape(first.name)}</span> '
                + " · ".join(links)
            )
        search = key_search_text(key).lower()
        rows.append(
            "<tr"
            f' data-name="{html.escape(value.lower())}"'
            f' data-cat="{html.escape(category)}"'
            f' data-occ="{entry["occ"]}"'
            f' data-tests="{len(entry["tests"])}"'
            f' data-solo="{solo}"'
            f' data-rank="{rank}"'
            f' data-search="{html.escape(search)}"'
            ">"
            f"<td>{key_label_html(key)}</td>"
            f'<td class="muted">{html.escape(CATEGORY_LABEL.get(category, category))}</td>'
            f'<td class="num">{entry["occ"]}</td>'
            f'<td class="num">{len(entry["tests"])}</td>'
            f'<td class="num">{solo}</td>'
            f'<td class="num">{rank}</td>'
            f'<td class="example">{example}</td>'
            "</tr>"
        )
    return (
        "<section>"
        "<h2>All causes</h2>"
        '<div class="controls">'
        '<input id="cause-search" type="search" placeholder="Search causes...">'
        '<select id="cause-category">'
        '<option value="">All categories</option>'
        '<option value="token">Tokens</option>'
        '<option value="construct">Constructs</option>'
        '<option value="annotation">Annotations</option>'
        '<option value="other">Other</option>'
        "</select>"
        "</div>"
        '<table class="plain sortable" id="causes-table">'
        "<thead><tr>"
        '<th data-sort="name">Cause</th>'
        '<th data-sort="cat">Category</th>'
        '<th data-sort="occ" class="num sorted-desc">Occurrences</th>'
        '<th data-sort="tests" class="num">Tests</th>'
        '<th data-sort="solo" class="num">Solo</th>'
        '<th data-sort="rank" class="num">Greedy #</th>'
        "<th>Example</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        '<p class="hint">Solo and Greedy # are explained in '
        '<a href="#how-to-read">How to read this report</a>.</p>'
        "</section>"
    )


def render_tests(data: dict, root: Path, output_dir: Path) -> str:
    tests = [test for test in data["tests"] if test.keys]
    tests.sort(
        key=lambda test: (
            STATUS_ORDER.get(test.status, 99),
            test.name.lower(),
        )
    )
    rows = []
    for test in tests:
        keys = sorted(test.keys.items(), key=lambda item: (-item[1], item[0]))
        chips = " ".join(
            f'<span class="chip">{key_label_html(key)}'
            f'<span class="count">{count}</span></span>'
            for key, count in keys
        )
        log_target = test.logfile or (root / test.logpath)
        log_href = link_href(log_target, output_dir)
        test_href = link_href(root / test.testpath, output_dir) if test.testpath else ""
        links = []
        if log_href:
            links.append(f'<a href="{html.escape(log_href)}">log</a>')
        if test_href:
            links.append(f'<a href="{html.escape(test_href)}">test</a>')
        tags = " ".join(sorted(test.tags))
        search = " ".join(
            [test.name, tags] + [key_search_text(key) for key in test.keys]
        ).lower()
        rows.append(
            "<tr"
            f' data-status="{html.escape(test.status)}"'
            f' data-search="{html.escape(search)}"'
            ">"
            f"<td><code>{html.escape(test.name)}</code></td>"
            f"<td>{status_badge(test.status)}</td>"
            f'<td class="muted">{html.escape(tags)}</td>'
            f'<td class="chips"><span class="chips-inner">{chips}</span></td>'
            f'<td class="links">{" · ".join(links)}</td>'
            "</tr>"
        )
    return (
        "<section>"
        "<h2>Tests with unsupported constructs</h2>"
        '<div class="controls">'
        '<input id="test-search" type="search" '
        'placeholder="Search tests, tags, causes...">'
        "</div>"
        '<table class="plain sortable" id="tests-table">'
        "<thead><tr>"
        '<th data-sort="name">Test</th>'
        '<th data-sort="status">Status</th>'
        '<th data-sort="tags">Tags</th>'
        "<th>Causes</th>"
        "<th>Links</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        "</section>"
    )


CSS = """
:root {
  --bg: #0f172a;
  --panel: #111c34;
  --panel-2: #162240;
  --text: #e6edf7;
  --muted: #8ca0bf;
  --line: #24345a;
  --green: #3fb950;
  --yellow: #d29922;
  --red: #f85149;
  --gray: #6e7681;
  --blue: #58a6ff;
  --accent: #7c9cff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
header {
  padding: 28px 32px 20px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #131f3b, #0f172a);
}
header h1 { margin: 0 0 6px; font-size: 26px; }
header .meta { margin: 0; color: var(--muted); }
main { padding: 24px 32px 48px; max-width: 1500px; margin: 0 auto; }
section { margin: 0 0 34px; }
h2 { font-size: 18px; margin: 0 0 10px; }
.lead, .hint { color: var(--muted); margin: 0 0 12px; }
.hint { font-size: 12px; }
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 16px;
}
.card .value { font-size: 26px; font-weight: 650; }
.card .pct { font-size: 13px; color: var(--muted); margin-left: 6px; }
.card .label { color: var(--muted); font-size: 12px; margin-top: 2px; }
.card.green { border-color: #1f6b32; }
.card.green .value { color: var(--green); }
.card.yellow { border-color: #6b561a; }
.card.yellow .value { color: var(--yellow); }
.card.red { border-color: #7a2220; }
.card.red .value { color: var(--red); }
.card.gray { border-color: #3b4250; }
.card.gray .value { color: #b6bfcc; }
.card.blue { border-color: #1f4e7a; }
.card.blue .value { color: var(--blue); }
.note {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: 14px 18px;
  color: var(--muted);
}
.note strong { color: var(--text); }
.note h2 { color: var(--text); font-size: 16px; margin: 0 0 10px; }
.note p { margin: 0 0 9px; }
.note p:last-child { margin-bottom: 0; }
.defs {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin: 0 0 12px;
}
.defs div {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
}
.defs h3 { margin: 0 0 4px; font-size: 13px; color: var(--text); }
.defs p { margin: 0; font-size: 13px; }
.example-box {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 14px;
  margin: 0 0 12px;
  font-size: 13px;
}
.example-box ul { margin: 6px 0 0; padding-left: 20px; }
.example-box li { margin: 2px 0; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.controls { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.controls input, .controls select {
  background: var(--panel);
  border: 1px solid var(--line);
  color: var(--text);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
}
.controls input { min-width: 320px; }
table.plain {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}
table.plain th, table.plain td {
  padding: 9px 11px;
  border-bottom: 1px solid var(--line);
  text-align: left;
}
table.plain th { vertical-align: top; }
table.plain td { vertical-align: baseline; }
table.plain td > code,
table.plain td .badge,
table.plain td .chip { vertical-align: baseline; }
table.plain thead th {
  background: var(--panel-2);
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .03em;
  position: sticky;
  top: 0;
  z-index: 1;
}
table.plain tbody tr:hover { background: #14203c; }
table.plain tbody tr:last-child td { border-bottom: none; }
table.sortable th[data-sort] { cursor: pointer; user-select: none; }
table.sortable th[data-sort]:hover { color: var(--text); }
th.sorted-desc::after { content: " ↓"; color: var(--accent); }
th.sorted-asc::after { content: " ↑"; color: var(--accent); }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.wide { min-width: 180px; }
.muted { color: var(--muted); }
code {
  background: #0b1428;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 1px 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.bar {
  height: 7px;
  background: #0b1428;
  border: 1px solid var(--line);
  border-radius: 4px;
  margin-top: 5px;
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #2f81f7, #58a6ff);
}
.badge {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11.5px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.badge-passed { color: var(--green); border-color: #1f6b32; background: #0f2a18; }
.badge-warning { color: var(--yellow); border-color: #6b561a; background: #2a2210; }
.badge-failed { color: var(--red); border-color: #7a2220; background: #2a1212; }
.badge-unverified { color: #b6bfcc; border-color: #3b4250; background: #1a1f29; }
.badge-negative-pass { color: var(--blue); border-color: #1f4e7a; background: #0f1f33; }
.badge-unknown { color: var(--muted); border-color: var(--line); }
.chips-inner {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 5px;
  width: 100%;
  vertical-align: baseline;
}
.chip {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 1px 6px;
  font-size: 12px;
  line-height: 18px;
}
.chip .count {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.chip code { border: none; background: transparent; padding: 0; }
#tests-table th:last-child,
#tests-table td.links {
  width: 1%;
  white-space: nowrap;
  text-align: right;
}
.example { min-width: 180px; }
"""

JS = """
function applyFilters(tableId, searchId, selectId, attr) {
  const table = document.getElementById(tableId);
  const search = document.getElementById(searchId);
  const select = selectId ? document.getElementById(selectId) : null;
  if (!table || !table.tBodies.length) return;
  function apply() {
    const query = (search ? search.value : "").trim().toLowerCase();
    const value = select ? select.value : "";
    for (const row of table.tBodies[0].rows) {
      const text = (row.dataset.search || "").toLowerCase();
      const okQuery = !query || text.includes(query);
      const okValue = !value || row.dataset[attr] === value;
      row.hidden = !(okQuery && okValue);
    }
  }
  if (search) search.addEventListener("input", apply);
  if (select) select.addEventListener("change", apply);
  apply();
}

for (const table of document.querySelectorAll("table.sortable")) {
  for (const th of table.querySelectorAll("th[data-sort]")) {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      const ascending = th.dataset.dir !== "asc";
      const body = table.tBodies[0];
      const rows = [...body.rows];
      rows.sort((a, b) => {
        const av = a.dataset[key] || "";
        const bv = b.dataset[key] || "";
        const an = Number(av);
        const bn = Number(bv);
        const numeric = av !== "" && bv !== "" && !Number.isNaN(an) && !Number.isNaN(bn);
        const cmp = numeric ? an - bn : av.localeCompare(bv, "en");
        return ascending ? cmp : -cmp;
      });
      th.dataset.dir = ascending ? "asc" : "desc";
      for (const row of rows) body.appendChild(row);
      for (const other of table.querySelectorAll("th")) {
        other.classList.remove("sorted-asc", "sorted-desc");
      }
      th.classList.add(ascending ? "sorted-asc" : "sorted-desc");
    });
  }
}

applyFilters("causes-table", "cause-search", "cause-category", "cat");
applyFilters("tests-table", "test-search", null, "status");
"""


def render_how_to_read(data: dict) -> str:
    unparsed = ""
    if data["unparsed_priority"]:
        unparsed = (
            f"<p><strong>{data['unparsed_priority']}</strong> warning tests "
            "have no parsed causes (empty or non-standard log); they are "
            "excluded from greedy coverage.</p>"
        )
    return (
        '<section class="note" id="how-to-read">'
        "<h2>How to read this report</h2>"
        "<p>Only <code>VerihoggFormat</code> warnings from sv-tests logs are "
        "analyzed. Causes are grouped into tokens, constructs, annotation "
        "issues, and other codes.</p>"
        '<div class="defs">'
        "<div><h3>Occurrences</h3><p>Total number of times the cause appears "
        "in the logs.</p></div>"
        "<div><h3>Tests</h3><p>Number of distinct tests that contain the "
        "cause at least once.</p></div>"
        "<div><h3>Solo</h3><p>Warning tests where this cause is the only "
        "parsed cause. A test with <code>end</code> and <code>real</code> "
        "counts toward Tests for both, but toward Solo for neither.</p></div>"
        "<div><h3>Greedy #</h3><p>An ordering, not a count. At each step, "
        "pick the cause that would close the most still-open warning tests if "
        "it were the only remaining blocker; remove those tests and repeat. "
        "Ties are broken by occurrence count. Cumulative shows how many tests "
        "would be clean after fixing causes 1..N.</p></div>"
        "</div>"
        '<div class="example-box">'
        "<strong>Example.</strong> A has only <code>end</code>; B has "
        "<code>end</code> and <code>real</code>; C has <code>real</code> and "
        "<code>or</code>."
        "<ul>"
        "<li>Solo: <code>end=1</code>, <code>real=0</code>, "
        "<code>or=0</code>.</li>"
        "<li>Greedy: <code>end</code> (+1, A), <code>real</code> (+1, B), "
        "<code>or</code> (+1, C); cumulative 1, 2, 3.</li>"
        "</ul></div>"
        "<p><strong>Why this is a heuristic.</strong> A test can contain "
        "several unsupported constructs; fixing one may leave other warnings "
        "or expose a new warning on the same or another line. The logs "
        "describe current formatter output, not the result of a future patch. "
        "Causes such as <code>bracket</code> and <code>macro</code> are often "
        "secondary symptoms. Treat <code>Newly clean</code> as simulated "
        "coverage, not as a guarantee that the test will pass.</p>"
        + unparsed
        + "</section>"
    )


def render_page(data: dict, root: Path, output: Path, args: argparse.Namespace) -> str:
    output_dir = output.parent
    total = len(data["tests"])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>VerihoggFormat — unsupported constructs</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        "<header>"
        "<h1>VerihoggFormat: unsupported constructs</h1>"
        f'<p class="meta">{total} tests · generated {html.escape(generated)} · '
        '<a href="constructs.html">Warning constructs</a></p>'
        "</header>\n<main>\n"
        + render_cards(data)
        + "\n"
        + render_how_to_read(data)
        + "\n"
        + render_group_table(data)
        + "\n"
        + render_greedy(data, args.top)
        + "\n"
        + render_causes(data, root, output_dir)
        + "\n"
        + render_tests(data, root, output_dir)
        + "\n</main>\n"
        f"<script>{JS}</script>\n</body>\n</html>\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTML report of unsupported VerihoggFormat constructs "
        "from sv-tests results."
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
        help="output HTML path (default: <report>/unsupported.html)",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="include failed tests in Solo/Greedy",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="number of greedy rows to show (0 = all, default: 25)",
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
    output = (args.output or (root / "unsupported.html")).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    tests = load_tests(root)
    if not tests:
        die(f"No VerihoggFormat tests found in {root}")

    data = build_stats(tests, args.include_failed)
    page = render_page(data, root, output, args)
    output.write_text(page, encoding="utf-8")

    if not args.quiet:
        print(
            f"Report: {output} "
            f"({len(tests)} tests, {len(data['stats'])} causes, "
            f"{data['status_counts'].get('warning', 0)} warning tests)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
