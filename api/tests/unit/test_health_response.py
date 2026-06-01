from shared.models import ServiceStatus

from app.api.health import build_health_response


def test_build_health_response_uses_shared_status_model() -> None:
    response = build_health_response()

    assert response.status is ServiceStatus.OK
    assert response.service.name == "api"
