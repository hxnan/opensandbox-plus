export type Page<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type CurrentUser = {
  subject_id: string;
  username?: string | null;
  email?: string | null;
  display_name?: string | null;
  roles: string[];
  features: Record<string, boolean>;
};

export type CredentialSummary = {
  id: string;
  name: string;
  public_prefix: string;
  status: string;
  expires_at?: string | null;
  last_used_at?: string | null;
  last_used_ip?: string | null;
  issued_by_agent_id?: string | null;
  created_at: string;
};

export type IssuedCredential = CredentialSummary & {
  key: string;
};

export type AdminCredentialSummary = CredentialSummary & {
  owner_subject_id: string;
};

export type AdminUserSummary = {
  subject_id: string;
  casdoor_owner: string;
  casdoor_user: string;
  username?: string | null;
  email?: string | null;
  display_name?: string | null;
  status: string;
  roles: string[];
  active_credentials: number;
  active_sandboxes: number;
  created_at: string;
  updated_at: string;
};

export type UsageStatus = {
  quota: {
    scope_type: string;
    scope_id: string;
    max_running_sandboxes?: number | null;
    max_timeout_seconds?: number | null;
    max_create_per_minute?: number | null;
    global_rule_id?: string | null;
    user_rule_id?: string | null;
  };
  usage: {
    active_sandboxes: number;
    created_sandboxes_last_minute: number;
  };
  remaining: {
    active_sandboxes?: number | null;
    create_per_minute?: number | null;
  };
};

export type RuntimeBackend = {
  id: string;
  name: string;
  region?: string | null;
  kind: string;
  status: string;
  health_status: string;
  opensandbox_base_url: string;
  weight: number;
  running_sandboxes?: number;
  last_checked_at?: string | null;
  last_error?: string | null;
};

export type PlatformStatus = {
  generated_at: string;
  backends: RuntimeBackend[];
  summary: {
    active_credentials: number;
    running_sandboxes: number;
    failed_sandboxes_15m: number;
    recent_backend_errors_15m: number;
    sandbox_states?: Record<string, number>;
  };
};

export type QuotaRule = {
  id: string;
  scope_type: "global" | "user";
  scope_id: string;
  max_running_sandboxes?: number | null;
  max_timeout_seconds?: number | null;
  max_create_per_minute?: number | null;
  allowed_runtime_profile_ids?: string[] | null;
  allowed_image_patterns?: string[] | null;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: number;
  request_id: string;
  actor_subject_id?: string | null;
  credential_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  decision: "allow" | "deny" | "error";
  ip?: string | null;
  user_agent?: string | null;
  error_code?: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
};

export type SandboxRecord = Record<string, unknown> & {
  id?: string;
  sandboxId?: string;
  sandbox_id?: string;
  state?: string;
  status?: string | { state?: string };
  image?: string | { uri?: string };
  expiresAt?: string;
  expires_at?: string;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(status: number, message: string, code?: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  token?: string;
  cloudKey?: string;
  query?: Record<string, string | number | undefined | null>;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = {};
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (options.cloudKey) headers["OPEN-SANDBOX-API-KEY"] = options.cloudKey;
  if (options.body !== undefined) headers["content-type"] = "application/json";

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });
  const text = await response.text();
  const data = text ? safeJson(text) : null;

  if (!response.ok) {
    const detail = isRecord(data) ? data.detail : undefined;
    const body = isRecord(detail) ? detail : isRecord(data) ? data : undefined;
    const code = typeof body?.code === "string" ? body.code : undefined;
    const message =
      typeof body?.message === "string" ? body.message : `HTTP ${response.status}`;
    throw new ApiError(response.status, message, code, body?.details);
  }

  return data as T;
}

export function sandboxId(record: SandboxRecord): string {
  const value = record.id ?? record.sandboxId ?? record.sandbox_id;
  return typeof value === "string" ? value : "";
}

export function sandboxState(record: SandboxRecord): string {
  if (typeof record.status === "object" && record.status?.state) return record.status.state;
  if (typeof record.status === "string") return record.status;
  return typeof record.state === "string" ? record.state : "unknown";
}

export function sandboxImage(record: SandboxRecord): string {
  if (typeof record.image === "string") return record.image;
  if (typeof record.image === "object" && typeof record.image.uri === "string") {
    return record.image.uri;
  }
  return "";
}

export function sandboxExpiresAt(record: SandboxRecord): string | undefined {
  const value = record.expiresAt ?? record.expires_at;
  return typeof value === "string" ? value : undefined;
}

export function normalizeSandboxList(payload: Record<string, unknown>): SandboxRecord[] {
  for (const key of ["items", "sandboxes", "data"]) {
    const value = payload[key];
    if (Array.isArray(value)) return value.filter(isRecord) as SandboxRecord[];
  }
  return [];
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
