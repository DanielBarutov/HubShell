import asyncio
import json
import typing

import httpx

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.workstations.domain_relay import RelaySettings


class DiyHttpRelayControl:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def set_state(self, settings: RelaySettings, on: bool) -> str:
        # IP literals and fixed paths prevent arbitrary URL/proxy/redirect access.
        host = f"[{settings.ip}]" if ":" in settings.ip else settings.ip
        base_url = f"http://{host}:{settings.port}"
        state = "on" if on else "off"
        try:
            async with asyncio.timeout(12):
                async with httpx.AsyncClient(
                    base_url=base_url,
                    timeout=5,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                ) as client:
                    await self._request(client, settings, "/zeroconf/switch", {"switch": state})
                    # DIY requires at least 200 ms between requests.
                    await asyncio.sleep(0.2)
                    result = await self._request(client, settings, "/zeroconf/info", {})
                    data = result.get("data")
                    if not isinstance(data, dict) or data.get("switch") != state:
                        raise ApplicationError(
                            ErrorCode.DEPENDENCY_UNAVAILABLE,
                            "Команда отправлена, но состояние реле не подтверждено",
                        )
                    return state
        except (httpx.HTTPError, TimeoutError, ValueError) as error:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Реле недоступно или вернуло некорректный ответ; проверьте его состояние",
            ) from error

    @staticmethod
    async def _request(
        client: httpx.AsyncClient,
        settings: RelaySettings,
        path: str,
        data: dict[str, str],
    ) -> dict[str, typing.Any]:
        async with client.stream(
            "POST", path, json={"deviceid": settings.deviceid, "data": data}
        ) as response:
            if response.status_code != 200:
                raise ApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Реле вернуло ошибку HTTP")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 16_384:
                    raise ValueError("Relay response is too large")
            result = json.loads(body)
            if not isinstance(result, dict) or type(result.get("error")) is not int:
                raise ValueError("Relay response has no valid error code")
            if result["error"] != 0:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    f"Реле отклонило команду (DIY error {result['error']})",
                )
            return result
