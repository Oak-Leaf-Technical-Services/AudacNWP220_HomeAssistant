# Implementation validation, 2026-09-26

## Software

- Home Assistant 2026.2.3, Python 3.13.15, Linux/WSL.
- pytest-homeassistant-custom-component 0.13.316.
- 29 offline tests passed; hardware test is skipped by default.
- Integration coverage: 93% in the offline suite.
- Ruff lint/format checks passed.
- Official hassfest from Home Assistant tag 2026.2.3: one integration checked,
  zero invalid integrations. GitHub CI also includes HACS validation; the remote
  HACS action has not been run before publication.

Offline tests cover real frame parsing, checksums, multiple frames, incomplete
datagrams, malformed replies, range conversion, timeout/backoff, cancelled and
closed clients, recovery, stale/duplicate replies, serialized concurrent requests,
raw-frame injection rejection, unknown responses, setup failure, config flow,
options, reconfiguration identity, HA writes/readback and availability recovery.

Unknown error-response types in the fake server are explicitly synthetic. The
physical NWP220 silently ignored the invalid writes below; no explicit error
grammar has been inferred.

## Physical-device writes

The user authorized changes to any output of the test panel. Output 4 was used.
Its original core state was restored and compared after every test session:
all 12 channel levels 0 dB, all mutes false, output routes 1/2/5/6.
Firmware revision was not obtained from this ASCII API.

| Operation | Observed result |
| --- | --- |
| Output 4 VOLUME -1.00 | GET_RSP acknowledgement and independent readback -1.00 |
| VOLUME -0.50 and -0.10 | No acknowledgement; independent GET remained -1.00 |
| VOLUME -91, 1, INVALID | No acknowledgement; independent GET remained -1.00 |
| MUTE TRUE / FALSE | Matching acknowledgement and independent readback |
| ROUTE 0 / 1 / 2 / 5 / 6 | Each acknowledged and independently read back |
| ALL_OUT VOLUME with only slot 4 populated | Slot 4 changed; other documented channels unchanged |
| ALL_OUT MUTE with only slot 4 populated | Slot 4 changed; other documented channels unchanged |
| GET/SET BT_PAIR, then FALSE cancellation | Acknowledged; initial pairing state FALSE |
| GET and SET BT_DISCONNECT | No response within the two-second deadline |
| CLIENT addresses through 65535 | Correct echo in response destination |
| Counter wrap and new local socket | Readback succeeded |

The integer-dB step is based on observed behaviour, not the two-decimal response
format. It is not a claim to have swept every allowed gain value or firmware.
Pairing was cancelled after testing. Bluetooth disconnect behaviour with an
actively connected source remains unverified.

## Home Assistant against the physical NWP220

`tests/test_hardware_ha.py` passed against the real panel with no mock client:

1. Set up the config entry and all platforms in Home Assistant's test runtime.
2. Call HA's number action to set output 4 to -1 dB.
3. Call HA's switch action to mute output 4.
4. Call HA's select action to choose XLR 1 for output 4.
5. Compare HA's coordinator state with a separate full device readback.
6. Drop incoming replies locally for one refresh, check HA becomes unavailable,
   then resume replies and check automatic endpoint/state recovery.
7. Restore original route, level and mute; compare the entire core snapshot.
8. Unload the integration and close its endpoint.

The lost-reply test simulates packet loss in the client. No physical network
disconnection, power-cycle, reboot, firmware update or network setting change
was performed. This does not replace a long-duration deployment or power-loss test.

## Evidence

Local debug logs are excluded from Git:

- `captures/write-validation.log`: initial investigation; a fractional write
  timed out, and the finally block restored state.
- `captures/write-validation-2.log`: routing/mute, invalid writes, source address
  checks and restoration.
- `captures/optional-validation-2.log`: grouped writes, Bluetooth results and
  restoration.
- `captures/ha-hardware-recovery.log`: HA actions, state transitions and recovery.

`tests/fixtures/hardware_write_observations.json` contains extracted wire bytes
and no-response cases from the successful investigation sessions. Network endpoints
and log timestamps are omitted. The original read fixtures remain separate.

## Release scope

Core UDP functionality is implemented and hardware-validated. Deferred items are
mixer coefficients, additional source mappings, Bluetooth disconnect, a hardware
serial/MAC identifier and a verified notification subscription. These are not
represented as working native entities. The raw action allows further investigation
without inventing additional protocol commands.

The minimum HA version matches the test runtime. No changes have been installed
into the user's running HA instance or published to GitHub as part of this work.
