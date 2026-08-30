import asyncio
import dataclasses
import typing


class HealthCheck(typing.Protocol):
    async def check(self) -> bool:
        """Return whether the dependency is available."""


@dataclasses.dataclass(frozen=True)
class Readiness:
    ready: bool
    checks: dict[str, str]


async def check_readiness(checks: dict[str, HealthCheck]) -> Readiness:
    if not checks:
        return Readiness(ready=True, checks={"configuration": "ok"})

    names = tuple(checks)
    results = await asyncio.gather(
        *(checks[name].check() for name in names),
        return_exceptions=True,
    )
    statuses = {
        name: "ok" if result is True else "failed"
        for name, result in zip(names, results, strict=True)
    }
    return Readiness(ready=all(status == "ok" for status in statuses.values()), checks=statuses)
