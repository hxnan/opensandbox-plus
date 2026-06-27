# opensandbox-plus

OpenSandbox Plus is a managed control plane for OpenSandbox. MVP shape:

- one self-developed `opensandbox-plus` service;
- FastAPI backend with OpenSandbox-compatible APIs and `/api/v1` management APIs;
- React/Vite Console built into the same service image;
- PostgreSQL, Redis, Casdoor, and OpenSandbox wired through docker-compose.

## Repository Layout

```text
server/    FastAPI app, SQLAlchemy models, Alembic migrations
console/   React/Vite Console
deploy/    Dockerfile, docker-compose, environment example
docs/      technical plan and MVP API/DDL contract
```

## MVP Delivery

The local MVP delivery and acceptance record is in `docs/MVP交付验收记录.md`.
It captures the simplified two-role model, docker-compose deployment path,
demo accounts, verification commands, passed checks, current boundaries, and
future upgrade direction.

The commit/PR preparation note is in `docs/MVP提交说明.md`.

The enterprise production-readiness roadmap is in `docs/企业级生产就绪演进路线.md`.

The next-stage implementation log is in `docs/下一阶段实施记录.md`.

## Local Skeleton Checks

```powershell
python -m compileall server\opensandbox_plus
cd server
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .
cd ..\console
npm run build
```

The Docker Compose entrypoint is:

```powershell
docker compose -f deploy\docker-compose.yml up --build
```

Local verification:

```powershell
# Only validate docker-compose syntax
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -ConfigOnly

# Start the stack and verify local endpoints; -Migrate also runs an explicit Alembic check
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -Start -Migrate

# Optional: run the Agent key -> OpenSandbox-compatible API -> admin disable flow
# with the local Casdoor seed users.
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -RunBusinessFlow -UseDemoTokens

# Or pass real JWTs explicitly.
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -RunBusinessFlow `
  -AgentBearerToken "<agent-jwt>" `
  -AdminBearerToken "<admin-jwt>"
```

The verification checks compose config, optional migrations, `/health`, Console static assets,
Casdoor discovery/JWKS, the `admin/osb-console` application, and OpenSandbox internal health from the
`opensandbox-plus` container.

The `opensandbox-plus` container waits for PostgreSQL and runs Alembic on startup by default.
Set `OSB_PLUS_RUN_MIGRATIONS=false` to disable startup migrations.

## Console OIDC

The Console uses Casdoor OIDC Authorization Code + PKCE. For local Vite dev, start from
`console/.env.example`; for docker-compose builds, the same values are passed as Docker build args.

Default local values:

- `VITE_CASDOOR_AUTHORITY=http://localhost:8000`
- `VITE_CASDOOR_CLIENT_ID=osb-console`
- `VITE_CASDOOR_REDIRECT_URI=http://localhost:5173/` for Vite dev, `http://localhost:8080/` for compose

The Console now uses Casdoor OIDC as the management-plane login path. Personal cloud sandbox
keys are issued from the credential page and are used for OpenSandbox-compatible API access.

## Production Configuration Baseline

`OSB_PLUS_DEPLOYMENT_ENV` defaults to `development` for the local docker-compose stack. When it is
set to `production`, startup configuration validation rejects weak local defaults:

- `OSB_PLUS_PUBLIC_BASE_URL` and `OSB_PLUS_CASDOOR_ISSUER` must use `https://`.
- `OSB_PLUS_CREDENTIAL_SECRET_PEPPER` must be replaced with a strong random secret.
- `OSB_PLUS_OPENSANDBOX_INTERNAL_API_KEY` must be replaced with a strong internal key.
- `OSB_PLUS_CASDOOR_ADMIN_CLIENT_SECRET`, when configured, must not use a weak default.

Casdoor local setup is documented in `deploy/casdoor/README.md`. The docker-compose stack mounts
`deploy/casdoor/init_data.json` into Casdoor, seeding the `osb-console` application plus
`agent-demo` and `admin-demo` local users. After the stack is running, check the setup with:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\casdoor\check-casdoor.ps1
```
