"""Read-only Twitch chat over IRC. Anonymous login, so no credentials needed."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable

log = logging.getLogger("clipper.chat")

HOST, PORT = "irc.chat.twitch.tv", 6697


async def read_chat(channel: str, on_message: Callable[[float, str, str], None]) -> None:
    """Call on_message(timestamp, user, text) for every chat message. Runs until cancelled."""
    channel = channel.lower()
    while True:
        writer = None
        try:
            reader, writer = await asyncio.open_connection(HOST, PORT, ssl=True)
            writer.write(f"NICK justinfan{random.randint(10000, 99999)}\r\nJOIN #{channel}\r\n".encode())
            await writer.drain()
            log.info("[%s] chat connected", channel)
            while True:
                raw = await asyncio.wait_for(reader.readline(), timeout=360)
                if not raw:
                    raise ConnectionError("chat connection closed")
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("PING"):
                    writer.write(line.replace("PING", "PONG", 1).encode() + b"\r\n")
                    await writer.drain()
                    continue
                # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message text
                if " PRIVMSG #" in line and line.startswith(":"):
                    prefix, _, rest = line[1:].partition(" PRIVMSG #")
                    user = prefix.split("!", 1)[0]
                    text = rest.partition(" :")[2]
                    on_message(time.time(), user, text)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # network trouble: reconnect
            log.warning("[%s] chat error: %s; reconnecting in 5s", channel, e)
            await asyncio.sleep(5)
        finally:
            if writer is not None:
                writer.close()
