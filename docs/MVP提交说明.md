# OpenSandbox Plus MVP 提交说明

## 建议提交标题

```text
feat: deliver opensandbox plus mvp control plane
```

## 变更摘要

本次提交交付 OpenSandbox Plus MVP：一个面向 OpenSandbox 的云沙箱管理控制面。架构上保留未来拆分为分布式服务的能力，但当前自研部分收敛为单个 `opensandbox-plus` 服务，降低部署和联调复杂度。

核心变更：

| 模块 | 内容 |
| --- | --- |
| 技术方案 | 调整为平台管理员、Agent 用户两个核心角色，移除租户管理员 |
| 后端服务 | 新增 FastAPI 控制面、Casdoor JWT 鉴权、个人云沙箱 key、配额、审计、平台状态、OpenSandbox 兼容 API |
| OpenSandbox 兼容层 | 对 Agent 暴露 `/v1/sandboxes` 等原生兼容 API，用个人 key 认证后转发到内部 OpenSandbox server key |
| Console | 新增 React/Vite 管理台，支持登录、凭据、沙箱、用户、平台状态、配额、审计等基础页面 |
| 数据库 | 新增 SQLAlchemy 模型和 Alembic 初始迁移 |
| 部署 | 新增 Dockerfile、docker-compose、Casdoor 本地初始化、环境变量样例 |
| 验收脚本 | 新增本地验证脚本，覆盖配置检查、迁移、健康检查、Casdoor、业务主链路 |
| 文档 | 新增技术方案、MVP API/DDL、交付验收记录、Casdoor 本地说明 |

## PR 描述草稿

```markdown
## Summary

- deliver the OpenSandbox Plus MVP as a single deployable control-plane service
- add per-Agent cloud sandbox credentials while keeping OpenSandbox-compatible `/v1/sandboxes` APIs
- add FastAPI backend, React/Vite Console, Alembic schema, Casdoor local bootstrap, docker-compose deployment, and local verification scripts
- document the simplified two-role model, API/DDL contract, local deployment, and acceptance record

## Validation

- `docker compose -f deploy\docker-compose.yml config --quiet`
- `powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -Migrate -RunBusinessFlow -UseDemoTokens -TimeoutSeconds 300`
- `cd server && ..\.venv\Scripts\python.exe -m pytest`
- `cd server && ..\.venv\Scripts\python.exe -m ruff check .`
- `cd console && npm run build`

## Notes

- MVP deploys with docker-compose; next-stage work focuses on production baseline, multi-OpenSandbox cluster management, image management, and observability.
- Observability is limited to current platform status in the management plane.
- Tenant admin is intentionally removed from the role model.
- Local Casdoor seed enables password grant only for automated verification.
```

## 验收状态

| 检查项 | 状态 |
| --- | --- |
| docker-compose 配置 | 通过 |
| 真实 compose 环境业务流 | 通过 |
| 后端测试 | 13 passed |
| 后端 lint | 通过 |
| 前端构建 | 通过，有 Vite 大 chunk 提示 |
| Python/Node 生成物 | 已通过 `.gitignore` 排除 |

## 提交前建议检查

```powershell
git status --short --untracked-files=all
docker compose -f deploy\docker-compose.yml config --quiet
cd server
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .
cd ..\console
npm run build
```

## 本次不提交的内容

以下内容属于本地依赖、构建产物或参考代码，不应进入提交：

| 路径 | 原因 |
| --- | --- |
| `.venv/` | 本地 Python 虚拟环境 |
| `console/node_modules/` | 本地 Node 依赖 |
| `console/dist/` | 前端构建产物 |
| `console/tsconfig.tsbuildinfo` | TypeScript 增量构建缓存 |
| `server/opensandbox_plus_server.egg-info/` | Python 打包元数据 |
| `server/.pytest_cache/` | 测试缓存 |
| `server/.ruff_cache/` | lint 缓存 |
| `opensandbox-temp/` | OpenSandbox 参考源码 |
