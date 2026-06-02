from notifications.tags import standard_tags


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
