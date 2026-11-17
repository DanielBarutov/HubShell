import math
import time
from collections import OrderedDict

from redis.asyncio import Redis

_LIMIT = 10
_WINDOW_SECONDS = 900

# Set the expiry in the same operation as the first increment.
_RESERVE = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then
    return math.max(1, redis.call('TTL', KEYS[1]))
end
if count == 0 then
    redis.call('SET', KEYS[1], 1, 'EX', ARGV[2])
else
    redis.call('INCR', KEYS[1])
end
return 0
"""


class LoginRateLimit:
    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    async def reserve(self, ip: str) -> int:
        """Reserve one attempt; return seconds to retry, or zero if admitted."""
        if self._redis is not None:
            return await self._redis.eval(
                _RESERVE, 1, f"gameclub:auth:operator-login:{ip}", _LIMIT, _WINDOW_SECONDS
            )

        # shortcut: limits are per process without Redis, configure Redis for shared deployments.
        now = time.monotonic()
        while self._windows and next(iter(self._windows.values()))[0] <= now:
            self._windows.popitem(last=False)
        expires, count = self._windows.get(ip, (now + _WINDOW_SECONDS, 0))
        if count >= _LIMIT:
            return math.ceil(expires - now)
        self._windows[ip] = (expires, count + 1)
        return 0
