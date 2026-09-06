from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional, Tuple


PROTOCOL_VERSION = 1


class Page(IntEnum):
    BOOT = 0
    HOME = 1
    MOVE = 2
    TEMPERATURE = 3
    FILES = 4
    PRINT = 5
    TUNE = 6
    BED = 7
    MACROS = 8
    SETTINGS = 9
    WIFI = 10
    WIFI_PASSWORD = 11
    SYSTEM = 12
    DIALOG = 13
    ACCENT = 14


@dataclass(frozen=True)
class Action:
    name: str
    argument: Optional[int] = None


# Touch events are handled on release only. IDs must match the HMI project.
TOUCH_ACTIONS: Dict[Tuple[int, int], Action] = {
    (Page.HOME, 1): Action("open_move"),
    (Page.HOME, 2): Action("open_temperature"),
    (Page.HOME, 3): Action("open_files"),
    (Page.HOME, 4): Action("open_bed"),
    (Page.HOME, 5): Action("open_macros"),
    (Page.HOME, 6): Action("open_settings"),
    (Page.HOME, 7): Action("emergency_stop"),
    (Page.MOVE, 1): Action("open_home"),
    (Page.MOVE, 2): Action("move_home_all"),
    (Page.MOVE, 3): Action("move_home_x"),
    (Page.MOVE, 4): Action("move_home_y"),
    (Page.MOVE, 5): Action("move_home_z"),
    (Page.MOVE, 6): Action("move_x_minus"),
    (Page.MOVE, 7): Action("move_x_plus"),
    (Page.MOVE, 8): Action("move_y_minus"),
    (Page.MOVE, 9): Action("move_y_plus"),
    (Page.MOVE, 10): Action("move_z_minus"),
    (Page.MOVE, 11): Action("move_z_plus"),
    (Page.MOVE, 12): Action("move_step", 1),
    (Page.MOVE, 13): Action("move_step", 10),
    (Page.MOVE, 14): Action("move_step", 100),
    (Page.MOVE, 20): Action("move_force_toggle"),
    (Page.TEMPERATURE, 1): Action("open_home"),
    (Page.TEMPERATURE, 2): Action("temperature_nozzle", -5),
    (Page.TEMPERATURE, 3): Action("temperature_nozzle", 5),
    (Page.TEMPERATURE, 4): Action("temperature_bed", -5),
    (Page.TEMPERATURE, 5): Action("temperature_bed", 5),
    (Page.TEMPERATURE, 6): Action("temperature_fan", -10),
    (Page.TEMPERATURE, 7): Action("temperature_fan", 10),
    (Page.TEMPERATURE, 8): Action("temperature_preset", 0),
    (Page.TEMPERATURE, 9): Action("temperature_preset", 1),
    (Page.TEMPERATURE, 10): Action("temperature_preset", 2),
    (Page.TEMPERATURE, 11): Action("temperature_preset", 3),
    (Page.FILES, 1): Action("files_back"),
    (Page.FILES, 2): Action("files_internal"),
    (Page.FILES, 3): Action("files_usb"),
    (Page.FILES, 4): Action("files_previous"),
    (Page.FILES, 5): Action("files_next"),
    (Page.FILES, 6): Action("files_up"),
    (Page.FILES, 7): Action("files_refresh"),
    (Page.FILES, 10): Action("files_select", 0),
    (Page.FILES, 11): Action("files_select", 1),
    (Page.FILES, 12): Action("files_select", 2),
    (Page.FILES, 13): Action("files_select", 3),
    (Page.FILES, 14): Action("files_select", 4),
    (Page.FILES, 15): Action("files_print"),
    (Page.FILES, 18): Action("files_select", 0),
    (Page.FILES, 19): Action("files_select", 0),
    (Page.FILES, 20): Action("files_select", 1),
    (Page.FILES, 22): Action("files_select", 1),
    (Page.FILES, 21): Action("files_select", 2),
    (Page.FILES, 25): Action("files_select", 2),
    (Page.FILES, 26): Action("files_select", 3),
    (Page.FILES, 27): Action("files_select", 3),
    (Page.FILES, 23): Action("files_select", 4),
    (Page.FILES, 28): Action("files_select", 4),
    (Page.FILES, 29): Action("files_sort"),
    (Page.FILES, 30): Action("files_sort"),
    (Page.PRINT, 1): Action("open_home"),
    (Page.PRINT, 2): Action("print_pause_resume"),
    (Page.PRINT, 3): Action("print_cancel"),
    (Page.PRINT, 4): Action("open_temperature"),
    (Page.TUNE, 1): Action("open_print"),
    (Page.TUNE, 2): Action("tune_speed", -10),
    (Page.TUNE, 3): Action("tune_speed", 10),
    (Page.TUNE, 4): Action("tune_flow", -5),
    (Page.TUNE, 5): Action("tune_flow", 5),
    (Page.TUNE, 6): Action("tune_fan", -10),
    (Page.TUNE, 7): Action("tune_fan", 10),
    (Page.TUNE, 8): Action("tune_reset"),
    (Page.BED, 1): Action("open_home"),
    (Page.BED, 2): Action("bed_home_z"),
    (Page.BED, 3): Action("bed_probe"),
    (Page.BED, 4): Action("bed_mesh_calibrate"),
    (Page.BED, 5): Action("bed_mesh_load"),
    (Page.BED, 6): Action("bed_mesh_clear"),
    (Page.BED, 7): Action("bed_z_offset", -1),
    (Page.BED, 8): Action("bed_z_offset", 1),
    (Page.BED, 9): Action("bed_save"),
    (Page.MACROS, 1): Action("open_home"),
    (Page.MACROS, 2): Action("macros_previous"),
    (Page.MACROS, 3): Action("macros_next"),
    (Page.MACROS, 10): Action("macros_select", 0),
    (Page.MACROS, 11): Action("macros_select", 1),
    (Page.MACROS, 12): Action("macros_select", 2),
    (Page.MACROS, 13): Action("macros_select", 3),
    (Page.MACROS, 14): Action("macros_select", 4),
    (Page.MACROS, 15): Action("macros_select", 5),
    (Page.MACROS, 16): Action("macros_run"),
    (Page.SETTINGS, 1): Action("open_wifi"),
    (Page.SETTINGS, 2): Action("open_system"),
    (Page.SETTINGS, 3): Action("open_accent"),
    (Page.SETTINGS, 9): Action("open_home"),
    (Page.WIFI, 1): Action("wifi_scan"),
    (Page.WIFI, 2): Action("wifi_previous"),
    (Page.WIFI, 3): Action("wifi_next"),
    (Page.WIFI, 9): Action("open_settings"),
    (Page.WIFI, 10): Action("wifi_select", 0),
    (Page.WIFI, 11): Action("wifi_select", 1),
    (Page.WIFI, 12): Action("wifi_select", 2),
    (Page.WIFI, 13): Action("wifi_select", 3),
    (Page.WIFI, 14): Action("wifi_select", 4),
    (Page.WIFI_PASSWORD, 1): Action("wifi_connect"),
    (Page.WIFI_PASSWORD, 2): Action("open_wifi"),
    (Page.WIFI_PASSWORD, 3): Action("open_wifi"),
    (Page.SYSTEM, 1): Action("open_settings"),
    (Page.SYSTEM, 2): Action("system_klipper_restart"),
    (Page.SYSTEM, 3): Action("system_firmware_restart"),
    (Page.SYSTEM, 4): Action("system_reboot"),
    (Page.SYSTEM, 5): Action("system_shutdown"),
    (Page.SYSTEM, 11): Action("system_update_check"),
    (Page.SYSTEM, 12): Action("system_update_all"),
    (Page.DIALOG, 1): Action("dialog_cancel"),
    (Page.DIALOG, 2): Action("dialog_confirm"),
    (Page.ACCENT, 1): Action("open_settings"),
    (Page.ACCENT, 10): Action("accent_select", 0),
    (Page.ACCENT, 11): Action("accent_select", 1),
    (Page.ACCENT, 12): Action("accent_select", 2),
    (Page.ACCENT, 13): Action("accent_select", 3),
    (Page.ACCENT, 14): Action("accent_select", 4),
    (Page.ACCENT, 17): Action("language_next"),
    (Page.ACCENT, 18): Action("keyboard_next"),
}

for component_id, key_index in enumerate(range(10), start=4):
    TOUCH_ACTIONS[(Page.WIFI_PASSWORD, component_id)] = Action(
        "wifi_key", key_index
    )

for component_id, key_index in enumerate(range(10, 36), start=14):
    TOUCH_ACTIONS[(Page.WIFI_PASSWORD, component_id)] = Action(
        "wifi_key", key_index
    )

TOUCH_ACTIONS[(Page.WIFI_PASSWORD, 40)] = Action("wifi_shift")
TOUCH_ACTIONS[(Page.WIFI_PASSWORD, 41)] = Action("wifi_backspace")


def action_for_touch(page_id: int, component_id: int, pressed: bool) -> Optional[Action]:
    if pressed:
        return None
    return TOUCH_ACTIONS.get((page_id, component_id))
