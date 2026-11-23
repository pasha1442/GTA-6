"""YouTube go-live lookup and live chat reader.

No API key: this reads the same public web endpoints the YouTube site uses.
They are unofficial, so they can change without notice.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.request
from typing import Callable

log = logging.getLogger("clipper.youtube")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "SOCS=CAI; CONSENT=YES+1",  # skip the EU cookie-consent redirect
}


def _fetch(url: str, body: dict | None = None) -> str:
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(_HEADERS)
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def find_live_video(ident: str) -> str | None:
    """Return the video id of the channel's current live stream, or None."""
    if ident.startswith("watch?v="):  # a specific video rather than a channel
        html = _fetch(f"https://www.youtube.com/{ident}")
        return ident[len("watch?v="):] if '"isLiveNow":true' in html else None
    html = _fetch(f"https://www.youtube.com/{ident}/live")
    m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"', html)
    if not m or '"isLiveNow":true' not in html:
        return None
    return m.group(1)


class _Chat:
    """One live-chat session for one video."""

    def __init__(self, video_id: str):
        html = _fetch(f"https://www.youtube.com/live_chat?is_popout=1&v={video_id}")
        key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', html)
        data = re.search(r'(?:window\["ytInitialData"\]|ytInitialData)\s*=\s*(\{.*?\});\s*</script>', html, re.S)
        if not (key and ver and data):
            raise RuntimeError("could not read the live chat page (chat disabled or stream ended?)")
        self._url = f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={key.group(1)}&prettyPrint=false"
        self._context = {"client": {"clientName": "WEB", "clientVersion": ver.group(1)}}
        chat = json.loads(data.group(1)).get("contents", {}).get("liveChatRenderer")
        if not chat:
            raise RuntimeError("this stream has no live chat")
        self.continuation = self._all_messages_token(chat) or _next_token(chat)[0]
        if not self.continuation:
            raise RuntimeError("live chat has no continuation token")

    @staticmethod
    def _all_messages_token(chat: dict) -> str | None:
        """Token for the 'Live chat' view (every message) instead of 'Top chat'."""
        try:
            items = chat["header"]["liveChatHeaderRenderer"]["viewSelector"][
                "sortFilterSubMenuRenderer"]["subMenuItems"]
            return items[1]["continuation"]["reloadContinuationData"]["continuation"]
        except (KeyError, IndexError, TypeError):
            return None

    def poll(self) -> tuple[list[tuple[float, str, str]], float] | None:
        """Return (messages, seconds to wait), or None when the chat has ended."""
        raw = _fetch(self._url, {"context": self._context, "continuation": self.continuation})
        chat = json.loads(raw).get("continuationContents", {}).get("liveChatContinuation")
        if not chat:
            return None
        token, wait = _next_token(chat)
        if not token:
            return None
        self.continuation = token
        messages = []
        for action in chat.get("actions", []):
            item = action.get("addChatItemAction", {}).get("item", {})
            for renderer in item.values():
                if isinstance(renderer, dict) and "timestampUsec" in renderer:
                    ts = int(renderer["timestampUsec"]) / 1e6
                    user = renderer.get("authorName", {}).get("simpleText", "")
                    runs = renderer.get("message", {}).get("runs", [])
                    text = "".join(
                        r.get("text") or (r.get("emoji", {}).get("shortcuts") or [""])[0] for r in runs
                    )
                    messages.append((ts, user, text))
        return messages, wait


def _next_token(chat: dict) -> tuple[str | None, float]:
    for c in chat.get("continuations", []):
        for d in c.values():
            if isinstance(d, dict) and d.get("continuation"):
                wait = float(d.get("timeoutMs", 3000)) / 1000
                return d["continuation"], min(max(wait, 1.0), 5.0)
    return None, 3.0


async def read_chat(video_id: str, on_message: Callable[[float, str, str], None]) -> None:
    """Call on_message(timestamp, user, text) per chat message until the chat ends."""
    started = time.time()
    skew = None  # local clock minus YouTube's clock, so times line up with the recording
    failures = 0
    chat = None
    while True:
        try:
            if chat is None:
                chat = await asyncio.to_thread(_Chat, video_id)
                log.info("[%s] chat connected", video_id)
            result = await asyncio.to_thread(chat.poll)
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            failures += 1
            chat = None
            log.warning("[%s] chat error: %s; retrying in %ds", video_id, e, min(5 * failures, 60))
            await asyncio.sleep(min(5 * failures, 60))
            continue
        if result is None:
            log.info("[%s] chat ended", video_id)
            return
        messages, wait = result
        if messages:
            now = time.time()
            gap = now - max(ts for ts, _, _ in messages)
            skew = gap if skew is None else min(skew, gap)
            for ts, user, text in messages:
                local = ts + skew
                if local >= started - 2:  # drop the backlog sent on connect
                    on_message(local, user, text)
        await asyncio.sleep(wait)
