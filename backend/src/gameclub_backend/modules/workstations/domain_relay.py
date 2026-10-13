import dataclasses
import ipaddress
import re


@dataclasses.dataclass(frozen=True)
class RelaySettings:
    ip: str
    port: int
    deviceid: str

    def __post_init__(self) -> None:
        address = ipaddress.ip_address(self.ip)
        networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
        if "%" in self.ip or not any(address in ipaddress.ip_network(n) for n in networks):
            raise ValueError("Relay IP must be a private LAN address")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("Relay port must be between 1 and 65535")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.deviceid):
            raise ValueError("Relay deviceid must contain 1–128 letters, digits, _ or -")
        object.__setattr__(self, "ip", str(address))
