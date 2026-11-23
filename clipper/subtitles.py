"""Burned-in subtitles for Shorts / Reels: a few words at a time, the spoken word highlighted.

English speech is shown as spoken. Hindi (or Urdu) speech is shown in Hinglish:
Hindi written in Roman letters the way people type it ("bhai ye kya ho gaya").
Claude does that conversion when an API key is set; otherwise a built-in
letter-by-letter romanizer is used, which is readable but less natural.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("clipper.subtitles")

HINGLISH_LANGUAGES = {"hi", "ur"}


# ---------------------------------------------------------------- caption chunks

def build_cues(words: list[dict], start: float, end: float, max_words: int = 3, max_chars: int = 18,
               max_gap: float = 0.6) -> list[dict]:
    """Group the words spoken between `start` and `end` into short captions.

    `words` are {start, end, word} in seconds into the whole video. Returned cues use
    seconds into the clip: {"start", "end", "words": [{start, end, word}]}.
    A cue ends after `max_words` words, at `max_chars` characters, at a pause, or
    after a sentence-ending mark.
    """
    picked = [{"start": max(w["start"], start) - start, "end": min(w["end"], end) - start, "word": w["word"]}
              for w in words if w["end"] > start + 0.05 and w["start"] < end - 0.05 and w["word"].strip()]
    cues: list[dict] = []
    current: list[dict] = []
    for w in picked:
        if current:
            text_len = len(" ".join(x["word"] for x in current + [w]))
            pause = w["start"] - current[-1]["end"] > max_gap
            # A short sentence-ending word ("hai.") joins the caption before it instead of flashing alone.
            tail = re.search(r"[.?!।]$", w["word"]) and len(w["word"]) <= 6 and text_len <= max_chars + 6
            if (((len(current) >= max_words or text_len > max_chars) and not tail) or pause
                    or re.search(r"[.?!।]$", current[-1]["word"])):
                cues.append(current)
                current = []
        current.append(w)
    if current:
        cues.append(current)
    out = [{"start": c[0]["start"], "end": c[-1]["end"], "words": c} for c in cues]
    # Keep each caption on screen until the next one when the gap is short, to avoid flicker.
    for a, b in zip(out, out[1:]):
        if b["start"] - a["end"] < 0.5:
            a["end"] = b["start"]
    if out:
        out[-1]["end"] = min(out[-1]["end"] + 0.3, end - start)
    return out


# ---------------------------------------------------------------- Hinglish

_SYSTEM_HINGLISH = """You convert speech-recognition captions from Hindi (in Devanagari, \
sometimes Urdu script) into Hinglish: the same words written in Roman letters the way Indian \
viewers type on YouTube and WhatsApp, e.g. "bhai ye kya ho gaya", "main nahi jaunga", "accha hai".

Rules:
- Transliterate, do not translate. Keep every word the speaker said, in the same order.
- English words written in Devanagari become normal English spelling (गेम -> game, मिशन -> mission).
- Words already in Roman letters stay as they are.
- Use common casual spellings (hai, nahi, kya, bhi, mein, kar raha, accha), lowercase except names.
- Return exactly one output line per input line, in the same order. Keep the word count of each \
line the same as the input wherever you can, since words are timed one by one."""

_SCHEMA_HINGLISH = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["lines"],
    "additionalProperties": False,
}


def to_hinglish(lines: list[str], model: str, use_claude: bool) -> list[str]:
    """Hinglish version of each line (same length list)."""
    if not lines:
        return []
    if use_claude:
        from .llm import ask_json

        numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
        answer = ask_json(_SYSTEM_HINGLISH, f"Convert these {len(lines)} caption lines:\n{numbered}",
                          _SCHEMA_HINGLISH, model=model, effort="low", max_tokens=16000)
        got = answer.get("lines")
        if isinstance(got, list) and len(got) == len(lines):
            return [re.sub(r"^\s*\d+\.\s*", "", g).strip() or romanize(l) for g, l in zip(got, lines)]
        log.warning("Hinglish conversion by Claude failed (%s); using the built-in romanizer",
                    answer.get("error", f"got {len(got) if isinstance(got, list) else 'no'} lines for {len(lines)}"))
    return [romanize(line) for line in lines]


_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
           "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
           "ौ": "au", "ॉ": "o", "ॅ": "e"}
_CONSONANTS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
               "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
               "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
               "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l"}
_NUKTA = {"क": "q", "ख": "kh", "ग": "gh", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh", "य": "y"}
_PRECOMPOSED = {"क़": "क़", "ख़": "ख़", "ग़": "ग़", "ज़": "ज़", "ड़": "ड़", "ढ़": "ढ़", "फ़": "फ़", "य़": "य़"}
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_FINAL_SHORT = {"aa": "a", "ee": "i", "oo": "u"}   # word-final long vowels are usually typed short


def _romanize_word(word: str) -> str:
    for a, b in _PRECOMPOSED.items():
        word = word.replace(a, b)
    # Split into syllables: [consonant, vowel] where vowel None = inherent "a" not yet decided.
    units: list[list] = []   # [text, vowel, is_consonant]
    tail = ""
    i = 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in _CONSONANTS:
            text = _CONSONANTS[ch]
            if nxt == "़":
                text = _NUKTA.get(ch, text)
                i += 1
            units.append([text, None, True])
        elif ch in _MATRAS and units and units[-1][2]:
            units[-1][1] = _MATRAS[ch]
        elif ch == "्" and units and units[-1][2]:
            units[-1][1] = ""
        elif ch in _VOWELS:
            units.append(["", _VOWELS[ch], False])
        elif ch in "ंँ" and units:
            units[-1].append("n")
        elif ch == "ः" and units:
            units[-1].append("h")
        elif ch == "।":
            tail += "."
        else:
            units.append([ch.translate(_DIGITS), "", False])
        i += 1
    # Schwa deletion: drop the inherent "a" at the end of a word, and between a vowel and a
    # consonant that carries its own vowel (karana -> karna, samajhana -> samajhna).
    has_vowel = lambda u: u[1] is None or u[1] != ""
    if len(units) > 1 and units[-1][2] and units[-1][1] is None and len(units[-1]) == 3:
        units[-1][1] = ""
    for k in range(len(units) - 2, 0, -1):
        u, prev, nxt = units[k], units[k - 1], units[k + 1]
        if (u[2] and u[1] is None and len(u) == 3 and has_vowel(prev) and len(prev) == 3
                and nxt[2] and has_vowel(nxt)):
            u[1] = ""
    out = []
    for k, u in enumerate(units):
        vowel = "a" if u[1] is None else u[1]
        if k == len(units) - 1 and len(units) > 1:
            vowel = _FINAL_SHORT.get(vowel, vowel)
        elif vowel == "aa" and k + 1 < len(units) and not units[k + 1][2] and units[k + 1][1]:
            vowel = "a"   # bhaai -> bhai, aaie -> aie
        out.append(u[0] + vowel + "".join(u[3:]))
    return "".join(out) + tail


def romanize(text: str) -> str:
    """Letter-by-letter Devanagari to Hinglish; other text passes through unchanged."""
    return re.sub(r"[ऀ-ॿ]+", lambda m: _romanize_word(m.group(0)), text)


# ---------------------------------------------------------------- .ass file

def _ts(seconds: float) -> str:
    cs = max(int(round(seconds * 100)), 0)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def hook_text(text: str) -> str:
    """Clean on-screen hook text: no emoji (the subtitle font has none), single spaces, CAPITALS."""
    text = "".join(ch for ch in text if ord(ch) < 0x2100)
    return re.sub(r"\s+", " ", text).strip().upper()


def write_ass(cues: list[dict], path: Path, margin_v: int = 520, font: str = "Arial Black",
              size: int = 78, highlight: str = "&H0000E5FF&", upper: bool = False,
              hook: str | None = None, hook_margin: int = 300, duration: float | None = None) -> Path:
    """Write cues as an .ass subtitle file for a 1080x1920 video.

    Each cue's text may differ from its words (Hinglish); `cue["text"]` wins when present.
    If the shown text has as many words as were timed, the spoken word is highlighted.
    `hook`: a headline shown at the top for the whole clip (black text on a yellow box),
    so viewers know straight away what the short is about.
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,70,70,{margin_v},1
Style: Hook,{font},68,&H00000000,&H00000000,&H0000E5FF,&H64000000,-1,0,0,0,100,100,0,0,3,16,0,8,90,90,{hook_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hook = hook_text(hook) if hook else ""
    if hook:
        end = duration if duration is not None else max((c["end"] for c in cues), default=60.0)
        pop = r"{\fscx70\fscy70\t(0,220,\fscx108\fscy108)\t(220,340,\fscx100\fscy100)}"
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(end + 1)},Hook,,0,0,0,,{pop}{_escape(hook)}")
    for cue in cues:
        text = cue.get("text") or " ".join(w["word"] for w in cue["words"])
        text = text.upper() if upper else text
        shown = text.split()
        timed = cue["words"]
        if len(shown) == len(timed) and len(timed) > 1:
            for i, w in enumerate(timed):
                start = cue["start"] if i == 0 else w["start"]
                stop = timed[i + 1]["start"] if i + 1 < len(timed) else cue["end"]
                if stop <= start:
                    continue
                parts = [(f"{{\\c{highlight}}}{_escape(s)}{{\\c&H00FFFFFF&}}" if j == i else _escape(s))
                         for j, s in enumerate(shown)]
                lines.append(f"Dialogue: 0,{_ts(start)},{_ts(stop)},Cap,,0,0,0,,{' '.join(parts)}")
        else:
            lines.append(f"Dialogue: 0,{_ts(cue['start'])},{_ts(cue['end'])},Cap,,0,0,0,,{_escape(text)}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def clip_cues(transcript: dict, start: float, end: float) -> list[dict]:
    words = [w for s in transcript.get("segments", []) for w in s.get("words", [])]
    return build_cues(words, start, end)


def caption_lines(transcript: dict, start: float, end: float) -> list[str]:
    """The text of each caption of a clip, as spoken (one line per caption)."""
    return [" ".join(w["word"] for w in c["words"]) for c in clip_cues(transcript, start, end)]


def make_subtitles(transcript: dict, start: float, end: float, path: Path, *, language: str | None,
                   margin_v: int, model: str, use_claude: bool, upper: bool = False,
                   hinglish: list[str] | None = None, hook: str | None = None,
                   hook_margin: int = 300) -> tuple[Path, list[dict]] | None:
    """Write the subtitle file for one clip. Returns (path, cues) or None when nobody speaks.

    `hinglish`: ready-made Hinglish, one line per caption (written by Claude Code).
    """
    cues = clip_cues(transcript, start, end)
    if not cues:
        return None
    lang = language or transcript.get("language")
    if lang in HINGLISH_LANGUAGES:
        spoken = [" ".join(w["word"] for w in c["words"]) for c in cues]
        if hinglish and len(hinglish) == len(cues):
            texts = hinglish
        else:
            if hinglish:
                log.warning("hinglish file has %d lines for %d captions; ignoring it", len(hinglish), len(cues))
            texts = to_hinglish(spoken, model, use_claude)
        for cue, text in zip(cues, texts):
            cue["text"] = text
    return write_ass(cues, path, margin_v=margin_v, upper=upper, hook=hook, hook_margin=hook_margin,
                     duration=end - start), cues
