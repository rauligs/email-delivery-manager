from shared.models import ServiceStatus

from background.config import Settings
from background.worker.jobs import run_worker_job


def test_worker_job_returns_shared_service_record() -> None:
    settings = Settings(environment="test")

    result = run_worker_job(settings=settings)

    assert result.name == "worker"
    assert result.status is ServiceStatus.OK
    assert result.detail == "worker job completed in test"
