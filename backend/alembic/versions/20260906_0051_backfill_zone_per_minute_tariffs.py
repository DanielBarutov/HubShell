"""Create internal per-minute tariff snapshots for existing zone rates."""

import datetime
import typing
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0051"
down_revision: str | None = "20260906_0050"
branch_labels: str | typing.Sequence[str] | None = None
depends_on: str | typing.Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.datetime.now(datetime.UTC)
    groups = sa.table(
        "workstation_groups",
        sa.column("id", sa.String(length=128)),
        sa.column("name", sa.String(length=128)),
        sa.column("per_minute_price_cents", sa.BigInteger()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    tariffs = sa.table(
        "tariffs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=128)),
        sa.column("group_id", sa.String(length=128)),
        sa.column("duration_minutes", sa.Integer()),
        sa.column("price_cents", sa.BigInteger()),
        sa.column("valid_from", sa.DateTime(timezone=True)),
        sa.column("valid_to", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean()),
        sa.column("tariff_key", sa.String(length=128)),
        sa.column("version", sa.Integer()),
        sa.column("lifecycle", sa.String(length=16)),
        sa.column("billing_mode", sa.String(length=16)),
        sa.column("price_per_minute_cents", sa.BigInteger()),
        sa.column("free_minutes", sa.Integer()),
        sa.column("window_start_minute", sa.Integer()),
        sa.column("window_end_minute", sa.Integer()),
        sa.column("window_timezone", sa.String(length=64)),
    )

    for group in bind.execute(
        sa.select(
            groups.c.id,
            groups.c.name,
            groups.c.per_minute_price_cents,
            groups.c.updated_at,
        ).where(groups.c.per_minute_price_cents > 0)
    ).mappings():
        tariff_key = f"zone:{group['id']}:per_minute"
        current = bind.execute(
            sa.select(
                tariffs.c.price_per_minute_cents,
                tariffs.c.active,
                tariffs.c.lifecycle,
                tariffs.c.valid_from,
                tariffs.c.valid_to,
            )
            .where(tariffs.c.tariff_key == tariff_key)
            .order_by(tariffs.c.version.desc())
            .limit(1)
        ).mappings().first()
        if current is not None and (
            current["price_per_minute_cents"] == group["per_minute_price_cents"]
            and current["active"]
            and current["lifecycle"] == "published"
            and current["valid_from"] <= now
            and (current["valid_to"] is None or now < current["valid_to"])
        ):
            continue

        latest_version = bind.execute(
            sa.select(sa.func.coalesce(sa.func.max(tariffs.c.version), 0)).where(
                tariffs.c.tariff_key == tariff_key
            )
        ).scalar_one()
        bind.execute(
            sa.update(tariffs)
            .where(tariffs.c.tariff_key == tariff_key, tariffs.c.active.is_(True))
            .values(active=False, lifecycle="archived")
        )
        bind.execute(
            sa.insert(tariffs).values(
                id=uuid.uuid4(),
                name=f"{group['name']} · Поминутно",
                group_id=group["id"],
                duration_minutes=1,
                price_cents=0,
                valid_from=group["updated_at"] or datetime.datetime.now(datetime.UTC),
                valid_to=None,
                active=True,
                tariff_key=tariff_key,
                version=int(latest_version) + 1,
                lifecycle="published",
                billing_mode="per_minute",
                price_per_minute_cents=group["per_minute_price_cents"],
                free_minutes=0,
                window_start_minute=None,
                window_end_minute=None,
                window_timezone=None,
            )
        )


def downgrade() -> None:
    # The migration can update an existing tariff history and does not persist
    # which rows it created. A broad DELETE would destroy operator data during
    # downgrade, so keep the data and require an explicit operator migration
    # if a rollback of these snapshots is ever needed.
    pass
