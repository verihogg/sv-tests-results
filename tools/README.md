# VerihoggFormat unsupported-constructs report

`sv_tests_unsupported_report.py` reads an sv-tests report for `VerihoggFormat`
and generates a standalone HTML page listing unsupported constructs, their
causes, affected tests, and fix-priority estimates.

The script uses only the Python standard library. It does not modify
`report.csv`, logs, tests, or any other input data.

## Requirements

- Python 3.9 or newer.
- An sv-tests report produced with `VerihoggFormat` results.
- No third-party Python packages.

## What the script needs

The script is a post-processor for an sv-tests report, not for raw runner logs.
It needs the report metadata that maps tests to their logs and test pages.

| Input | Required | Purpose |
|---|---|---|
| `results/verihoggformat/*.config.js` | Yes | Test metadata and paths to logs and test pages. |
| `VerihoggFormat` warning logs | Yes, for cause analysis | Plain logs in `logs/...` or HTML logs in `report/logs/...`. |
| `report.csv` | No | Adds status, tags, and group. Without it, status comes from `config.js` and tags from the config file names. |
| `tests/*.html` | No | Used only for `test` links. Analysis still works without them, but the links will be broken. |

This means:

- an sv-tests report directory such as `out/report` or `verihogg-format/` with
  `VerihoggFormat` results contains everything needed;
- raw `out/logs` alone is not enough: there is no `config.js` to map tests to
  logs;
- `report.csv` and `config.js` without logs produce an HTML page, but warning
  tests remain unparsed and no causes are listed;
- `report.csv` alone is not enough.

## Quick start

Run from the `sv-tests-results` repository root:

```sh
python3 tools/sv_tests_unsupported_report.py --report verihogg-format
```

This writes:

```text
verihogg-format/unsupported.html
```

The report prints a one-line summary with the total test count, number of
unique causes, and number of warning tests.

## Warning constructs table

For a user-facing table with only warning constructs and links to example test
code, run the separate generator:

```sh
python3 tools/sv_tests_warning_constructs.py --report verihogg-format
```

This writes `verihogg-format/constructs.html`. The page contains one row per
warning construct and links each row to a test source page. The detailed
report links to this page, and this page links back to `unsupported.html`.

The script accepts `--report`, `--output`, and `--quiet` with the same meaning
as the detailed report generator. It reads the same report inputs and does not
modify them.

## Choosing the report directory

`--report` accepts any of these layouts:

- an sv-tests run directory, such as `../sv-tests/out`;
- the `report/` subdirectory of a run, such as `../sv-tests/out/report`;
- a published report directory, such as `verihogg-format`;
- a `tests_reports/<name>` directory.

The script looks for `results/verihoggformat` in the given path and, if needed,
in `<path>/report`. The directory containing `results/verihoggformat` is the
report root.

Examples:

```sh
# Published verihogg-format report
python3 tools/sv_tests_unsupported_report.py --report verihogg-format

# Local sv-tests run
python3 tools/sv_tests_unsupported_report.py --report ../sv-tests/out

# Explicit output path
python3 tools/sv_tests_unsupported_report.py \
  --report verihogg-format \
  --output verihogg-format/unsupported.html

# Include failed tests in Solo/Greedy and show more greedy rows
python3 tools/sv_tests_unsupported_report.py \
  --report verihogg-format \
  --include-failed \
  --top 50
```

## Options

```text
--report PATH       Report directory (required).
--output PATH       Output HTML path. Default: <report-root>/unsupported.html.
--include-failed    Include failed tests in Solo/Greedy calculations.
--top N             Number of rows in the greedy table. Default: 25.
                    Use 0 to show all rows.
--quiet             Do not print the summary line.
```

By default, only warning tests are used for `Solo` and `Greedy`. The `Tests`
column still counts every test that contains the cause.

## Input layout

A typical report root looks like this:

```text
<report-root>/
  results/
    verihoggformat/
      *.config.js       # required; test metadata and log paths
  report.csv            # optional; adds status, tags, and group
  logs/                 # plain logs and/or HTML logs
  tests/                # HTML test pages used for links
```

For `tests_reports/<name>`, plain logs are often in `<name>/logs`, while HTML
logs are in `<name>/report/logs`. The script resolves log paths inside the
report root first and falls back to plain logs outside it. If the log path in
`config.js` starts with `logs/`, that prefix is removed while searching.

Only `VerihoggFormat` entries are analyzed. Results for other tools are ignored.

## Reuse and scope

- The script can be reused for any `VerihoggFormat` report with the layout
  above. Point `--report` at the new run and regenerate; there are no hard-coded
  absolute paths.
- A published report directory such as `verihogg-format/` can be used directly
  as input. It already contains `report.csv`, `results/verihoggformat/`, logs,
  and test pages.
- Both old and new log formats are supported (see below).
- The generated HTML is a static snapshot. Regenerate it for each run instead
  of copying an old HTML file: if moved next to another report's `logs/` and
  `tests/`, its relative links point to that report's files while the numbers
  still describe the original run.
- Other tools are not supported as-is. The script currently hard-codes
  `VerihoggFormat`, `results/verihoggformat`, and Verihogg-specific cause
  classification. Reusing it for another tool would require a `--tool` option
  and tool-specific parsing and classification.

## Output and publishing

The generated HTML is self-contained: CSS and JavaScript are embedded, and the
relative links to `logs/...` and `tests/...` are computed from the output file
location.

For links to work after publishing, keep `unsupported.html` in the same
directory as `logs/` and `tests/`, and keep `constructs.html` next to
`unsupported.html` so the cross-links between the two pages keep working. For
example, publishing the `verihogg-format/` directory as-is keeps the report,
the constructs page, and all log/test links working. If the HTML is moved
somewhere else, relative links may point outside the published tree or stop
working.

The page includes:

- summary cards;
- a breakdown by test suite;
- a greedy fix-priority table;
- a sortable table of all causes;
- a searchable table of tests with unsupported constructs.

The separate `constructs.html` page is a compact table with only warning
constructs and links to example test code.

## How the numbers work

- `Occurrences`: total number of times a cause appears in the logs.
- `Tests`: number of distinct tests that contain the cause at least once.
- `Solo`: number of warning tests where this cause is the only parsed cause.
  A test with both `end` and `real` counts toward `Tests` for both causes, but
  toward `Solo` for neither.
- `Greedy #`: an ordering, not a count. At each step, the script picks the cause
  that would close the most still-open warning tests if it were the only
  remaining blocker, removes those tests, and repeats.
- `Cumulative`: how many tests would be clean after fixing causes 1 through N.
- `Newly clean`: simulated coverage for a single step, not a guarantee.

Fixing one cause may leave other warnings or expose a new warning. The logs
describe current formatter output, not the result of a future patch.

## Supported log formats

The parser understands both formats produced by sv-tests:

- old per-warning lines, for example:
  `Warning in ...: <message>; original text preserved [code]`;
- the newer grouped summary, marked by
  `The formatter does not support these constructs yet`.

Warnings that cannot be parsed are still counted as unparsed and are noted in
the report.

## Development checks

```sh
python3 -m py_compile tools/sv_tests_unsupported_report.py
python3 -m py_compile tools/sv_tests_warning_constructs.py
```

If `ruff` is installed:

```sh
ruff check tools/sv_tests_unsupported_report.py tools/sv_tests_warning_constructs.py
ruff format --check tools/sv_tests_unsupported_report.py tools/sv_tests_warning_constructs.py
```

## Troubleshooting

- `No results/verihoggformat directory found`:
  pass the directory that contains `results/verihoggformat`, or its parent
  `report/` directory.
- Broken log/test links after publishing:
  keep `unsupported.html` next to the published `logs/` and `tests/` folders.
- Empty or missing causes for some tests:
  check that the corresponding log files exist and use one of the supported
  formats.
