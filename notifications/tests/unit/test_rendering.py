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


# --- subastae templates ------------------------------------------------------
# One template per email the auctions app sends today over SMTP; the producers
# migrate by enqueueing these template names with the variables asserted here.


def test_subastae_verify_email_renders_link_in_button_and_fallback() -> None:
    url = "https://subastae.com/verificar?token=t1"

    html = render_template("subastae", "verify_email", {"verify_url": url})

    assert "Verifica tu email" in html
    assert html.count(url) == 2  # CTA link plus copy-paste fallback
    assert "puedes ignorar este mensaje" in html


def test_subastae_password_reset_renders_link_expiry_and_security_note() -> None:
    url = "https://subastae.com/restablecer?token=t2"

    html = render_template("subastae", "password_reset", {"reset_url": url, "expiry_minutes": 30})

    assert "Restablecer contraseña" in html
    assert html.count(url) == 2  # CTA link plus copy-paste fallback
    assert "30 minutos" in html
    assert "nunca te pedirá tu contraseña" in html


def test_subastae_google_login_hint_refers_to_the_reset_request() -> None:
    html = render_template(
        "subastae", "google_login_hint", {"login_url": "https://subastae.com/login"}
    )

    assert "Tu cuenta usa Google" in html
    assert 'href="https://subastae.com/login"' in html
    # Sent by the password-reset path for Google-only accounts: the copy must
    # name the reset request (no login attempt happened) and stay neutral.
    assert "restablecer tu contraseña" in html
    assert "Si no fuiste tú" in html
    assert "iniciar sesión" not in html


def test_subastae_registration_attempt_links_to_login() -> None:
    html = render_template(
        "subastae", "registration_attempt", {"login_url": "https://subastae.com/login"}
    )

    assert "Intento de registro" in html
    assert 'href="https://subastae.com/login"' in html


def _digest_card(**overrides: object) -> dict[str, object]:
    card: dict[str, object] = {
        "tag_label": "Nueva Subasta",
        "description": "Piso de 90 m² en el centro",
        "price": "120.000 €",
        "discount_pct": 35,
        "location": "Valencia, Valencia",
        "asset_type": "Vivienda",
        "origin": "BOE",
        "url": "https://subastae.com/subasta/A1/L1",
    }
    card.update(overrides)
    return card


def test_subastae_alert_digest_renders_sections_cards_and_unsubscribe() -> None:
    data = {
        "hero_title": "Nuevas oportunidades",
        "hero_subtitle": "Tus alertas han encontrado 2 subastas.",
        "sections": [
            {"title": "Tus alertas", "cards": [_digest_card()]},
            {
                "title": "Tus favoritos",
                "cards": [
                    _digest_card(
                        tag_label="Bajada de Precio",
                        discount_pct=0,
                        url="https://subastae.com/subasta/A2/L1",
                    )
                ],
            },
        ],
        "unsubscribe_url": "https://subastae.com/baja?token=t3",
    }

    html = render_template("subastae", "alert_digest", data)

    assert "Nuevas oportunidades" in html
    assert "Tus alertas" in html
    assert "Tus favoritos" in html
    assert html.count("Ver detalle") == 2
    assert html.count("-35%") == 1  # only the discounted card shows a discount
    assert 'href="https://subastae.com/baja?token=t3"' in html


def test_subastae_alert_digest_omits_unsubscribe_for_favorites_only_digest() -> None:
    data = {
        "hero_title": "Novedades en tus favoritos",
        "hero_subtitle": "Un lote que sigues ha cambiado.",
        "sections": [{"title": "Tus favoritos", "cards": [_digest_card()]}],
        "unsubscribe_url": "",
    }

    html = render_template("subastae", "alert_digest", data)

    assert "Cancelar estas alertas" not in html
    assert 'href=""' not in html


def test_subastae_weekly_report_renders_download_link_and_availability() -> None:
    data = {
        "hero_title": "Tu Excel semanal está listo",
        "hero_copy": "Hemos preparado el informe global de subastas activas para esta semana.",
        "download_url": "https://subastae.com/descargas/r1.xlsx",
        "available_until_date": "12 de enero",
        "account_url": "https://subastae.com/cuenta",
    }

    html = render_template("subastae", "weekly_report", data)

    assert "Tu Excel semanal está listo" in html
    assert 'href="https://subastae.com/descargas/r1.xlsx"' in html
    assert "Descargar Excel" in html
    assert "12 de enero" in html
    assert 'href="https://subastae.com/cuenta"' in html


def test_subastae_weekly_report_hides_download_when_no_report() -> None:
    data = {
        "hero_title": "Sin subastas activas esta semana",
        "hero_copy": "Esta semana no hemos encontrado subastas activas en el informe global.",
        "download_url": "",
        "available_until_date": "",
        "account_url": "https://subastae.com/cuenta",
    }

    html = render_template("subastae", "weekly_report", data)

    assert "Sin subastas activas esta semana" in html
    assert "Descargar Excel" not in html
    assert "Disponible hasta" not in html


def test_subastae_announcement_renders_paragraphs_and_cta() -> None:
    data = {
        "title": "Nuevo Excel semanal de subastas",
        "paragraphs": [
            "Hemos creado un informe semanal en Excel con las subastas activas.",
            "Ya puedes gestionar el Excel semanal desde tu cuenta.",
        ],
        "cta_label": "Activar Excel semanal",
        "cta_url": "https://subastae.com/cuenta",
    }

    html = render_template("subastae", "announcement", data)

    assert "Nuevo Excel semanal de subastas" in html
    for paragraph in data["paragraphs"]:
        assert paragraph in html
    assert 'href="https://subastae.com/cuenta"' in html
    assert "Activar Excel semanal" in html


def test_subastae_announcement_omits_cta_when_url_is_empty() -> None:
    data = {
        "title": "Aviso",
        "paragraphs": ["Solo texto."],
        "cta_label": "",
        "cta_url": "",
    }

    html = render_template("subastae", "announcement", data)

    assert "Aviso" in html
    assert "<a " not in html
