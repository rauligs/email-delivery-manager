from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ServiceStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class ServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    status: ServiceStatus = ServiceStatus.OK
    detail: str | None = None
