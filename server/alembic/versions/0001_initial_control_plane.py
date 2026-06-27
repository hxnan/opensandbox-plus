"""initial control plane schema

Revision ID: 0001_initial_control_plane
Revises:
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial_control_plane"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _execute_batch(sql: str) -> None:
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def upgrade() -> None:
    _execute_batch(
        """
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
        """
    )

    _execute_batch(
        """
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
        """
    )

    _execute_batch(
        """
        insert into runtime_profiles (
          id, name, cpu_limit, memory_limit, timeout_seconds, max_renew_seconds, status
        ) values (
          'profile_default', 'default', '1000m', '1Gi', 3600, 86400, 'active'
        ) on conflict (id) do nothing;

        insert into quota_rules (
          id, scope_type, scope_id, max_running_sandboxes, max_timeout_seconds,
          max_create_per_minute, allowed_runtime_profile_ids, allowed_image_patterns
        ) values (
          'quota_global_default', 'global', '*', 10, 3600, 20,
          array['profile_default'], array['python:*', 'node:*', 'ubuntu:*']
        ) on conflict (id) do nothing;
        """
    )


def downgrade() -> None:
    _execute_batch(
        """
        drop table if exists audit_events;
        drop table if exists quota_usage;
        drop table if exists quota_rules;
        drop table if exists sandbox_events;
        drop table if exists sandboxes;
        drop table if exists runtime_backends;
        drop table if exists runtime_profiles;
        drop table if exists cloud_sandbox_credentials;
        drop table if exists user_identities;
        """
    )
