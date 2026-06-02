# email-delivery-manager

This is a reference project template for a small product system with separate
application boundaries and shared Python domain code.

## Structure

- `api/` - FastAPI service
- `background/` - worker and scraper processes
  - `background/src/background/worker/` - durable worker example
  - `background/src/background/scraper/` - scraper example
- `notifications/` - serverless notification engine (render, send, deploy);
  see [`DEPLOYMENT.md`](DEPLOYMENT.md) for infra deployment and
  [`TENANT-ONBOARDING.md`](TENANT-ONBOARDING.md) for tenant setup
- `shared/` - Python resources shared by API and background, such as models
- `web/` - Next.js 16.2.6 frontend
- `e2e/` - Playwright tests for the full local ecosystem
- `scripts/verify.sh` - repo-level verification contract used by the AI workflow

## Tests

- API tests are split into `api/tests/unit/` and `api/tests/integration/`.
- Background worker tests live under `background/tests/{unit,integration}/worker/`.
- Background scraper tests live under `background/tests/{unit,integration}/scraper/`.
- Web tests live under `web/tests/unit/` and `web/tests/integration/`.
- End-to-end tests live under `e2e/tests/` and exercise web, API, and background.

Run the full scaffold verification from the repo root:

```sh
./scripts/verify.sh
```

## Run

```sh
cd api
uv sync
uv run uvicorn app.main:app --reload
```

```sh
cd background
uv sync
uv run background-worker worker
```

```sh
cd shared
uv sync
uv run pytest
```

```sh
cd web
npm install
npm run dev
```

```sh
cd e2e
npm install
npm run test
```

## Docker Compose Reference

The Compose files are intentionally split so each runtime concern is clear and
can be combined as needed:

- `docker-compose.db.yml` - Postgres 18+ database.
- `docker-compose.web-api.yml` - Traefik reverse proxy, web, and API.
- `docker-compose.background.yml` - worker and scraper processes.

Run the whole local ecosystem:

```sh
docker compose -f docker-compose.db.yml -f docker-compose.web-api.yml -f docker-compose.background.yml up --build
```

Run only web and API behind Traefik:

```sh
docker compose -f docker-compose.web-api.yml up --build
```

Traefik routes:

- Web: http://web.localhost
- API: http://api.localhost/health
- Traefik dashboard: http://localhost:8080

The database uses local development credentials in `docker-compose.db.yml`. Change
them before using the scaffold outside local development.

AI workflow commands and docs are in `AI-WORKFLOW.md`.
