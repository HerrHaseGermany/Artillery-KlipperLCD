import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

from .i18n import KEYBOARD_BY_KEY, LANGUAGES


def rgb888_to_565(color: str) -> int:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError("Expected a six-digit RGB color")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)


def blend_rgb888(foreground: str, background: str, amount: float) -> str:
    """Blend an accent into a UI surface and return a six-digit RGB color."""
    if not 0.0 <= amount <= 1.0:
        raise ValueError("Blend amount must be between zero and one")

    def channels(color: str) -> tuple[int, int, int]:
        value = color.lstrip("#")
        if len(value) != 6:
            raise ValueError("Expected a six-digit RGB color")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    front = channels(foreground)
    back = channels(background)
    mixed = tuple(
        round(back[index] + (front[index] - back[index]) * amount)
        for index in range(3)
    )
    return "#%02x%02x%02x" % mixed


@dataclass(frozen=True)
class Accent:
    key: str
    name: str
    color: str
    strong: str

    @property
    def nextion_color(self) -> int:
        return rgb888_to_565(self.color)

    @property
    def nextion_soft_color(self) -> int:
        return rgb888_to_565(blend_rgb888(self.color, "#20262e", 0.18))


ACCENTS = (
    Accent("orange", "Orange", "#efa53b", "#d98920"),
    Accent("blue", "Blau", "#3da5ff", "#268be0"),
    Accent("green", "Grün", "#45bd82", "#2e9c68"),
    Accent("purple", "Violett", "#a579ff", "#875ee0"),
    Accent("red", "Rot", "#e45b60", "#cd4248"),
)
ACCENT_BY_KEY: Dict[str, Accent] = {accent.key: accent for accent in ACCENTS}


@dataclass(frozen=True)
class ScreenSettings:
    accent: str = "orange"
    language: str = "de"
    keyboard_layout: str = "de_qwertz"


class SettingsStore:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)

    def load(self) -> ScreenSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            accent = str(payload.get("accent", "orange"))
            language = str(payload.get("language", "de"))
            keyboard_layout = str(payload.get("keyboard_layout", "de_qwertz"))
        except (OSError, ValueError, TypeError):
            return ScreenSettings()
        if accent not in ACCENT_BY_KEY:
            accent = "orange"
        if language not in LANGUAGES:
            language = "de"
        if keyboard_layout not in KEYBOARD_BY_KEY:
            keyboard_layout = "de_qwertz"
        return ScreenSettings(
            accent=accent,
            language=language,
            keyboard_layout=keyboard_layout,
        )

    def save(self, settings: ScreenSettings) -> None:
        if settings.accent not in ACCENT_BY_KEY:
            raise ValueError("Unknown accent color: %s" % settings.accent)
        if settings.language not in LANGUAGES:
            raise ValueError("Unknown language: %s" % settings.language)
        if settings.keyboard_layout not in KEYBOARD_BY_KEY:
            raise ValueError("Unknown keyboard layout: %s" % settings.keyboard_layout)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": 2,
                        "accent": settings.accent,
                        "language": settings.language,
                        "keyboard_layout": settings.keyboard_layout,
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
