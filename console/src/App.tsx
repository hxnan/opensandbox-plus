import {
  AuditOutlined,
  CloudServerOutlined,
  CopyOutlined,
  DashboardOutlined,
  DeleteOutlined,
  KeyOutlined,
  LoginOutlined,
  LogoutOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  StopOutlined,
  SyncOutlined,
  UserOutlined
} from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import type { MenuProps } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  type AdminCredentialSummary,
  type AdminUserSummary,
  type AuditEvent,
  type CredentialSummary,
  type CurrentUser,
  type IssuedCredential,
  type Page,
  type PlatformStatus,
  type QuotaRule,
  type RuntimeBackend,
  type SandboxRecord,
  type UsageStatus,
  apiRequest,
  normalizeSandboxList,
  sandboxExpiresAt,
  sandboxId,
  sandboxImage,
  sandboxState
} from "./api";
import {
  type OidcSession,
  completeSigninRedirect,
  getOidcConfig,
  getOidcSession,
  hasSigninResponse,
  removeOidcSession,
  signinRedirect,
  signoutRedirect
} from "./auth";

const { Header, Content, Sider } = Layout;

type ViewKey =
  | "overview"
  | "credentials"
  | "users"
  | "sandboxes"
  | "platform"
  | "quotas"
  | "audit";

type AuthState = {
  token: string;
  manualToken: string;
  cloudKey: string;
  oidcSession: OidcSession | null;
  tokenSource: "oidc" | "manual" | "none";
  setToken: (value: string) => void;
  setCloudKey: (value: string) => void;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  forgetOidcSession: () => Promise<void>;
};

const menuItems: MenuProps["items"] = [
  { key: "overview", icon: <DashboardOutlined />, label: "概览" },
  { key: "credentials", icon: <KeyOutlined />, label: "凭据" },
  { key: "users", icon: <UserOutlined />, label: "用户" },
  { key: "sandboxes", icon: <CloudServerOutlined />, label: "沙箱" },
  { key: "platform", icon: <SafetyCertificateOutlined />, label: "平台" },
  { key: "quotas", icon: <SyncOutlined />, label: "配额" },
  { key: "audit", icon: <AuditOutlined />, label: "审计" }
];

export default function App() {
  const [view, setView] = useState<ViewKey>("overview");
  const [manualToken, setManualToken] = useLocalStorage("osb-plus-console-token", "");
  const [cloudKey, setCloudKey] = useLocalStorage("osb-plus-cloud-key", "");
  const [oidcSession, setOidcSession] = useState<OidcSession | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      try {
        const isSigninCallback = hasSigninResponse();
        const session = isSigninCallback ? await completeSigninRedirect() : await getOidcSession();
        if (!cancelled) {
          setOidcSession(session);
          if (session && isSigninCallback) {
            message.success("登录成功");
          }
        }
      } catch (err) {
        if (!cancelled) {
          message.error(errorText(err));
        }
      }
    }

    void loadSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async () => {
    await signinRedirect();
  }, []);

  const signOut = useCallback(async () => {
    try {
      await signoutRedirect();
    } catch {
      await removeOidcSession();
      setOidcSession(null);
    }
  }, []);

  const forgetOidcSession = useCallback(async () => {
    await removeOidcSession();
    setOidcSession(null);
  }, []);

  const token = manualToken || oidcSession?.accessToken || "";
  const tokenSource: AuthState["tokenSource"] = manualToken
    ? "manual"
    : oidcSession?.accessToken
      ? "oidc"
      : "none";

  const auth = useMemo(
    () => ({
      token,
      manualToken,
      cloudKey,
      oidcSession,
      tokenSource,
      setToken: setManualToken,
      setCloudKey,
      signIn,
      signOut,
      forgetOidcSession
    }),
    [
      token,
      manualToken,
      cloudKey,
      oidcSession,
      tokenSource,
      setManualToken,
      setCloudKey,
      signIn,
      signOut,
      forgetOidcSession
    ]
  );

  return (
    <Layout className="app-shell">
      <Sider width={232} theme="light" className="sidebar">
        <div className="brand">OpenSandbox Plus</div>
        <Menu
          mode="inline"
          selectedKeys={[view]}
          items={menuItems}
          onClick={(item) => setView(item.key as ViewKey)}
        />
      </Sider>
      <Layout>
        <Header className="topbar">
          <Typography.Text strong>单服务 MVP 控制面</Typography.Text>
          <AuthToolbar auth={auth} />
        </Header>
        <Content className="content">{renderView(view, auth)}</Content>
      </Layout>
    </Layout>
  );
}

function AuthToolbar({ auth }: { auth: AuthState }) {
  const oidcConfig = getOidcConfig();
  const profileName =
    auth.oidcSession?.profile.name ||
    auth.oidcSession?.profile.preferred_username ||
    auth.oidcSession?.profile.email ||
    auth.oidcSession?.profile.sub;

  return (
    <Space className="auth-toolbar" size={8} wrap>
      <Tag color={auth.tokenSource === "oidc" ? "green" : auth.tokenSource === "manual" ? "gold" : "default"}>
        {auth.tokenSource === "oidc" ? profileName || "OIDC" : auth.tokenSource === "manual" ? "手动 token" : "未登录"}
      </Tag>
      <Button size="small" icon={<LoginOutlined />} onClick={() => void auth.signIn()}>
        登录
      </Button>
      <Button
        size="small"
        icon={<LogoutOutlined />}
        disabled={!auth.oidcSession}
        onClick={() => void auth.signOut()}
      >
        退出
      </Button>
      <Input.Password
        size="small"
        className="token-input"
        placeholder="Bearer token override"
        value={auth.manualToken}
        onChange={(event) => auth.setToken(event.target.value)}
      />
      <Input.Password
        size="small"
        className="token-input"
        placeholder="Cloud sandbox key"
        value={auth.cloudKey}
        onChange={(event) => auth.setCloudKey(event.target.value)}
      />
      <Button
        size="small"
        icon={<DeleteOutlined />}
        onClick={() => {
          auth.setToken("");
          auth.setCloudKey("");
          void auth.forgetOidcSession();
        }}
      />
      <Typography.Text type="secondary" className="oidc-config">
        {oidcConfig.clientId}@{oidcConfig.authority}
      </Typography.Text>
    </Space>
  );
}

function renderView(view: ViewKey, auth: AuthState) {
  switch (view) {
    case "credentials":
      return <CredentialsPage auth={auth} />;
    case "users":
      return <UsersPage auth={auth} />;
    case "sandboxes":
      return <SandboxesPage auth={auth} />;
    case "platform":
      return <PlatformPage auth={auth} />;
    case "quotas":
      return <QuotasPage auth={auth} />;
    case "audit":
      return <AuditPage auth={auth} />;
    default:
      return <OverviewPage auth={auth} />;
  }
}

function OverviewPage({ auth }: { auth: AuthState }) {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [usage, setUsage] = useState<UsageStatus | null>(null);
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    setError(null);
    try {
      const [nextMe, nextUsage] = await Promise.all([
        apiRequest<CurrentUser>("/api/v1/me", { token: auth.token }),
        apiRequest<UsageStatus>("/api/v1/me/usage", { token: auth.token })
      ]);
      setMe(nextMe);
      setUsage(nextUsage);
      try {
        setStatus(
          await apiRequest<PlatformStatus>("/api/v1/admin/platform-status", {
            token: auth.token
          })
        );
      } catch {
        setStatus(null);
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="概览" onRefresh={load} loading={loading} />
      {error ? <Alert type="error" message={error} showIcon /> : null}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card size="small" title="当前用户">
            {me ? (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="Subject">{me.subject_id}</Descriptions.Item>
                <Descriptions.Item label="名称">
                  {me.display_name || me.username || "-"}
                </Descriptions.Item>
                <Descriptions.Item label="角色">
                  <Space wrap>
                    {me.roles.map((role) => (
                      <Tag key={role}>{role}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12} lg={4}>
          <Card size="small">
            <Statistic
              title="活跃沙箱"
              value={usage?.usage.active_sandboxes ?? 0}
              suffix={limitSuffix(usage?.quota.max_running_sandboxes)}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={4}>
          <Card size="small">
            <Statistic
              title="每分钟创建"
              value={usage?.usage.created_sandboxes_last_minute ?? 0}
              suffix={limitSuffix(usage?.quota.max_create_per_minute)}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={4}>
          <Card size="small">
            <Statistic
              title="运行中"
              value={status?.summary.running_sandboxes ?? usage?.usage.active_sandboxes ?? 0}
            />
          </Card>
        </Col>
        <Col xs={24} md={12} lg={4}>
          <Card size="small">
            <Statistic title="Backend 错误" value={status?.summary.recent_backend_errors_15m ?? 0} />
          </Card>
        </Col>
      </Row>
      <BackendStatusTable backends={status?.backends ?? []} />
    </Space>
  );
}

function CredentialsPage({ auth }: { auth: AuthState }) {
  const [items, setItems] = useState<CredentialSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [issued, setIssued] = useState<IssuedCredential | null>(null);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    try {
      const page = await apiRequest<Page<CredentialSummary>>("/api/v1/cloud-sandbox/credentials", {
        token: auth.token,
        query: { page_size: 100 }
      });
      setItems(page.items);
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createCredential(values: { name: string; agent_id?: string; expires_in_days?: number }) {
    try {
      const credential = await apiRequest<IssuedCredential>("/api/v1/cloud-sandbox/credentials", {
        method: "POST",
        token: auth.token,
        body: values
      });
      form.resetFields();
      setIssued(credential);
      auth.setCloudKey(credential.key);
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  async function mutateCredential(id: string, action: "disable" | "rotate" | "delete") {
    const path =
      action === "delete"
        ? `/api/v1/cloud-sandbox/credentials/${id}`
        : `/api/v1/cloud-sandbox/credentials/${id}:${action}`;
    try {
      const result = await apiRequest<CredentialSummary | IssuedCredential>(path, {
        method: action === "delete" ? "DELETE" : "POST",
        token: auth.token
      });
      if (action === "rotate" && "key" in result) {
        setIssued(result);
        auth.setCloudKey(result.key);
      }
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="云沙箱凭据" onRefresh={load} loading={loading} />
      <Card size="small" title="颁发凭据">
        <Form form={form} layout="inline" onFinish={createCredential}>
          <Form.Item name="name" rules={[{ required: true }]} className="inline-form-item">
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="agent_id" className="inline-form-item">
            <Input placeholder="Agent ID" />
          </Form.Item>
          <Form.Item name="expires_in_days" className="inline-form-item">
            <InputNumber min={1} placeholder="有效天数" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>
              颁发
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Table<CredentialSummary>
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "Prefix", dataIndex: "public_prefix" },
          {
            title: "状态",
            dataIndex: "status",
            render: (value: string) => <StatusTag value={value} />
          },
          { title: "Agent", dataIndex: "issued_by_agent_id", render: valueOrDash },
          { title: "最近使用", dataIndex: "last_used_at", render: formatTime },
          { title: "创建时间", dataIndex: "created_at", render: formatTime },
          {
            title: "操作",
            width: 220,
            render: (_, row) => (
              <Space>
                <Button
                  size="small"
                  icon={<StopOutlined />}
                  onClick={() => void mutateCredential(row.id, "disable")}
                >
                  禁用
                </Button>
                <Button
                  size="small"
                  icon={<SyncOutlined />}
                  onClick={() => void mutateCredential(row.id, "rotate")}
                >
                  轮换
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => void mutateCredential(row.id, "delete")}
                />
              </Space>
            )
          }
        ]}
      />
      <IssuedKeyModal issued={issued} onClose={() => setIssued(null)} />
    </Space>
  );
}

function UsersPage({ auth }: { auth: AuthState }) {
  const [items, setItems] = useState<AdminUserSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [credentialOwner, setCredentialOwner] = useState<AdminUserSummary | null>(null);
  const [credentialItems, setCredentialItems] = useState<AdminCredentialSummary[]>([]);
  const [credentialLoading, setCredentialLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    try {
      const page = await apiRequest<Page<AdminUserSummary>>("/api/v1/admin/users", {
        token: auth.token,
        query: { page_size: 100, ...filters }
      });
      setItems(page.items);
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token, filters]);

  const loadCredentials = useCallback(
    async (subjectId: string) => {
      if (!auth.token) return;
      setCredentialLoading(true);
      try {
        const page = await apiRequest<Page<AdminCredentialSummary>>(
          `/api/v1/admin/users/${encodeURIComponent(subjectId)}/credentials`,
          {
            token: auth.token,
            query: { page_size: 100 }
          }
        );
        setCredentialItems(page.items);
      } catch (err) {
        message.error(errorText(err));
      } finally {
        setCredentialLoading(false);
      }
    },
    [auth.token]
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function openCredentials(user: AdminUserSummary) {
    setCredentialOwner(user);
    await loadCredentials(user.subject_id);
  }

  async function disableAdminCredential(id: string) {
    try {
      await apiRequest(`/api/v1/admin/credentials/${encodeURIComponent(id)}:disable`, {
        method: "POST",
        token: auth.token
      });
      message.success("已禁用");
      if (credentialOwner) {
        await loadCredentials(credentialOwner.subject_id);
      }
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="用户" onRefresh={load} loading={loading} />
      <Card size="small" title="过滤">
        <Form
          form={form}
          layout="inline"
          onFinish={(values) => setFilters(compact(values as Record<string, string>))}
        >
          <Form.Item name="keyword" className="wide-form-item">
            <Input placeholder="Subject / 用户名 / 邮箱" />
          </Form.Item>
          <Form.Item name="status" className="inline-form-item">
            <Select
              allowClear
              placeholder="状态"
              options={[
                { value: "active", label: "active" },
                { value: "disabled", label: "disabled" }
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<ReloadOutlined />}>
              查询
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Table<AdminUserSummary>
        size="small"
        rowKey="subject_id"
        loading={loading}
        dataSource={items}
        columns={[
          {
            title: "用户",
            render: (_, row) => (
              <Space direction="vertical" size={0}>
                <Typography.Text strong>{userDisplayName(row)}</Typography.Text>
                <Typography.Text type="secondary">{row.email || row.username || "-"}</Typography.Text>
              </Space>
            )
          },
          {
            title: "Subject",
            dataIndex: "subject_id",
            ellipsis: true,
            render: (value: string) => <Typography.Text copyable>{value}</Typography.Text>
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 104,
            render: (value: string) => <StatusTag value={value} />
          },
          {
            title: "角色",
            dataIndex: "roles",
            render: (roles: string[]) =>
              roles.length ? (
                <Space size={4} wrap>
                  {roles.map((role) => (
                    <Tag key={role}>{role}</Tag>
                  ))}
                </Space>
              ) : (
                "-"
              )
          },
          { title: "活跃凭据", dataIndex: "active_credentials", width: 104 },
          { title: "活跃沙箱", dataIndex: "active_sandboxes", width: 104 },
          { title: "更新时间", dataIndex: "updated_at", render: formatTime },
          {
            title: "操作",
            width: 96,
            render: (_, row) => (
              <Button
                size="small"
                icon={<KeyOutlined />}
                onClick={() => void openCredentials(row)}
              >
                凭据
              </Button>
            )
          }
        ]}
      />
      <Modal
        title={credentialOwner ? `用户凭据 - ${userDisplayName(credentialOwner)}` : "用户凭据"}
        open={credentialOwner !== null}
        onCancel={() => {
          setCredentialOwner(null);
          setCredentialItems([]);
        }}
        footer={null}
        width={980}
      >
        <Table<AdminCredentialSummary>
          size="small"
          rowKey="id"
          loading={credentialLoading}
          dataSource={credentialItems}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "Prefix", dataIndex: "public_prefix" },
            {
              title: "状态",
              dataIndex: "status",
              width: 104,
              render: (value: string) => <StatusTag value={value} />
            },
            { title: "Agent", dataIndex: "issued_by_agent_id", render: valueOrDash },
            { title: "过期时间", dataIndex: "expires_at", render: formatTime },
            { title: "最近使用", dataIndex: "last_used_at", render: formatTime },
            {
              title: "操作",
              width: 88,
              render: (_, row) => (
                <Button
                  size="small"
                  icon={<StopOutlined />}
                  disabled={row.status !== "active"}
                  onClick={() => void disableAdminCredential(row.id)}
                >
                  禁用
                </Button>
              )
            }
          ]}
        />
      </Modal>
    </Space>
  );
}

function SandboxesPage({ auth }: { auth: AuthState }) {
  const [items, setItems] = useState<SandboxRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!auth.cloudKey) return;
    setLoading(true);
    try {
      const payload = await apiRequest<Record<string, unknown>>("/v1/sandboxes", {
        cloudKey: auth.cloudKey
      });
      setItems(normalizeSandboxList(payload));
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.cloudKey]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createSandbox(values: { image: string; timeout?: number }) {
    try {
      await apiRequest<Record<string, unknown>>("/v1/sandboxes", {
        method: "POST",
        cloudKey: auth.cloudKey,
        body: {
          ...values,
          image: { uri: values.image },
          entrypoint: ["/bin/sh", "-c", "sleep 3600"],
          resourceLimits: { cpu: "500m", memory: "512Mi" }
        }
      });
      form.resetFields();
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  async function deleteSandbox(id: string) {
    try {
      await apiRequest<Record<string, unknown>>(`/v1/sandboxes/${encodeURIComponent(id)}`, {
        method: "DELETE",
        cloudKey: auth.cloudKey
      });
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  if (!auth.cloudKey) return <MissingCloudKey />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="沙箱" onRefresh={load} loading={loading} />
      <Card size="small" title="创建沙箱">
        <Form form={form} layout="inline" onFinish={createSandbox}>
          <Form.Item name="image" rules={[{ required: true }]} className="inline-form-item">
            <Input placeholder="镜像" />
          </Form.Item>
          <Form.Item name="timeout" className="inline-form-item">
            <InputNumber min={1} placeholder="TTL 秒" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<SendOutlined />}>
              创建
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Table<SandboxRecord>
        size="small"
        rowKey={(row) => sandboxId(row)}
        loading={loading}
        dataSource={items}
        columns={[
          { title: "ID", render: (_, row) => <Typography.Text copyable>{sandboxId(row)}</Typography.Text> },
          { title: "镜像", render: (_, row) => sandboxImage(row) || "-" },
          { title: "状态", render: (_, row) => <StatusTag value={sandboxState(row)} /> },
          { title: "过期时间", render: (_, row) => formatTime(sandboxExpiresAt(row)) },
          {
            title: "操作",
            width: 96,
            render: (_, row) => (
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => void deleteSandbox(sandboxId(row))}
              />
            )
          }
        ]}
      />
    </Space>
  );
}

function PlatformPage({ auth }: { auth: AuthState }) {
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [backends, setBackends] = useState<RuntimeBackend[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    setError(null);
    try {
      const [nextStatus, backendPage] = await Promise.all([
        apiRequest<PlatformStatus>("/api/v1/admin/platform-status", { token: auth.token }),
        apiRequest<Page<RuntimeBackend>>("/api/v1/admin/runtime-backends", {
          token: auth.token
        })
      ]);
      setStatus(nextStatus);
      setBackends(backendPage.items);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="平台状态" onRefresh={load} loading={loading} />
      {error ? <Alert type="error" message={error} showIcon /> : null}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="活跃凭据" value={status?.summary.active_credentials ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="运行沙箱" value={status?.summary.running_sandboxes ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="15 分钟失败" value={status?.summary.failed_sandboxes_15m ?? 0} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic title="15 分钟后端错误" value={status?.summary.recent_backend_errors_15m ?? 0} />
          </Card>
        </Col>
      </Row>
      <BackendStatusTable backends={status?.backends ?? backends} />
    </Space>
  );
}

function QuotasPage({ auth }: { auth: AuthState }) {
  const [items, setItems] = useState<QuotaRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    try {
      const page = await apiRequest<Page<QuotaRule>>("/api/v1/admin/quotas", {
        token: auth.token,
        query: { page_size: 100 }
      });
      setItems(page.items);
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveQuota(values: Record<string, unknown>) {
    const quotaId = String(values.id ?? "");
    if (!quotaId) return;
    try {
      await apiRequest<QuotaRule>(`/api/v1/admin/quotas/${encodeURIComponent(quotaId)}`, {
        method: "PUT",
        token: auth.token,
        body: {
          scope_type: values.scope_type,
          scope_id: values.scope_id,
          max_running_sandboxes: values.max_running_sandboxes ?? null,
          max_timeout_seconds: values.max_timeout_seconds ?? null,
          max_create_per_minute: values.max_create_per_minute ?? null,
          allowed_runtime_profile_ids: csv(values.allowed_runtime_profile_ids),
          allowed_image_patterns: csv(values.allowed_image_patterns)
        }
      });
      form.resetFields();
      await load();
    } catch (err) {
      message.error(errorText(err));
    }
  }

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="配额" onRefresh={load} loading={loading} />
      <Card size="small" title="保存规则">
        <Form form={form} layout="inline" onFinish={saveQuota}>
          <Form.Item name="id" rules={[{ required: true }]} className="inline-form-item">
            <Input placeholder="规则 ID" />
          </Form.Item>
          <Form.Item name="scope_type" rules={[{ required: true }]} className="inline-form-item">
            <Select
              placeholder="Scope"
              options={[
                { value: "global", label: "global" },
                { value: "user", label: "user" }
              ]}
            />
          </Form.Item>
          <Form.Item name="scope_id" rules={[{ required: true }]} className="inline-form-item">
            <Input placeholder="Scope ID" />
          </Form.Item>
          <Form.Item name="max_running_sandboxes" className="inline-form-item">
            <InputNumber min={0} placeholder="并发" />
          </Form.Item>
          <Form.Item name="max_timeout_seconds" className="inline-form-item">
            <InputNumber min={1} placeholder="TTL" />
          </Form.Item>
          <Form.Item name="max_create_per_minute" className="inline-form-item">
            <InputNumber min={0} placeholder="每分钟" />
          </Form.Item>
          <Form.Item name="allowed_runtime_profile_ids" className="wide-form-item">
            <Input placeholder="Profile IDs" />
          </Form.Item>
          <Form.Item name="allowed_image_patterns" className="wide-form-item">
            <Input placeholder="Image patterns" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Table<QuotaRule>
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={[
          { title: "ID", dataIndex: "id" },
          { title: "Scope", render: (_, row) => `${row.scope_type}:${row.scope_id}` },
          { title: "并发", dataIndex: "max_running_sandboxes", render: limitText },
          { title: "TTL", dataIndex: "max_timeout_seconds", render: limitText },
          { title: "每分钟", dataIndex: "max_create_per_minute", render: limitText },
          { title: "更新时间", dataIndex: "updated_at", render: formatTime },
          {
            title: "操作",
            width: 92,
            render: (_, row) => (
              <Button size="small" onClick={() => form.setFieldsValue(formValuesFromQuota(row))}>
                编辑
              </Button>
            )
          }
        ]}
      />
    </Space>
  );
}

function AuditPage({ auth }: { auth: AuthState }) {
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!auth.token) return;
    setLoading(true);
    try {
      const page = await apiRequest<Page<AuditEvent>>("/api/v1/admin/audit-events", {
        token: auth.token,
        query: { page_size: 100, ...filters }
      });
      setItems(page.items);
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [auth.token, filters]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!auth.token) return <MissingToken />;

  return (
    <Space direction="vertical" size={16} className="stack">
      <SectionHeader title="审计" onRefresh={load} loading={loading} />
      <Card size="small" title="过滤">
        <Form
          form={form}
          layout="inline"
          onFinish={(values) => setFilters(compact(values as Record<string, string>))}
        >
          <Form.Item name="action" className="inline-form-item">
            <Input placeholder="Action" />
          </Form.Item>
          <Form.Item name="actor_subject_id" className="wide-form-item">
            <Input placeholder="Actor" />
          </Form.Item>
          <Form.Item name="resource_type" className="inline-form-item">
            <Input placeholder="Resource" />
          </Form.Item>
          <Form.Item name="decision" className="inline-form-item">
            <Select
              allowClear
              placeholder="Decision"
              options={[
                { value: "allow", label: "allow" },
                { value: "deny", label: "deny" },
                { value: "error", label: "error" }
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<ReloadOutlined />}>
              查询
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Table<AuditEvent>
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={items}
        expandable={{
          expandedRowRender: (row) => (
            <pre className="json-block">{JSON.stringify(row.payload ?? {}, null, 2)}</pre>
          )
        }}
        columns={[
          { title: "时间", dataIndex: "created_at", render: formatTime },
          { title: "Action", dataIndex: "action" },
          {
            title: "Decision",
            dataIndex: "decision",
            render: (value: AuditEvent["decision"]) => <DecisionTag value={value} />
          },
          { title: "Actor", dataIndex: "actor_subject_id", ellipsis: true },
          { title: "Credential", dataIndex: "credential_id", ellipsis: true },
          { title: "Resource", render: (_, row) => `${row.resource_type}:${row.resource_id ?? "-"}` },
          { title: "Error", dataIndex: "error_code", render: valueOrDash },
          { title: "Request", dataIndex: "request_id", ellipsis: true }
        ]}
      />
    </Space>
  );
}

function BackendStatusTable({ backends }: { backends: RuntimeBackend[] }) {
  return (
    <Table<RuntimeBackend>
      size="small"
      rowKey="id"
      pagination={false}
      dataSource={backends}
      columns={[
        { title: "名称", dataIndex: "name" },
        { title: "类型", dataIndex: "kind" },
        { title: "地址", dataIndex: "opensandbox_base_url", ellipsis: true },
        { title: "权重", dataIndex: "weight", width: 80 },
        { title: "运行中", dataIndex: "running_sandboxes", width: 88, render: valueOrZero },
        {
          title: "状态",
          dataIndex: "status",
          width: 96,
          render: (value: string) => <StatusTag value={value} />
        },
        {
          title: "健康",
          dataIndex: "health_status",
          width: 104,
          render: (value: string) => <StatusTag value={value} />
        },
        { title: "检查时间", dataIndex: "last_checked_at", render: formatTime },
        { title: "错误", dataIndex: "last_error", ellipsis: true, render: valueOrDash }
      ]}
    />
  );
}

function SectionHeader({
  title,
  onRefresh,
  loading
}: {
  title: string;
  onRefresh: () => void;
  loading?: boolean;
}) {
  return (
    <div className="section-header">
      <Typography.Title level={4}>{title}</Typography.Title>
      <Button icon={<ReloadOutlined />} loading={loading} onClick={() => onRefresh()}>
        刷新
      </Button>
    </div>
  );
}

function MissingToken() {
  return <Alert type="warning" message="缺少 Bearer token" showIcon />;
}

function MissingCloudKey() {
  return <Alert type="warning" message="缺少云沙箱 key" showIcon />;
}

function IssuedKeyModal({
  issued,
  onClose
}: {
  issued: IssuedCredential | null;
  onClose: () => void;
}) {
  return (
    <Modal title="新凭据" open={issued !== null} onCancel={onClose} footer={null}>
      <Space direction="vertical" className="stack">
        <Input.TextArea value={issued?.key ?? ""} rows={4} readOnly />
        <Button
          icon={<CopyOutlined />}
          onClick={() => {
            if (issued?.key) void navigator.clipboard.writeText(issued.key);
          }}
        >
          复制
        </Button>
      </Space>
    </Modal>
  );
}

function StatusTag({ value }: { value: string }) {
  const color = statusColor(value);
  return (
    <Tag color={color}>
      <Badge color={color === "default" ? "gray" : color} text={value} />
    </Tag>
  );
}

function DecisionTag({ value }: { value: AuditEvent["decision"] }) {
  const color = value === "allow" ? "green" : value === "deny" ? "orange" : "red";
  return <Tag color={color}>{value}</Tag>;
}

function useLocalStorage(key: string, initialValue: string) {
  const [value, setValue] = useState(() => localStorage.getItem(key) ?? initialValue);
  const setStoredValue = useCallback(
    (next: string) => {
      setValue(next);
      if (next) localStorage.setItem(key, next);
      else localStorage.removeItem(key);
    },
    [key]
  );
  return [value, setStoredValue] as const;
}

function statusColor(value: string) {
  const normalized = value.toLowerCase();
  if (["active", "healthy", "running"].includes(normalized)) return "green";
  if (["pending", "unknown", "paused", "draining"].includes(normalized)) return "gold";
  if (["disabled", "revoked", "deleted", "stopped"].includes(normalized)) return "default";
  return "red";
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function valueOrDash(value?: unknown) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function valueOrZero(value?: unknown) {
  return value === undefined || value === null || value === "" ? 0 : String(value);
}

function userDisplayName(user: AdminUserSummary) {
  return user.display_name || user.username || user.email || user.subject_id;
}

function limitText(value?: number | null) {
  return value === undefined || value === null ? "不限" : value;
}

function limitSuffix(value?: number | null) {
  return value === undefined || value === null ? "/不限" : `/${value}`;
}

function errorText(error: unknown) {
  if (error instanceof ApiError) {
    return error.code ? `${error.code}: ${error.message}` : error.message;
  }
  return error instanceof Error ? error.message : "请求失败";
}

function csv(value: unknown) {
  if (typeof value !== "string") return null;
  const parts = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return parts.length ? parts : null;
}

function compact(values: Record<string, string>) {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value));
}

function formValuesFromQuota(rule: QuotaRule) {
  return {
    ...rule,
    allowed_runtime_profile_ids: rule.allowed_runtime_profile_ids?.join(","),
    allowed_image_patterns: rule.allowed_image_patterns?.join(",")
  };
}
