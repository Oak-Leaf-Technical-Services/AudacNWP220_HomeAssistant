# Phase 1: protocol and capability map

Research date: 2026-09-26. These are documentation findings, not hardware observations.

Follow-up: [initial hardware observations](hardware-session-2026-09-26.md) confirm
UDP 8711, core and grouped reads, CRLF framing and CRC32 replies. They also record
the supplied LUNA-F manual's TCP port and the failed NWP220 TCP connection attempts.
Unresolved items below describe the original research checkpoint; consult the
session report for the evidence now available.

Implementation follow-up: [write and HA validation](implementation-validation.md)
records whole-dB controls, source-address correlation, pairing cancellation and
the implemented entity scope. The table below is the original proposed mapping;
in particular, disconnect and mixer entities are deferred after hardware tests.

## Authoritative sources

1. [NWP220 ASCII command manual](https://audac.eu/eu/products/d/nwp220---network-input-panel---2-x-xlr-plus-bt-4-ch/command-manual/pdf/command-manual.pdf), labelled Nwp220 V1.2.1-RD-96, pages 1–7.
2. [Required Port Numbers revision 1.7, 28 May 2026](https://downloads.pvs.global/downloads/audac/products/information-sheets/AUDAC-Port-Numbers-V1.7.pdf), pages 1–2; linked from the current NWP220 product page.
3. [AUDAC Commander example](https://education.audac.eu/be-en/how-to-tutorials/d/audac-touch/commander-functionality/205-how-to-send-commands-to-multiple-audac-devices-via-a-single-commander/205-how-to-send-commands-to-multiple-audac-devices-via-a-single-commander).

## Transport finding

Source 2 lists NWP/NIO control on UDP 8711/8712, with no TCP control port.
It also explicitly describes NWP sockets as UDP. Source 3 demonstrates UDP
multicast on 8711. Unicast reply endpoints and port roles need hardware validation.
Do not substitute another AUDAC model's TCP port or silently assume TCP 5001.

## Documented command surface and proposed mapping

| Command | Scope / values | Proposed HA entity |
| --- | --- | --- |
| VOLUME | 2 XLR, 2 Bluetooth, 4 Dante inputs, 4 Dante outputs; -90…0 dB | 12 numbers |
| MUTE | Same channels; TRUE/FALSE | 12 switches |
| ROUTE | 4 Dante outputs; -1…21; -1 means mixed and is read-only | 4 selects, with mixed handled as observed status |
| MIXER | 4 outputs; indices 1…16; -90…0 dB | Optional advanced numbers after source mapping validation |
| BT_PAIR | Boolean pairing trigger | Button, subject to observed semantics |
| BT_DISCONNECT | Boolean disconnect trigger | Button, subject to observed semantics |

Source 1 defines these six commands. Source 3 identifies route values 1/2 as XLR
and 5/6 as Bluetooth left/right. Other route labels remain unresolved.

Framing: `#|destination|source|type^target^command|arguments|CRC|` plus CRLF;
LF is also accepted. Case matters. Types: GET_REQ, SET_REQ, GET_RSP; GET_RSP
acknowledges valid reads/writes. Source is optional; NWP220 and NWP220>0 match
any address. CRC may be `U`.

Grouped targets: ALL_IN/ALL_OUT for volume/mute; ALL_OUT for routing.
Preserve reserved positions and empty values.

## Implementation decisions pending evidence

- Obtain actual GET requests/responses, errors and write acknowledgements before
  encoding their detailed semantics. The published examples predominantly show SET.
- Verify grouped GET support independently of grouped SET support.
- Verify volume resolution before assigning HA number steps.
- Do not offer all integers in a documented numeric range as meaningful routing
  choices until their actual meanings and applicability are known.
- Distinguish channel attenuation from analogue preamp gain. Product capabilities
  alone do not supply a command API for phantom power, input mode, EQ or AGC.
- No documented MAC/serial query was found in this command list. Do not use the
  configurable device address or IP as a physical-device unique ID.
- No error grammar, notification subscription or heartbeat contract was found.
  Capture unknown replies rather than assigning invented error codes.
- Do not create Bluetooth-connected, signal-present or firmware entities without
  a verified way to obtain those values.

## Proposed integration design

These are engineering proposals, not claims about device behaviour:

- Separate message codec, asynchronous transport/client, and Home Assistant code.
- Serialize requests initially; match responses using verified addressing,
  target and command fields. Investigate late replies and notifications before
  treating a matching response as authoritative for a specific operation.
- Use a central coordinator for polling unless hardware demonstrates reliable
  notifications. Read back state after writes; do not replay uncertain writes.
- Use bounded timeouts, bounded buffers, backoff and cancellation-safe shutdown.
- Keep raw TX/RX at debug level, with sensitive fields redacted if encountered.
- Make raw-command input accept exactly one validated frame and reject injected
  separators/terminators that could introduce another command.
- Prefer a verified hardware identifier. If unavailable, evaluate a stored
  per-entry identity with host reconfiguration, clearly documenting that duplicate
  physical devices cannot then be reliably detected across address changes.

[Home Assistant config-flow guidance](https://developers.home-assistant.io/docs/core/integration/config_flow/)
supports setup-time validation and reconfiguration; its unique-ID guidance excludes
IP addresses and mutable names. Implementation and tests will follow that contract.

[HACS integration requirements](https://www.hacs.dev/docs/publish/integration/)
require integration runtime files under one `custom_components` directory.
Release metadata and installation instructions belong to the implementation/release
phase; this research checkpoint is intentionally not advertised as installable.
