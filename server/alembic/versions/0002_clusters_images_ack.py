"""clusters images and ack deployment foundation

Revision ID: 0002_clusters_images_ack
Revises: 0001_initial_control_plane
Create Date: 2026-06-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_clusters_images_ack"
down_revision: Union[str, None] = "0001_initial_control_plane"
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
        alter table runtime_backends add column if not exists provider text;
        alter table runtime_backends add column if not exists external_cluster_id text;
        alter table runtime_backends add column if not exists namespace text;
        alter table runtime_backends add column if not exists registry_url text;
        alter table runtime_backends add column if not exists kubeconfig_secret_ref text;

        create table sandbox_images (
          id text primary key,
          name text not null,
          version text not null,
          source_type text not null,
          source_uri text,
          architecture text not null default 'amd64',
          runtime_profile_id text references runtime_profiles(id),
          risk_level text not null default 'low',
          status text not null default 'draft',
          description text,
          created_by_subject_id text,
          metadata jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint ck_sandbox_image_source_type check (source_type in ('manual_upload', 'external_registry')),
          constraint ck_sandbox_image_risk_level check (risk_level in ('low', 'medium', 'high')),
          constraint ck_sandbox_image_status check (status in ('draft', 'active', 'disabled')),
          constraint uq_sandbox_image_version_arch unique (name, version, architecture)
        );

        create table image_distributions (
          id text primary key,
          image_id text not null references sandbox_images(id),
          runtime_backend_id text not null references runtime_backends(id),
          registry_url text,
          target_ref text,
          status text not null default 'pending',
          retry_count int not null default 0,
          last_error text,
          last_synced_at timestamptz,
          metadata jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint ck_image_distribution_status check (status in ('pending', 'uploading', 'available', 'failed', 'disabled')),
          constraint ck_image_distribution_retry check (retry_count >= 0),
          constraint uq_image_distribution_backend unique (image_id, runtime_backend_id)
        );

        create table ack_cluster_deployments (
          id text primary key,
          runtime_backend_id text references runtime_backends(id),
          aliyun_cluster_id text not null,
          region text not null,
          namespace text not null default 'opensandbox',
          vpc_id text,
          registry_url text,
          kubeconfig_secret_ref text,
          status text not null default 'draft',
          precheck_payload jsonb,
          deployment_payload jsonb,
          last_error text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint ck_ack_deployment_status check (
            status in ('draft', 'prechecking', 'ready', 'deploying', 'deployed', 'failed', 'disabled')
          )
        );
        """
    )

    _execute_batch(
        """
        create index idx_backends_provider_external on runtime_backends(provider, external_cluster_id);
        create index idx_images_status_name on sandbox_images(status, name);
        create index idx_image_distributions_image_status on image_distributions(image_id, status);
        create index idx_image_distributions_backend_status on image_distributions(runtime_backend_id, status);
        create index idx_ack_deployments_status_region on ack_cluster_deployments(status, region);
        create index idx_ack_deployments_backend on ack_cluster_deployments(runtime_backend_id);
        """
    )


def downgrade() -> None:
    _execute_batch(
        """
        drop table if exists ack_cluster_deployments;
        drop table if exists image_distributions;
        drop table if exists sandbox_images;
        drop index if exists idx_backends_provider_external;
        alter table runtime_backends drop column if exists kubeconfig_secret_ref;
        alter table runtime_backends drop column if exists registry_url;
        alter table runtime_backends drop column if exists namespace;
        alter table runtime_backends drop column if exists external_cluster_id;
        alter table runtime_backends drop column if exists provider;
        """
    )
