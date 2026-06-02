"""Render a tenant's HTML template with a delivery request's ``template_data``.

Templates live under ``src/notifications/templates/<tenant>/<name>.html`` and are
packaged with the Lambda, so at runtime they are read from the deployed code's
filesystem rather than fetched over the network. Autoescaping is on: rendered
values come from request payloads and must not be trusted as markup.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES_ROOT = Path(__file__).parent / "templates"


@lru_cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_ROOT)),
        autoescape=select_autoescape(("html",)),
        undefined=StrictUndefined,
    )


def render_template(tenant: str, template_name: str, template_data: dict[str, Any]) -> str:
    """Render ``<tenant>/<template_name>.html`` with ``template_data`` to HTML.

    Raises ``jinja2.TemplateNotFound`` when the tenant or template is unknown and
    ``jinja2.UndefinedError`` when the template references missing data.
    """
    template = _environment().get_template(f"{tenant}/{template_name}.html")
    return template.render(**template_data)
