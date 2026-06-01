from shared.models import ServiceRecord, ServiceStatus

from background.config import Settings


def run_worker_job(*, settings: Settings) -> ServiceRecord:
    return ServiceRecord(
        name="worker",
        status=ServiceStatus.OK,
        detail=f"worker job completed in {settings.environment}",
    )
