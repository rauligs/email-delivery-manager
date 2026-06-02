import pytest
from jinja2 import TemplateNotFound, UndefinedError

from notifications.rendering import render_template


def test_welcome_renders_supplied_values() -> None:
    html = render_template("acme", "welcome", {"name": "Ada", "product": "Acme Mail"})

    assert "Welcome, Ada!" in html
    assert "Acme Mail" in html


def test_weekly_report_renders_a_row_per_item_in_the_loop() -> None:
    rows = [
        {"label": "Sent", "value": 1200},
        {"label": "Opened", "value": 640},
        {"label": "Bounced", "value": 3},
    ]

    html = render_template("acme", "weekly_report", {"name": "Ada", "rows": rows})

    assert html.count("<tr>") == len(rows) + 1  # one header row plus one per item
    for row in rows:
        assert row["label"] in html
        assert str(row["value"]) in html


def test_values_are_html_escaped() -> None:
    html = render_template("acme", "welcome", {"name": "<b>x</b>", "product": "P&Q"})

    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "P&amp;Q" in html


def test_unknown_template_raises() -> None:
    with pytest.raises(TemplateNotFound):
        render_template("acme", "does_not_exist", {})


def test_missing_template_data_raises() -> None:
    with pytest.raises(UndefinedError):
        render_template("acme", "welcome", {"name": "Ada"})
