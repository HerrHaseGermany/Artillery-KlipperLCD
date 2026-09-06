from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PrinterState:
    connected: bool = False
    klippy_state: str = "offline"
    print_state: str = "standby"
    filename: str = ""
    nozzle_temperature: float = 0.0
    nozzle_target: float = 0.0
    bed_temperature: float = 0.0
    bed_target: float = 0.0
    fan_speed: float = 0.0
    speed_factor: float = 1.0
    extrude_factor: float = 1.0
    progress: float = 0.0
    print_duration: float = 0.0
    total_duration: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    homed_axes: str = ""
    z_offset: float = 0.0
    probe_triggered: bool = False


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    active: bool = False

    @property
    def secured(self) -> bool:
        return bool(self.security and self.security != "--")


@dataclass(frozen=True)
class NetworkState:
    connected: bool = False
    ssid: str = ""
    ip_address: str = ""
    wifi_ip_address: str = ""
    lan_ip_address: str = ""
    signal: Optional[int] = None


@dataclass(frozen=True)
class SystemInfo:
    hostname: str = "–"
    distribution: str = "–"
    klipper_version: str = "–"
    moonraker_version: str = "–"
    api_version: str = "–"


@dataclass(frozen=True)
class UpdateStatus:
    available: int = 0
    busy: bool = False


@dataclass(frozen=True)
class GCodeEntry:
    name: str
    path: str
    is_directory: bool
    source: str
    size: int = 0
    modified: float = 0.0
    volume: str = ""


@dataclass(frozen=True)
class USBVolume:
    name: str
    path: str
    label: str = ""

    @property
    def display_name(self) -> str:
        return self.label or self.name
