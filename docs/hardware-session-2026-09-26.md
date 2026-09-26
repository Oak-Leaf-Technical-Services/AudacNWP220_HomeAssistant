# NWP220 read-only hardware session, 2026-09-26

## Outcome

Native ASCII communication succeeded over **unicast UDP 8711** with the supplied
NWP220 at `192.168.10.103`. TCP control was not established.
All probes were read-only; no SET requests or configuration changes were made.
Firmware version remains unknown.

## TCP investigation

The supplied `AUDAC-LUNA-F-command-manual.pdf` explicitly lists TCP 5001 with
10 sockets, UDP 8711, and WebSocket 80 on pages 1 and 27 (LUNA-F V1.5/V1.6).
These are LUNA-F specifications, not an NWP220-specific TCP guarantee.

The NWP220 answered two pings at approximately 1 ms. TCP 5001 was attempted twice,
with 3-second and 4-second connection deadlines. Both attempts timed out. TCP
80, 8711 and 8712 also timed out with 4-second deadlines. No TCP connection was
established, so no TCP command framing could be tested.

Timeouts do not prove a device has no TCP implementation: filtering or a different
endpoint could produce the same result. This was a bounded candidate-port test,
not an exhaustive scan. It provides no evidence for implementing NWP220 TCP.

The first sandboxed socket attempt was denied locally with Windows error 10013;
it is excluded from device evidence. The reported network tests were rerun outside
the network-restricted sandbox.

## Confirmed UDP exchange

An ephemeral local UDP socket received a response from the device's port 8711:

```text
TX #|NWP220|CLIENT>1|GET_REQ^INPUT_XLR>1>VOLUME>1^VOLUME||U|\r\n
RX #|CLIENT>1|NWP220>1|GET_RSP^INPUT_XLR>1>VOLUME>1^VOLUME|0.00|017B2950|\r\n
```

An empty source field also worked, producing an empty response destination.
Explicit addressing to `NWP220>1` worked for the complete state snapshot.
Empty GET arguments, `U` in requests, and CRLF termination are now observed facts.
Responses use CRC32; all 37 snapshot checksums independently validated with
Python's `zlib.crc32` over the documented pipe-delimited span.

Two equivalent query variants sent to UDP 8712 received no response within their
2-second windows. This does not establish the purpose of 8712 or exclude another
protocol on that port.

## Snapshot

37 serialized requests produced 37 matching replies, with no timeout. Recorded
elapsed times were 15–32 ms (Windows event-loop timing is coarse).

| Query | Observed result |
| --- | --- |
| Individual VOLUME, all 12 documented channels | `0.00` for every channel |
| Individual MUTE, all 12 documented channels | `FALSE` for every channel |
| Individual ROUTE, Dante outputs 1–4 | `1`, `2`, `5`, `6` |
| ALL_IN VOLUME | 12 `0.00` slots |
| ALL_OUT VOLUME | 8 `0.00` slots |
| ALL_IN MUTE | 12 `FALSE` slots |
| ALL_OUT MUTE | 8 `FALSE` slots |
| ALL_OUT ROUTE | `1^2^5^6^0^0^0^0` |
| MIXER, each Dante output, empty GET argument | GET_RSP with empty argument |

Individual and grouped values agree at documented active indices. AUDAC's routing
example identifies 1/2 as XLR 1/2 and 5/6 as Bluetooth left/right; this session did
not physically verify those audio paths.

## Findings affecting implementation

- Grouped **reads** work. Five requests can obtain core volume/mute/route state.
- Reserved slots are populated in replies, whereas the command manual illustrates
  gaps for grouped writes. Preserve positional indexing; never expose reserved
  channels merely because their response slots contain values. This is a response
  behaviour clarification, not evidence that reserved channels are supported.
- Empty MIXER payloads are not zero-valued mixes. The query may require explicit
  indices or other semantics; resolving that is necessary before exposing mixer
  controls or promising restoration of custom mixes.
- No traffic arrived during a subsequent 5-second idle listen on the same socket.
  No external state changes were induced. Notification support remains unknown.
- The response device address is configurable and remains unsuitable as a unique
  hardware identity.

## Evidence and reproduction

Local raw captures (ignored by Git):

- `captures/endpoint-probe.jsonl`
- `captures/read-only-snapshot.jsonl`

Each contains timestamps, exact byte hex and escaped byte representations.
`tests/fixtures/hardware_read_only.json` retains all 37 snapshot request/reply
pairs with exact wire bytes and provenance, excluding network addresses.
It is captured evidence, not a fake-server implementation or a completed test suite.

```powershell
python tools/probe_nwp.py 192.168.10.103
python tools/probe_nwp.py 192.168.10.103 --snapshot --output captures/read-only-snapshot.jsonl
```

The probe is an investigation tool, not the production asynchronous protocol
client. It deliberately makes no SET requests and performs no retries of writes.

Next implementation should use the confirmed UDP transport unless further
NWP220-specific TCP evidence becomes available. Write acknowledgements, error
behaviour, volume increments, routing restoration, identity and recovery remain
separate validation work; this session does not establish production readiness.
