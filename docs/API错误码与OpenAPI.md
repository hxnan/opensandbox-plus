# API 错误码与 OpenAPI 契约

OpenSandbox Plus 暴露标准 OpenAPI 文档：

- JSON: `GET /openapi.json`
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`

## 错误响应结构

管理 API 与 OpenSandbox 兼容 API 的错误响应保持统一外层结构：

```json
{
  "detail": {
    "code": "UNAUTHENTICATED",
    "message": "missing Authorization header",
    "request_id": "req_01HTZ8K4Y2Q7F2N",
    "details": {}
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `detail.code` | 稳定错误码，供 Agent、Console 和运维工具判断失败类型 |
| `detail.message` | 面向开发者的简短错误说明 |
| `detail.request_id` | 请求追踪 ID，同时写入响应头 `X-Request-ID` |
| `detail.details` | 可选结构化详情，例如字段校验错误 |

## 常用错误码

| 错误码 | 含义 |
| --- | --- |
| `UNAUTHENTICATED` | 管理面 Bearer token 缺失、格式错误、过期或无效 |
| `FORBIDDEN` | 用户无所需角色、状态不可用或无访问权限 |
| `MISSING_API_KEY` | OpenSandbox 兼容 API 缺少 `OPEN-SANDBOX-API-KEY` |
| `INVALID_CREDENTIAL` | 云沙箱凭据无效、禁用、过期或格式错误 |
| `INVALID_REQUEST` | 请求体、查询参数或上传内容不合法 |
| `VALIDATION_ERROR` | 请求未通过 schema 校验 |
| `NOT_FOUND` | 资源不存在 |
| `CONFLICT` | 写操作与当前状态冲突 |
| `QUOTA_EXCEEDED` | 用户、凭据或平台配额已耗尽 |
| `PAYLOAD_TOO_LARGE` | 上传或请求体超过配置限制 |
| `OPENSANDBOX_BACKEND_ERROR` | 下游 OpenSandbox 集群不可用或返回错误 |
| `NOT_IMPLEMENTED` | 兼容接口已预留但当前尚未实现 |

## 联调建议

- 客户端应优先使用 `detail.code` 做分支处理，不要解析 `message`。
- 排障时同时记录 `detail.request_id` 和响应头 `X-Request-ID`。
- 兼容 API 仍保持 OpenSandbox 原生路径与认证头语义，仅错误体增加稳定 code 和 request ID。
