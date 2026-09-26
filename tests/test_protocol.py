"""Pure Python parser/client tests, including real capture regression cases."""

import asyncio
import json
import unittest
from dataclasses import replace

from .fake_nwp import FakeNwp, wire
from .protocol_support import ROOT, nwp


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.message = nwp.Message("CLIENT>1", "NWP220>1", "GET_RSP", "ALL_OUT", "ROUTE", "1^2^5^6^0^0^0^0")

    def test_real_capture_frames(self):
        fixture = json.loads((ROOT / "tests/fixtures/hardware_read_only.json").read_text())
        for exchange in fixture["exchanges"]:
            request = nwp.parse_frame(bytes.fromhex(exchange["request_hex"]))
            response = nwp.parse_frame(bytes.fromhex(exchange["response_hex"]))
            self.assertEqual((request.target, request.command), (response.target, response.command))
            self.assertEqual(response.kind, "GET_RSP")

    def test_crc16_crc32_and_lf(self):
        data = self.message.encode()
        fields = data.split(b"|")
        fields[5] = f"{nwp.crc16(b'|' + b'|'.join(fields[1:5]) + b'|'):04X}".encode()
        self.assertEqual(nwp.parse_frame(b"|".join(fields)), self.message)
        self.assertEqual(nwp.parse_frame(wire(self.message)), self.message)
        self.assertEqual(nwp.parse_frame(data.replace(b"\r\n", b"\n")), self.message)

    def test_multiple_complete_messages(self):
        self.assertEqual(nwp.parse_datagram(self.message.encode() * 2), (self.message,) * 2)

    def test_fragmented_datagrams_are_not_joined(self):
        data = self.message.encode()
        for piece in (data[:20], data[20:]):
            with self.assertRaises(nwp.ProtocolError):
                nwp.parse_datagram(piece)

    def test_malformed_and_checksum(self):
        for bad in (
            b"",
            b"junk\n",
            b"#|||U|\n",
            b"\xff\n",
            b"x" * 20000 + b"\n",
            wire(self.message).replace(b"1^2", b"2^2"),
            self.message.encode() + b"junk",
        ):
            with self.subTest(bad=bad[:30]), self.assertRaises(nwp.ProtocolError):
                nwp.parse_datagram(bad)

    def test_request_injection(self):
        for argument in ("x|U|", "\r\n#|", "\x00", "é"):
            with self.assertRaises(nwp.ProtocolError):
                replace(self.message, argument=argument).encode()

    def test_conversions(self):
        self.assertEqual(nwp.volume("-20.00"), -20)
        self.assertTrue(nwp.mute("TRUE"))
        self.assertFalse(nwp.mute("FALSE"))
        self.assertEqual(nwp.route("-1"), -1)
        for value in ("NaN", "inf", "1", "-91", True):
            with self.assertRaises(nwp.ProtocolError):
                nwp.volume(value)
        for value in ("1", "true", ""):
            with self.assertRaises(nwp.ProtocolError):
                nwp.mute(value)
        with self.assertRaises(nwp.ProtocolError):
            nwp.route("22")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeNwp()
        self.transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: self.fake, local_addr=("127.0.0.1", 0)
        )
        self.client = nwp.Nwp220("127.0.0.1", self.transport.get_extra_info("sockname")[1], timeout=0.5)

    async def asyncTearDown(self):
        await self.client.close()
        self.transport.close()
        await asyncio.sleep(0)

    async def test_snapshot_and_reserved_slots(self):
        state = await self.client.snapshot()
        self.assertEqual(len(state.levels), 12)
        self.assertEqual(state.routes, (1, 2, 5, 6))
        self.assertEqual(len(self.fake.requests), 5)
        self.assertEqual(len(self.fake.peers), 1)

    async def test_set_and_readback(self):
        await self.client.set_volume(11, -20)
        await self.client.set_mute(11, True)
        await self.client.set_route(3, 1)
        state = await self.client.snapshot()
        self.assertEqual((state.levels[11], state.mutes[11], state.routes[3]), (-20, True, 1))

    async def test_reject_writes_before_network(self):
        for operation in (
            lambda: self.client.set_volume(1, -0.5),
            lambda: self.client.set_route(0, -1),
            lambda: self.client.set_mute(0, "TRUE"),
            lambda: self.client.set_volume(-1, 0),
        ):
            with self.assertRaises((ValueError, nwp.ProtocolError)):
                await operation()
        self.assertEqual(self.fake.requests, [])

    async def test_timeout_no_write_replay_and_recovery(self):
        self.fake.mode = "drop"
        with self.assertRaises(nwp.CommunicationError):
            await self.client.set_mute(0, True)
        self.assertEqual(len(self.fake.requests), 1)
        with self.assertRaises(nwp.CommunicationError):
            await self.client.snapshot()
        self.assertEqual(len(self.fake.requests), 1)
        self.fake.mode = "normal"
        await asyncio.sleep(1.05)
        self.assertEqual(await self.client.get_volume(0), 0)
        self.assertEqual(len(self.fake.peers), 2)

    async def test_bad_packets_and_wrong_destination_timeout(self):
        for mode in ("malformed", "wrong_destination"):
            self.fake.mode = mode
            self.client._retry_at = 0
            with self.assertRaises(nwp.CommunicationError):
                await self.client.get_volume(0)

    async def test_unknown_error_response(self):
        self.fake.mode = "error"
        with self.assertRaises(nwp.UnexpectedResponse) as context:
            await self.client.get_volume(0)
        self.assertEqual(context.exception.message.argument, "unsupported")

    async def test_stale_and_duplicate_replies(self):
        self.fake.mode = "stale_then_valid"
        self.assertEqual(await self.client.get_volume(0), 0)
        self.fake.mode = "duplicate"
        self.assertEqual(await self.client.get_volume(0), 0)
        self.assertEqual(await self.client.get_volume(0), 0)

    async def test_parallel_requests_use_one_socket(self):
        self.assertEqual(await asyncio.gather(*(self.client.get_volume(i) for i in range(8))), [0] * 8)
        self.assertEqual(len(self.fake.peers), 1)
        self.assertEqual(len({r.source for r in self.fake.requests}), 8)

    async def test_cancel_then_reconnect(self):
        self.fake.mode = "drop"
        task = asyncio.create_task(self.client.get_volume(0))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.fake.mode = "normal"
        self.assertEqual(await self.client.get_volume(0), 0)

    async def test_close_pending_and_repeated_close(self):
        self.fake.mode = "drop"
        task = asyncio.create_task(self.client.get_volume(0))
        await asyncio.sleep(0.01)
        await self.client.close()
        with self.assertRaises(nwp.CommunicationError):
            await task
        await self.client.close()

    async def test_raw_single_frame_and_readdressing(self):
        reply = await self.client.send_raw("#|ALL|CLIENT>900|GET_REQ^ALL_OUT^ROUTE||U|")
        self.assertEqual(reply.argument, "1^2^5^6^0^0^0^0")
        self.assertEqual(self.fake.requests[0].destination, "NWP220")
        for bad in ("#|ALL||GET_REQ^ALL_OUT^ROUTE||U|\n" * 2, "#|ALL||SET_FRC^ALL_OUT^ROUTE|1|U|"):
            with self.assertRaises(nwp.ProtocolError):
                await self.client.send_raw(bad)

    async def test_invalid_group_does_not_produce_partial_state(self):
        self.fake.values["ALL_OUT", "MUTE"] = "FALSE"
        with self.assertRaises(nwp.ProtocolError):
            await self.client.snapshot()
