"""Native AUDAC NWP220 ASCII/UDP client. No Home Assistant dependencies.

UDP preserves datagrams: incomplete frames are rejected, never concatenated with
an unrelated datagram. Requests share one socket and are serialized. A different
CLIENT address per request rejects delayed/duplicated responses, including SET
echoes arriving during readback. This addressing is verified on real hardware.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import socket
import zlib
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)
DEFAULT_PORT = 8711
MAX_FRAME = 16384
INPUT_INDICES = (0, 1, 4, 5, 8, 9, 10, 11)
CHANNELS = tuple(
    (f"{kind}>{i}>VOLUME>1", f"{label} {i}")
    for kind, label, count in (
        ("INPUT_XLR", "XLR input", 2),
        ("INPUT_BLUETOOTH", "Bluetooth input", 2),
        ("INPUT_DANTE", "Dante input", 4),
        ("OUTPUT_DANTE", "Dante output", 4),
    )
    for i in range(1, count + 1)
)
# Only documented, meaningful source labels; do not invent reserved sources.
ROUTES = {0: "Off", 1: "XLR 1", 2: "XLR 2", 5: "Bluetooth left", 6: "Bluetooth right"}


class NwpError(Exception):
    """Base error for transport and protocol failures."""


class ProtocolError(NwpError):
    """Malformed frame, checksum, or unsupported value."""


class CommunicationError(NwpError):
    """Endpoint unavailable or response missing."""


class UnexpectedResponse(NwpError):
    """A matching reply did not acknowledge the request with GET_RSP.

    No undocumented AUDAC error grammar is assumed. The raw reply is retained.
    """

    def __init__(self, message: Message):
        self.message = message
        super().__init__(f"Unexpected {message.kind} reply for {message.command}")


@dataclass(frozen=True)
class Message:
    destination: str
    source: str
    kind: str
    target: str
    command: str
    argument: str

    def encode(self) -> bytes:
        fields = (self.destination, self.source, self.kind, self.target, self.command, self.argument)
        if any(any(ord(c) < 32 or ord(c) > 126 or c == "|" for c in f) for f in fields):
            raise ProtocolError("Frame fields must be printable ASCII without pipes")
        if any("^" in f for f in fields[:5]):
            raise ProtocolError("Unexpected block separator")
        if not all((self.kind, self.target, self.command)):
            raise ProtocolError("Missing command header")
        data = (
            f"#|{self.destination}|{self.source}|{self.kind}^{self.target}^{self.command}|{self.argument}|U|\r\n"
        ).encode("ascii")
        if len(data) > MAX_FRAME:
            raise ProtocolError("Frame too long")
        return data


def crc16(data: bytes) -> int:
    """CRC16-ARC (reflected 0x8005)."""
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value


def parse_frame(data: bytes) -> Message:
    """Validate exactly one complete ASCII frame, including optional CRC."""
    if len(data) > MAX_FRAME or not data.endswith(b"\n"):
        raise ProtocolError("Oversized or unterminated frame")
    body = data[:-2] if data.endswith(b"\r\n") else data[:-1]
    if any(c < 32 or c > 126 for c in body):
        raise ProtocolError("Non-ASCII or control character in frame")
    fields = body.split(b"|")
    if len(fields) != 7 or fields[0] != b"#" or fields[-1] != b"":
        raise ProtocolError("Invalid frame structure")
    checksum = fields[5]
    checked = b"|" + b"|".join(fields[1:5]) + b"|"
    if checksum != b"U":
        if not re.fullmatch(rb"(?:[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8})", checksum):
            raise ProtocolError("Invalid checksum format")
        expected = crc16(checked) if len(checksum) == 4 else zlib.crc32(checked)
        if expected != int(checksum, 16):
            raise ProtocolError("Checksum mismatch")
    header = fields[3].decode("ascii").split("^")
    if len(header) != 3 or not all(header):
        raise ProtocolError("Invalid command header")
    return Message(fields[1].decode(), fields[2].decode(), *header, fields[4].decode())


def parse_datagram(data: bytes) -> tuple[Message, ...]:
    """Accept one or several complete frames; never buffer across datagrams."""
    if not data or len(data) > MAX_FRAME or not data.endswith(b"\n"):
        raise ProtocolError("Incomplete or oversized datagram")
    return tuple(parse_frame(line + b"\n") for line in data.split(b"\n")[:-1])


def volume(value: str | float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        raise ProtocolError("Invalid volume") from err
    if isinstance(value, bool) or not math.isfinite(result) or not -90 <= result <= 0:
        raise ProtocolError("Volume must be between -90 and 0 dB")
    return result


def mute(value: str) -> bool:
    if value not in ("TRUE", "FALSE"):
        raise ProtocolError("Invalid mute value")
    return value == "TRUE"


def route(value: str) -> int:
    if not re.fullmatch(r"-?\d+", value):
        raise ProtocolError("Invalid route value")
    result = int(value)
    if not -1 <= result <= 21:
        raise ProtocolError("Route outside documented range")
    return result


@dataclass(frozen=True)
class State:
    levels: tuple[float, ...]
    mutes: tuple[bool, ...]
    routes: tuple[int, ...]
    address: str


class _Wire(asyncio.DatagramProtocol):
    def __init__(self, client: Nwp220):
        self.client = client

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if self.client._wire is self:
            self.client._received(data)

    def error_received(self, exc: Exception) -> None:
        if self.client._wire is self:
            self.client._failed(CommunicationError(str(exc)))

    def connection_lost(self, exc: Exception | None) -> None:
        if self.client._wire is self:
            self.client._failed(CommunicationError("UDP endpoint closed"))


class Nwp220:
    """Single-endpoint, serialized asynchronous client with bounded recovery.

    No automatic SET retries. Pollers call again after failures; reconnection is
    demand-driven with exponential cooldown, capped at 60 seconds.
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT, *, timeout: float = 2):
        if not host or not 1 <= port <= 65535 or timeout <= 0:
            raise ValueError("Invalid endpoint or timeout")
        self.host, self.port, self.timeout = host, port, timeout
        self._lock = asyncio.Lock()
        self._transport: asyncio.DatagramTransport | None = None
        self._wire: _Wire | None = None
        self._pending: tuple[Message, asyncio.Future[Message]] | None = None
        self._sequence = 0
        self._closed = False
        self._failures = 0
        self._retry_at = 0.0
        self.address: str | None = None

    def _disconnect(self) -> None:
        transport, self._transport = self._transport, None
        self._wire = None
        if transport is not None:
            transport.close()

    def _failed(self, error: NwpError) -> None:
        if self._pending and not self._pending[1].done():
            self._pending[1].set_exception(error)
        self._disconnect()

    async def close(self) -> None:
        """Cancel pending work and permanently close; safe to call repeatedly."""
        self._closed = True
        self._failed(CommunicationError("Client closed"))

    async def _connect(self) -> None:
        if self._closed:
            raise CommunicationError("Client closed")
        if asyncio.get_running_loop().time() < self._retry_at:
            raise CommunicationError("Endpoint is in retry cooldown")
        if self._transport is None:
            wire = _Wire(self)
            transport, _ = await asyncio.wait_for(
                asyncio.get_running_loop().create_datagram_endpoint(
                    lambda: wire, remote_addr=(self.host, self.port), family=socket.AF_INET
                ),
                self.timeout,
            )
            if self._closed:
                transport.close()
                raise CommunicationError("Client closed")
            self._wire = wire
            self._transport = transport

    def _received(self, data: bytes) -> None:
        try:
            messages = parse_datagram(data)
        except ProtocolError as err:
            LOGGER.debug("Discarding malformed datagram: %s", err)
            return
        for message, frame in zip(messages, data.splitlines(keepends=True), strict=True):
            self._log("RX", message, frame)
            if not self._pending:
                continue
            request, future = self._pending
            if (
                future.done()
                or message.destination != request.source
                or not re.fullmatch(r"NWP220>\d+", message.source)
                or (message.target, message.command) != (request.target, request.command)
            ):
                continue
            if message.kind != "GET_RSP":
                future.set_exception(UnexpectedResponse(message))
            else:
                self.address = message.source
                future.set_result(message)

    @staticmethod
    def _log(direction: str, message: Message, data: bytes) -> None:
        if message.command in {"VOLUME", "MUTE", "ROUTE", "MIXER", "BT_PAIR", "BT_DISCONNECT"}:
            LOGGER.debug("%s: %r", direction, data)
        else:
            LOGGER.debug("%s: undocumented command payload redacted (%d bytes)", direction, len(data))

    async def _request(self, kind: str, target: str, command: str, argument: str = "") -> Message:
        async with self._lock:
            # No re-use on the same socket: isolates stale packets after wrap.
            if self._sequence >= 65535:
                self._disconnect()
                self._sequence = 0
            self._sequence += 1
            request = Message("NWP220", f"CLIENT>{self._sequence}", kind, target, command, argument)
            encoded = request.encode()  # Validate before opening any socket.
            future = asyncio.get_running_loop().create_future()
            try:
                await self._connect()
                self._pending = request, future
                self._log("TX", request, encoded)
                assert self._transport is not None
                self._transport.sendto(encoded)
                reply = await asyncio.wait_for(future, self.timeout)
                self._failures = 0
                self._retry_at = 0
                return reply
            except asyncio.CancelledError:
                self._disconnect()
                raise
            except (OSError, TimeoutError, CommunicationError) as err:
                self._disconnect()
                # A rejected call during cooldown must not extend the cooldown.
                now = asyncio.get_running_loop().time()
                if now >= self._retry_at:
                    self._failures += 1
                    self._retry_at = now + min(60, 2 ** min(self._failures - 1, 6))
                raise CommunicationError(
                    f"No valid response from {self.host}:{self.port}: {str(err) or type(err).__name__}"
                ) from err
            finally:
                self._pending = None
                if not future.done():
                    future.cancel()

    async def get(self, target: str, command: str) -> Message:
        return await self._request("GET_REQ", target, command)

    async def get_volume(self, channel: int) -> float:
        return volume((await self.get(self._channel(channel), "VOLUME")).argument)

    @staticmethod
    def _channel(channel: int) -> str:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel < len(CHANNELS):
            raise ValueError("Invalid channel")
        return CHANNELS[channel][0]

    async def set_volume(self, channel: int, value: float) -> None:
        value = volume(value)
        if not value.is_integer():
            raise ValueError("NWP220 volume requires whole dB steps")
        await self._request("SET_REQ", self._channel(channel), "VOLUME", f"{value:.2f}")

    async def set_mute(self, channel: int, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError("Mute must be a boolean")
        await self._request("SET_REQ", self._channel(channel), "MUTE", "TRUE" if value else "FALSE")

    async def set_route(self, output: int, value: int) -> None:
        if type(output) is not int or not 0 <= output < 4 or type(value) is not int or value not in ROUTES:
            raise ValueError("Unknown output or unsupported route")
        await self._request("SET_REQ", f"OUTPUT_DANTE>{output + 1}>MIXER>1", "ROUTE", str(value))

    async def bluetooth(self, command: str) -> None:
        if command not in ("BT_PAIR", "BT_DISCONNECT"):
            raise ValueError("Unsupported Bluetooth operation")
        await self._request("SET_REQ", "INPUT_BLUETOOTH>1>BLUETOOTH>1", command, "TRUE")

    async def cancel_pairing(self) -> None:
        await self._request("SET_REQ", "INPUT_BLUETOOTH>1>BLUETOOTH>1", "BT_PAIR", "FALSE")

    async def send_raw(self, frame: str) -> Message:
        """Validate a single request; route it only to this device and correlate it.

        Source/destination are deliberately replaced. Commands containing secrets
        must not be sent while raw debug logging is enabled.
        """
        try:
            data = frame.encode("ascii")
        except UnicodeEncodeError as err:
            raise ProtocolError("Only ASCII commands are supported") from err
        if not data.endswith(b"\n"):
            data += b"\r\n"
        request = parse_frame(data)
        if request.kind not in ("GET_REQ", "SET_REQ"):
            raise ProtocolError("Only GET_REQ and SET_REQ requests are accepted")
        return await self._request(request.kind, request.target, request.command, request.argument)

    async def snapshot(self) -> State:
        """Five grouped reads, ignoring reserved positions but never shifting them."""
        values = {}
        for target, command, count in (
            ("ALL_IN", "VOLUME", 12),
            ("ALL_OUT", "VOLUME", 8),
            ("ALL_IN", "MUTE", 12),
            ("ALL_OUT", "MUTE", 8),
            ("ALL_OUT", "ROUTE", 8),
        ):
            parts = (await self.get(target, command)).argument.split("^")
            if len(parts) != count:
                raise ProtocolError(f"Unexpected {target} {command} group length")
            values[target, command] = parts
        levels = tuple(volume(values["ALL_IN", "VOLUME"][i]) for i in INPUT_INDICES)
        levels += tuple(volume(v) for v in values["ALL_OUT", "VOLUME"][:4])
        mutes = tuple(mute(values["ALL_IN", "MUTE"][i]) for i in INPUT_INDICES)
        mutes += tuple(mute(v) for v in values["ALL_OUT", "MUTE"][:4])
        return State(levels, mutes, tuple(route(v) for v in values["ALL_OUT", "ROUTE"][:4]), self.address or "")
