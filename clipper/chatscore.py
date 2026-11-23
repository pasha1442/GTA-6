"""How much one chat message says about the moment on screen.

Chat on big Indian gaming streams spikes for many reasons that have nothing to do
with the gameplay: "W" spam, greetings, giveaway begging, like-goal counts, bot
messages and complaints about the stream itself ("mute", "no sound", "lag"). Those count for nothing here. Laughter and shock count double, because
they are the reactions that mark a moment worth clipping.
"""
from __future__ import annotations

import re

BOTS = {"nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot"}

# Whole message is one of these: noise.
_NOISE = re.compile(
    r"^(w+|l+|f+|gg+|\?+|\.+|!+|first|1st|claim(ed)?|hi+|hii+|hello+|hey+|helo+|hlo+|"
    r"namaste|ram ram|jai shree ram|good (morning|night|evening)|gm|gn|ok+|k+|yes+|no+|"
    r"\d+(\.\d+)?\s*k?\s*(likes?|views?|lies)?|"           # like / view counts: "97k", "100k likes"
    r")$", re.I)
# Message is about getting something from the streamer, not about the game.
_BEGGING = re.compile(r"\b(ps ?5|giveaway|give ?away|dedo|de do|please give|gift|members?hip|"
                      r"pin me|reply me|notice me|heart me|shout ?out|birthday)\b", re.I)
# Message is a complaint about the stream itself (muted mic, lag), not a reaction.
_TECH = re.compile(r"\b(un)?mute+d?\b|\bno (sound|audio|voice)\b|^(sound|audio|mic|voice)\b|\bmic (on|off)\b|"
                   r"\b(lag+|lagging|buffer(ing)?|quality|low res|blur+y?|brightness|volume|awaz|aawaz)\b",
                   re.I)
_LAUGH = re.compile(r"(ha){2,}|(he){3,}|\bl+o+l+\b|lmao+|lmfao|rofl|😂|🤣|"
                    r":face_with_tears_of_joy:|:rolling_on_the_floor_laughing:|"
                    r"\bxd+\b|hasi|haste haste|\bhaha", re.I)
_SHOCK = re.compile(r"\b(omg|wtf|bruh+|what+|kya+|bhai kya|ye kya|risky|bc|bsdk|mc|"
                    r"no way|insane|crazy|clip (it|this|that)|clip kar|clutch)\b|😱|💀|🔥|:skull:",
                    re.I)
_EMOJI_CODE = re.compile(r":[\w\-]+:")


def message_weight(user: str, text: str) -> float:
    """0 for noise, 2 for a laugh or shocked reaction, 1 for anything else."""
    user = user.lstrip("@").lower()
    if user in BOTS:
        return 0.0
    t = text.strip()
    if not t:
        return 0.0
    if _TECH.search(t):
        return 0.0
    if _LAUGH.search(t) or _SHOCK.search(t):
        return 2.0
    bare = _EMOJI_CODE.sub("", t).strip()
    if not bare:  # only channel emotes / emoji codes, and not laughing ones
        return 0.5
    if (_NOISE.match(bare) or _BEGGING.search(bare)
            or all(_NOISE.match(word) for word in bare.split())):  # "HELLO HELLO", "w w w"
        return 0.0
    return 1.0
