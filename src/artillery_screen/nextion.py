import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol, Union


LOGGER = logging.getLogger(__name__)
TERMINATOR = b"\xff\xff\xff"


class SerialPort(Protocol):
    in_waiting: int

    def read(self, size: int = 1) -> bytes:
        ...

    def write(self, data: bytes) -> int:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class TouchEvent:
    page_id: int
    component_id: int
    pressed: bool


@dataclass(frozen=True)
class PageEvent:
    page_id: int


@dataclass(frozen=True)
class StringResponse:
    value: str


@dataclass(frozen=True)
class NumberResponse:
    value: int


@dataclass(frozen=True)
class StatusResponse:
    code: int


NextionEvent = Union[
    TouchEvent,
    PageEvent,
    StringResponse,
    NumberResponse,
    StatusResponse,
]


def escape_text(value: object) -> str:
    """Return text safe for a quoted Nextion assignment."""
    text = str(value).replace("\\", "/").replace('"', "'")
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def parse_packet(packet: bytes) -> Optional[NextionEvent]:
    if not packet:
        return None
    code = packet[0]
    if code == 0x65 and len(packet) == 4:
        return TouchEvent(packet[1], packet[2], packet[3] == 1)
    if code == 0x66 and len(packet) == 2:
        return PageEvent(packet[1])
    if code == 0x70:
        return StringResponse(packet[1:].decode("utf-8", errors="replace"))
    if code == 0x71 and len(packet) == 5:
        return NumberResponse(int.from_bytes(packet[1:], "little"))
    if len(packet) == 1:
        return StatusResponse(code)
    LOGGER.debug("Unknown Nextion packet: %s", packet.hex())
    return None


class NextionTransport:
    def __init__(self, serial_port: SerialPort):
        self.serial = serial_port
        self._buffer = bytearray()

    @classmethod
    def open(cls, device: str, baudrate: int) -> "NextionTransport":
        import serial

        port = serial.Serial(
            port=device,
            baudrate=baudrate,
            timeout=0,
            write_timeout=1,
        )
        return cls(port)

    def close(self) -> None:
        self.serial.close()

    def command(self, command: str) -> None:
        payload = command.encode("utf-8") + TERMINATOR
        self.serial.write(payload)

    def set_text(self, component: str, value: object) -> None:
        self.command('%s.txt="%s"' % (component, escape_text(value)))

    def set_value(self, component: str, value: int) -> None:
        self.command("%s.val=%d" % (component, int(value)))

    def show_page(self, page: str) -> None:
        self.command("page %s" % page)

    def poll(self) -> List[NextionEvent]:
        waiting = getattr(self.serial, "in_waiting", 0)
        if waiting:
            self._buffer.extend(self.serial.read(waiting))

        events: List[NextionEvent] = []
        while True:
            end = self._buffer.find(TERMINATOR)
            if end < 0:
                break
            packet = bytes(self._buffer[:end])
            del self._buffer[: end + len(TERMINATOR)]
            event = parse_packet(packet)
            if event is not None:
                events.append(event)
        return events

    def query_text(self, component: str, timeout: float = 2.0) -> str:
        self.command("get %s.txt" % component)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.poll():
                if isinstance(event, StringResponse):
                    return event.value
            time.sleep(0.01)
        raise TimeoutError("No string response from %s" % component)

