import asyncio
import logging

from samsungtvws.async_remote import SamsungTVWSAsyncRemote
from samsungtvws.remote import SendRemoteKey

logging.basicConfig(level=logging.DEBUG)

host = "10.23.17.77"
port = 8002


async def main():
    tv = SamsungTVWSAsyncRemote(host=host, port=port, token_file="token_file")
    logging.debug(f"Connecting to {host}:{port}")
    await tv.start_listening()
    logging.debug("Connected")

    # Request app_list
    # logging.info(await tv.app_list())

    # Turn off
    await tv.send_command(SendRemoteKey.click("KEY_POWER"))

    # Turn off (FrameTV)
    # await tv.send_command(SendRemoteKey.hold_key("KEY_POWER", 3))

    # Rotate Frame TV (with auto rotation mount)
    # await tv.send_command(SendRemoteKey.hold_key("KEY_MULTI_VIEW", 3))

    await asyncio.sleep(15)

    await tv.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
