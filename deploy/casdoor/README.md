# Casdoor local bootstrap

This directory keeps the local Casdoor setup contract for OpenSandbox Plus.

Casdoor supports startup data import through `init_data.json`; official docs say the file is loaded automatically when it exists at the instance root, and Docker can mount it at `/init_data.json`. The local docker-compose stack mounts `deploy/casdoor/init_data.json` there so a fresh stack gets the `osb-console` OIDC application, demo users, and OpenSandbox Plus roles without hand-editing the admin UI.

The local stack also mounts `deploy/casdoor/app.conf`. Casdoor reuses the compose PostgreSQL service and stores its own tables with the `casdoor_` prefix in the `opensandbox_plus` database.

The login UI is configured to use `http://localhost:8080/casdoor-static` for logo,
favicon, manifest, and language flag assets. This keeps the local sign-in page usable
in restricted networks without reaching `cdn.casbin.org` or `cdn.casdoor.com`.

Official references:

- Data initialization: https://casdoor.ai/docs/deployment/data-initialization/
- Public API: https://casdoor.ai/docs/basic/public-api/
- Core concepts: https://casdoor.ai/docs/basic/core-concepts/

## Local endpoints

| Item | Value |
| --- | --- |
| Casdoor URL | `http://localhost:8000` |
| Console URL | `http://localhost:8080` |
| Vite dev URL | `http://localhost:5173` |
| Organization | `built-in` |
| Console application ID | `admin/osb-console` |
| Console client ID | `osb-console` |
| Backend expected audience | `osb-console` |

Casdoor default demo admin is commonly `built-in/admin` with password `123`. Change it for any non-local environment.

## Seed Data

The local seed file creates or updates the demo organization/users under `built-in` and the Console application as `admin/osb-console`:

| Object | Value |
| --- | --- |
| Application | `admin/osb-console` |
| Agent user | `agent-demo` / `123456` |
| Platform admin | `admin-demo` / `123456` |
| Agent role | `osb_agent_user` |
| Admin role | `osb_platform_admin` |

The demo users expose roles both through Casdoor role membership and through `tag` / `properties.osb_roles`, matching the backend role extraction logic used by OpenSandbox Plus.

`password` grant is enabled only in the local seed file so automated verification can obtain demo tokens without browser interaction. Do not enable it for the production Console application; production users should use Authorization Code + PKCE.

## Application

The seed data creates an application named `osb-console` owned by `admin` and bound to the `built-in` organization. If you configure Casdoor manually, use the same settings.

Required settings:

| Setting | Value |
| --- | --- |
| Client ID | `osb-console` |
| Client type | Public / SPA |
| Token format | JWT |
| Grant types | `authorization_code`, `refresh_token`; local seed also enables `password` for `verify-local.ps1 -UseDemoTokens` |
| PKCE | S256 enabled |
| Redirect URIs | `http://localhost:8080/`, `http://localhost:5173/` |
| Post logout redirect URIs | `http://localhost:8080/`, `http://localhost:5173/` |
| Token fields | include `roles`, `groups`, `properties`, `tag` when available |

The backend accepts OpenSandbox Plus roles from any of these token claims:

- `roles`
- `role`
- `groups`
- `permissions`
- `properties.osb_roles`
- `properties.roles`
- `tag`

## Roles

Create these role names or make sure they appear in token claims:

| Role | Meaning |
| --- | --- |
| `osb_agent_user` | Can issue personal cloud sandbox credentials and use cloud sandbox APIs |
| `osb_platform_admin` | Can access platform administration APIs |

Useful local users from the seed data:

| User | Roles |
| --- | --- |
| `agent-demo` | `osb_agent_user` |
| `admin-demo` | `osb_agent_user`, `osb_platform_admin` |

## Check

After Casdoor is running and the application is configured:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\casdoor\check-casdoor.ps1
```

The script verifies discovery, JWKS, and tries to read the `admin/osb-console` application plus demo users through Casdoor's public API.
