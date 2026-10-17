"""Remove only the bonus records owned by an explicitly created integration-test client."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def clear_client_bonus_records(connection: AsyncConnection, client_id: uuid.UUID) -> None:
    for table in (
        "client_bonus_receipts",
        "client_bonus_earnings",
        "client_bonus_debits",
        "client_bonus_sessions",
        "client_bonus_operations",
        "client_bonus_reservations",
        "client_bonus_wallets",
    ):
        await connection.execute(
            text(f"DELETE FROM {table} WHERE client_id = :bonus_client_id"),
            {"bonus_client_id": client_id},
        )
