"""Validate grouped writes and Bluetooth triggers on an authorized test panel."""

import argparse
import asyncio
import logging

from validate_hardware import nwp


async def main(host):
    client = nwp.Nwp220(host)
    original = await client.snapshot()
    try:
        for command, argument in (("VOLUME", "^^^-1^^^^"), ("MUTE", "^^^TRUE^^^^")):
            reply = await client.send_raw(f"#|NWP220||SET_REQ^ALL_OUT^{command}|{argument}|U|")
            print("GROUPED", command, reply, await client.snapshot(), flush=True)
        for command in ("BT_PAIR", "BT_DISCONNECT"):
            try:
                print("BLUETOOTH_GET", command, await client.get("INPUT_BLUETOOTH>1>BLUETOOTH>1", command), flush=True)
            except nwp.NwpError as err:
                print("BLUETOOTH_GET_ERROR", command, repr(err), flush=True)
                await asyncio.sleep(1.1)
            try:
                await client.bluetooth(command)
                print("BLUETOOTH_SET", command, "ACKNOWLEDGED", flush=True)
            except nwp.NwpError as err:
                print("BLUETOOTH_ERROR", command, repr(err), flush=True)
                await asyncio.sleep(1.1)
            finally:
                if command == "BT_PAIR":
                    try:
                        print(
                            "PAIRING_CANCEL",
                            await client.send_raw("#|NWP220||SET_REQ^INPUT_BLUETOOTH>1>BLUETOOTH>1^BT_PAIR|FALSE|U|"),
                            flush=True,
                        )
                    except nwp.NwpError as err:
                        print("PAIRING_CANCEL_ERROR", repr(err), flush=True)
                        await asyncio.sleep(1.1)
    finally:
        await client.close()
        restore = nwp.Nwp220(host)
        try:
            await restore.set_volume(11, original.levels[11])
            await restore.set_mute(11, original.mutes[11])
            final = await restore.snapshot()
            print("RESTORED", final, flush=True)
            assert final == original
        finally:
            await restore.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    asyncio.run(main(args.host))
