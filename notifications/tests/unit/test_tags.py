from notifications.tags import standard_tags, tenant_tags


def test_standard_tags_returns_the_required_tag_set() -> None:
    assert standard_tags("staging") == {
        "app": "notification-engine",
        "environment": "staging",
        "managed-by": "email-delivery-manager",
    }


def test_standard_tags_threads_the_environment_through() -> None:
    assert standard_tags("prod")["environment"] == "prod"


def test_standard_tags_returns_a_fresh_mapping_each_call() -> None:
    first = standard_tags("test")
    first["app"] = "mutated"

    assert standard_tags("test")["app"] == "notification-engine"


def test_tenant_tags_extends_the_standard_set_with_the_tenant() -> None:
    assert tenant_tags("staging", "subastae") == {
        **standard_tags("staging"),
        "tenant": "subastae",
    }


def test_tenant_tags_threads_environment_and_slug_through() -> None:
    tags = tenant_tags("prod", "acme")

    assert tags["environment"] == "prod"
    assert tags["tenant"] == "acme"
