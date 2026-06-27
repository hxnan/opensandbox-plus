# OpenSandbox Plus MVP 交付验收记录

记录日期：2026-06-26

## 交付范围

本次 MVP 采用简化架构：自研部分只有一个 `opensandbox-plus` 服务，同时承载 Console、管理面 API、OpenSandbox 兼容 API、凭据校验、授权、审计和平台状态聚合。

核心角色保留两个：

| 角色 | 能力 |
| --- | --- |
| 平台管理员 | 查看平台状态、用户、凭据、配额、审计记录，并可禁用用户云沙箱凭据 |
| Agent 用户 | 登录 Agent 后通过 API 申请云沙箱凭据 key，后续使用该 key 访问云沙箱 |

对 Agent 开放的沙箱 API 与 OpenSandbox 原生 API 保持兼容。差异只在认证模型：OpenSandbox 原生部署通常是整个 server 共用一个 key；OpenSandbox Plus 改为每个 Agent 用户可申请自己的云沙箱 key，服务端再用内部 server key 转发到 OpenSandbox。

## 下一阶段关键需求优先级

| 优先级 | 关键需求 | 下一步目标 |
| --- | --- | --- |
| P0 | 阿里云 ACK/K8s 集群接入与 OpenSandbox 套件部署 | 无缝接入阿里云服务的 K8s 集群，完成环境预检，一键部署完整 OpenSandbox 服务套件，并自动纳管 |
| P0 | 多 OpenSandbox 集群管理 | 支持多集群注册、健康检查、容量状态、调度策略和故障切换 |
| P0 | OpenSandbox 镜像管理与分发 | 支持手动上传镜像，上传完成后自动推送到各 OpenSandbox 集群镜像仓库，并展示同步状态 |
| P1 | 项目大屏首页与文生图宣传资产 | 增加介绍和推销 OpenSandbox Plus 的首页，结合文生图生成背景图和宣传图 |

## 本地部署

当前本地部署使用 docker-compose：

```powershell
docker compose -f deploy\docker-compose.yml up -d --build
```

本地服务地址：

| 服务 | 地址 |
| --- | --- |
| OpenSandbox Plus Console/API | `http://localhost:8080` |
| Casdoor | `http://localhost:8000` |
| OpenSandbox | compose 内部服务 `opensandbox:8080` |
| PostgreSQL | compose 内部服务 `postgres:5432` |
| Redis | compose 内部服务 `redis:6379` |

本地种子账号：

| 用户 | 密码 | 角色 |
| --- | --- | --- |
| `agent-demo` | `123456` | Agent 用户 |
| `admin-demo` | `123456` | Agent 用户、平台管理员 |

## 验收命令

配置检查：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -ConfigOnly
```

启动并验证基础链路：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -Start -Migrate
```

运行完整业务流：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\verify-local.ps1 -Migrate -RunBusinessFlow -UseDemoTokens -TimeoutSeconds 300
```

代码质量检查：

```powershell
cd server
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .

cd ..\console
npm run build
```

> 注意：上面的 PowerShell 示例中 `.venv` 位于仓库根目录；如果从其他目录执行，请改用绝对路径。

## 已通过验收项

| 项目 | 结果 |
| --- | --- |
| docker-compose 配置检查 | 通过 |
| `opensandbox-plus` 健康检查 `/health` | 通过 |
| Console 静态页 | 通过 |
| Casdoor discovery/JWKS | 通过 |
| Casdoor `admin/osb-console` 应用检查 | 通过 |
| demo Agent token 获取 | 通过 |
| demo Admin token 获取 | 通过 |
| Agent 当前用户接口 `/api/v1/me` | 通过 |
| Agent 申请云沙箱 key | 通过 |
| 云沙箱 key 调用 `POST /v1/sandboxes` | 通过 |
| 云沙箱 key 调用 `GET /v1/sandboxes` | 通过 |
| 云沙箱 key 调用 `DELETE /v1/sandboxes/{id}` | 通过 |
| 平台管理员查询用户 | 通过 |
| 平台管理员查询用户凭据 | 通过 |
| 平台管理员禁用凭据 | 通过 |
| 被禁用 key 再访问云沙箱 | 返回 401，通过 |
| 后端测试 | `13 passed` |
| 后端 lint | 通过 |
| 前端构建 | 通过，有 Vite 大 chunk 提示 |

## Console 验收路径

1. 打开 `http://localhost:8080`。
2. 使用 `agent-demo / 123456` 登录。
3. 在凭据页面申请云沙箱 key。
4. 使用该 key 在沙箱页面创建、查看、删除沙箱。
5. 切换 `admin-demo / 123456` 登录。
6. 在用户、凭据、平台状态、配额和审计页面检查管理面数据。
7. 禁用某个用户 key 后，确认该 key 无法继续访问云沙箱 API。

## 当前边界

MVP 暂不包含以下能力：

| 能力 | 当前处理 |
| --- | --- |
| 生产级部署体系 | 暂用 docker-compose，后续优先补齐生产基线、集群管理、镜像管理和可观测能力 |
| 完整可观测平台 | 暂不接入 Prometheus/Grafana/Tracing，仅在管理面获取当前最新平台状态 |
| 多 OpenSandbox 集群管理 | MVP 先接入单 OpenSandbox backend，后续支持多集群注册、健康检查、容量状态和调度策略 |
| OpenSandbox 镜像管理 | MVP 暂不提供镜像上传和分发，后续支持手动上传镜像并自动推送到各 OpenSandbox 集群镜像仓库 |
| 阿里云 ACK/K8s 接入 | MVP 暂不直接部署云上 OpenSandbox 套件，后续支持无缝接入阿里云 ACK/K8s 集群并部署完整 OpenSandbox 服务 |
| 多租户管理员 | 已从方案中移除，只保留平台管理员和 Agent 用户 |
| Console 生产级权限配置 UI | 先提供基础页面和 API 能力，后续按运营需求增强 |
| 高级配额策略 | 已保留配额模型和接口，先覆盖默认配额与管理员调整 |
| OpenSandbox 全量原生 API | MVP 已覆盖核心生命周期 API，后续按使用频率补齐 |

## 后续升级方向

1. 补齐生产基线：CI、生产配置手册、安全基线、运行手册和可重复验收脚本。
2. 增加多 OpenSandbox 集群管理：集群注册、健康检查、容量状态、调度策略和故障切换。
3. 增加 OpenSandbox 镜像管理：手动上传镜像、镜像仓库配置、自动推送到各集群、同步状态和失败重试。
4. 增加阿里云 ACK/K8s 接入：完成集群接入、环境预检、一键部署完整 OpenSandbox 服务套件，并自动纳管为 OpenSandbox 集群。
5. 引入 Prometheus 指标、结构化日志、Trace 和告警。
6. 补齐 OpenSandbox 原生 API 的长尾接口兼容。
7. 增加项目大屏首页：介绍和推销 OpenSandbox Plus，展示核心价值、架构能力、使用流程，并结合文生图生成背景图和宣传图。
8. 增强 Console 的运营视图、筛选、批量操作、集群视图、镜像视图和风险提示。
9. 增加真实外部 Casdoor/OIDC 环境的部署手册与验收脚本。
