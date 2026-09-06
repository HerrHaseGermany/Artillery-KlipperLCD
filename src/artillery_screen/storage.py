import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

from .models import GCodeEntry, USBVolume


GCODE_SUFFIXES = {".gcode", ".gco", ".g"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class StorageError(RuntimeError):
    pass


def _safe_name(value: str, fallback: str) -> str:
    result = SAFE_NAME.sub("_", value).strip("._")
    return result or fallback


def _inside(root: Path, relative: str = "") -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise StorageError("Pfad liegt außerhalb des Datenträgers") from exc
    return candidate


class USBMediaManager:
    def __init__(
        self,
        mount_root: str = "/media/artillery",
        import_root: str = "/home/biqu/printer_data/gcodes/.artillery-usb",
        require_mount: bool = True,
    ):
        self.mount_root = Path(mount_root)
        self.import_root = Path(import_root)
        self.require_mount = require_mount

    def volumes(self) -> List[USBVolume]:
        if not self.mount_root.is_dir():
            return []
        volumes = []
        for path in self.mount_root.iterdir():
            if not path.is_dir():
                continue
            if self.require_mount and not path.is_mount():
                continue
            volumes.append(
                USBVolume(
                    name=path.name,
                    path=str(path),
                    label=self._volume_label(path.name),
                )
            )
        return sorted(volumes, key=lambda volume: volume.display_name.casefold())

    @staticmethod
    def _volume_label(device_name: str) -> str:
        labels = Path("/dev/disk/by-label")
        device = Path("/dev") / device_name
        if not labels.is_dir():
            return ""
        try:
            resolved_device = device.resolve()
            for link in labels.iterdir():
                if link.resolve() == resolved_device:
                    return link.name
        except OSError:
            return ""
        return ""

    def _volume(self, name: str) -> USBVolume:
        for volume in self.volumes():
            if volume.name == name:
                return volume
        raise StorageError("USB-Datenträger ist nicht mehr verfügbar")

    def list_directory(self, volume_name: str, relative: str = "") -> List[GCodeEntry]:
        volume = self._volume(volume_name)
        volume_root = Path(volume.path).resolve()
        directory = _inside(volume_root, relative)
        if not directory.is_dir():
            raise StorageError("USB-Ordner wurde nicht gefunden")

        entries = []
        try:
            children: Iterable[Path] = directory.iterdir()
            for child in children:
                if child.name.startswith("."):
                    continue
                is_directory = child.is_dir()
                if not is_directory and child.suffix.lower() not in GCODE_SUFFIXES:
                    continue
                stat = child.stat()
                relative_path = str(child.resolve().relative_to(volume_root))
                entries.append(
                    GCodeEntry(
                        name=child.name,
                        path=relative_path,
                        is_directory=is_directory,
                        source="usb",
                        size=stat.st_size,
                        modified=stat.st_mtime,
                        volume=volume.name,
                    )
                )
        except OSError as exc:
            raise StorageError("USB-Datenträger kann nicht gelesen werden") from exc
        return sorted(entries, key=lambda item: (not item.is_directory, item.name.casefold()))

    def import_for_print(self, entry: GCodeEntry) -> str:
        if entry.source != "usb" or entry.is_directory:
            raise StorageError("Nur eine USB-G-Code-Datei kann importiert werden")
        if Path(entry.name).suffix.lower() not in GCODE_SUFFIXES:
            raise StorageError("Dateityp wird nicht unterstützt")

        volume = self._volume(entry.volume)
        source = _inside(Path(volume.path), entry.path)
        if not source.is_file():
            raise StorageError("USB-Datei wurde nicht gefunden")

        device_directory = _safe_name(volume.display_name, "usb")
        relative_parent = Path(entry.path).parent
        safe_parts = [
            _safe_name(part, "ordner")
            for part in relative_parent.parts
            if part not in ("", ".")
        ]
        destination_directory = self.import_root / device_directory
        for part in safe_parts:
            destination_directory /= part
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = destination_directory / _safe_name(entry.name, "druck.gcode")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".import-",
            dir=str(destination_directory),
        )
        try:
            with os.fdopen(descriptor, "wb") as target, source.open("rb") as origin:
                shutil.copyfileobj(origin, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

        return str(destination.relative_to(self.import_root.parent))
