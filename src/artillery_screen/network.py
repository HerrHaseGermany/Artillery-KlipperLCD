import ipaddress
import logging
import subprocess
from typing import List, Sequence

from .models import NetworkState, WifiNetwork


LOGGER = logging.getLogger(__name__)


class NetworkManagerError(RuntimeError):
    pass


def split_escaped(line: str, separator: str = ":") -> List[str]:
    fields: List[str] = []
    current: List[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == separator:
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


class NetworkManager:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def _run(
        self,
        args: Sequence[str],
        input_text: str = "",
    ) -> subprocess.CompletedProcess:
        try:
            completed = subprocess.run(
                list(args),
                input=input_text,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise NetworkManagerError(str(exc)) from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise NetworkManagerError(message or "NetworkManager command failed")
        return completed

    def scan(self) -> List[WifiNetwork]:
        result = self._run(
            [
                "nmcli",
                "-t",
                "-e",
                "yes",
                "-f",
                "IN-USE,SSID,SIGNAL,SECURITY",
                "device",
                "wifi",
                "list",
                "--rescan",
                "yes",
            ]
        )
        by_ssid = {}
        for line in result.stdout.splitlines():
            fields = split_escaped(line)
            if len(fields) != 4 or not fields[1]:
                continue
            active, ssid, signal, security = fields
            network = WifiNetwork(
                ssid=ssid,
                signal=int(signal or 0),
                security=security,
                active=active.strip() == "*",
            )
            previous = by_ssid.get(ssid)
            if (
                previous is None
                or (network.active and not previous.active)
                or (network.active == previous.active and network.signal > previous.signal)
            ):
                by_ssid[ssid] = network
        return sorted(
            by_ssid.values(),
            key=lambda item: (not item.active, -item.signal, item.ssid.casefold()),
        )

    def connect(self, network: WifiNetwork, password: str = "") -> None:
        if network.secured and not password:
            raise NetworkManagerError("Für dieses WLAN ist ein Passwort erforderlich")

        args = [
            "nmcli",
            "--ask",
            "--wait",
            str(int(self.timeout)),
            "device",
            "wifi",
            "connect",
            network.ssid,
        ]
        # --ask keeps the password out of argv and therefore out of process lists.
        secret_input = (password + "\n") if network.secured else ""
        self._run(args, input_text=secret_input)

    def state(self) -> NetworkState:
        result = self._run(
            [
                "nmcli",
                "-t",
                "-e",
                "yes",
                "-f",
                (
                    "GENERAL.DEVICE,GENERAL.TYPE,GENERAL.STATE,"
                    "GENERAL.CONNECTION,IP4.ADDRESS"
                ),
                "device",
                "show",
            ]
        )

        devices = []
        current = {}
        for line in result.stdout.splitlines():
            key, _, value = line.partition(":")
            if key == "GENERAL.DEVICE":
                if current:
                    devices.append(current)
                current = {"device": value.replace("\\:", ":")}
            elif current:
                current[key] = value.replace("\\:", ":")
        if current:
            devices.append(current)

        connected = False
        ssid = ""
        wifi_ip_address = ""
        lan_ip_address = ""
        for device in devices:
            if not device.get("GENERAL.STATE", "").startswith("100"):
                continue
            connected = True
            raw_address = next(
                (
                    value
                    for key, value in device.items()
                    if key.startswith("IP4.ADDRESS") and value
                ),
                "",
            )
            address = ""
            if raw_address:
                try:
                    address = str(ipaddress.ip_interface(raw_address).ip)
                except ValueError:
                    address = raw_address.split("/", 1)[0]

            device_type = device.get("GENERAL.TYPE", "")
            if device_type == "wifi" and not wifi_ip_address:
                wifi_ip_address = address
                ssid = device.get("GENERAL.CONNECTION", "")
            elif device_type == "ethernet" and not lan_ip_address:
                lan_ip_address = address

        return NetworkState(
            connected=connected,
            ssid=ssid,
            ip_address=wifi_ip_address or lan_ip_address,
            wifi_ip_address=wifi_ip_address,
            lan_ip_address=lan_ip_address,
        )
