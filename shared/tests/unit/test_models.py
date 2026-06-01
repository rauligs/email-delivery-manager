from shared.models import ServiceRecord, ServiceStatus


def test_service_record_defaults_to_ok() -> None:
    record = ServiceRecord(name="api")

    assert record.status is ServiceStatus.OK
    assert record.model_dump() == {
        "name": "api",
        "status": ServiceStatus.OK,
        "detail": None,
    }
