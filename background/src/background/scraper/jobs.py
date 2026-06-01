from shared.models import ServiceRecord, ServiceStatus

from background.config import Settings


def normalize_title(title: str) -> str:
    return " ".join(title.split())


def run_scraper_job(*, settings: Settings, title: str) -> ServiceRecord:
    return ServiceRecord(
        name="scraper",
        status=ServiceStatus.OK,
        detail=f"scraped {normalize_title(title)!r} in {settings.environment}",
    )
