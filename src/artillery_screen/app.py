import argparse
import logging
import posixpath
import re
import signal
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Dict, List, Optional

import requests

from .i18n import (
    KEYBOARD_BY_KEY,
    KEYBOARD_LAYOUTS,
    LANGUAGES,
    LANGUAGE_NAMES,
    translate,
)
from .models import GCodeEntry, NetworkState, PrinterState, WifiNetwork
from .moonraker import MoonrakerClient, MoonrakerError
from .network import NetworkManager, NetworkManagerError
from .nextion import NextionTransport, TouchEvent
from .protocol import Action, PROTOCOL_VERSION, Page, action_for_touch
from .settings import ACCENTS, ACCENT_BY_KEY, ScreenSettings, SettingsStore
from .storage import StorageError, USBMediaManager
from .ui_labels import UI_LABELS, translate_label


LOGGER = logging.getLogger(__name__)
WIFI_SYMBOLS = (
    "!", "@", "#", "$", "%", "^", "&", "*", "(", ")",
    "-", "_", "=", "+", "[", "]", "{", "}", "\\", "|",
    ";", ":", "'", '"', ",", ".", "<", ">", "/",
    "?", "`", "~", " ", ".", "-", "_",
)
FILE_SORT_MODES = (
    ("name_asc", "sort_name_asc_short", "sort_name_asc"),
    ("name_desc", "sort_name_desc_short", "sort_name_desc"),
    ("newest", "sort_newest_short", "sort_newest"),
    ("oldest", "sort_oldest_short", "sort_oldest"),
)
TEMPERATURE_PRESETS = (
    ("preset_off", 0, 0),
    ("PLA", 200, 60),
    ("PETG", 235, 75),
    ("ABS", 250, 100),
)
NOZZLE_MAX = 300
BED_MAX = 110
BOOT_PICTURE = 70
ORANGE_PAGE_PICTURES = {
    "home": 132,
    "move": 133,
    "temperature": 134,
    "files": 135,
    "print": 136,
    "tune": 137,
    "bed": 138,
    "macros": 139,
    "settings": 140,
    "wifi": 141,
    "wifi_password": 142,
    "wifi_symbols": 143,
    "accent": 144,
    "system": 145,
    "dialog": 146,
}
ACCENT_PICTURE_ORDER = (
    "home",
    "move",
    "temperature",
    "files",
    "print",
    "tune",
    "bed",
    "macros",
    "settings",
    "wifi",
    "wifi_password",
    "wifi_symbols",
    "accent",
    "system",
    "dialog",
)
ACCENT_PICTURE_BASES = {
    "blue": 72,
    "green": 87,
    "purple": 102,
    "red": 117,
}
BACKGROUND_COLOR = 4259
SURFACE_COLOR = 8485
LINE_COLOR = 14857
TEXT_COLOR = 63423
MUTED_COLOR = 42391
DANGER_COLOR = 58059
DARK_TEXT_COLOR = 4225
DARK_PANEL_COLOR = 2178
GOOD_COLOR = 17904
GOOD_SURFACE_COLOR = 6533
GOOD_LINE_COLOR = 13000


def format_duration(seconds: float) -> str:
    total_minutes = max(0, round(seconds)) // 60
    hours, minutes = divmod(total_minutes, 60)
    return "%02d:%02d" % (hours, minutes)


def sort_gcode_entries(entries: List[GCodeEntry], mode: str) -> List[GCodeEntry]:
    """Sort folders before files, then apply the selected ordering per group."""

    def sort_group(group: List[GCodeEntry]) -> List[GCodeEntry]:
        ordered = sorted(group, key=lambda entry: entry.name.casefold())
        if mode == "name_desc":
            ordered.reverse()
        elif mode == "newest":
            ordered.sort(key=lambda entry: entry.modified, reverse=True)
        elif mode == "oldest":
            ordered.sort(key=lambda entry: entry.modified)
        return ordered

    directories = [entry for entry in entries if entry.is_directory]
    files = [entry for entry in entries if not entry.is_directory]
    return sort_group(directories) + sort_group(files)


class ArtilleryScreen:
    WIFI_ROWS = 5
    FILE_ROWS = 5
    MACRO_ROWS = 6

    def __init__(
        self,
        display: NextionTransport,
        moonraker: MoonrakerClient,
        network: NetworkManager,
        settings: SettingsStore,
        usb_media: Optional[USBMediaManager] = None,
        poll_interval: float = 0.5,
    ):
        self.display = display
        self.moonraker = moonraker
        self.network = network
        self.settings = settings
        self.usb_media = usb_media or USBMediaManager()
        self.poll_interval = poll_interval
        self.running = False
        self.current_page = Page.BOOT
        self._last_fields: Dict[str, object] = {}
        self._last_poll = 0.0
        self._last_network_poll = 0.0
        self._printer_state = PrinterState()
        self._network_state = NetworkState()
        self._wifi_networks: List[WifiNetwork] = []
        self._wifi_offset = 0
        self._selected_wifi: Optional[WifiNetwork] = None
        self._wifi_password = ""
        self._wifi_input_mode = 0
        self._file_source = "internal"
        self._file_path = ""
        self._file_volume = ""
        self._file_entries: List[GCodeEntry] = []
        self._file_offset = 0
        self._selected_file: Optional[GCodeEntry] = None
        self._file_sort_index = 2
        self._move_step = 1.0
        self._force_move_enabled = False
        self._macro_names: List[str] = []
        self._macro_offset = 0
        self._selected_macro = ""
        saved_settings = self.settings.load()
        self._language = saved_settings.language
        self._keyboard_layout = saved_settings.keyboard_layout
        self._accent_index = next(
            index for index, accent in enumerate(ACCENTS) if accent.key == saved_settings.accent
        )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="screen-io")
        self._scan_future: Optional[Future] = None
        self._connect_future: Optional[Future] = None
        self._print_future: Optional[Future] = None
        self._system_future: Optional[Future] = None
        self._pending_dialog_action: Optional[str] = None

    def start(self) -> None:
        self.running = True
        self.display.command("bkcmd=3")
        self._render_static_labels(Page.BOOT)
        self.display.set_value("boot.jProgress", 10)
        self.display.set_text("boot.tStatus", self._tr("boot_connecting"))
        self.display.set_value("boot.vaProtocol", PROTOCOL_VERSION)
        self.display.set_value("boot.jProgress", 30)
        self.apply_accent(self._accent_index, persist=False)
        self.display.set_value("boot.jProgress", 45)
        self._printer_state = self.moonraker.printer_state()
        self.display.set_text(
            "boot.tStatus",
            self._tr("boot_connected")
            if self._printer_state.connected
            else self._tr("boot_no_connection"),
        )
        self.display.set_value("boot.jProgress", 75)
        self.update_network_status()
        self.display.set_value("boot.jProgress", 95)
        self.display.set_value("boot.jProgress", 100)
        self.show_page(Page.HOME)
        now = time.monotonic()
        self._last_poll = now
        self._last_network_poll = now

        while self.running:
            for event in self.display.poll():
                if isinstance(event, TouchEvent):
                    action = action_for_touch(
                        event.page_id,
                        event.component_id,
                        event.pressed,
                    )
                    if action is not None:
                        self.handle_action(action)

            self.process_background_jobs()
            now = time.monotonic()
            if now - self._last_poll >= self.poll_interval:
                self._last_poll = now
                self._printer_state = self.moonraker.printer_state()
                if self.current_page == Page.HOME:
                    self.render_home(self._printer_state)
                elif self.current_page == Page.MOVE:
                    self.render_move(self._printer_state)
                elif self.current_page == Page.TEMPERATURE:
                    self.render_temperature(self._printer_state)
                elif self.current_page == Page.PRINT:
                    self.render_print(self._printer_state)
                elif self.current_page == Page.TUNE:
                    self.render_tune(self._printer_state)
                elif self.current_page == Page.BED:
                    self.render_bed(self._printer_state)
            if now - self._last_network_poll >= 5.0:
                self._last_network_poll = now
                self.update_network_status()
            time.sleep(0.02)

    def stop(self) -> None:
        self.running = False
        self._executor.shutdown(wait=False)

    def show_page(self, page: Page) -> None:
        if self.current_page == Page.MOVE and page != Page.MOVE:
            self._force_move_enabled = False
        self.current_page = page
        self.display.show_page(page.name.lower())
        self._apply_page_background(page)
        prefix = page.name.lower() + "."
        for field in list(self._last_fields):
            if field.startswith(prefix):
                del self._last_fields[field]
        self._clear_live_readouts(page)
        self._render_static_labels(page)
        if page == Page.HOME:
            self.render_home(self._printer_state)
            self.render_network_status()
        elif page == Page.MOVE:
            accent = ACCENTS[self._accent_index]
            for component in ("tX", "tY", "tZ"):
                self.display.command("move.%s.bco=8485" % component)
                self.display.command(
                    "move.%s.pco=%d" % (component, accent.nextion_color)
                )
            self.display.command("move.tStep.bco=4259")
            self.display.command("move.tStep.pco=42391")
            self.display.command("move.tStatus.bco=4259")
            self.display.command("move.tStatus.pco=42391")
            self.render_move(self._printer_state)
        elif page == Page.TEMPERATURE:
            accent = ACCENTS[self._accent_index]
            for component in ("tNozzle", "tBed", "tFan"):
                self.display.command("temperature.%s.bco=8485" % component)
                self.display.command(
                    "temperature.%s.pco=%d" % (component, accent.nextion_color)
                )
            self.display.command("temperature.tStatus.bco=4259")
            self.display.command("temperature.tStatus.pco=42391")
            self.render_temperature(self._printer_state)
            self._set_text(
                "temperature.tStatus",
                self._tr("target_applied")
                if self._printer_state.connected
                else self._tr("klipper_offline"),
            )
        elif page == Page.PRINT:
            accent = ACCENTS[self._accent_index]
            for component in ("tProgress", "tNozzle", "tBed"):
                self.display.command("print.%s.bco=8485" % component)
                self.display.command(
                    "print.%s.pco=%d" % (component, accent.nextion_color)
                )
            for component in ("tFile", "tState", "tElapsed", "tStatus"):
                self.display.command("print.%s.bco=4259" % component)
                self.display.command("print.%s.pco=42391" % component)
            self.render_print(self._printer_state)
        elif page == Page.TUNE:
            accent = ACCENTS[self._accent_index]
            for component in ("tSpeed", "tFlow", "tFan"):
                self.display.command("tune.%s.bco=8485" % component)
                self.display.command(
                    "tune.%s.pco=%d" % (component, accent.nextion_color)
                )
            self.display.command("tune.tStatus.bco=4259")
            self.display.command("tune.tStatus.pco=42391")
            self.render_tune(self._printer_state)
        elif page == Page.BED:
            accent = ACCENTS[self._accent_index]
            for component in ("tZ", "tOffset", "tProbe"):
                self.display.command("bed.%s.bco=8485" % component)
                self.display.command(
                    "bed.%s.pco=%d" % (component, accent.nextion_color)
                )
            self.display.command("bed.tStatus.bco=4259")
            self.display.command("bed.tStatus.pco=42391")
            self.render_bed(self._printer_state)
        elif page == Page.MACROS:
            self.refresh_macros()
        elif page == Page.SETTINGS:
            self.display.command("settings.tWifiI.bco=10631")
            self.display.command("settings.tLanIP.bco=10631")
            self.display.command("settings.tAccen.bco=8485")
            self.render_network_status()
            self.render_accent_status()
        elif page == Page.WIFI:
            for row in range(self.WIFI_ROWS):
                self.display.command("wifi.tSSID%d.bco=8485" % row)
                self.display.command("wifi.tSSID%d.pco=63423" % row)
                self.display.command("wifi.tMeta%d.bco=8485" % row)
                self.display.command("wifi.tMeta%d.pco=42391" % row)
            self.display.command("wifi.tStatus.bco=%d" % BACKGROUND_COLOR)
            self.display.command("wifi.tStatus.pco=%d" % MUTED_COLOR)
            self._render_wifi_connection_card()
            self.render_wifi_list()
        elif page == Page.WIFI_PASSWORD:
            accent = ACCENTS[self._accent_index]
            self.display.command("wifi_password.tSSID.bco=8485")
            self.display.command("wifi_password.tSSID.pco=63423")
            self.display.command("wifi_password.tPass.bco=5923")
            self.display.command("wifi_password.tPass.pco=63423")
            self.display.command("wifi_password.tPass.pw=1")
            self.display.command("wifi_password.tStatus.bco=4259")
            self.display.command("wifi_password.tStatus.pco=42391")
            self.display.command(
                "wifi_password.tCase.bco=%d" % accent.nextion_soft_color
            )
            self.display.command(
                "wifi_password.tCase.pco=%d" % accent.nextion_color
            )
            self.render_wifi_password()
        elif page == Page.FILES:
            self.refresh_files()
        elif page == Page.SYSTEM:
            for component in ("tHost", "tKlipper", "tMoon", "tNetwork"):
                self.display.command("system.%s.bco=8485" % component)
                self.display.command("system.%s.pco=63423" % component)
                self.display.command("system.%s.xcen=0" % component)
            self.display.command("system.tStatus.bco=4259")
            self.display.command("system.tStatus.pco=42391")
            self.refresh_system_info()
        elif page == Page.DIALOG:
            self.display.command("dialog.tTitle.bco=8485")
            self.display.command("dialog.tTitle.pco=63423")
            self.display.command("dialog.tMessage.bco=8485")
            self.display.command("dialog.tMessage.pco=42391")
            self.display.command("dialog.tMessage.isbr=1")
        elif page == Page.ACCENT:
            self.display.command(
                "accent.tCurrent.bco=%d"
                % ACCENTS[self._accent_index].nextion_soft_color
            )
            self.display.command("accent.tCurrent.xcen=0")
            self.render_accent_status()
            self.render_locale_status()

    def _set_text(self, component: str, value: object) -> None:
        if self._last_fields.get(component) != value:
            self.display.set_text(component, value)
            self._last_fields[component] = value

    def _set_value(self, component: str, value: int) -> None:
        if self._last_fields.get(component) != value:
            self.display.set_value(component, value)
            self._last_fields[component] = value

    def _clear_live_readouts(self, page: Page) -> None:
        """Remove HMI editor placeholders before live values are rendered."""
        components = {
            Page.HOME: (
                "tNozzle", "tBed", "tState", "tFile", "tConnection", "tWifi",
            ),
            Page.MOVE: ("tX", "tY", "tZ", "tStep", "tStatus", "tForce"),
            Page.TEMPERATURE: ("tNozzle", "tBed", "tFan", "tStatus"),
            Page.FILES: (
                "tPath", "tSource", "tSort", "tStatus",
                "tName0", "tName1", "tName2", "n3x", "tName4",
                "tMeta0", "tMeta1", "tMeta2", "tMeta3", "tMeta4",
            ),
            Page.PRINT: (
                "tFile", "tState", "tProgress", "tElapsed",
                "tNozzle", "tBed", "tStatus",
            ),
            Page.TUNE: ("tSpeed", "tFlow", "tFan", "tStatus"),
            Page.BED: ("tZ", "tOffset", "tProbe", "tStatus"),
            Page.MACROS: (
                "tPage", "tStatus", "tName0", "tName1", "tName2",
                "tName3", "tName4", "tName5",
            ),
            Page.SETTINGS: ("tWifiI", "tLanIP", "tAccen"),
            Page.WIFI: (
                "tStatus", "tSSID0", "tSSID1", "tSSID2", "tSSID3", "tSSID4",
                "tMeta0", "tMeta1", "tMeta2", "tMeta3", "tMeta4",
            ),
            Page.WIFI_PASSWORD: ("tSSID", "tPass", "tCase", "tStatus"),
            Page.SYSTEM: ("tHost", "tKlipper", "tMoon", "tNetwork", "tStatus"),
            Page.DIALOG: ("tTitle", "tMessage"),
            Page.ACCENT: ("tCurrent",),
        }.get(page, ())
        prefix = page.name.lower()
        for component in components:
            self.display.set_text("%s.%s" % (prefix, component), "")

    def _picture_id(self, page: Page, symbols: bool = False) -> int:
        if page == Page.BOOT:
            return BOOT_PICTURE
        picture_key = (
            "wifi_symbols"
            if page == Page.WIFI_PASSWORD and symbols
            else page.name.lower()
        )
        accent_key = ACCENTS[self._accent_index].key
        if accent_key == "orange":
            return ORANGE_PAGE_PICTURES[picture_key]
        return (
            ACCENT_PICTURE_BASES[accent_key]
            + ACCENT_PICTURE_ORDER.index(picture_key)
        )

    def _apply_page_background(self, page: Page, symbols: bool = False) -> None:
        self.display.command(
            "%s.pic=%d" % (page.name.lower(), self._picture_id(page, symbols))
        )

    def _draw_text(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        value: object,
        color: int = TEXT_COLOR,
        align: int = 0,
    ) -> None:
        if not hasattr(self.display, "command"):
            return
        text = str(value).replace("\\", "/").replace('"', "'")
        text = "\r".join(" ".join(line.split()) for line in text.split("\r"))
        self.display.command(
            'xstr %d,%d,%d,%d,0,%d,%d,%d,1,3,"%s"'
            % (x, y, width, height, color, BACKGROUND_COLOR, align, text)
        )

    def _render_static_labels(self, page: Page) -> None:
        colors = {
            "accent": ACCENTS[self._accent_index].nextion_color,
            "text": TEXT_COLOR,
            "muted": MUTED_COLOR,
            "danger": DANGER_COLOR,
            "dark": DARK_TEXT_COLOR,
        }
        for label in UI_LABELS.get(page.name.lower(), ()):
            self._draw_text(
                label.x,
                label.y,
                label.width,
                label.height,
                translate_label(self._language, label.source),
                color=colors[label.role],
                align=label.align,
            )

    def _render_boot_logo(self) -> None:
        """Draw the Artillery mark in the currently selected accent color."""
        color = ACCENTS[self._accent_index].nextion_color
        segments = (
            (122, 87, 101, 100),
            (101, 100, 101, 148),
            (101, 148, 122, 161),
            (122, 106, 132, 112),
            (132, 138, 132, 112),
            (132, 138, 122, 144),
            (150, 87, 171, 100),
            (171, 100, 171, 148),
            (171, 148, 150, 161),
            (150, 106, 140, 112),
            (140, 138, 140, 112),
            (140, 138, 150, 144),
        )
        for x1, y1, x2, y2 in segments:
            for offset in range(-3, 4):
                self.display.command(
                    "line %d,%d,%d,%d,%d"
                    % (x1 + offset, y1, x2 + offset, y2, color)
                )

    def _render_keyboard_labels(self) -> None:
        layout = KEYBOARD_BY_KEY[self._keyboard_layout]
        if self._wifi_input_mode == 2:
            labels = ["SPC" if key == " " else key for key in WIFI_SYMBOLS]
        elif self._wifi_input_mode == 1:
            labels = [key.lower() if key.isalpha() else key for key in layout.keys]
        else:
            labels = list(layout.keys)
        rows = (
            (range(0, 10), 12, 209, 22, 25),
            (range(10, 20), 12, 245, 22, 25),
            (range(20, 29), 23, 281, 22, 25),
            (range(29, 36), 33, 317, 27, 30),
        )
        for indexes, start_x, y, width, step in rows:
            for column, key_index in enumerate(indexes):
                self._draw_text(
                    start_x + column * step,
                    y,
                    width,
                    31,
                    labels[key_index],
                    color=TEXT_COLOR,
                    align=1,
                )
        self._draw_text(12, 353, 75, 34, self._tr("keyboard_cancel"), align=1)
        self._draw_text(
            186,
            353,
            74,
            34,
            self._tr("keyboard_connect"),
            color=DARK_TEXT_COLOR,
            align=1,
        )

    def _tr(self, key: str, **values: object) -> str:
        return translate(getattr(self, "_language", "de"), key, **values)

    def _state_label(self, state: str) -> str:
        key = "state_" + state
        translated = self._tr(key)
        return state.title() if translated == key else translated

    def _save_settings(self) -> None:
        self.settings.save(
            ScreenSettings(
                accent=ACCENTS[self._accent_index].key,
                language=self._language,
                keyboard_layout=self._keyboard_layout,
            )
        )

    def _render_row_card(
        self,
        page: str,
        row: int,
        geometry: tuple[int, int, int, int],
        visible: bool,
        touch: str,
        text_components: tuple[str, ...],
        selected: bool = False,
    ) -> None:
        if not hasattr(self.display, "command"):
            return
        x, y, width, height = geometry
        if visible:
            border = (
                ACCENTS[self._accent_index].nextion_color if selected else LINE_COLOR
            )
            self.display.command(
                "fill %d,%d,%d,%d,%d"
                % (x, y, width, height, SURFACE_COLOR)
            )
            self.display.command(
                "draw %d,%d,%d,%d,%d"
                % (x, y, x + width - 1, y + height - 1, border)
            )
        else:
            self.display.command(
                "fill %d,%d,%d,%d,%d"
                % (x, y, width, height, BACKGROUND_COLOR)
            )
        enabled = 1 if visible else 0
        self.display.command("tsw %s,%d" % (touch, enabled))
        for component in text_components:
            self.display.command("vis %s,%d" % (component, enabled))
            self.display.command("tsw %s,%d" % (component, enabled))

    def render_home(self, state: PrinterState) -> None:
        if not state.connected:
            self._set_text("home.tNozzle", "– / – °C")
            self._set_text("home.tBed", "– / – °C")
            self._set_text("home.tState", self._tr("klipper_offline"))
            self._set_text("home.tFile", self._tr("no_print_selected"))
            self._set_value("home.jProgress", 0)
            self._set_text("home.tConnection", self._tr("klipper_offline"))
            return
        self._set_text(
            "home.tNozzle",
            "%d / %d °C" % (state.nozzle_temperature, state.nozzle_target),
        )
        self._set_text(
            "home.tBed",
            "%d / %d °C" % (state.bed_temperature, state.bed_target),
        )
        self._set_text(
            "home.tState",
            self._state_label(state.print_state),
        )
        self._set_text("home.tFile", state.filename or self._tr("no_print_selected"))
        self._set_value("home.jProgress", round(state.progress * 100))
        self._set_text(
            "home.tConnection",
            self._tr("klipper_connected") if state.connected else self._tr("klipper_offline"),
        )

    def render_move(self, state: PrinterState) -> None:
        self._set_text("move.tX", "%.2f" % state.x if state.connected else "–")
        self._set_text("move.tY", "%.2f" % state.y if state.connected else "–")
        self._set_text("move.tZ", "%.2f" % state.z if state.connected else "–")
        self._set_text(
            "move.tStep",
            self._tr(
                "step_width",
                value=("0,1" if self._move_step == 0.1 and self._language == "de" else "%g" % self._move_step),
            ),
        )
        self._render_move_step_selection()
        self.render_force_move()

    def _render_move_step_selection(self) -> None:
        accent = ACCENTS[self._accent_index]
        geometries = (
            (12, 361, 79, 44),
            (96, 361, 79, 44),
            (181, 361, 79, 44),
        )
        values = (0.1, 1.0, 10.0)
        labels = (
            "0,1 mm" if self._language == "de" else "0.1 mm",
            "1,0 mm" if self._language == "de" else "1.0 mm",
            "10 mm",
        )
        for geometry, value, label in zip(geometries, values, labels):
            x, y, width, height = geometry
            active = value == self._move_step
            self.display.command(
                "draw %d,%d,%d,%d,%d"
                % (
                    x,
                    y,
                    x + width - 1,
                    y + height - 1,
                    accent.nextion_color if active else LINE_COLOR,
                )
            )
            self._draw_text(
                x,
                y,
                width,
                height,
                label,
                color=accent.nextion_color if active else TEXT_COLOR,
                align=1,
            )

    def render_force_move(self) -> None:
        state_key = "move._force_enabled"
        if self._last_fields.get(state_key) != self._force_move_enabled:
            self.display.command(
                "move.tForce.bco=%d" % (12548 if self._force_move_enabled else 8485)
            )
            self.display.command("move.tForce.pco=58059")
            self._last_fields[state_key] = self._force_move_enabled
        self._set_text(
            "move.tForce",
            self._tr("force_enabled") if self._force_move_enabled else self._tr("force_disabled"),
        )

    def render_temperature(self, state: PrinterState) -> None:
        if not state.connected:
            self._set_text("temperature.tNozzle", "– / – °C")
            self._set_text("temperature.tBed", "– / – °C")
            self._set_text("temperature.tFan", "– %")
            return
        self._set_text(
            "temperature.tNozzle",
            "%d / %d °C" % (round(state.nozzle_temperature), round(state.nozzle_target)),
        )
        self._set_text(
            "temperature.tBed",
            "%d / %d °C" % (round(state.bed_temperature), round(state.bed_target)),
        )
        self._set_text("temperature.tFan", "%d %%" % round(state.fan_speed * 100))

    def render_print(self, state: PrinterState) -> None:
        if not state.connected:
            self._set_text("print.tFile", self._tr("no_active_print"))
            self._set_text("print.tState", self._tr("klipper_offline"))
            self._set_value("print.jProgress", 0)
            self._set_text("print.tProgress", "– %")
            self._set_text("print.tElapsed", "–:–")
            self._set_text("print.tNozzle", "– / – °C")
            self._set_text("print.tBed", "– / – °C")
            self._set_text("print.tStatus", self._tr("klipper_offline"))
            return
        progress = round(state.progress * 100)
        self._set_text("print.tFile", state.filename or self._tr("no_active_print"))
        self._set_text(
            "print.tState",
            self._state_label(state.print_state),
        )
        self._set_value("print.jProgress", progress)
        self._set_text("print.tProgress", "%d %%" % progress)
        self._set_text("print.tElapsed", format_duration(state.print_duration))
        self._set_text(
            "print.tNozzle",
            "%d / %d °C" % (round(state.nozzle_temperature), round(state.nozzle_target)),
        )
        self._set_text(
            "print.tBed",
            "%d / %d °C" % (round(state.bed_temperature), round(state.bed_target)),
        )
        self._set_text(
            "print.tStatus",
            self._tr("print_paused") if state.print_state == "paused" else self._tr("print_running"),
        )

    def render_tune(self, state: PrinterState) -> None:
        if not state.connected:
            self._set_text("tune.tSpeed", "– %")
            self._set_text("tune.tFlow", "– %")
            self._set_text("tune.tFan", "– %")
            self._set_text("tune.tStatus", self._tr("klipper_offline"))
            return
        self._set_text("tune.tSpeed", "%d %%" % round(state.speed_factor * 100))
        self._set_text("tune.tFlow", "%d %%" % round(state.extrude_factor * 100))
        self._set_text("tune.tFan", "%d %%" % round(state.fan_speed * 100))

    def render_bed(self, state: PrinterState) -> None:
        if not state.connected:
            self._set_text("bed.tZ", "– mm")
            self._set_text("bed.tOffset", "– mm")
            self._set_text("bed.tProbe", self._tr("klipper_offline"))
            self._set_text("bed.tStatus", self._tr("klipper_offline"))
            return
        self._set_text("bed.tZ", "%.3f mm" % state.z)
        self._set_text("bed.tOffset", "%+.3f mm" % state.z_offset)
        self._set_text(
            "bed.tProbe",
            self._tr("probe_triggered") if state.probe_triggered else self._tr("probe_open"),
        )

    def render_network_status(self) -> None:
        state = self._network_state
        if self.current_page == Page.HOME:
            label = state.ssid if state.wifi_ip_address else self._tr("wifi_disconnected")
            self._set_text("home.tWifi", label)
        elif self.current_page == Page.SETTINGS:
            self._set_text(
                "settings.tWifiI",
                "WLAN  " + (state.wifi_ip_address or "–"),
            )
            self._set_text(
                "settings.tLanIP",
                "LAN   " + (state.lan_ip_address or "–"),
            )
        elif self.current_page == Page.WIFI:
            self._render_wifi_connection_card()

    def _render_wifi_connection_card(self) -> None:
        state = self._network_state
        connected = bool(state.ssid and state.wifi_ip_address)
        if not connected:
            self.display.command(
                "fill 12,65,248,56,%d" % BACKGROUND_COLOR
            )
            return

        self.display.command(
            "fill 12,65,248,56,%d" % GOOD_SURFACE_COLOR
        )
        self.display.command(
            "draw 12,65,259,120,%d" % GOOD_LINE_COLOR
        )
        self.display.command("cirs 23,82,4,%d" % GOOD_COLOR)
        self._draw_text(34, 69, 210, 20, state.ssid, color=TEXT_COLOR)
        self._draw_text(
            34,
            91,
            210,
            18,
            "%s · %s" % (self._tr("wifi_connected"), state.wifi_ip_address),
            color=MUTED_COLOR,
        )

    def update_network_status(self) -> None:
        try:
            self._network_state = self.network.state()
        except NetworkManagerError as exc:
            LOGGER.warning("Network status failed: %s", exc)
            return
        self.render_network_status()

    def render_accent_status(self) -> None:
        accent = ACCENTS[self._accent_index]
        accent_name = self._tr("accent_name_" + accent.key)
        if self.current_page == Page.SETTINGS:
            self._set_text("settings.tAccen", accent_name)
        elif self.current_page == Page.ACCENT:
            self.display.command(
                "accent.tCurrent.pco=%d" % accent.nextion_color
            )
            self._set_text("accent.tCurrent", accent_name)
            self._set_value("accent.vaSelected", self._accent_index)

    def render_locale_status(self) -> None:
        if self.current_page != Page.ACCENT:
            return
        self._draw_text(
            24,
            382,
            224,
            24,
            self._tr("language_option", name=LANGUAGE_NAMES[self._language]),
            color=TEXT_COLOR,
            align=0,
        )
        layout = KEYBOARD_BY_KEY[self._keyboard_layout]
        self._draw_text(
            24,
            431,
            224,
            24,
            self._tr("keyboard_option", name=layout.name),
            color=TEXT_COLOR,
            align=0,
        )

    def cycle_language(self) -> None:
        index = (LANGUAGES.index(self._language) + 1) % len(LANGUAGES)
        self._language = LANGUAGES[index]
        self._last_fields.clear()
        self._save_settings()
        self.show_page(self.current_page)

    def cycle_keyboard_layout(self) -> None:
        keys = [layout.key for layout in KEYBOARD_LAYOUTS]
        index = (keys.index(self._keyboard_layout) + 1) % len(keys)
        self._keyboard_layout = keys[index]
        self._save_settings()
        self.render_locale_status()

    def handle_action(self, action: Action) -> None:
        navigation = {
            "open_home": Page.HOME,
            "open_move": Page.MOVE,
            "open_temperature": Page.TEMPERATURE,
            "open_files": Page.FILES,
            "open_print": Page.PRINT,
            "open_bed": Page.BED,
            "open_macros": Page.MACROS,
            "open_settings": Page.SETTINGS,
            "open_system": Page.SYSTEM,
            "open_wifi": Page.WIFI,
            "open_accent": Page.ACCENT,
        }
        if action.name in navigation:
            if action.name == "open_wifi" and self.current_page == Page.WIFI_PASSWORD:
                self._wifi_password = ""
            self.show_page(navigation[action.name])
            if action.name == "open_wifi":
                self.scan_wifi()
            return
        if action.name == "emergency_stop":
            self.moonraker.emergency_stop()
        elif action.name == "wifi_scan":
            self.scan_wifi()
        elif action.name == "wifi_previous":
            self._wifi_offset = max(0, self._wifi_offset - self.WIFI_ROWS)
            self.render_wifi_list()
        elif action.name == "wifi_next":
            maximum = max(0, len(self._wifi_networks) - self.WIFI_ROWS)
            self._wifi_offset = min(maximum, self._wifi_offset + self.WIFI_ROWS)
            self.render_wifi_list()
        elif action.name == "wifi_select" and action.argument is not None:
            self.select_wifi(action.argument)
        elif action.name == "wifi_connect":
            self.connect_wifi(password=self._wifi_password)
        elif action.name == "wifi_key" and action.argument is not None:
            if len(self._wifi_password) < 63:
                layout = KEYBOARD_BY_KEY[self._keyboard_layout]
                if not 0 <= action.argument < len(layout.keys):
                    return
                character = layout.keys[action.argument]
                if self._wifi_input_mode == 1 and character.isalpha():
                    character = character.lower()
                elif self._wifi_input_mode == 2:
                    character = WIFI_SYMBOLS[action.argument]
                self._wifi_password += character
                self.render_wifi_password()
        elif action.name == "wifi_shift":
            self._wifi_input_mode = (self._wifi_input_mode + 1) % 3
            self.render_wifi_password()
        elif action.name == "wifi_backspace":
            self._wifi_password = self._wifi_password[:-1]
            self.render_wifi_password()
        elif action.name == "files_internal":
            self.select_file_source("internal")
        elif action.name == "files_usb":
            self.select_file_source("usb")
        elif action.name == "files_previous":
            self._file_offset = max(0, self._file_offset - self.FILE_ROWS)
            self.render_file_list()
        elif action.name == "files_next":
            maximum = max(0, len(self._file_entries) - self.FILE_ROWS)
            self._file_offset = min(maximum, self._file_offset + self.FILE_ROWS)
            self.render_file_list()
        elif action.name == "files_up":
            self.files_up()
        elif action.name == "files_refresh":
            self.refresh_files()
        elif action.name == "files_sort":
            self.cycle_file_sort()
        elif action.name == "files_back":
            if self._file_path or self._file_volume:
                self.files_up()
            else:
                self.show_page(Page.HOME)
        elif action.name == "files_select" and action.argument is not None:
            self.select_file_row(action.argument)
        elif action.name == "files_print":
            self.start_selected_file()
        elif action.name == "print_pause_resume":
            self.toggle_print_pause()
        elif action.name == "print_cancel":
            self.request_print_cancel()
        elif action.name == "tune_speed" and action.argument is not None:
            self.adjust_tuning("speed", action.argument)
        elif action.name == "tune_flow" and action.argument is not None:
            self.adjust_tuning("flow", action.argument)
        elif action.name == "tune_fan" and action.argument is not None:
            self.adjust_tuning("fan", action.argument)
        elif action.name == "tune_reset":
            self.reset_tuning()
        elif action.name.startswith("bed_"):
            self.handle_bed_action(action)
        elif action.name == "macros_previous":
            self._macro_offset = max(0, self._macro_offset - self.MACRO_ROWS)
            self.render_macros()
        elif action.name == "macros_next":
            maximum = max(0, len(self._macro_names) - self.MACRO_ROWS)
            self._macro_offset = min(maximum, self._macro_offset + self.MACRO_ROWS)
            self.render_macros()
        elif action.name == "macros_select" and action.argument is not None:
            self.select_macro(action.argument)
        elif action.name == "macros_run":
            self.run_selected_macro()
        elif action.name == "accent_select" and action.argument is not None:
            self.apply_accent(action.argument)
        elif action.name == "language_next":
            self.cycle_language()
        elif action.name == "keyboard_next":
            self.cycle_keyboard_layout()
        elif action.name == "system_update_check":
            self.check_updates()
        elif action.name.startswith("system_"):
            self.request_system_action(action.name)
        elif action.name == "dialog_cancel":
            return_page = {
                "move_force_enable": Page.MOVE,
                "print_cancel": Page.PRINT,
                "bed_save_config": Page.BED,
            }.get(self._pending_dialog_action, Page.SYSTEM)
            self._pending_dialog_action = None
            self.show_page(return_page)
        elif action.name == "dialog_confirm":
            if self._pending_dialog_action == "move_force_enable":
                self._pending_dialog_action = None
                self._force_move_enabled = True
                self._move_step = 0.1
                self.show_page(Page.MOVE)
                self._set_text(
                    "move.tStatus",
                    self._tr("force_warning"),
                )
            elif self._pending_dialog_action == "print_cancel":
                self.confirm_print_cancel()
            elif self._pending_dialog_action == "bed_save_config":
                self.confirm_bed_save()
            else:
                self.confirm_system_action()
        elif action.name == "move_force_toggle":
            self.toggle_force_move()
        elif action.name.startswith("move_home_"):
            self.home_axis(action.name.removeprefix("move_home_"))
        elif action.name.startswith("move_") and action.name.endswith(("_minus", "_plus")):
            _prefix, axis, direction = action.name.split("_")
            self.jog_axis(axis.upper(), -1 if direction == "minus" else 1)
        elif action.name == "move_step" and action.argument is not None:
            requested_step = action.argument / 10.0
            if self._force_move_enabled and requested_step > 1.0:
                self._set_text("move.tStatus", self._tr("force_max"))
                return
            self._move_step = requested_step
            self.render_move(self._printer_state)
        elif action.name == "temperature_nozzle" and action.argument is not None:
            self.adjust_heater("extruder", action.argument)
        elif action.name == "temperature_bed" and action.argument is not None:
            self.adjust_heater("heater_bed", action.argument)
        elif action.name == "temperature_fan" and action.argument is not None:
            self.adjust_fan(action.argument)
        elif action.name == "temperature_preset" and action.argument is not None:
            self.apply_temperature_preset(action.argument)

    def apply_accent(self, index: int, persist: bool = True) -> None:
        if not 0 <= index < len(ACCENTS):
            return
        self._accent_index = index
        accent = ACCENTS[index]
        # vaAccent is a global-scope variable on the boot page. Each HMI page
        # applies it to its highlighted text, symbols and active controls.
        self.display.set_value("boot.vaAccent", accent.nextion_color)
        self.display.command("boot.jProgress.pco=%d" % accent.nextion_color)
        if self.current_page == Page.BOOT:
            self._render_boot_logo()
        self.render_accent_status()
        if persist:
            self._save_settings()
            self.show_page(self.current_page)

    def _movement_locked(self) -> bool:
        if self._printer_state.print_state in ("printing", "paused"):
            self._set_text("move.tStatus", self._tr("print_locked"))
            return True
        return False

    def home_axis(self, axis: str) -> None:
        if self._movement_locked():
            return
        self._force_move_enabled = False
        self.render_force_move()
        suffix = "" if axis == "all" else " " + axis.upper()
        try:
            self.moonraker.run_gcode("G28" + suffix)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Homing failed: %s", exc)
            self._set_text("move.tStatus", self._tr("homing_failed"))
        else:
            self._set_text(
                "move.tStatus",
                self._tr("home_all")
                if axis == "all"
                else self._tr("home_axis", axis=axis.upper()),
            )

    def jog_axis(self, axis: str, direction: int) -> None:
        if axis not in ("X", "Y", "Z") or direction not in (-1, 1):
            return
        if self._movement_locked():
            return
        distance = self._move_step * direction
        if self._force_move_enabled:
            stepper = {"X": "stepper_x", "Y": "stepper_y", "Z": "stepper_z"}[axis]
            velocity = 5 if axis == "Z" else 20
            acceleration = 100 if axis == "Z" else 500
            script = (
                "FORCE_MOVE STEPPER=%s DISTANCE=%.3f VELOCITY=%d ACCEL=%d"
                % (stepper, distance, velocity, acceleration)
            )
        else:
            feedrate = 600 if axis == "Z" else 6000
            script = "G91\nG0 %s%.3f F%d\nG90" % (axis, distance, feedrate)
        try:
            self.moonraker.run_gcode(script)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Axis movement failed: %s", exc)
            self._set_text(
                "move.tStatus",
                self._tr("force_not_enabled")
                if self._force_move_enabled
                else self._tr("movement_failed"),
            )
        else:
            self._set_text(
                "move.tStatus",
                (
                    self._tr("force_move_result", axis=axis, distance=distance)
                    if self._force_move_enabled
                    else self._tr("move_result", axis=axis, distance=distance)
                ),
            )

    def toggle_force_move(self) -> None:
        if self._movement_locked():
            return
        if self._force_move_enabled:
            self._force_move_enabled = False
            self.render_force_move()
            self._set_text("move.tStatus", self._tr("force_deactivated"))
            return
        self._pending_dialog_action = "move_force_enable"
        self.show_page(Page.DIALOG)
        self._set_text("dialog.tTitle", self._tr("force_confirm_title"))
        self._set_text(
            "dialog.tMessage",
            self._tr("force_confirm_message"),
        )

    def adjust_heater(self, heater: str, delta: int) -> None:
        if heater not in ("extruder", "heater_bed"):
            return
        current = (
            self._printer_state.nozzle_target
            if heater == "extruder"
            else self._printer_state.bed_target
        )
        maximum = NOZZLE_MAX if heater == "extruder" else BED_MAX
        target = max(0, min(maximum, round(current) + delta))
        try:
            self.moonraker.run_gcode(
                "SET_HEATER_TEMPERATURE HEATER=%s TARGET=%d" % (heater, target)
            )
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Heater target failed: %s", exc)
            self._set_text("temperature.tStatus", self._tr("temperature_failed"))
        else:
            label = self._tr("nozzle") if heater == "extruder" else self._tr("bed")
            if heater == "extruder":
                self._printer_state = replace(
                    self._printer_state,
                    nozzle_target=float(target),
                )
            else:
                self._printer_state = replace(
                    self._printer_state,
                    bed_target=float(target),
                )
            self.render_temperature(self._printer_state)
            self._set_text(
                "temperature.tStatus",
                self._tr("heater_target", label=label, target=target),
            )

    def adjust_fan(self, delta: int) -> None:
        percent = max(0, min(100, round(self._printer_state.fan_speed * 100) + delta))
        script = "M107" if percent == 0 else "M106 S%d" % round(percent * 255 / 100)
        try:
            self.moonraker.run_gcode(script)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Fan target failed: %s", exc)
            self._set_text("temperature.tStatus", self._tr("fan_failed"))
        else:
            self._printer_state = replace(
                self._printer_state,
                fan_speed=percent / 100.0,
            )
            self.render_temperature(self._printer_state)
            self._set_text(
                "temperature.tStatus",
                self._tr("part_fan", percent=percent),
            )

    def apply_temperature_preset(self, index: int) -> None:
        if not 0 <= index < len(TEMPERATURE_PRESETS):
            return
        name, nozzle, bed = TEMPERATURE_PRESETS[index]
        commands = [
            "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=%d" % nozzle,
            "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=%d" % bed,
        ]
        if index == 0:
            commands.append("M107")
        try:
            self.moonraker.run_gcode("\n".join(commands))
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Temperature preset failed: %s", exc)
            self._set_text("temperature.tStatus", self._tr("preset_failed"))
        else:
            self._printer_state = replace(
                self._printer_state,
                nozzle_target=float(nozzle),
                bed_target=float(bed),
                fan_speed=0.0 if index == 0 else self._printer_state.fan_speed,
            )
            self.render_temperature(self._printer_state)
            self._set_text(
                "temperature.tStatus",
                self._tr("heating_off")
                if index == 0
                else self._tr("preset_applied", name=name, nozzle=nozzle, bed=bed),
            )

    def toggle_print_pause(self) -> None:
        state = self._printer_state.print_state
        try:
            if state == "paused":
                self.moonraker.resume_print()
                next_state = "printing"
            elif state == "printing":
                self.moonraker.pause_print()
                next_state = "paused"
            else:
                self._set_text("print.tStatus", self._tr("no_active_print"))
                return
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Print pause/resume failed: %s", exc)
            self._set_text("print.tStatus", self._tr("print_control_failed"))
            return
        self._printer_state = replace(self._printer_state, print_state=next_state)
        self.render_print(self._printer_state)

    def request_print_cancel(self) -> None:
        if self._printer_state.print_state not in ("printing", "paused"):
            self._set_text("print.tStatus", self._tr("no_active_print"))
            return
        self._pending_dialog_action = "print_cancel"
        self.show_page(Page.DIALOG)
        self._set_text("dialog.tTitle", self._tr("cancel_print_title"))
        self._set_text(
            "dialog.tMessage",
            self._tr("cancel_print_message"),
        )

    def confirm_print_cancel(self) -> None:
        try:
            self.moonraker.cancel_print()
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Print cancellation failed: %s", exc)
            self._set_text("dialog.tMessage", self._tr("cancel_print_failed"))
            return
        self._pending_dialog_action = None
        self._printer_state = replace(
            self._printer_state,
            print_state="cancelled",
            progress=0.0,
        )
        self.show_page(Page.PRINT)
        self._set_text("print.tStatus", self._tr("print_cancelled"))

    def adjust_tuning(self, kind: str, delta: int) -> None:
        current = {
            "speed": round(self._printer_state.speed_factor * 100),
            "flow": round(self._printer_state.extrude_factor * 100),
            "fan": round(self._printer_state.fan_speed * 100),
        }.get(kind)
        if current is None:
            return
        minimum, maximum = {
            "speed": (50, 200),
            "flow": (50, 150),
            "fan": (0, 100),
        }[kind]
        value = max(minimum, min(maximum, current + delta))
        command = {
            "speed": "M220 S%d" % value,
            "flow": "M221 S%d" % value,
            "fan": "M107" if value == 0 else "M106 S%d" % round(value * 255 / 100),
        }[kind]
        try:
            self.moonraker.run_gcode(command)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Tune command failed: %s", exc)
            self._set_text("tune.tStatus", self._tr("tune_failed"))
            return
        replacements = {
            "speed": {"speed_factor": value / 100.0},
            "flow": {"extrude_factor": value / 100.0},
            "fan": {"fan_speed": value / 100.0},
        }[kind]
        self._printer_state = replace(self._printer_state, **replacements)
        self.render_tune(self._printer_state)
        self._set_text(
            "tune.tStatus",
            self._tr(
                "tune_value",
                label=self._tr("tune_" + kind),
                value=value,
            ),
        )

    def reset_tuning(self) -> None:
        try:
            self.moonraker.run_gcode("M220 S100\nM221 S100")
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Tune reset failed: %s", exc)
            self._set_text("tune.tStatus", self._tr("reset_failed"))
            return
        self._printer_state = replace(
            self._printer_state,
            speed_factor=1.0,
            extrude_factor=1.0,
        )
        self.render_tune(self._printer_state)
        self._set_text("tune.tStatus", self._tr("reset_done"))

    def handle_bed_action(self, action: Action) -> None:
        if action.name == "bed_save":
            self._pending_dialog_action = "bed_save_config"
            self.show_page(Page.DIALOG)
            self._set_text("dialog.tTitle", self._tr("save_offset_title"))
            self._set_text("dialog.tMessage", self._tr("save_offset_message"))
            return
        commands = {
            "bed_home_z": "G28 Z",
            "bed_probe": "PROBE",
            "bed_mesh_calibrate": "BED_MESH_CALIBRATE",
            "bed_mesh_load": "BED_MESH_PROFILE LOAD=default",
            "bed_mesh_clear": "BED_MESH_CLEAR",
        }
        if action.name == "bed_z_offset" and action.argument is not None:
            delta = action.argument * 0.01
            command = "SET_GCODE_OFFSET Z_ADJUST=%+.2f MOVE=1" % delta
        else:
            command = commands.get(action.name)
        if command is None:
            return
        try:
            self.moonraker.run_gcode(command)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Bed action failed: %s", exc)
            self._set_text("bed.tStatus", self._tr("bed_action_failed"))
            return
        if action.name == "bed_z_offset" and action.argument is not None:
            self._printer_state = replace(
                self._printer_state,
                z_offset=self._printer_state.z_offset + action.argument * 0.01,
            )
            self.render_bed(self._printer_state)
        self._set_text("bed.tStatus", command.replace("_", " "))

    def confirm_bed_save(self) -> None:
        try:
            self.moonraker.run_gcode("SAVE_CONFIG")
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("SAVE_CONFIG failed: %s", exc)
            self._set_text("dialog.tMessage", self._tr("save_failed"))
            return
        self._pending_dialog_action = None
        self.show_page(Page.BED)
        self._set_text("bed.tStatus", self._tr("configuration_saved"))

    def refresh_macros(self) -> None:
        try:
            self._macro_names = self.moonraker.list_macros()
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Macro list failed: %s", exc)
            self._macro_names = []
            self._set_text("macros.tStatus", self._tr("macros_unavailable"))
        self._macro_offset = min(self._macro_offset, max(0, len(self._macro_names) - self.MACRO_ROWS))
        self.render_macros()

    def render_macros(self) -> None:
        visible = self._macro_names[self._macro_offset : self._macro_offset + self.MACRO_ROWS]
        for row in range(self.MACRO_ROWS):
            name = visible[row] if row < len(visible) else ""
            marker = "▶ " if name and name == self._selected_macro else ""
            self._render_row_card(
                "macros",
                row,
                (12, 67 + row * 52, 248, 47),
                bool(name),
                "bRow%d" % row,
                ("tName%d" % row,),
                selected=bool(name and name == self._selected_macro),
            )
            self._set_text("macros.tName%d" % row, marker + name)
        page_number = self._macro_offset // self.MACRO_ROWS + 1
        self._set_text("macros.tPage", self._tr("page", number=page_number))

    def select_macro(self, row: int) -> None:
        index = self._macro_offset + row
        if 0 <= index < len(self._macro_names):
            self._selected_macro = self._macro_names[index]
            self.render_macros()
            self._set_text(
                "macros.tStatus",
                self._tr("selected", name=self._selected_macro),
            )

    def run_selected_macro(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self._selected_macro):
            self._set_text("macros.tStatus", self._tr("select_macro_first"))
            return
        try:
            self.moonraker.run_gcode(self._selected_macro)
        except (requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("Macro execution failed: %s", exc)
            self._set_text("macros.tStatus", self._tr("macro_failed"))
        else:
            self._set_text(
                "macros.tStatus",
                self._tr("started", name=self._selected_macro),
            )

    def refresh_system_info(self) -> None:
        try:
            info = self.moonraker.system_info()
        except (KeyError, requests.RequestException, MoonrakerError) as exc:
            LOGGER.warning("System information failed: %s", exc)
            self._set_text("system.tStatus", self._tr("system_unavailable"))
            return
        self._set_text("system.tHost", info.hostname)
        self._set_text("system.tKlipper", info.klipper_version)
        self._set_text("system.tMoon", info.moonraker_version)
        addresses = []
        if self._network_state.lan_ip_address:
            addresses.append("LAN " + self._network_state.lan_ip_address)
        if self._network_state.wifi_ip_address:
            addresses.append("WLAN " + self._network_state.wifi_ip_address)
        self._set_text("system.tNetwork", " · ".join(addresses) or self._tr("not_connected"))
        try:
            update_status = self.moonraker.update_status()
        except (KeyError, requests.RequestException, MoonrakerError):
            self._set_text("system.tStatus", info.distribution)
        else:
            self.render_update_status(update_status.available, update_status.busy)

    def render_update_status(self, available: int, busy: bool = False) -> None:
        if self.current_page != Page.SYSTEM:
            return
        if busy:
            message = self._tr("update_running")
        elif available:
            message = self._tr(
                "updates_available_one" if available == 1 else "updates_available_many",
                count=available,
            )
        else:
            message = self._tr("system_current")
        self._set_text("system.tStatus", message)

    def check_updates(self) -> None:
        if self._system_future is not None:
            return
        if self._printer_state.print_state in ("printing", "paused"):
            self._set_text("system.tStatus", self._tr("print_locked"))
            return
        self._pending_dialog_action = "system_update_check"
        self._set_text("system.tStatus", self._tr("checking_updates"))
        self._system_future = self._executor.submit(self.moonraker.refresh_updates)

    def request_system_action(self, action: str) -> None:
        if self._system_future is not None:
            return
        if action in ("system_reboot", "system_shutdown", "system_update_all") and self._printer_state.print_state in (
            "printing",
            "paused",
        ):
            self._set_text("system.tStatus", self._tr("print_locked"))
            return
        prompts = {
            "system_klipper_restart": (
                self._tr("restart_klipper_title"),
                self._tr("restart_klipper_message"),
            ),
            "system_firmware_restart": (
                self._tr("restart_firmware_title"),
                self._tr("restart_firmware_message"),
            ),
            "system_reboot": (
                self._tr("restart_board_title"),
                self._tr("restart_board_message"),
            ),
            "system_shutdown": (
                self._tr("shutdown_board_title"),
                self._tr("shutdown_board_message"),
            ),
            "system_update_all": (
                self._tr("install_updates_title"),
                self._tr("install_updates_message"),
            ),
        }
        prompt = prompts.get(action)
        if prompt is None:
            return
        self._pending_dialog_action = action
        self.show_page(Page.DIALOG)
        self._set_text("dialog.tTitle", prompt[0])
        self._set_text("dialog.tMessage", prompt[1])

    def confirm_system_action(self) -> None:
        action = self._pending_dialog_action
        if action is None or self._system_future is not None:
            return
        callbacks = {
            "system_klipper_restart": self.moonraker.restart_klipper,
            "system_firmware_restart": self.moonraker.firmware_restart,
            "system_reboot": self.moonraker.reboot_host,
            "system_shutdown": self.moonraker.shutdown_host,
            "system_update_all": self.moonraker.install_updates,
        }
        callback = callbacks.get(action)
        if callback is None:
            return
        self._set_text("dialog.tMessage", self._tr("command_running"))
        self._system_future = self._executor.submit(callback)

    def scan_wifi(self) -> None:
        if self._scan_future is not None:
            return
        self._set_text("wifi.tStatus", self._tr("searching_wifi"))
        self._scan_future = self._executor.submit(self.network.scan)

    def process_background_jobs(self) -> None:
        if self._scan_future is not None and self._scan_future.done():
            try:
                self._wifi_networks = self._scan_future.result()
                self._wifi_offset = 0
                if self.current_page == Page.WIFI:
                    self.render_wifi_list()
                    self._set_text(
                        "wifi.tStatus",
                        self._tr("networks_found", count=len(self._wifi_networks)),
                    )
            except NetworkManagerError as exc:
                LOGGER.warning("Wi-Fi scan failed: %s", exc)
                if self.current_page == Page.WIFI:
                    self._set_text("wifi.tStatus", self._tr("wifi_scan_failed"))
            finally:
                self._scan_future = None

        if self._connect_future is not None and self._connect_future.done():
            try:
                self._connect_future.result()
            except NetworkManagerError as exc:
                network_name = self._selected_wifi.ssid if self._selected_wifi else "?"
                LOGGER.warning("Wi-Fi connection failed for %r: %s", network_name, exc)
                self.display.set_text(
                    "wifi_password.tStatus",
                    self._tr("connection_failed"),
                )
            else:
                self.update_network_status()
                self.show_page(Page.WIFI)
                self.scan_wifi()
            finally:
                self._connect_future = None

        if self._print_future is not None and self._print_future.done():
            try:
                filename = self._print_future.result()
            except (
                OSError,
                requests.RequestException,
                MoonrakerError,
                StorageError,
            ) as exc:
                LOGGER.warning("Print start failed: %s", exc)
                if self.current_page == Page.FILES:
                    self._set_text("files.tStatus", self._tr("file_start_failed"))
            else:
                LOGGER.info("Print started: %s", filename)
                self._printer_state = replace(
                    self._printer_state,
                    print_state="printing",
                    filename=filename,
                    progress=0.0,
                )
                self.show_page(Page.PRINT)
            finally:
                self._print_future = None

        if self._system_future is not None and self._system_future.done():
            action = self._pending_dialog_action
            try:
                result = self._system_future.result()
            except (requests.RequestException, MoonrakerError) as exc:
                LOGGER.warning("System action failed: %s", exc)
                if action == "system_update_check" and self.current_page == Page.SYSTEM:
                    self._set_text("system.tStatus", self._tr("update_check_failed"))
                elif self.current_page == Page.DIALOG:
                    self._set_text("dialog.tMessage", self._tr("system_action_failed"))
            else:
                if action == "system_update_check":
                    self.render_update_status(result.available, result.busy)
                elif action in ("system_reboot", "system_shutdown", "system_update_all"):
                    self._set_text(
                        "dialog.tMessage",
                        {
                            "system_reboot": self._tr("board_restarting"),
                            "system_shutdown": self._tr("board_shutdown"),
                            "system_update_all": self._tr("updates_installing"),
                        }[action],
                    )
                else:
                    self.show_page(Page.SYSTEM)
                    self._set_text("system.tStatus", self._tr("restart_triggered"))
            finally:
                self._system_future = None
                self._pending_dialog_action = None

    def render_wifi_list(self) -> None:
        visible = self._wifi_networks[
            self._wifi_offset : self._wifi_offset + self.WIFI_ROWS
        ]
        for row in range(self.WIFI_ROWS):
            if row < len(visible):
                network = visible[row]
                marker = "✓ " if network.active else ""
                lock = " • " + self._tr("secured") if network.secured else ""
                self._render_row_card(
                    "wifi",
                    row,
                    (12, 131 + row * 61, 248, 55),
                    True,
                    "bRow%d" % row,
                    ("tSSID%d" % row, "tMeta%d" % row),
                    selected=network.active,
                )
                self._set_text("wifi.tSSID%d" % row, marker + network.ssid)
                self._set_text(
                    "wifi.tMeta%d" % row,
                    "%d%%%s" % (network.signal, lock),
                )
            else:
                self._render_row_card(
                    "wifi",
                    row,
                    (12, 131 + row * 61, 248, 55),
                    False,
                    "bRow%d" % row,
                    ("tSSID%d" % row, "tMeta%d" % row),
                )
                self._set_text("wifi.tSSID%d" % row, "")
                self._set_text("wifi.tMeta%d" % row, "")

    def render_wifi_password(self) -> None:
        self._apply_page_background(
            Page.WIFI_PASSWORD,
            symbols=self._wifi_input_mode == 2,
        )
        self._render_static_labels(Page.WIFI_PASSWORD)
        self._render_keyboard_labels()
        for component in ("tSSID", "tPass", "tCase", "tStatus"):
            self._last_fields.pop("wifi_password." + component, None)
        ssid = self._selected_wifi.ssid if self._selected_wifi else "–"
        self._set_text("wifi_password.tSSID", ssid)
        self._set_text("wifi_password.tPass", self._wifi_password)
        self._set_text(
            "wifi_password.tCase",
            ("ABC", "abc", "?#")[self._wifi_input_mode],
        )

    def select_file_source(self, source: str) -> None:
        if source not in ("internal", "usb"):
            return
        self._file_source = source
        self._file_path = ""
        self._file_volume = ""
        self._file_offset = 0
        self._selected_file = None
        self.refresh_files()

    def refresh_files(self) -> None:
        try:
            if self._file_source == "internal":
                self._file_entries = self.moonraker.list_gcodes(self._file_path)
            elif not self._file_volume:
                self._file_entries = [
                    GCodeEntry(
                        name=volume.display_name,
                        path="",
                        is_directory=True,
                        source="usb",
                        volume=volume.name,
                    )
                    for volume in self.usb_media.volumes()
                ]
            else:
                self._file_entries = self.usb_media.list_directory(
                    self._file_volume,
                    self._file_path,
                )
        except (
            KeyError,
            OSError,
            ValueError,
            requests.RequestException,
            MoonrakerError,
            StorageError,
        ) as exc:
            LOGGER.warning("File list failed: %s", exc)
            self._file_entries = []
            self._set_text("files.tStatus", self._tr("file_list_unavailable"))
        else:
            if self._file_source == "usb" and not self._file_entries:
                message = self._tr("no_usb") if not self._file_volume else self._tr("folder_empty")
            else:
                message = self._tr("entries", count=len(self._file_entries))
            self._set_text("files.tStatus", message)
        self._file_entries = sort_gcode_entries(
            self._file_entries,
            FILE_SORT_MODES[self._file_sort_index][0],
        )
        self._file_offset = min(
            self._file_offset,
            max(0, len(self._file_entries) - self.FILE_ROWS),
        )
        self._selected_file = None
        self.render_file_list()

    @staticmethod
    def _format_file_size(size: int) -> str:
        if size >= 1024 * 1024:
            return "%.1f MB" % (size / (1024 * 1024))
        if size >= 1024:
            return "%.0f KB" % (size / 1024)
        return "%d B" % size

    def render_file_list(self) -> None:
        if self.current_page != Page.FILES:
            return
        self._render_file_source_tabs()
        source_label = "INT" if self._file_source == "internal" else "USB"
        path_parts = []
        if self._file_volume:
            path_parts.append(self._file_volume)
        if self._file_path:
            path_parts.append(self._file_path)
        self._set_text("files.tSource", source_label)
        self._set_text("files.tPath", "/" + "/".join(path_parts))
        self._set_text(
            "files.tSort",
            self._tr(FILE_SORT_MODES[self._file_sort_index][1]),
        )
        visible = self._file_entries[
            self._file_offset : self._file_offset + self.FILE_ROWS
        ]
        for row in range(self.FILE_ROWS):
            name_component = "n3x" if row == 3 else "tName%d" % row
            if row < len(visible):
                entry = visible[row]
                selected = entry == self._selected_file
                marker = "> " if selected else ""
                self._render_row_card(
                    "files",
                    row,
                    (12, 138 + row * 52, 248, 48),
                    True,
                    "bRow%d" % row,
                    (name_component, "tMeta%d" % row),
                    selected=selected,
                )
                self._set_text("files." + name_component, marker + entry.name)
                self._set_text(
                    "files.tMeta%d" % row,
                    self._tr("folder")
                    if entry.is_directory
                    else self._format_file_size(entry.size),
                )
            else:
                self._render_row_card(
                    "files",
                    row,
                    (12, 138 + row * 52, 248, 48),
                    False,
                    "bRow%d" % row,
                    (name_component, "tMeta%d" % row),
                )
                self._set_text("files." + name_component, "")
                self._set_text("files.tMeta%d" % row, "")

    def _render_file_source_tabs(self) -> None:
        accent = ACCENTS[self._accent_index]
        tabs = (
            ("internal", 16, self._tr("source_internal")),
            ("usb", 137, "USB"),
        )
        for source, x, label in tabs:
            active = source == self._file_source
            self.display.command(
                "fill %d,65,119,28,%d"
                % (
                    x,
                    accent.nextion_soft_color if active else DARK_PANEL_COLOR,
                )
            )
            self._draw_text(
                x,
                64,
                119,
                30,
                label,
                color=accent.nextion_color if active else MUTED_COLOR,
                align=1,
            )

    def cycle_file_sort(self) -> None:
        self._file_sort_index = (self._file_sort_index + 1) % len(FILE_SORT_MODES)
        mode, _short_label, status_label = FILE_SORT_MODES[self._file_sort_index]
        self._file_entries = sort_gcode_entries(self._file_entries, mode)
        self._file_offset = 0
        self._selected_file = None
        self.render_file_list()
        self._set_text(
            "files.tStatus",
            self._tr("sorting", mode=self._tr(status_label)),
        )

    def files_up(self) -> None:
        if self._file_path:
            self._file_path = posixpath.dirname(self._file_path)
        elif self._file_source == "usb" and self._file_volume:
            self._file_volume = ""
        else:
            return
        self._file_offset = 0
        self._selected_file = None
        self.refresh_files()

    def select_file_row(self, row: int) -> None:
        index = self._file_offset + row
        if index >= len(self._file_entries):
            return
        entry = self._file_entries[index]
        if entry.is_directory:
            if self._file_source == "usb" and not self._file_volume:
                self._file_volume = entry.volume
                self._file_path = ""
            else:
                self._file_path = entry.path
            self._file_offset = 0
            self._selected_file = None
            self.refresh_files()
            return
        self._selected_file = entry
        self._set_text("files.tStatus", self._tr("selected", name=entry.name))
        self.render_file_list()

    def start_selected_file(self) -> None:
        if self._selected_file is None:
            self._set_text("files.tStatus", self._tr("select_file_first"))
            return
        if self._print_future is not None:
            return
        selected = self._selected_file
        self._set_text("files.tStatus", self._tr("preparing_print"))

        def prepare_and_start() -> str:
            filename = selected.path
            if selected.source == "usb":
                filename = self.usb_media.import_for_print(selected)
            self.moonraker.start_print(filename)
            return filename

        self._print_future = self._executor.submit(prepare_and_start)

    def select_wifi(self, row: int) -> None:
        index = self._wifi_offset + row
        if index >= len(self._wifi_networks):
            return
        self._selected_wifi = self._wifi_networks[index]
        if self._selected_wifi.secured:
            self._wifi_password = ""
            self._wifi_input_mode = 0
            self.show_page(Page.WIFI_PASSWORD)
            self.display.set_text("wifi_password.tStatus", "")
        else:
            self.connect_wifi(password="")

    def connect_wifi(self, password: Optional[str] = None) -> None:
        if self._selected_wifi is None or self._connect_future is not None:
            return
        if password is None:
            try:
                password = self.display.query_text("wifi_password.tPass")
            except TimeoutError:
                self.display.set_text("wifi_password.tStatus", self._tr("no_input"))
                return
        self.display.set_text("wifi_password.tStatus", self._tr("connecting"))
        self._connect_future = self._executor.submit(
            self.network.connect,
            self._selected_wifi,
            password,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Artillery X4 UART screen service")
    parser.add_argument("--device", default="/dev/ttyS2")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--moonraker", default="http://127.0.0.1:7125")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument(
        "--settings",
        default="/home/biqu/printer_data/config/artillery-screen.json",
    )
    parser.add_argument("--usb-mount-root", default="/media/artillery")
    parser.add_argument(
        "--usb-import-root",
        default="/home/biqu/printer_data/gcodes/.artillery-usb",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    display = NextionTransport.open(args.device, args.baudrate)
    app = ArtilleryScreen(
        display=display,
        moonraker=MoonrakerClient(args.moonraker),
        network=NetworkManager(),
        settings=SettingsStore(args.settings),
        usb_media=USBMediaManager(args.usb_mount_root, args.usb_import_root),
        poll_interval=args.poll_interval,
    )

    def stop(_signum: int, _frame: object) -> None:
        app.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        app.start()
    finally:
        display.close()


if __name__ == "__main__":
    main()
