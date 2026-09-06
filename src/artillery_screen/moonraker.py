import logging
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

import requests

from .models import GCodeEntry, PrinterState, SystemInfo, UpdateStatus


LOGGER = logging.getLogger(__name__)


class MoonrakerError(RuntimeError):
    pass


class MoonrakerClient:
    OBJECT_QUERY = (
        "extruder&heater_bed&fan&gcode_move&print_stats&toolhead&virtual_sdcard&probe"
    )

    def __init__(self, base_url: str, timeout: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = self.session.get(
            self.base_url + path,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise MoonrakerError(str(payload["error"]))
        return payload["result"]

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            self.base_url + path,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise MoonrakerError(str(body["error"]))
        return body.get("result", {})

    def printer_state(self) -> PrinterState:
        try:
            server = self._get("/server/info")
            result = self._get(
                "/printer/objects/query?" + self.OBJECT_QUERY
            )
        except (requests.RequestException, ValueError, KeyError, MoonrakerError) as exc:
            LOGGER.warning("Moonraker is unavailable: %s", exc)
            return PrinterState()

        status = result.get("status", {})
        extruder = status.get("extruder", {})
        bed = status.get("heater_bed", {})
        fan = status.get("fan", {})
        stats = status.get("print_stats", {})
        toolhead = status.get("toolhead", {})
        sdcard = status.get("virtual_sdcard", {})
        gcode_move = status.get("gcode_move", {})
        probe = status.get("probe", {})
        position = toolhead.get("position", [0.0, 0.0, 0.0])
        homing_origin = gcode_move.get("homing_origin", [0.0, 0.0, 0.0])

        return PrinterState(
            connected=bool(server.get("klippy_connected")),
            klippy_state=str(server.get("klippy_state", "offline")),
            print_state=str(stats.get("state", "standby")),
            filename=str(stats.get("filename", "")),
            nozzle_temperature=float(extruder.get("temperature", 0.0)),
            nozzle_target=float(extruder.get("target", 0.0)),
            bed_temperature=float(bed.get("temperature", 0.0)),
            bed_target=float(bed.get("target", 0.0)),
            fan_speed=max(0.0, min(1.0, float(fan.get("speed", 0.0)))),
            speed_factor=max(0.0, float(gcode_move.get("speed_factor", 1.0))),
            extrude_factor=max(0.0, float(gcode_move.get("extrude_factor", 1.0))),
            progress=max(0.0, min(1.0, float(sdcard.get("progress", 0.0)))),
            print_duration=max(0.0, float(stats.get("print_duration", 0.0))),
            total_duration=max(0.0, float(stats.get("total_duration", 0.0))),
            x=float(position[0]) if len(position) > 0 else 0.0,
            y=float(position[1]) if len(position) > 1 else 0.0,
            z=float(position[2]) if len(position) > 2 else 0.0,
            homed_axes=str(toolhead.get("homed_axes", "")),
            z_offset=float(homing_origin[2]) if len(homing_origin) > 2 else 0.0,
            probe_triggered=bool(probe.get("last_query", False)),
        )

    def run_gcode(self, script: str) -> None:
        self._post("/printer/gcode/script", {"script": script})

    def emergency_stop(self) -> None:
        self._post("/printer/emergency_stop", {})

    def system_info(self) -> SystemInfo:
        server = self._get("/server/info")
        printer = self._get("/printer/info")
        machine = self._get("/machine/system_info").get("system_info", {})
        distribution = machine.get("distribution", {})
        return SystemInfo(
            hostname=str(printer.get("hostname", "–")),
            distribution=str(distribution.get("name", "–")),
            klipper_version=str(printer.get("software_version", "–")),
            moonraker_version=str(server.get("moonraker_version", "–")),
            api_version=str(server.get("api_version_string", "–")),
        )

    def restart_klipper(self) -> None:
        self._post("/printer/restart", {})

    def firmware_restart(self) -> None:
        self._post("/printer/firmware_restart", {})

    def reboot_host(self) -> None:
        self._post("/machine/reboot", {})

    def shutdown_host(self) -> None:
        self._post("/machine/shutdown", {})

    @staticmethod
    def _parse_update_status(result: Dict[str, Any]) -> UpdateStatus:
        available = 0
        for name, item in result.get("version_info", {}).items():
            if name == "system":
                if int(item.get("package_count", 0)) > 0:
                    available += 1
                continue
            current = str(item.get("version", ""))
            remote = str(item.get("remote_version", ""))
            commits = int(item.get("commits_behind_count", 0))
            if commits > 0 or (current and remote and current != remote):
                available += 1
        return UpdateStatus(
            available=available,
            busy=bool(result.get("busy", False)),
        )

    def update_status(self) -> UpdateStatus:
        return self._parse_update_status(self._get("/machine/update/status"))

    def refresh_updates(self) -> UpdateStatus:
        return self._parse_update_status(
            self._post("/machine/update/refresh", {})
        )

    def install_updates(self) -> None:
        self._post("/machine/update/upgrade", {})

    def list_gcodes(self, relative_path: str = "") -> List[GCodeEntry]:
        requested_path = PurePosixPath(relative_path)
        if requested_path.is_absolute() or ".." in requested_path.parts:
            raise ValueError("G-Code-Pfad muss relativ zur virtual_sdcard bleiben")
        clean_path = "" if str(requested_path) == "." else str(requested_path)
        result = self._get(
            "/server/files/directory",
            {
                "path": "gcodes" + ("/" + clean_path if clean_path else ""),
                "extended": "true",
            },
        )
        entries = []
        for item in result.get("dirs", []):
            name = str(item.get("dirname", ""))
            if not name:
                continue
            path = str(PurePosixPath(clean_path) / name) if clean_path else name
            entries.append(
                GCodeEntry(
                    name=name,
                    path=path,
                    is_directory=True,
                    source="internal",
                    modified=float(item.get("modified", 0.0)),
                )
            )
        for item in result.get("files", []):
            name = str(item.get("filename", ""))
            if not name:
                continue
            path = str(PurePosixPath(clean_path) / name) if clean_path else name
            entries.append(
                GCodeEntry(
                    name=name,
                    path=path,
                    is_directory=False,
                    source="internal",
                    size=int(item.get("size", 0)),
                    modified=float(item.get("modified", 0.0)),
                )
            )
        return sorted(entries, key=lambda item: (not item.is_directory, item.name.casefold()))

    def start_print(self, filename: str) -> None:
        response = self.session.post(
            self.base_url + "/printer/print/start",
            params={"filename": filename},
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise MoonrakerError(str(body["error"]))

    def pause_print(self) -> None:
        self._post("/printer/print/pause", {})

    def resume_print(self) -> None:
        self._post("/printer/print/resume", {})

    def cancel_print(self) -> None:
        self._post("/printer/print/cancel", {})

    def list_macros(self) -> List[str]:
        result = self._get("/printer/objects/list")
        prefix = "gcode_macro "
        return sorted(
            object_name[len(prefix):]
            for object_name in result.get("objects", [])
            if object_name.startswith(prefix)
        )
