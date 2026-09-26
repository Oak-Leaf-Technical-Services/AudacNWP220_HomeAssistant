# Hardware validation checkpoint

Status: **initial read-only session completed** at the supplied device IP.
See [the session report](hardware-session-2026-09-26.md) for observed UDP replies
and TCP connection timeouts. Firmware version remains unknown. The rest of this
document is the broader validation plan, not a claim that every test has run.

Later [implementation validation](implementation-validation.md) records successful
core writes, HA state comparison, simulated packet-loss recovery and the remaining
limitations. The checklist below remains the original full validation plan.

## Evidence recording

For every test, record date, firmware, transport, local/remote port, exact escaped
TX/RX bytes, elapsed time, expected behaviour, observed behaviour and restoration
result. Keep capture fixtures separate from documentation-derived test fixtures.
Remove network identifiers before publishing captures when appropriate.

## First session: read-only discovery

1. Record the IP, firmware version and current settings from AUDAC Touch where
   available. Do not change firmware or network configuration.
2. Resolve the transport discrepancy. Test documented unicast control endpoints;
   investigate TCP only with an identified candidate endpoint. Do not assume that
   an open TCP socket implements this protocol.
3. Verify framing, CRLF/LF handling, response source and destination, checksum form,
   query argument syntax, response timing and repeated reads.
4. Read one volume, mute and route; compare with AUDAC Touch. Expand to all channels.
5. Try grouped reads and record index positions, gaps and unsupported responses.
6. Observe idle traffic and updates caused by an external controller. Determine
   whether notifications require registration or a particular listening port.
7. Investigate hardware identity through documented discovery or other official
   material; do not invent identification commands.

## Controlled write validation

Snapshot every affected setting first. A route change may alter mixer coefficients,
so capture those too before testing routing; do not assume restoring a route alone
restores a custom mix.

- Use an idle or isolated path for routing and mute tests.
- Initially reduce an existing level slightly, read back, then restore it.
- Record SET acknowledgement and subsequent GET independently.
- Confirm source labels, reserved routing values, mixed state and volume resolution.
- Test grouped partial writes only after confirming their index map and capturing
  all affected settings.
- Test invalid values only on an isolated path: a device may clamp instead of reject.
- Do not sweep gain extremes or activate Bluetooth disconnect/pairing on a live
  source merely to discover behaviour.
- Do not update firmware, factory-reset, reboot or change network configuration
  without explicit approval.

## Recovery and regression

Simulate client-side transport loss first. Verify timeout handling, availability,
backoff, recovery, shutdown, stale replies and concurrent entity operations.
For TCP, if confirmed, test stream fragmentation/coalescing and connection loss.
For UDP, test loss, duplication, reordering, delayed replies and endpoint recovery.
Test malformed and oversized input without unlimited memory growth.

Build the fake server from confirmed captures, retaining explicit provenance for
any synthetic edge cases. Add HA lifecycle/config-flow/coordinator tests after
the protocol checkpoint, then compare entity state with physical-device state.

## Release gates

- [ ] Transport and GET/SET/error semantics verified
- [ ] Physical identity strategy settled
- [ ] Core control restoration verified
- [ ] Parser/client tests pass
- [ ] HA setup, unload, reconfigure, service and outage tests pass
- [ ] Real hardware state agrees with HA
- [ ] HACS metadata, licence, CI and installation documentation complete

Initial UDP transport and core GET behaviour have hardware evidence. Complete
GET/SET/error validation and the remaining release gates are still outstanding.
