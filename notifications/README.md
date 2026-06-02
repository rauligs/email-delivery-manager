# Notifications

Serverless notification engine (render, send, deploy). Python module routed to
the `python` skill. See [`../TENANT-ONBOARDING.md`](../TENANT-ONBOARDING.md) for
tenant setup.

```sh
uv sync
uv run notifications
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Configuration

`src/notifications/config.py` is the single reader of environment variables:

| Variable           | Default        | Notes                                    |
| ------------------ | -------------- | ---------------------------------------- |
| `ENVIRONMENT`      | (required)     | Deployment target, e.g. `staging`/`prod` |
| `AWS_REGION`       | `eu-central-1` | Deployment region                        |
| `AWS_PROFILE`      | (unset)        | Optional named profile for local SSO     |
| `DELIVERY_DLQ_URL` | (unset)        | SQS DLQ URL injected by the stack         |

Optional `.env` support is for local CLI use only and must hold non-secret
operator config. `.env` is gitignored.
