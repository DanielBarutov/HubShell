"""Read confirmed financial checkpoints without exposing V2 persistence to delivery."""

import uuid

from gameclub_backend.modules.eventing_v2.application.ports import V2SessionChainRepository


class V2ClientUpdateReadiness:
    def __init__(self, chains: V2SessionChainRepository) -> None:
        self._chains = chains

    async def is_confirmed(
        self,
        device_id: str,
        session_id: uuid.UUID,
        last_sequence: int,
        last_payload_hash: str | None,
    ) -> bool:
        chain = await self._chains.get(session_id)
        if chain is None:
            return last_sequence == 0 and last_payload_hash is None
        return (
            chain.device_id == device_id
            and chain.last_sequence == last_sequence
            and chain.last_payload_hash == last_payload_hash
        )
