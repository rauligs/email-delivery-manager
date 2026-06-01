import argparse

from background.config import get_settings
from background.scraper.jobs import run_scraper_job
from background.worker.jobs import run_worker_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run background jobs.")
    parser.add_argument(
        "job",
        nargs="?",
        default="worker",
        choices=["worker", "scraper"],
        help="Job to run.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()

    if args.job == "worker":
        result = run_worker_job(settings=settings)
    elif args.job == "scraper":
        result = run_scraper_job(settings=settings, title=" Example  Scraped  Page ")
    else:
        raise ValueError(f"Unsupported job: {args.job}")

    print(result.model_dump_json())
    return 0
