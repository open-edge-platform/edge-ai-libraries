# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point for the VIPPET performance benchmark suite.

Usage (from the project root)::

    PYTHONPATH=vippet/tests/performance python -m perf_helpers.cli [FLAGS] [-- PYTEST_ARGS]

Effective configuration precedence (later wins)::

    built-in defaults -> YAML (--config / PERF_CONFIG) -> env vars -> CLI flags

A normal run writes the fully resolved config to a private temp file,
exports it through ``PERF_CONFIG_FILE`` and runs ``python -m pytest -m perf``
in a subprocess. ``--dry-run`` prints the resolved matrix with exclusion
reasons and exits without submitting any job.
"""

import argparse
import httpx
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from .matrix import Matrix, MatrixFilters
from .preflight import FATAL_PREFLIGHT_EXIT_CODE, PreflightError, wait_for_vippet_ready
from .reporters import (
    ReportInputError,
    generate_html_report,
    load_result,
    resolve_result_json,
)
from .settings import (
    ENV_CONFIG_FILE,
    PERF_DIR,
    SPECS,
    ResolvedSettings,
    SettingSpec,
    SettingsError,
    resolve_settings,
)

FUNCTIONAL_DIR: Path = PERF_DIR.parent / "functional"

EXIT_OK = 0
EXIT_USAGE = 2
LATEST_LINK_NAME = "latest"


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #


def _argparse_type(spec: SettingSpec) -> Callable[[str], Any]:
    def convert(text: str) -> Any:
        try:
            return spec.coerce(text)
        except SettingsError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    convert.__name__ = spec.kind  # shown by argparse in error messages
    return convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m perf_helpers.cli",
        description=(
            "Run the VIPPET performance benchmark. Precedence: defaults -> "
            "YAML -> env vars -> CLI flags. Arguments after '--' are passed "
            "to pytest unchanged."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="NAME_OR_PATH",
        help=(
            "Config preset name in config/ (default, quick, full) or a YAML "
            "path. Defaults to $PERF_CONFIG_FILE, then $PERF_CONFIG, then "
            "'default'."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved matrix and exclusions, then exit 0 without running jobs.",
    )
    mode.add_argument(
        "--report-only",
        nargs="*",
        metavar="PATH",
        default=None,
        # None means the flag is absent; [] means "use latest".
        help=(
            "Rebuild the HTML report from result JSON (file, run directory "
            "or 'latest' symlink); several paths render as several runs. "
            "Defaults to <results-dir>/latest. Does not contact ViPPET."
        ),
    )
    parser.add_argument(
        "--report-output",
        metavar="PATH",
        default=None,
        help="HTML output path for --report-only.",
    )

    group = parser.add_argument_group("settings (override YAML and env)")
    for spec in SPECS:
        env_note = f" [env: {spec.env}]" if spec.env else ""
        help_text = f"{spec.help} (YAML: {spec.key}){env_note}"
        if spec.kind == "bool":
            group.add_argument(
                spec.flag,
                dest=spec.dest,
                action="store_const",
                const=True,
                default=None,
                help=help_text,
            )
            assert spec.negative_flag, spec.key
            group.add_argument(
                spec.negative_flag,
                dest=spec.dest,
                action="store_const",
                const=False,
                help=f"Set {spec.key} to false.",
            )
        else:
            group.add_argument(
                spec.flag,
                dest=spec.dest,
                type=_argparse_type(spec),
                default=None,
                metavar=spec.metavar,
                choices=spec.choices if spec.kind == "choice" else None,
                help=help_text,
            )
    return parser


def split_passthrough(argv: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split ``argv`` at the first ``--`` into (cli_args, pytest_args)."""
    args = list(argv)
    if "--" in args:
        index = args.index("--")
        return args[:index], args[index + 1 :]
    return args, []


def cli_overrides(namespace: argparse.Namespace) -> dict[str, Any]:
    return {
        spec.key: getattr(namespace, spec.dest)
        for spec in SPECS
        if getattr(namespace, spec.dest) is not None
    }


# --------------------------------------------------------------------------- #
# Environment handed to pytest / helpers
# --------------------------------------------------------------------------- #


def settings_env(settings: ResolvedSettings) -> dict[str, str]:
    """Env vars that make downstream consumers see the resolved values.

    Every exported variable is declared as ``env=`` on its spec, so values a
    user already exported are part of the resolution (env layer) and direct
    ``pytest`` runs see exactly the same values as CLI runs.
    """
    return {spec.env: str(settings[spec.key]) for spec in SPECS if spec.env}


def _ensure_import_paths() -> None:
    for path in (PERF_DIR, FUNCTIONAL_DIR):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


# --------------------------------------------------------------------------- #
# --dry-run
# --------------------------------------------------------------------------- #


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [list(map(str, headers))] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(headers))]
    lines = []
    for n, row in enumerate(cells):
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        if n == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def format_settings(settings: ResolvedSettings) -> str:
    rows = [
        (spec.key, _render(settings[spec.key]), settings.sources[spec.key])
        for spec in SPECS
    ]
    return f"Config file: {settings.config_path}\n" + _table(
        ("setting", "value", "source"), rows
    )


def _render(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(map(str, value)) if value else "(none)"
    return str(value)


def format_matrix(matrix: Matrix) -> str:
    """Render the dry-run report: matrix, exclusions and run-time skips."""
    out: list[str] = []
    families = ", ".join(matrix.available_families) or "(none)"
    out.append(f"Host device families: {families}")
    streams = ", ".join(map(str, matrix.stream_counts))

    rows = matrix.rows()
    will_run = [
        (case.pipeline_id, case.device_family, s, case.case_id + f"_x{s}")
        for case, s in rows
        if case.pipeline_id not in matrix.missing_models
    ]
    out.append("")
    out.append(
        f"Matrix: {len(will_run)} run(s) = pipeline x variant x streams [{streams}]"
    )
    out.append(
        _table(("pipeline", "variant", "streams", "test id"), will_run)
        if will_run
        else "  (empty)"
    )

    out.append("")
    out.append(f"Excluded: {len(matrix.excluded)} pipeline/variant(s)")
    out.append(
        _table(
            ("pipeline", "variant", "reason", "detail"),
            [
                (
                    e.pipeline_id or e.pipeline_name or "?",
                    e.variant,
                    e.reason.value,
                    e.detail,
                )
                for e in matrix.excluded
            ],
        )
        if matrix.excluded
        else "  (none)"
    )

    skipped = [
        (
            case.pipeline_id,
            case.device_family,
            s,
            ", ".join(matrix.missing_models[case.pipeline_id]),
        )
        for case, s in rows
        if case.pipeline_id in matrix.missing_models
    ]
    out.append("")
    out.append(f"Skipped at run time: missing_models: {len(skipped)} run(s)")
    out.append(
        _table(("pipeline", "variant", "streams", "missing models"), skipped)
        if skipped
        else "  (none)"
    )
    return "\n".join(out)


def _default_discover(settings: ResolvedSettings) -> Matrix:
    # helpers.config reads VIPPET_BASE_URL at import time; export first.
    os.environ.update(settings_env(settings))
    _ensure_import_paths()
    from .discovery import discover_matrix

    return discover_matrix(MatrixFilters.from_settings(settings))


def _default_preflight(
    base_url: str,
    readiness_timeout_seconds: float,
    poll_interval: float,
    request_timeout: float,
    *,
    report: Callable[[str], None] = print,
) -> None:
    """Open an HTTP client and run the real ViPPET readiness check."""
    with httpx.Client(headers={"Accept": "application/json"}) as client:
        wait_for_vippet_ready(
            base_url,
            readiness_timeout_seconds,
            poll_interval,
            request_timeout,
            client=client,
            report=report,
        )


def run_dry_run(
    settings: ResolvedSettings,
    *,
    discover: Callable[[ResolvedSettings], Matrix] = _default_discover,
    preflight: Callable[..., None] = _default_preflight,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Print settings and the resolved matrix. Never submits a job."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    print(format_settings(settings), file=stdout)
    print("", file=stdout)
    try:
        preflight(
            settings["vippet.base_url"],
            settings["vippet.readiness_timeout_seconds"],
            settings["vippet.poll_interval"],
            settings["vippet.timeout"],
            report=lambda line: print(line, file=stderr),
        )
        matrix = discover(settings)
    except PreflightError as exc:
        print(f"error: {exc}", file=stderr)
        return FATAL_PREFLIGHT_EXIT_CODE
    except Exception as exc:  # report any discovery failure, never crash
        print(
            f"error: pipeline discovery failed: {type(exc).__name__}: {exc}",
            file=stderr,
        )
        return FATAL_PREFLIGHT_EXIT_CODE
    print(format_matrix(matrix), file=stdout)
    return EXIT_OK


# --------------------------------------------------------------------------- #
# --report-only
# --------------------------------------------------------------------------- #


def _report_output_path(
    runs: list[dict[str, Any]],
    paths: list[Path],
    output: str | None,
    results_dir: Path,
) -> Path:
    if output is not None:
        return Path(output).expanduser()
    if len(runs) == 1:
        return paths[0].parent / f"{runs[0]['benchmark_id']}.html"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return results_dir / f"report_{timestamp}.html"


def run_report_only(
    settings: ResolvedSettings,
    inputs: Sequence[str],
    output: str | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Rebuild the HTML report from saved result JSON. Never contacts ViPPET."""
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    results_dir = Path(settings["results.output_dir"])
    using_default = not inputs
    targets = list(inputs) or [str(results_dir / LATEST_LINK_NAME)]

    try:
        paths: list[Path] = []
        for target in targets:
            resolved = resolve_result_json(target)
            if resolved not in paths:
                paths.append(resolved)
        runs = [load_result(p) for p in paths]
        html = generate_html_report(runs)
    except ReportInputError as exc:
        message = str(exc)
        if using_default and message.startswith("result path not found"):
            message += (
                f"; no benchmark results in {results_dir} yet. Run a "
                "benchmark first (e.g. `make test-performance` or "
                "`python -m perf_helpers.cli`), or rebuild from a specific "
                "run with --report-only PATH."
            )
        print(f"error: {message}", file=stderr)
        return EXIT_USAGE
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        print(
            f"error: cannot render report: {type(exc).__name__}: {exc}",
            file=stderr,
        )
        return EXIT_USAGE

    html_path = _report_output_path(runs, paths, output, results_dir)
    try:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write report {html_path}: {exc}", file=stderr)
        return EXIT_USAGE

    print(f"HTML report: {html_path}", file=stdout)
    return EXIT_OK


# --------------------------------------------------------------------------- #
# pytest run
# --------------------------------------------------------------------------- #


def build_pytest_command(pytest_args: Sequence[str]) -> list[str]:
    """Build the command line to run pytest with the performance marker and the PERF_DIR."""
    command = [sys.executable, "-m", "pytest", "-m", "perf", str(PERF_DIR)]
    command.extend(pytest_args)
    return command


def run_pytest(
    settings: ResolvedSettings,
    pytest_args: Sequence[str],
    *,
    base_env: Mapping[str, str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> int:
    env = dict(os.environ if base_env is None else base_env)
    env.update(settings_env(settings))

    fd, config_file = tempfile.mkstemp(prefix="vippet-perf-", suffix=".yaml")
    try:
        # mkstemp creates the file with 0600 permissions.
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(settings.to_yaml())
        env[ENV_CONFIG_FILE] = config_file
        completed = runner(build_pytest_command(pytest_args), env=env, check=False)
        return int(completed.returncode)
    finally:
        Path(config_file).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    cli_args, pytest_args = split_passthrough(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    namespace = parser.parse_args(cli_args)

    if namespace.report_output is not None and namespace.report_only is None:
        parser.error("--report-output requires --report-only")

    try:
        settings = resolve_settings(
            config=namespace.config,
            env=os.environ,
            cli_overrides=cli_overrides(namespace),
        )
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if namespace.dry_run:
        return run_dry_run(settings)
    if namespace.report_only is not None:
        return run_report_only(settings, namespace.report_only, namespace.report_output)
    return run_pytest(settings, pytest_args)


if __name__ == "__main__":
    sys.exit(main())
