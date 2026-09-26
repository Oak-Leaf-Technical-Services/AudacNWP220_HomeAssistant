"""Explicit write-validation session on an authorized test NWP220.

Restores output 4 volume/mute/route in finally. Refuses mixed/unknown initial
routing because restoring an arbitrary mixer is not yet supported.
"""

import argparse
import asyncio
import importlib.util
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nwp_hardware", ROOT / "custom_components/audac_nwp/nwp220.py")
nwp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nwp
spec.loader.exec_module(nwp)


async def run(host):
    client = nwp.Nwp220(host)
    original = await client.snapshot()
    print("BEFORE", original, flush=True)
    if original.routes[3] not in nwp.ROUTES:
        await client.close()
        raise RuntimeError("Cannot safely restore original routing")
    try:
        for value in (-1, -0.5, -0.1):
            try:
                # Intentionally bypass the production whole-dB guard so this
                # investigation can reproduce firmware rejection of fractions.
                await client._request("SET_REQ", nwp.CHANNELS[11][0], "VOLUME", f"{value:.2f}")
            except nwp.NwpError as exc:
                print("VOLUME_ERROR", value, repr(exc), flush=True)
                await asyncio.sleep(1.1)
            print("VOLUME", value, "READBACK", await client.get_volume(11), flush=True)
        for enabled in (True, False):
            await client.set_mute(11, enabled)
            print("MUTE", enabled, "READBACK", (await client.get(nwp.CHANNELS[11][0], "MUTE")).argument, flush=True)
        for value in (0, 1, 2, 5, 6):
            await client.set_route(3, value)
            print(
                "ROUTE", value, "READBACK", (await client.get("OUTPUT_DANTE>4>MIXER>1", "ROUTE")).argument, flush=True
            )
        # Bypass normal range validation only for this expressly authorized test.
        for invalid in ("-91", "1", "INVALID"):
            try:
                reply = await client._request("SET_REQ", nwp.CHANNELS[11][0], "VOLUME", invalid)
                print("INVALID", invalid, "REPLY", reply, flush=True)
            except nwp.NwpError as exc:
                print("INVALID", invalid, "ERROR", repr(exc), flush=True)
                await asyncio.sleep(1.1)
            print("AFTER_INVALID", await client.get_volume(11), flush=True)
        client._sequence = 65534
        print("HIGH_CLIENT_ADDRESS", await client.get_volume(11), flush=True)
        print("WRAP_NEW_SOCKET", await client.get_volume(11), flush=True)
    finally:
        # New client also proves reacquisition after a client-side transport close.
        await client.close()
        restore = nwp.Nwp220(host)
        try:
            await restore.set_route(3, original.routes[3])
            await restore.set_volume(11, original.levels[11])
            await restore.set_mute(11, original.mutes[11])
            final = await restore.snapshot()
            print("RESTORED", final, flush=True)
            if final != original:
                raise RuntimeError("Restored state differs from original; inspect immediately")
        finally:
            await restore.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    asyncio.run(run(args.host))
