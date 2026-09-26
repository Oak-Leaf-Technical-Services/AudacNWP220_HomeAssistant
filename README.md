# AUDAC NWP for Home Assistant

Native local control of the **AUDAC NWP220** using its ASCII protocol over
**unicast UDP 8711**. No cloud account, external Python dependency or generic TCP
integration is required.

Version **0.1.0**. Requires **Home Assistant 2026.2.3 or later**. Tested with
Home Assistant 2026.2.3, a real NWP220 and a capture-based fake UDP server.
This is an independent custom integration, not an official AUDAC product.

## Entities

| Entity | Count | Behaviour |
| --- | ---: | --- |
| Channel level | 12 numbers | -90 to 0 dB, 1 dB steps |
| Channel mute | 12 switches | On means muted |
| Dante output source | 4 selects | Off, XLR 1/2, Bluetooth left/right |
| Connected | 1 binary sensor | Off after a failed poll |
| Protocol address | 1 diagnostic sensor | For example NWP220>1; not a hardware identifier |
| Start/cancel Bluetooth pairing | 2 buttons | Disabled by default; enable in entity settings |

The twelve level/mute channels are two XLR inputs, two Bluetooth inputs, four
Dante inputs and four Dante outputs. Levels are channel attenuation, not analogue
microphone preamp gain. Example entity names: **XLR input 1 level**, **XLR input 1
mute**, **Dante output 4 source**. Entity IDs depend on your device name.

Mixed or unmapped output routes remain visible as read-only select values; they
are never silently displayed as Off. Selecting a supported source replaces the
output's existing mix.

## Installation

### HACS custom repository

Add this repository to HACS:

1. Open **Custom repositories** from the HACS menu.
2. Add `https://github.com/Oak-Leaf-Technical-Services/AudacNWP220_HomeAssistant`
   with type **Integration**.
3. Download **AUDAC NWP** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → AUDAC NWP**.

Updates are downloaded through HACS; restart Home Assistant after updating.
This repository is not automatically included in HACS's default catalogue.

### Manual installation

Copy `custom_components/audac_nwp` into the `custom_components` directory inside
your Home Assistant configuration directory. The resulting path must be
`config/custom_components/audac_nwp/manifest.json`. Restart Home Assistant.

Alternatively, extract `dist/audac_nwp-0.1.0.zip` into the HA configuration
directory; it contains the `custom_components/audac_nwp/` layout. Build this archive
with `python tools/build_release.py`. Do not install development files into HA.

## Configuration

Enter the panel hostname or IPv4 address. Setup reads all core state before
creating an entry. The default is **UDP 8711**; advanced setup options allow a
different port. This integration does not use multicast or port 8712.

Allow traffic from HA to the panel's UDP 8711 and replies to HA's ephemeral UDP
port. Container networking and inter-VLAN firewall rules must permit this traffic.

Use **Reconfigure** to update the same panel's host/port. Use **Configure** to adjust
polling from 5–300 seconds (default 15 seconds). Five grouped requests read all
core controls; individual entities do not poll independently.

There is no documented serial/MAC query in the supported command list. Device
and entity IDs therefore use the persistent config-entry ID. They survive host
changes made through Reconfigure. Removing/re-adding creates a new identity;
different host aliases cannot reliably be detected as the same physical panel.
A configurable AUDAC address is never used as a unique hardware ID.

## Advanced raw-command action

The normal entities do not depend on this action. It accepts one complete
GET_REQ or SET_REQ frame, adds CRLF if omitted, validates framing/checksum, and
replaces both addresses to operate only on the selected panel. The optional
response contains the received argument. Core state is refreshed afterwards.

```yaml
action: audac_nwp.send_command
data:
  device_id: YOUR_AUDAC_DEVICE_ID
  command: "#|NWP220||GET_REQ^ALL_OUT^ROUTE||U|"
response_variable: audac_result
```

Only use commands supported by your panel. Raw commands can change settings;
writes are never retried automatically. Unsupported commands and invalid values
may be silently ignored and appear as timeouts.

## State and recovery

One managed UDP socket is shared by all entities for each panel. Requests are
serialized and correlated by client address, target and command. Different client
addresses prevent a delayed SET acknowledgement from satisfying a later GET.
Bad checksums and incomplete datagrams are discarded; multiple complete frames
in one datagram are supported.

After controls change, authoritative grouped state is read before updating HA.
A missing acknowledgement fails the action; the integration never blindly replays
a write. The next successful poll reconciles uncertain outcomes.

Communication failures make controls unavailable. Polling automatically recreates
the endpoint with a retry cooldown capped at 60 seconds. No reload should be
needed. Reliable unsolicited notifications remain unverified, so polling is used.

## Troubleshooting

- **Cannot connect:** check IP, UDP firewall rules and grouped-command support in
  the installed firmware. Ping alone does not prove protocol access.
- **TCP:** the LUNA-F manual's TCP 5001 specification does not establish NWP220
  support. This panel answered UDP 8711; tested TCP endpoints timed out.
- **Fractional levels:** hardware silently ignored them. Controls use whole dB.
- **Unavailable after raw commands:** wait for the next poll. Unsupported writes
  can produce the same timeout as a network interruption.
- **Unmapped source:** its current value is preserved as read-only. Use AUDAC
  Touch for routing/mixing not yet verified by this integration.

Enable raw logging temporarily:

```yaml
logger:
  default: warning
  logs:
    custom_components.audac_nwp: debug
```

Logs show TX/RX bytes for known audio commands. Undocumented command payloads are
redacted. Review logs before sharing: they can contain hosts/audio configuration.
Downloaded device diagnostics exclude the host and raw command history.

## Verified scope and limitations

Hardware validation covers individual/grouped reads, volume/mute/routing writes,
partial grouped volume/mute writes, pairing enable/cancel, CRC32, invalid values,
client-address correlation, socket recreation and HA state readback. A hardware
HA test also drops replies locally to verify unavailable/recovery behaviour and
restores the original core state. No device reboot or network change is performed.

Bluetooth disconnect did not acknowledge GET or SET on the test panel; it is not
exposed as a button. Mixer queries returned empty payloads, so mixer controls are
deferred. Phantom power, EQ, AGC, preamp gain and hardware identity are not inferred
from marketing capabilities. Firmware version is unknown; compatibility with every
firmware revision has not been established.

## Development

Pure protocol tests need only Python 3.13+: `python -m unittest tests.test_protocol -v`.
The complete HA test suite requires Linux and Python 3.13:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check custom_components tests tools
ruff format --check custom_components tests tools
```

Normal tests use mocks or a local UDP fake seeded from physical-device captures.
Malformed traffic, packet loss, duplicates and unknown errors are synthetic cases.
Only on an authorized, interruptible test panel:

```sh
AUDAC_TEST_HOST=192.168.10.103 pytest tests/test_hardware_ha.py
```

That opt-in test changes output 4, tests recovery and restores its original core
state. It rejects custom mixed routes because mixer restoration is unsupported.
The tools directory contains separate investigation scripts, not runtime dependencies.
GitHub Actions runs tests, Ruff, hassfest and HACS validation.

## References

- [Official NWP220 command manual](https://audac.eu/eu/products/d/nwp220---network-input-panel---2-x-xlr-plus-bt-4-ch/command-manual/pdf/command-manual.pdf)
- [AUDAC port requirements](https://downloads.pvs.global/downloads/audac/products/information-sheets/AUDAC-Port-Numbers-V1.7.pdf)
- [Protocol research](docs/protocol-map.md)
- [Initial hardware session](docs/hardware-session-2026-09-26.md)
- [Write and HA validation](docs/implementation-validation.md)
- [Release checklist](docs/releasing.md)

Licensed under the [MIT licence](LICENSE).
