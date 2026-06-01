# Notification Engine

A multi-tenant, serverless engine that renders templated emails and delivers them
on behalf of several distinct sending products. It consumes delivery requests off a
queue, renders the requested template with per-request data, and sends via Amazon SES.

All sending products are operated by the same owner (the operator's own private
projects), not external customers — so isolation between **Tenants** is logical, not a
security boundary, and there is no self-service or per-customer management surface.

## Language

**Tenant**:
A distinct sending product that owns its own templates, its own SES configuration set
(so bounce/complaint metrics stay separated), a default sender identity, and the set of
sending domains it is permitted to send from.
_Avoid_: app, app_id, site, "web application", tenant_apps

**Sender identity**:
The `from_address` an email is sent as. Resolved per request: the payload may supply one,
otherwise the **Tenant**'s default is used. Either way it must belong to that **Tenant**'s
permitted sending domains.

**Delivery request**:
A single queued message asking the engine to render one **Template** for one recipient and
send it. Carries the `tenant`, `template_name`, recipient, subject, optional sender
overrides, and the `template_data` used to render.
_Avoid_: job, event, notification (the message), payload

**Template**:
A named HTML document owned by a **Tenant**, rendered with a **Delivery request**'s
`template_data` to produce the email body.
_Avoid_: email body, layout

**Environment**:
A deployment of the whole engine (e.g. `prod`, `staging`). Not part of a Tenant's
identity — every Environment carries the same set of Tenants.
_Avoid_: encoding env into a Tenant id (e.g. `acme-prod`)

## Relationships

- The engine serves one or more **Tenants**
- A **Tenant** is identified by a stable slug (e.g. `acme`), carried on the wire as the
  `tenant` field — the same slug across every **Environment**
- A **Tenant** maps to exactly one SES configuration set per **Environment**
- A **Tenant** declares the sending domains it owns; the engine **rejects** any request whose
  **Sender identity** falls outside them (no cross-Tenant spoofing)
- The Tenant set and per-Tenant config live in one in-repo registry, read by **both** the
  infrastructure (creates the config sets) and the runtime handler (resolves them)
- Before a **Tenant** can send, each of its sending domains must be verified in SES (DKIM
  records added at Cloudflare DNS) and the AWS account must hold SES production access — a
  one-time manual prerequisite, walked through by a guided setup script
- A **Delivery request** names exactly one **Tenant** and one **Template**; the engine
  renders the **Template** with the request's data and sends it as the resolved
  **Sender identity**

## Example dialogue

> **Dev:** "The folders were named `tenant-a-prod`. Is `prod` part of the tenant?"
> **Domain expert:** "No — a **Tenant** is `acme`. `prod` is an **Environment**; we deploy
> the engine once per Environment and the same Tenants exist in each."

## Flagged ambiguities

- The source spec used `app_id`, "tenant", `tenant_apps`, "site", and "web application"
  for one concept — resolved to **Tenant**; wire field renamed `app_id` → `tenant`.
- Tenant folders embedded the environment (`tenant-a-prod`) — resolved: **Environment**
  is a deployment dimension, never part of the Tenant id.
