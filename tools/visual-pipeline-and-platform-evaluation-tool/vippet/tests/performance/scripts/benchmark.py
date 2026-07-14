#!/usr/bin/env python3
"""
VIPPET Benchmark Suite - Main Entry Point

Automated benchmarking of VIPPET pipelines across CPU/GPU/NPU devices.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from orchestrator import BenchmarkOrchestrator  # type: ignore[import-not-found]
from reporters import ResultExporter  # type: ignore[import-not-found]


def setup_logging(verbose: bool = False, quiet: bool = False):
    """
    Configure logging.

    Args:
        verbose: Enable verbose (DEBUG) logging
        quiet: Suppress all but ERROR logs
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)]
    )


def load_config(config_path: Path) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config


def merge_cli_args(config: dict, args: argparse.Namespace) -> dict:
    """
    Merge CLI arguments into configuration.

    Args:
        config: Base configuration
        args: Parsed CLI arguments

    Returns:
        Updated configuration
    """
    # Override VIPPET URL
    if args.vippet_url:
        config["vippet"]["base_url"] = args.vippet_url

    # Override output directory
    if args.output:
        config["results"]["output_dir"] = args.output

    # Override pipelines filter
    if args.pipelines:
        if args.pipelines == "*":
            config["benchmark"]["pipelines"] = "*"
        else:
            config["benchmark"]["pipelines"] = args.pipelines.split(",")

    # Override variants filter
    if args.variants:
        config["benchmark"]["variants"] = args.variants.split(",")

    # Override stream counts
    if args.streams:
        config["benchmark"]["stream_counts"] = [int(s) for s in args.streams.split(",")]

    # Quick mode
    if args.quick:
        config["benchmark"]["stream_counts"] = [1, 3]
        config["benchmark"]["variants"] = ["cpu", "gpu"]

    # Full mode
    if args.full:
        config["benchmark"]["stream_counts"] = [1, 3, 5, 10]
        config["benchmark"]["variants"] = ["cpu", "gpu", "npu", "gpu_npu"]

    return config


def create_symlink_latest(output_dir: Path, benchmark_dir: Path):
    """
    Create 'latest' symlink pointing to current results.

    Args:
        output_dir: Parent output directory
        benchmark_dir: Current benchmark results directory
    """
    latest_link = output_dir / "latest"

    # Remove existing symlink if present
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()

    # Create new symlink
    latest_link.symlink_to(benchmark_dir.name)
    logging.info(f"\n✓ Created symlink: {latest_link} -> {benchmark_dir.name}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="VIPPET Benchmark Suite - Automated pipeline benchmarking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick benchmark (fast, reduced coverage)
  %(prog)s --config config/quick.yaml

  # Full benchmark (comprehensive)
  %(prog)s --config config/full.yaml

  # CPU only
  %(prog)s --variants cpu

  # Specific pipelines
  %(prog)s --pipelines "license-plate-recognition,object-detection"

  # Custom VIPPET URL
  %(prog)s --vippet-url http://192.168.1.100:7860/api/v1

  # Dry run (show test matrix without running)
  %(prog)s --dry-run
        """,
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent.parent / "config" / "default.yaml",
        help="Configuration file (default: config/default.yaml)",
    )

    parser.add_argument(
        "--vippet-url", type=str, help="VIPPET API base URL (overrides config)"
    )

    parser.add_argument(
        "--output", type=Path, help="Output directory for results (overrides config)"
    )

    parser.add_argument(
        "--pipelines",
        type=str,
        help='Pipeline filter: "*" for all, or comma-separated list (overrides config)',
    )

    parser.add_argument(
        "--variants",
        type=str,
        help='Variant filter: comma-separated list (e.g., "cpu,gpu,npu") (overrides config)',
    )

    parser.add_argument(
        "--streams",
        type=str,
        help='Stream counts: comma-separated list (e.g., "1,3,5") (overrides config)',
    )

    parser.add_argument(
        "--quick", action="store_true", help="Quick mode: fewer streams, CPU+GPU only"
    )

    parser.add_argument(
        "--full", action="store_true", help="Full mode: all streams, all variants"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show test matrix without running benchmarks",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output (DEBUG level)"
    )

    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Quiet output (errors only)"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        # Load and merge configuration
        logging.info("=" * 70)
        logging.info("VIPPET BENCHMARK SUITE")
        logging.info("=" * 70)
        logging.info(f"\nLoading configuration: {args.config}")
        config = load_config(args.config)
        config = merge_cli_args(config, args)

        # Create orchestrator
        orchestrator = BenchmarkOrchestrator(config)

        if args.dry_run:
            # Dry run: discover and show test matrix
            logging.info("\n🔍 DRY RUN MODE - No benchmarks will be executed")

            hardware = orchestrator.discover_hardware()
            missing_models = orchestrator.check_model_installation()
            test_cases = orchestrator.generate_test_matrix(hardware, missing_models)

            logging.info(f"\n{'=' * 70}")
            logging.info("DRY RUN COMPLETE")
            logging.info(f"{'=' * 70}")
            logging.info(f"\nTest matrix would execute {len(test_cases)} test case(s)")
            logging.info("\nTo run these tests, remove the --dry-run flag")

            orchestrator.close()
            return 0

        # Run benchmark
        result = orchestrator.run_benchmark()
        orchestrator.close()

        # Determine output directory
        output_dir = Path(config["results"]["output_dir"])
        benchmark_id = result.benchmark_id

        # Create timestamped subdirectory
        benchmark_dir = output_dir / benchmark_id
        benchmark_dir.mkdir(parents=True, exist_ok=True)

        # Export results
        formats = config["results"]["formats"]
        exporter = ResultExporter(benchmark_dir, formats)
        exporter.export(result.to_dict())

        # Generate HTML report
        json_path = benchmark_dir / f"{benchmark_id}.json"
        html_path = benchmark_dir / f"{benchmark_id}.html"
        try:
            import importlib.util

            report_script = Path(__file__).parent / "generate_report.py"
            spec = importlib.util.spec_from_file_location(
                "generate_report", report_script
            )
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            runs = mod.load_results([json_path])
            html_path.write_text(mod.generate_html(runs))
            logging.info(f"  ✓ HTML report saved: {html_path}")
        except Exception as e:
            logging.warning(f"  ⚠ HTML report skipped: {e}")

        # Create 'latest' symlink
        if config["results"].get("create_latest_link", True):
            create_symlink_latest(output_dir, benchmark_dir)

        # Final summary
        logging.info(f"\n{'=' * 70}")
        logging.info("BENCHMARK COMPLETE ✓")
        logging.info(f"{'=' * 70}")
        logging.info(f"\nResults directory: {benchmark_dir}")
        logging.info(f"HTML report:       {html_path}")

        # Exit with error if any tests failed
        if result.summary["failed"] > 0:
            logging.warning(f"\n⚠️  {result.summary['failed']} test(s) failed")
            return 1

        return 0

    except KeyboardInterrupt:
        logging.error("\n\n⚠️  Interrupted by user")
        return 130

    except Exception as e:
        logging.error(f"\n❌ ERROR: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
