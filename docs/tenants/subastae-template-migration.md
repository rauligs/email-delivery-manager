# Subastae — Per-Template Migration Instructions

How to migrate each `auctions_scraper` producer off `smtplib`/Gmail onto the delivery
queue. One section per template; each is self-contained so an agent can migrate one
producer without reading anything else. Source of truth for the contracts:
`notifications/tests/unit/test_rendering.py` (each variable below is exercised there).

## Rules that apply to every template

- **Enqueue, don't send.** Replace the SMTP build+send with one SQS `SendMessage` of the
  JSON payload to the delivery queue:
  `https://sqs.eu-central-1.amazonaws.com/679296256915/notification-engine-delivery-prod`
  (region `eu-central-1`). The producer's IAM principal needs `sqs:SendMessage` on that
  queue — nothing else.
- **Payload envelope** (all four required, non-empty):

  ```json
  {"tenant": "subastae", "template_name": "<name>", "to": "<recipient>",
   "subject": "<Spanish subject>", "template_data": { ... }}
  ```

  Optional: `from_name`, `from_address` (defaults to `hola@subastae.com`; any other
  address must be on `subastae.com` or the request is rejected).
- **Subjects live in the producer**, not the template. Keep the existing Spanish
  subject lines when migrating.
- **Every listed variable is required** (rendering is `StrictUndefined`). A missing key
  means the message is rejected to the DLQ — no retry. "Optional" blocks are disabled by
  passing `""` (strings) or `0` (numbers), never by omitting the key.
- **Pass plain strings, pre-formatted.** Values are HTML-escaped by the engine. Format
  prices/dates in the producer (`"120.000 €"`, not a float).
- **Delete the SMTP workarounds** in the migrated module: the 1/sec throttle, reconnect
  loops, and `SMTPServerDisconnected` retries exist only because of Gmail; SES + SQS
  make them dead code.
- **Do not cut over until SES production access is granted** (check
  `docs/tenants/subastae.md` checklist).

## `verify_email` — email verification

- **Producer:** `routers/auth_router.py`
- `template_data`: `verify_url` — absolute URL with the verification token.

```json
{"tenant": "subastae", "template_name": "verify_email", "to": "<user email>",
 "subject": "Verifica tu correo en Subastae",
 "template_data": {"verify_url": "https://subastae.com/verificar?token=..."}}
```

## `password_reset` — password reset link

- **Producer:** `routers/auth_router.py`
- `template_data`: `reset_url` (absolute URL), `expiry_minutes` (int).

```json
{"tenant": "subastae", "template_name": "password_reset", "to": "<user email>",
 "subject": "Restablece tu contraseña",
 "template_data": {"reset_url": "https://subastae.com/reset?token=...", "expiry_minutes": 30}}
```

## `google_login_hint` — "your account uses Google"

- **Producer:** `routers/auth_router.py` (password reset requested for a Google-login account)
- `template_data`: `login_url`.

```json
{"tenant": "subastae", "template_name": "google_login_hint", "to": "<user email>",
 "subject": "Tu cuenta usa el acceso con Google",
 "template_data": {"login_url": "https://subastae.com/login"}}
```

## `registration_attempt` — account already exists

- **Producer:** `routers/auth_router.py` (registration attempted with an existing email)
- `template_data`: `login_url`.

```json
{"tenant": "subastae", "template_name": "registration_attempt", "to": "<user email>",
 "subject": "Intento de registro en Subastae",
 "template_data": {"login_url": "https://subastae.com/login"}}
```

## `weekly_report` — weekly Excel report download

- **Producer:** `auctions/management/weekly_email_delivery.py`
- `template_data`:
  - `hero_title`, `hero_copy` — headline + intro copy.
  - `download_url` — Excel download link; **`""` hides the whole download block**
    (use for the "no report this week" case).
  - `available_until_date` — pre-formatted date string the link expires.
  - `account_url` — link to the user's account page.

```json
{"tenant": "subastae", "template_name": "weekly_report", "to": "<user email>",
 "subject": "Tu informe semanal de subastas",
 "template_data": {"hero_title": "Tu informe está listo",
   "hero_copy": "Esta semana hay 42 subastas que encajan con tus filtros.",
   "download_url": "https://subastae.com/informes/2026-07-20.xlsx",
   "available_until_date": "27 de julio de 2026",
   "account_url": "https://subastae.com/cuenta"}}
```

## `alert_digest` — alert/favorites digest

- **Producer:** `auctions/management/dispatch_alerts.py`
- `template_data`:
  - `hero_title`, `hero_subtitle` — headline + count line.
  - `sections` — list of `{"title": str, "cards": [<card>, ...]}`.
  - Each **card** (all 8 keys required): `tag_label` (e.g. `"Nueva Subasta"`,
    `"Bajada de Precio"`), `description`, `price` (pre-formatted string),
    `discount_pct` (int; **`0` hides the discount badge**), `location`, `asset_type`,
    `origin` (e.g. `"BOE"`), `url` (lot detail link).
  - `unsubscribe_url` — **`""` omits the unsubscribe footer** (favorites-only digests,
    which carry no alert-unsubscribe URL). Alert digests must pass a real URL.

```json
{"tenant": "subastae", "template_name": "alert_digest", "to": "<user email>",
 "subject": "Nuevas oportunidades en tus alertas",
 "template_data": {"hero_title": "Nuevas oportunidades",
   "hero_subtitle": "Tus alertas han encontrado 2 subastas.",
   "sections": [{"title": "Tus alertas", "cards": [
     {"tag_label": "Nueva Subasta", "description": "Piso de 90 m² en el centro",
      "price": "120.000 €", "discount_pct": 35, "location": "Valencia, Valencia",
      "asset_type": "Vivienda", "origin": "BOE",
      "url": "https://subastae.com/subasta/A1/L1"}]}],
   "unsubscribe_url": "https://subastae.com/baja?token=..."}}
```

## `announcement` — one-off announcements

- **Producer:** `auctions/management/announcements.py`
- `template_data`:
  - `title` — headline.
  - `paragraphs` — list of plain-text strings, one per paragraph.
  - `cta_label`, `cta_url` — call-to-action button; **`cta_url: ""` hides the button**
    (pass `cta_label: ""` too for consistency).

```json
{"tenant": "subastae", "template_name": "announcement", "to": "<user email>",
 "subject": "Novedades en Subastae",
 "template_data": {"title": "Nueva búsqueda por mapa",
   "paragraphs": ["Ya puedes explorar subastas sobre el mapa.", "Pruébalo en tu próxima búsqueda."],
   "cta_label": "Probar ahora", "cta_url": "https://subastae.com/mapa"}}
```

## `welcome` — new-user welcome

- **Producer:** not in the current producer table — wire it where registration completes
  if/when a welcome email is wanted.
- `template_data`: `name` — the user's display name.

```json
{"tenant": "subastae", "template_name": "welcome", "to": "<user email>",
 "subject": "¡Bienvenido a Subastae!",
 "template_data": {"name": "Raúl"}}
```

## Verifying a migrated producer

From `notifications/`, send that producer's exact payload through the live pipeline:

```sh
uv run smoke-test subastae <template> --env prod --profile default --data '<template_data JSON>' --wait
```

Exit 0 with `Confirmed delivered` proves the payload contract; then the producer's own
integration test only needs to assert the enqueued JSON, not delivery.
