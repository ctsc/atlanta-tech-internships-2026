"""CLI entry point for the Atlanta Tech Internships pipeline.

Supports running the full pipeline or individual stages:
    python main.py --full             # Run complete pipeline (default)
    python main.py --discover-only    # Discovery only
    python main.py --readme-only      # Regenerate README only
    python main.py --check-links-only # Link checking only
"""

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger("internship_pipeline")


def _setup_logging() -> None:
    """Configure root logging to INFO with a timestamped format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _run_step(name: str, func: object, is_async: bool = False) -> bool:
    """Execute a single pipeline step with error isolation.

    Args:
        name: Human-readable step name for logging.
        func: Callable to execute (sync or async).
        is_async: Whether func is an async coroutine function.

    Returns:
        True if the step succeeded, False otherwise.
    """
    logger.info("Starting step: %s", name)
    try:
        if is_async:
            asyncio.run(func())
        else:
            func()
        logger.info("Completed step: %s", name)
        return True
    except Exception:
        logger.exception("Step failed: %s", name)
        return False


def run_full_pipeline() -> None:
    """Run the complete pipeline: discover -> validate -> deduplicate -> check_links -> archive -> readme."""
    from scripts.archive_stale import archive_stale
    from scripts.check_links import check_all_links
    from scripts.deduplicate import deduplicate_all
    from scripts.discover import discover_all
    from scripts.generate_readme import generate_readme
    from scripts.validate import validate_all

    steps: list[tuple[str, object, bool]] = [
        ("Discover new listings", discover_all, True),
        ("Validate & enrich with AI", validate_all, False),
        ("Deduplicate listings", deduplicate_all, False),
        ("Check link health", check_all_links, True),
        ("Archive stale listings", archive_stale, False),
        ("Generate README", generate_readme, False),
    ]

    succeeded = 0
    failed = 0
    for name, func, is_async in steps:
        if _run_step(name, func, is_async):
            succeeded += 1
        else:
            failed += 1

    logger.info(
        "Pipeline complete: %d/%d steps succeeded, %d failed",
        succeeded,
        succeeded + failed,
        failed,
    )
    if failed > 0:
        logger.warning("Some pipeline steps failed — check logs above for details")


def run_discover_only() -> None:
    """Run only the discovery step."""
    from scripts.discover import discover_all

    _run_step("Discover new listings", discover_all, is_async=True)


def run_readme_only() -> None:
    """Run only the README generation step."""
    from scripts.generate_readme import generate_readme

    _run_step("Generate README", generate_readme, is_async=False)


def run_check_links_only() -> None:
    """Run only the link health check step."""
    from scripts.check_links import check_all_links

    _run_step("Check link health", check_all_links, is_async=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace with the selected mode.
    """
    parser = argparse.ArgumentParser(
        description="Atlanta Tech Internships — automated pipeline",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--full",
        action="store_true",
        help="Run the complete pipeline (default)",
    )
    group.add_argument(
        "--discover-only",
        action="store_true",
        help="Run only the discovery step",
    )
    group.add_argument(
        "--readme-only",
        action="store_true",
        help="Regenerate README.md from current data",
    )
    group.add_argument(
        "--check-links-only",
        action="store_true",
        help="Run only the link health checker",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point that dispatches to the selected pipeline mode.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).
    """
    _setup_logging()
    args = parse_args(argv)

    if args.discover_only:
        run_discover_only()
    elif args.readme_only:
        run_readme_only()
    elif args.check_links_only:
        run_check_links_only()
    else:
        # Default to full pipeline (covers --full and no args)
        run_full_pipeline()


if __name__ == "__main__":
    main()
