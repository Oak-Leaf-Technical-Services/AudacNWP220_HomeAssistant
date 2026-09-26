"""UDP fake seeded from real read captures; failure injection is synthetic."""

import asyncio
import json
import zlib
from dataclasses import replace

from .protocol_support import ROOT, nwp


def wire(message):
    data = message.encode()
    fields = data.split(b"|")
    checksum = zlib.crc32(b"|" + b"|".join(fields[1:5]) + b"|")
    return b"|".join(fields[:5] + [f"{checksum:08X}".encode(), b"\r\n"])


class FakeNwp(asyncio.DatagramProtocol):
    def __init__(self):
        fixture = json.loads((ROOT / "tests/fixtures/hardware_read_only.json").read_text())
        self.values = {}
        for pair in fixture["exchanges"]:
            response = nwp.parse_frame(bytes.fromhex(pair["response_hex"]))
            self.values[response.target, response.command] = response.argument
        self.requests = []
        self.peers = set()
        self.mode = "normal"
        self.delayed = []
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, peer):
        request = nwp.parse_frame(data)
        self.requests.append(request)
        self.peers.add(peer)
        if self.mode == "drop":
            return
        if request.kind == "SET_REQ":
            if request.command == "VOLUME":
                try:
                    value = nwp.volume(request.argument)
                    if not value.is_integer():
                        return
                except nwp.ProtocolError:
                    return
            self.values[request.target, request.command] = request.argument
            # Keep grouped mirrors coherent at documented active indices.
            for channel, (target, _) in enumerate(nwp.CHANNELS):
                if request.target == target:
                    group = "ALL_IN" if channel < 8 else "ALL_OUT"
                    index = nwp.INPUT_INDICES[channel] if channel < 8 else channel - 8
                    parts = self.values[group, request.command].split("^")
                    parts[index] = request.argument
                    self.values[group, request.command] = "^".join(parts)
            if request.command == "ROUTE":
                parts = self.values["ALL_OUT", "ROUTE"].split("^")
                parts[int(request.target.split(">")[1]) - 1] = request.argument
                self.values["ALL_OUT", "ROUTE"] = "^".join(parts)
        response = nwp.Message(
            request.source,
            "NWP220>1",
            "GET_RSP",
            request.target,
            request.command,
            self.values.get((request.target, request.command), ""),
        )
        if self.mode == "error":
            # Deliberately synthetic unknown reply, not a claimed AUDAC error type.
            response = replace(response, kind="SYNTHETIC_ERROR", argument="unsupported")
        if self.mode == "wrong_destination":
            response = replace(response, destination="CLIENT>0")
        if self.mode == "malformed":
            self.transport.sendto(b"nonsense\n", peer)
            return
        if self.mode == "stale_then_valid":
            self.transport.sendto(wire(replace(response, destination="CLIENT>0", argument="-80")), peer)
        self.transport.sendto(wire(response), peer)
        if self.mode == "duplicate":
            self.transport.sendto(wire(response), peer)
