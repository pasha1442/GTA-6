"""Turn a channel entry from config.json / the command line into a Source.

Accepted forms:
    name                      Twitch channel (default)
    twitch:name               Twitch channel
    https://twitch.tv/name    Twitch channel
    @handle                   YouTube channel handle
    youtube:@handle           YouTube channel handle (yt: also works)
    youtube:UCxxxxxxxx...     YouTube channel id
    https://youtube.com/@handle  or  .../channel/UCxxxx
    https://youtube.com/live/VIDEOID  or  .../watch?v=VIDEOID   one specific live video
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    platform: str  # "twitch" or "youtube"
    ident: str     # twitch login, or YouTube path part: "@handle" / "channel/UC..."
    name: str      # safe label used in logs, folders and file names


def parse_source(spec: str) -> Source:
    s = spec.strip()
    low = s.lower()

    # A link to one specific live video: youtube.com/live/ID, watch?v=ID, youtu.be/ID
    m = re.search(r"(?:youtube\.com/(?:live/|watch\?(?:.*&)?v=)|youtu\.be/)([\w-]{11})", s, re.I)
    if m:
        return Source("youtube", f"watch?v={m.group(1)}", f"yt-{m.group(1)}")
    m = re.search(r"youtube\.com/(@[\w.\-]+|channel/UC[\w-]{22})", s, re.I)
    if m:
        return _youtube(m.group(1))
    m = re.search(r"twitch\.tv/(\w+)", s, re.I)
    if m:
        return _twitch(m.group(1))

    for prefix in ("youtube:", "yt:"):
        if low.startswith(prefix):
            return _youtube(s[len(prefix):])
    if low.startswith("twitch:"):
        return _twitch(s[len("twitch:"):])
    if s.startswith("@") or re.fullmatch(r"UC[\w-]{22}", s):
        return _youtube(s)
    return _twitch(s)


def _twitch(login: str) -> Source:
    login = login.strip().lstrip("#").lower()
    if not re.fullmatch(r"\w+", login):
        raise ValueError(f"Not a valid Twitch channel name: {login!r}")
    return Source("twitch", login, login)


def _youtube(ident: str) -> Source:
    ident = ident.strip().strip("/")
    if re.fullmatch(r"UC[\w-]{22}", ident):
        ident = f"channel/{ident}"
    elif not ident.startswith(("@", "channel/")):
        ident = "@" + ident
    if not re.fullmatch(r"@[\w.\-]+|channel/UC[\w-]{22}", ident):
        raise ValueError(f"Not a valid YouTube channel: {ident!r}")
    label = ident.split("/")[-1].lstrip("@").lower()
    return Source("youtube", ident, f"yt-{label}")
