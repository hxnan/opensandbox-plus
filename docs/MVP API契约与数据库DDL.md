# OpenSandbox Plus MVP API 契约与数据库 DDL

本文是 `docs/技术方案.md` 的落地规格，目标是把 MVP 可直接开发的 API 契约、认证约定和 PostgreSQL DDL 固化下来。

## 1. 契约边界

OpenSandbox Plus 对外有两类 API：

| API 类型 | 路径 | 使用方 | 响应兼容要求 |
| --- | --- | --- | --- |
| OpenSandbox 原生兼容 API | `/v1/...` 和 OpenSandbox 已支持的无 `/v1` 路径 | Agent、SDK、CLI | 不包壳，尽量保持 OpenSandbox 原生请求体、响应体、状态码和错误模型 |
| OpenSandbox Plus 管理 API | `/api/v1/...` | Agent 登录态、Console、平台管理员 | 使用 OpenSandbox Plus 自有 JSON 契约 |

MVP 固化约定：

- Agent 用户登录 Agent 后，Agent 使用用户的 OIDC access token 调用凭据颁发 API。
- OpenSandbox Plus 颁发云沙箱凭据 key/token，后续 Agent 调 OpenSandbox 原生兼容 API 时只使用 `OPEN-SANDBOX-API-KEY`。
- OpenSandbox Server 的内部 `OPEN-SANDBOX-API-KEY` 只在 OpenSandbox Plus App 到 OpenSandbox Server 的出站请求中使用。
- Console 登录态使用 Casdoor OIDC Authorization Code + PKCE。
- 原生兼容 API 不引入 `Bearer` 认证，不要求 OpenSandbox SDK 修改认证方式。

## 2. 通用 HTTP 约定

### 2.1 Header

Agent 申请云沙箱凭据：

```http
Authorization: Bearer <casdoor_oidc_access_token>
Content-Type: application/json
X-Request-ID: <optional-request-id>
```

Agent 使用 OpenSandbox 原生兼容 API：

```http
OPEN-SANDBOX-API-KEY: osb_u_<public_prefix>.<secret_random>
X-Request-ID: <optional-request-id>
```

Console 调管理 API：

```http
Authorization: Bearer <casdoor_oidc_access_token>
Content-Type: application/json
X-Request-ID: <optional-request-id>
```

### 2.2 管理 API 错误格式

`/api/v1/...` 统一错误响应：

```json
{
  "code": "FORBIDDEN",
  "message": "permission denied",
  "request_id": "req_01j...",
  "details": {
    "resource": "sandbox:sbx_..."
  }
}
```

推荐错误码：

| HTTP | `code` | 说明 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 请求体、查询参数或路径参数非法 |
| 401 | `UNAUTHENTICATED` | 缺少登录态或登录态无效 |
| 401 | `INVALID_CLOUD_SANDBOX_CREDENTIAL` | 云沙箱凭据不存在、hash 不匹配或格式错误 |
| 403 | `FORBIDDEN` | 登录用户无权限访问资源 |
| 404 | `NOT_FOUND` | 资源不存在，或为避免泄漏而按不存在处理 |
| 409 | `CONFLICT` | 状态冲突，例如重复禁用、重复删除 |
| 429 | `RATE_LIMITED` | key、用户或平台级限流 |
| 500 | `INTERNAL_ERROR` | 未预期服务端错误 |
| 502 | `OPENSANDBOX_BACKEND_ERROR` | 内部 OpenSandbox backend 调用失败 |
| 503 | `NO_HEALTHY_BACKEND` | 无可用 OpenSandbox backend |

### 2.3 分页格式

管理 API 列表响应统一使用：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

MVP 页码从 1 开始，`page_size` 默认 20，最大 200。

## 3. Agent 用户 API

### 3.1 获取当前用户

```http
GET /api/v1/me
Authorization: Bearer <casdoor_oidc_access_token>
```

响应：

```json
{
  "subject_id": "casdoor:org:user_123",
  "username": "alice",
  "email": "alice@example.com",
  "display_name": "Alice",
  "roles": ["osb_agent_user"],
  "features": {
    "credential_issue": true,
    "sandbox_create": true,
    "admin_console": false
  }
}
```

处理规则：

- 校验 Casdoor JWT、issuer、audience、过期时间和签名。
- 同步或 upsert `user_identities`。
- 用户被 Casdoor 禁用或不具备 `osb_agent_user`/`osb_platform_admin` 时返回 403。

### 3.2 申请云沙箱凭据

```http
POST /api/v1/cloud-sandbox/credentials
Authorization: Bearer <casdoor_oidc_access_token>
Content-Type: application/json
```

请求：

```json
{
  "name": "agent-default-key",
  "agent_id": "agent-web",
  "expires_in_days": 180
}
```

响应：

```json
{
  "id": "cred_01j...",
  "name": "agent-default-key",
  "public_prefix": "7t3k9p",
  "key": "osb_u_7t3k9p.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "status": "active",
  "expires_at": "2026-12-21T00:00:00Z",
  "created_at": "2026-06-24T00:00:00Z"
}
```

处理规则：

- `key` 只在创建或轮换响应中返回一次，不落库。
- DB 只保存 `key_hash`、`public_prefix`、owner、状态和元数据。
- `name` 在同一用户下建议唯一；MVP 可用 DB 唯一约束强制。
- 每个用户默认最多 10 个未删除凭据。
- `expires_in_days` 默认 180，最大值由平台配置控制。
- 审计 `credential.issue`。

### 3.3 查询当前用户凭据

```http
GET /api/v1/cloud-sandbox/credentials?page=1&page_size=20
Authorization: Bearer <casdoor_oidc_access_token>
```

响应：

```json
{
  "items": [
    {
      "id": "cred_01j...",
      "name": "agent-default-key",
      "public_prefix": "7t3k9p",
      "status": "active",
      "expires_at": "2026-12-21T00:00:00Z",
      "last_used_at": "2026-06-24T01:02:03Z",
      "last_used_ip": "203.0.113.10",
      "issued_by_agent_id": "agent-web",
      "created_at": "2026-06-24T00:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 3.4 禁用或删除当前用户凭据

```http
POST /api/v1/cloud-sandbox/credentials/{credential_id}:disable
DELETE /api/v1/cloud-sandbox/credentials/{credential_id}
Authorization: Bearer <casdoor_oidc_access_token>
```

响应：

```json
{
  "id": "cred_01j...",
  "status": "disabled",
  "updated_at": "2026-06-24T02:00:00Z"
}
```

处理规则：

- `disable` 是可审计的软禁用。
- `DELETE` MVP 可实现为软删除或 revoked 状态，不物理删除审计相关记录。
- 当前用户只能操作自己的凭据；平台管理员使用管理员 API。

### 3.5 轮换当前用户凭据

```http
POST /api/v1/cloud-sandbox/credentials/{credential_id}:rotate
Authorization: Bearer <casdoor_oidc_access_token>
```

响应：

```json
{
  "id": "cred_01j...",
  "public_prefix": "9m2x0a",
  "key": "osb_u_9m2x0a.yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
  "status": "active",
  "rotated_at": "2026-06-24T02:10:00Z"
}
```

处理规则：

- 轮换后旧 secret 立即失效。
- `public_prefix` 可同步更换，便于清理缓存。
- 清理 Redis 中旧 prefix 的认证缓存。

### 3.6 当前用户用量

```http
GET /api/v1/me/usage
Authorization: Bearer <casdoor_oidc_access_token>
```

响应：

```json
{
  "quota": {
    "scope_type": "user",
    "scope_id": "casdoor:org:user_123",
    "max_running_sandboxes": 10,
    "max_timeout_seconds": 3600,
    "max_create_per_minute": 20,
    "allowed_runtime_profile_ids": ["profile_default"],
    "allowed_image_patterns": ["python:*", "node:*", "ubuntu:*"],
    "global_rule_id": "quota_global_default",
    "user_rule_id": null
  },
  "usage": {
    "active_sandboxes": 3,
    "created_sandboxes_last_minute": 1
  },
  "remaining": {
    "active_sandboxes": 7,
    "create_per_minute": 19
  }
}
```

## 4. 平台管理员 API

所有管理员 API 要求当前用户具备 `osb_platform_admin`。

### 4.1 用户列表

```http
GET /api/v1/admin/users?keyword=alice&status=active&page=1&page_size=20
```

响应字段：

```json
{
  "items": [
    {
      "subject_id": "casdoor:org:user_123",
      "username": "alice",
      "email": "alice@example.com",
      "display_name": "Alice",
      "status": "active",
      "roles": ["osb_agent_user"],
      "active_credentials": 2,
      "running_sandboxes": 3,
      "updated_at": "2026-06-24T00:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 4.2 用户凭据

```http
GET  /api/v1/admin/users/{subject_id}/credentials
POST /api/v1/admin/credentials/{credential_id}:disable
```

管理员禁用凭据响应：

```json
{
  "id": "cred_01j...",
  "owner_subject_id": "casdoor:org:user_123",
  "status": "disabled",
  "updated_at": "2026-06-24T02:00:00Z"
}
```

### 4.3 Runtime backend

```http
GET   /api/v1/admin/runtime-backends
POST  /api/v1/admin/runtime-backends
PATCH /api/v1/admin/runtime-backends/{backend_id}
```

创建请求：

```json
{
  "name": "local-opensandbox",
  "region": "local",
  "kind": "docker",
  "opensandbox_base_url": "http://opensandbox:8000",
  "api_key_env": "OPENSANDBOX_INTERNAL_API_KEY",
  "weight": 100,
  "status": "active",
  "capabilities": {
    "proxy": true,
    "websocket": true,
    "snapshots": false
  }
}
```

响应：

```json
{
  "id": "backend_01j...",
  "name": "local-opensandbox",
  "region": "local",
  "kind": "docker",
  "status": "active",
  "health_status": "unknown",
  "opensandbox_base_url": "http://opensandbox:8000",
  "api_key_env": "OPENSANDBOX_INTERNAL_API_KEY",
  "weight": 100,
  "capabilities": {
    "proxy": true,
    "websocket": true,
    "snapshots": false
  },
  "created_at": "2026-06-24T00:00:00Z",
  "updated_at": "2026-06-24T00:00:00Z"
}
```

### 4.4 Runtime profile

```http
GET  /api/v1/admin/runtime-profiles
POST /api/v1/admin/runtime-profiles
```

创建请求：

```json
{
  "name": "default",
  "cpu_limit": "1000m",
  "memory_limit": "1Gi",
  "timeout_seconds": 3600,
  "max_renew_seconds": 86400,
  "secure_access_default": true,
  "status": "active",
  "network_policy": {
    "defaultAction": "allow",
    "egress": []
  }
}
```

### 4.5 配额

```http
GET /api/v1/admin/quotas?scope_type=user&scope_id=casdoor:org:user_123
PUT /api/v1/admin/quotas/{quota_id}
```

更新请求：

```json
{
  "scope_type": "user",
  "scope_id": "casdoor:org:user_123",
  "max_running_sandboxes": 10,
  "max_timeout_seconds": 3600,
  "max_create_per_minute": 20,
  "allowed_runtime_profile_ids": ["profile_default"],
  "allowed_image_patterns": ["python:*", "node:*"]
}
```

用户级规则按字段覆盖全局规则；用户级字段为 `null` 时继承全局规则。全局规则字段为 `null` 表示该项不限。

### 4.6 审计、沙箱和平台状态

```http
GET /api/v1/admin/audit-events?action=sandbox.create&actor_subject_id=casdoor:org:user_123&page=1&page_size=20
GET /api/v1/admin/sandboxes?owner_subject_id=casdoor:org:user_123&state=running&page=1&page_size=20
GET /api/v1/admin/platform-status
```

`GET /api/v1/admin/audit-events` 响应：

```json
{
  "items": [
    {
      "id": 1001,
      "request_id": "req_01j...",
      "actor_subject_id": "casdoor:org:user_123",
      "credential_id": "cred_01j...",
      "action": "sandbox.create",
      "resource_type": "sandbox",
      "resource_id": "sbx_01j...",
      "decision": "allow",
      "ip": "203.0.113.10",
      "user_agent": "opensandbox-python/0.1",
      "error_code": null,
      "payload": {
        "backend_status_code": 202,
        "image": "python:3.12",
        "timeout": 3600
      },
      "created_at": "2026-06-24T02:30:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

`GET /api/v1/admin/platform-status` 响应：

```json
{
  "generated_at": "2026-06-24T02:30:00Z",
  "backends": [
    {
      "id": "backend_01j...",
      "name": "local-opensandbox",
      "status": "active",
      "health_status": "healthy",
      "running_sandboxes": 12,
      "last_checked_at": "2026-06-24T02:29:59Z",
      "last_error": null
    }
  ],
  "summary": {
    "active_credentials": 120,
    "running_sandboxes": 12,
    "failed_sandboxes_15m": 1,
    "recent_backend_errors_15m": 0
  }
}
```

## 5. OpenSandbox 原生兼容 API 处理契约

MVP 支持：

```http
POST   /v1/sandboxes
GET    /v1/sandboxes
GET    /v1/sandboxes/{sandbox_id}
DELETE /v1/sandboxes/{sandbox_id}
POST   /v1/sandboxes/{sandbox_id}/renew-expiration
POST   /v1/sandboxes/{sandbox_id}/pause
POST   /v1/sandboxes/{sandbox_id}/resume
GET    /v1/sandboxes/{sandbox_id}/endpoints/{port}
ANY    /v1/sandboxes/{sandbox_id}/proxy/{port}/{path...}
```

兼容规则：

1. 入站只接受 `OPEN-SANDBOX-API-KEY` 作为 Agent API 认证来源。
2. 认证通过后得到 `principal.subject_id`、`credential_id`、`public_prefix`。
3. create 前执行凭据状态、用户状态、配额、image policy、runtime profile、backend 健康检查。
4. create 成功后记录 `sandboxes` 索引，`public_sandbox_id` 默认等于 OpenSandbox 返回的 id；未来多 backend 冲突时可切换为 OpenSandbox Plus 生成 id。
5. list 先查询控制面 DB 并按当前用户过滤，再按 OpenSandbox 原生 `ListSandboxesResponse` 形态返回。
6. get/delete/renew/pause/resume/endpoint/proxy 先查 `sandboxes` 表确认归属，再调用对应 backend。
7. 出站到 OpenSandbox Server 时移除外部用户凭据，改用 backend 绑定的内部 key。
8. proxy 必须过滤 `authorization`、`cookie`、`OPEN-SANDBOX-API-KEY`、hop-by-hop headers。
9. 原生 API 错误响应尽量保持 OpenSandbox `{"code": "...", "message": "..."}` 形态，不使用管理 API 分页或包壳。

## 6. PostgreSQL DDL

MVP 使用 app 生成的文本 ID，例如 `cred_01j...`、`sbx_01j...`，避免数据库 ID 生成策略和业务 ID 耦合。DDL 可作为 Alembic 初始 migration 的基础。

```sql
create table user_identities (
  subject_id text primary key,
  casdoor_owner text not null,
  casdoor_user text not null,
  username text,
  email text,
  display_name text,
  status text not null default 'active',
  roles text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_user_status check (status in ('active', 'disabled', 'deleted'))
);

create table cloud_sandbox_credentials (
  id text primary key,
  owner_subject_id text not null references user_identities(subject_id),
  name text not null,
  public_prefix text not null unique,
  key_hash text not null,
  hash_algorithm text not null default 'hmac-sha256',
  status text not null default 'active',
  expires_at timestamptz,
  last_used_at timestamptz,
  last_used_ip inet,
  issued_by_agent_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  revoked_at timestamptz,
  constraint ck_credential_status check (status in ('active', 'disabled', 'revoked', 'expired')),
  constraint ck_credential_prefix_format check (public_prefix ~ '^[A-Za-z0-9_-]{6,32}$'),
  constraint uq_credential_owner_name unique (owner_subject_id, name)
);

create table runtime_profiles (
  id text primary key,
  name text not null unique,
  cpu_limit text,
  memory_limit text,
  timeout_seconds int not null,
  max_renew_seconds int,
  network_policy jsonb,
  image_policy_id text,
  secure_access_default boolean not null default true,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_runtime_profile_status check (status in ('active', 'disabled')),
  constraint ck_runtime_profile_timeout check (timeout_seconds > 0),
  constraint ck_runtime_profile_max_renew check (max_renew_seconds is null or max_renew_seconds >= timeout_seconds)
);

create table runtime_backends (
  id text primary key,
  name text not null unique,
  region text,
  kind text not null,
  status text not null default 'active',
  health_status text not null default 'unknown',
  opensandbox_base_url text not null,
  api_key_env text not null,
  weight int not null default 100,
  capabilities jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  last_checked_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_backend_kind check (kind in ('docker', 'kubernetes', 'remote')),
  constraint ck_backend_status check (status in ('active', 'disabled', 'draining')),
  constraint ck_backend_health check (health_status in ('unknown', 'healthy', 'unhealthy')),
  constraint ck_backend_weight check (weight >= 0)
);

create table sandboxes (
  id text primary key,
  public_sandbox_id text not null,
  opensandbox_id text not null,
  owner_subject_id text not null references user_identities(subject_id),
  created_by_credential_id text references cloud_sandbox_credentials(id),
  runtime_backend_id text not null references runtime_backends(id),
  runtime_profile_id text references runtime_profiles(id),
  image text,
  state text not null,
  requested_timeout_seconds int,
  expires_at timestamptz,
  last_opensandbox_payload jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  terminated_at timestamptz,
  constraint ck_sandbox_state check (state in ('pending', 'running', 'paused', 'stopping', 'stopped', 'failed', 'deleted', 'unknown')),
  constraint ck_sandbox_timeout check (requested_timeout_seconds is null or requested_timeout_seconds > 0),
  constraint uq_sandbox_owner_public unique (owner_subject_id, public_sandbox_id),
  constraint uq_sandbox_backend_open unique (runtime_backend_id, opensandbox_id)
);

create table sandbox_events (
  id bigserial primary key,
  sandbox_id text not null references sandboxes(id),
  event_type text not null,
  old_state text,
  new_state text,
  message text,
  payload jsonb,
  created_at timestamptz not null default now()
);

create table quota_rules (
  id text primary key,
  scope_type text not null,
  scope_id text not null,
  max_running_sandboxes int,
  max_timeout_seconds int,
  max_create_per_minute int,
  allowed_runtime_profile_ids text[],
  allowed_image_patterns text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_quota_scope check (scope_type in ('global', 'user')),
  constraint ck_quota_running check (max_running_sandboxes is null or max_running_sandboxes >= 0),
  constraint ck_quota_timeout check (max_timeout_seconds is null or max_timeout_seconds > 0),
  constraint ck_quota_create_rate check (max_create_per_minute is null or max_create_per_minute >= 0),
  constraint uq_quota_scope unique (scope_type, scope_id)
);

create table quota_usage (
  scope_type text not null,
  scope_id text not null,
  metric text not null,
  value numeric not null default 0,
  updated_at timestamptz not null default now(),
  primary key (scope_type, scope_id, metric),
  constraint ck_usage_value check (value >= 0)
);

create table audit_events (
  id bigserial primary key,
  request_id text not null,
  actor_subject_id text,
  credential_id text,
  action text not null,
  resource_type text not null,
  resource_id text,
  decision text not null,
  ip inet,
  user_agent text,
  error_code text,
  payload jsonb,
  created_at timestamptz not null default now(),
  constraint ck_audit_decision check (decision in ('allow', 'deny', 'error'))
);
```

推荐索引：

```sql
create index idx_users_status on user_identities(status);
create index idx_users_email on user_identities(email);

create index idx_credentials_owner_status on cloud_sandbox_credentials(owner_subject_id, status);
create index idx_credentials_prefix_status on cloud_sandbox_credentials(public_prefix, status);
create index idx_credentials_last_used on cloud_sandbox_credentials(last_used_at desc);

create index idx_backends_status_health on runtime_backends(status, health_status);

create index idx_sandboxes_owner_state on sandboxes(owner_subject_id, state);
create index idx_sandboxes_backend_openid on sandboxes(runtime_backend_id, opensandbox_id);
create index idx_sandboxes_public_owner on sandboxes(public_sandbox_id, owner_subject_id);
create index idx_sandboxes_expires on sandboxes(expires_at);
create index idx_sandboxes_updated on sandboxes(updated_at desc);

create index idx_sandbox_events_sandbox_created on sandbox_events(sandbox_id, created_at desc);
create index idx_audit_actor_created on audit_events(actor_subject_id, created_at desc);
create index idx_audit_credential_created on audit_events(credential_id, created_at desc);
create index idx_audit_action_created on audit_events(action, created_at desc);
create index idx_audit_resource_created on audit_events(resource_type, resource_id, created_at desc);
```

## 7. 初始种子数据

MVP 初始化时建议写入：

```sql
insert into runtime_profiles (
  id, name, cpu_limit, memory_limit, timeout_seconds, max_renew_seconds, status
) values (
  'profile_default', 'default', '1000m', '1Gi', 3600, 86400, 'active'
) on conflict (id) do nothing;

insert into quota_rules (
  id, scope_type, scope_id, max_running_sandboxes, max_timeout_seconds, max_create_per_minute, allowed_runtime_profile_ids, allowed_image_patterns
) values (
  'quota_global_default', 'global', '*', 10, 3600, 20, array['profile_default'], array['python:*', 'node:*', 'ubuntu:*']
) on conflict (id) do nothing;
```

`runtime_backends` 的初始数据可以来自部署配置，在应用启动时校验并 upsert：

```yaml
opensandbox:
  default_backend:
    id: backend_local
    name: local-opensandbox
    kind: docker
    base_url: http://opensandbox:8000
    api_key_env: OPENSANDBOX_INTERNAL_API_KEY
```

## 8. Alembic 拆分建议

初始迁移建议拆成 3 个文件，便于 review 和回滚：

1. `0001_core_identity_credentials.py`：`user_identities`、`cloud_sandbox_credentials`、相关索引。
2. `0002_runtime_sandbox_quota.py`：`runtime_profiles`、`runtime_backends`、`sandboxes`、`sandbox_events`、`quota_rules`、`quota_usage`。
3. `0003_audit_seed.py`：`audit_events`、默认 runtime profile、默认 quota rule。

## 9. 开发验收用例

MVP API 和 DDL 完成后至少验证：

1. 同一个 Casdoor 用户可以申请凭据，响应中返回一次明文 key。
2. DB 不保存明文 key，只保存 hash 和 prefix。
3. 使用该 key 可以调用 `POST /v1/sandboxes` 创建沙箱。
4. 用户 A 的 key 不能访问用户 B 的 sandbox。
5. 禁用凭据后，该 key 调原生 API 返回 401。
6. 管理员能禁用任意用户凭据，并写入 audit event。
7. `GET /api/v1/admin/platform-status` 在 OpenSandbox backend 不可用时仍返回可读状态，而不是整页失败。
8. `docker compose up` 后迁移、种子数据和单 backend 配置可重复执行。
