from shared.models import ServiceStatus

from background.config import Settings
from background.scraper.jobs import normalize_title, run_scraper_job


def test_normalize_title_collapses_whitespace() -> None:
    assert normalize_title(" Example  Scraped  Page ") == "Example Scraped Page"


def test_scraper_job_returns_shared_service_record() -> None:
    settings = Settings(environment="test")

    result = run_scraper_job(settings=settings, title=" Example  Scraped  Page ")

    assert result.name == "scraper"
    assert result.status is ServiceStatus.OK
    assert result.detail == "scraped 'Example Scraped Page' in test"
