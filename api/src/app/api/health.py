from fastapi import APIRouter
from pydantic import BaseModel
from shared.models import ServiceRecord, ServiceStatus

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: ServiceStatus
    service: ServiceRecord


def build_health_response() -> HealthResponse:
    service = ServiceRecord(name="api", status=ServiceStatus.OK)
    return HealthResponse(status=service.status, service=service)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return build_health_response()
