"""Read-only endpoint investigation; results are evidence, not API assumptions."""

import argparse
import asyncio
import json
import socket
from datetime import datetime, timezone
from pathlib import Path


class Probe:
    def __init__(self, host: str, output: Path):
        self.host = host
        self.output = output
        self.records = []

    def log(self, event: str, **fields):
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self.records.append(record)
        print(json.dumps(record), flush=True)

    async def tcp(self, port: int):
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, port), timeout=4)
            self.log("connected", transport="tcp", port=port)
            # Only send AUDAC syntax on candidate command ports, never HTTP.
            if port == 80:
                return
            frame = b"#|NWP220|CLIENT>1|GET_REQ^INPUT_XLR>1>VOLUME>1^VOLUME||U|\r\n"
            writer.write(frame)
            await writer.drain()
            self.log("TX", transport="tcp", port=port, data=repr(frame), hex=frame.hex())
            received = await asyncio.wait_for(reader.read(8192), timeout=2)
            self.log("RX", transport="tcp", port=port, data=repr(received), hex=received.hex())
        except (OSError, TimeoutError) as exc:
            self.log("failure", transport="tcp", port=port, error=repr(exc))
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()

    async def udp(self, port: int):
        loop = asyncio.get_running_loop()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setblocking(False)
            sock.bind(("0.0.0.0", 0))
            for source in ("CLIENT>1", ""):
                frame = f"#|NWP220|{source}|GET_REQ^INPUT_XLR>1>VOLUME>1^VOLUME||U|\r\n".encode("ascii")
                await loop.sock_sendto(sock, frame, (self.host, port))
                self.log("TX", transport="udp", port=port, local=sock.getsockname(), data=repr(frame), hex=frame.hex())
                deadline = loop.time() + 2
                while loop.time() < deadline:
                    try:
                        received, peer = await asyncio.wait_for(
                            loop.sock_recvfrom(sock, 65535), timeout=deadline - loop.time()
                        )
                    except TimeoutError:
                        self.log("listen_complete", transport="udp", port=port)
                        break
                    except OSError as exc:
                        self.log("failure", transport="udp", port=port, error=repr(exc))
                        break
                    self.log("RX", transport="udp", port=port, peer=peer, data=repr(received), hex=received.hex())

    async def run(self):
        try:
            # A small explicit endpoint list, not a network or full-port scan.
            for port in (5001, 80, 8711, 8712):
                await self.tcp(port)
            for port in (8711, 8712):
                await self.udp(port)
        finally:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text("\n".join(json.dumps(row) for row in self.records) + "\n", encoding="utf-8")

    async def snapshot(self):
        """Capture a serialized set of read-only queries on the confirmed UDP port."""
        queries = [
            ("ALL_IN", "VOLUME"),
            ("ALL_OUT", "VOLUME"),
            ("ALL_IN", "MUTE"),
            ("ALL_OUT", "MUTE"),
            ("ALL_OUT", "ROUTE"),
        ]
        for kind, count in (("INPUT_XLR", 2), ("INPUT_BLUETOOTH", 2), ("INPUT_DANTE", 4), ("OUTPUT_DANTE", 4)):
            for index in range(1, count + 1):
                for command in ("VOLUME", "MUTE"):
                    queries.append((f"{kind}>{index}>VOLUME>1", command))
        for index in range(1, 5):
            for command in ("ROUTE", "MIXER"):
                queries.append((f"OUTPUT_DANTE>{index}>MIXER>1", command))
        loop = asyncio.get_running_loop()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setblocking(False)
                sock.bind(("0.0.0.0", 0))
                for target, command in queries:
                    frame = f"#|NWP220>1|CLIENT>1|GET_REQ^{target}^{command}||U|\r\n".encode("ascii")
                    started = loop.time()
                    await loop.sock_sendto(sock, frame, (self.host, 8711))
                    self.log("TX", transport="udp", port=8711, data=repr(frame), hex=frame.hex())
                    deadline = loop.time() + 2
                    while loop.time() < deadline:
                        try:
                            data, peer = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), deadline - loop.time())
                        except TimeoutError:
                            self.log("timeout", target=target, command=command)
                            break
                        self.log(
                            "RX",
                            peer=peer,
                            data=repr(data),
                            hex=data.hex(),
                            elapsed_ms=round((loop.time() - started) * 1000, 2),
                        )
                        if peer[0] == self.host and f"GET_RSP^{target}^{command}|".encode() in data:
                            break
                    await asyncio.sleep(0.1)
                self.log("idle_listen_start", seconds=5)
                deadline = loop.time() + 5
                while loop.time() < deadline:
                    try:
                        data, peer = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), deadline - loop.time())
                    except TimeoutError:
                        break
                    self.log("idle_RX", peer=peer, data=repr(data), hex=data.hex())
                self.log("idle_listen_end")
        finally:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_text("\n".join(json.dumps(row) for row in self.records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("--output", type=Path, default=Path("captures/endpoint-probe.jsonl"))
    parser.add_argument("--snapshot", action="store_true", help="Read channel/grouped state on confirmed UDP 8711")
    args = parser.parse_args()
    probe = Probe(args.host, args.output)
    asyncio.run(probe.snapshot() if args.snapshot else probe.run())
