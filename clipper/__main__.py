"""Watch Twitch and YouTube channels, record while live, and cut a clip at every chat spike.

Usage:
    python -m clipper                     # channels from config.json
    python -m clipper chan1 @ythandle     # channels from the command line

A plain name is a Twitch channel; "@handle" or "youtube:..." is a YouTube channel.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from . import chat as twitch_chat
from . import youtube
from .notify import notify
from .recorder import Recorder, is_live
from .chatscore import message_weight
from .sources import Source, parse_source
from .spikes import Spike, SpikeDetector

log = logging.getLogger("clipper")
ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "channels": [],
    "quality": "best",
    "poll_seconds": 60,          # how often to check whether a channel is live
    "segment_seconds": 4,
    "keep_segments_seconds": 300,
    "clip_before_seconds": 20,   # video kept before the spike
    "clip_after_seconds": 15,    # video kept after the spike
    "clips_dir": "clips",
    "youtube_chat_delay_seconds": 8,
    # Ignore "W" spam, greetings, giveaway begging and like counts; count laughs double.
    "filter_chat_noise": True,
    # After a clip is cut: transcribe it, review it, and render a 9:16 reel.
    "post_process": True,
    "transcribe": True,
    "whisper_model": "auto",       # auto = "medium" on an NVIDIA GPU, "small" on CPU
    "whisper_language": None,      # None = detect; "hi" or "en" to force one
    "review": True,                # needs ANTHROPIC_API_KEY; skipped without it
    "review_model": "claude-opus-5-5",
    "review_min_score": 60,        # reels below this score are rejected
    "render_rejected": False,      # also render 9:16 for rejected clips
    # The only game whose clips get approved, plus hints that help the reviewer recognise it.
    "game": "GTA 6 (Grand Theft Auto VI)",
    "game_notes": ("Grand Theft Auto VI, released 19 November 2026. Set in the state of Leonida "
                   "(Vice City and surroundings), with protagonists Jason and Lucia. Earlier games "
                   "such as GTA 5, GTA Online and GTA RP / FiveM servers are NOT this game."),
    # Segments are temporary and large, so they stay out of the OneDrive folder.
    "segments_dir": str(Path.home() / ".clipcreator" / "segments"),
    # python -m clipper.shorts: Shorts / Reels with subtitles from an uploaded YouTube video.
    "shorts": {"count": 5, "min_seconds": 20, "max_seconds": 60,
               "layout": "auto",           # auto, fit, crop, or facecam (webcam on top)
               "subtitles": True,          # Hindi speech gets Hinglish subtitles
               "whisper_model": "auto",    # "large-v3" is more accurate for Hindi, but slower
               "model": "claude-opus-5-5"},
    "spike": {"window": 10, "baseline": 300, "warmup": 60, "factor": 3.0,
              "zscore": 3.0, "min_messages": 15, "cooldown": 60},
}


_post_lock = asyncio.Lock()


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    path = ROOT / "config.json"
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        cfg["spike"].update(user.pop("spike", {}))
        cfg["shorts"].update(user.pop("shorts", {}))
        cfg.update(user)
    return cfg


async def make_clip(cfg: dict, channel: str, rec: Recorder, spike: Spike, sample: list[str]) -> None:
    start = spike.ts - cfg["clip_before_seconds"]
    end = spike.ts + cfg["clip_after_seconds"]
    # Wait until the recording has caught up with the end of the clip.
    deadline = end + 60
    while rec.covered_until() < end and time.time() < deadline:
        await asyncio.sleep(1)
    stamp = datetime.fromtimestamp(spike.ts).strftime("%Y%m%d-%H%M%S")
    out = ROOT / cfg["clips_dir"] / channel / f"{channel}-{stamp}-x{spike.score:.1f}.mp4"
    ok = await asyncio.to_thread(rec.cut, start, end, out)
    if not ok:
        return
    out.with_suffix(".json").write_text(json.dumps({
        "channel": channel,
        "spike_time": datetime.fromtimestamp(spike.ts).isoformat(timespec="seconds"),
        "messages_in_window": spike.count,
        "baseline_per_window": round(spike.baseline, 2),
        "score": round(spike.score, 2),
        "sample_messages": sample,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("[%s] clip saved: %s", channel, out)
    if cfg["post_process"]:
        from .process import process_clip
        async with _post_lock:  # one clip at a time; transcription and encoding are heavy
            try:
                await asyncio.to_thread(process_clip, cfg, out)
            except Exception:
                log.exception("[%s] post-processing failed for %s", channel, out.name)


def find_stream(src: Source, quality: str) -> tuple[str, str] | None:
    """If the channel is live, return (stream URL, chat id); otherwise None."""
    if src.platform == "youtube":
        video_id = youtube.find_live_video(src.ident)
        return (youtube.watch_url(video_id), video_id) if video_id else None
    url = f"https://www.twitch.tv/{src.ident}"
    return (url, src.ident) if is_live(url, quality) else None


async def run_session(cfg: dict, src: Source, url: str, chat_id: str) -> None:
    """One live stream: record, read chat, cut clips. Returns when the stream ends."""
    channel = src.name
    read_chat = youtube.read_chat if src.platform == "youtube" else twitch_chat.read_chat
    rec = Recorder(channel, url, Path(cfg["segments_dir"]) / channel, cfg["quality"], cfg["segment_seconds"])
    # YouTube chat arrives in batches a few seconds late, so the newest seconds are
    # always incomplete; judging slightly in the past keeps the counts honest.
    delay = cfg["youtube_chat_delay_seconds"] if src.platform == "youtube" else 0
    detector = SpikeDetector(**cfg["spike"], delay=delay)
    recent_msgs: deque[str] = deque(maxlen=20)
    clip_tasks: set[asyncio.Task] = set()

    last_by_user: dict[str, tuple[float, str]] = {}

    def on_message(ts: float, user: str, text: str) -> None:
        weight = message_weight(user, text) if cfg["filter_chat_noise"] else 1.0
        if cfg["filter_chat_noise"] and user:
            # One viewer posting "h h h" or the same line again and again is not a crowd reacting.
            prev = last_by_user.get(user)
            if prev and (ts - prev[0] < 5 or (prev[1] == text.strip().lower() and ts - prev[0] < 60)):
                weight = 0.0
            last_by_user[user] = (ts, text.strip().lower())
            if len(last_by_user) > 20000:
                last_by_user.clear()
        detector.add(ts, weight)
        if weight > 0:
            recent_msgs.append(f"{user}: {text}")

    async def ticker() -> None:
        last_status = time.time()
        while True:
            await asyncio.sleep(1)
            now = time.time()
            spike = detector.check(now)
            if spike:
                log.info("[%s] SPIKE: %d msgs in %ds (normal %.1f, x%.1f)", channel,
                         spike.count, detector.window, spike.baseline, spike.score)
                t = asyncio.create_task(make_clip(cfg, channel, rec, spike, list(recent_msgs)))
                clip_tasks.add(t)
                t.add_done_callback(clip_tasks.discard)
            if now - last_status >= 30:
                last_status = now
                recent, mean, _, _ = detector.stats(now)
                log.info("[%s] chat: %d msgs in last %ds (normal %.1f), %d segments buffered",
                         channel, recent, detector.window, mean, len(rec.segments()))
                await asyncio.to_thread(rec.cleanup, cfg["keep_segments_seconds"])

    rec.start()
    background = [asyncio.create_task(read_chat(chat_id, on_message)), asyncio.create_task(ticker())]
    try:
        await asyncio.to_thread(rec.wait)
        if clip_tasks:  # let clips in progress finish
            await asyncio.gather(*clip_tasks, return_exceptions=True)
    finally:
        for t in background:
            t.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        rec.stop()


async def watch(cfg: dict, src: Source) -> None:
    channel = src.name
    log.info("[%s] watching (%s)", channel, src.platform)
    notified_for = None  # so a recording that keeps failing does not spam notifications
    while True:
        try:
            found = await asyncio.to_thread(find_stream, src, cfg["quality"])
            if found:
                url, chat_id = found
                log.info("[%s] is LIVE, recording %s", channel, url)
                if notified_for != chat_id or src.platform == "twitch" and notified_for is None:
                    notify(f"{channel} is live", "Recording and watching chat for spikes.")
                notified_for = chat_id
                began = time.time()
                await run_session(cfg, src, url, chat_id)
                if time.time() - began < 30:
                    log.warning("[%s] recording stopped almost at once; the stream could not be captured", channel)
                else:
                    log.info("[%s] stream ended", channel)
            else:
                notified_for = None
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[%s] unexpected error", channel)
        await asyncio.sleep(cfg["poll_seconds"])


async def main() -> None:
    cfg = load_config()
    specs = sys.argv[1:] or cfg["channels"]
    if not specs:
        sys.exit("No channels given. Add them to config.json or run: python -m clipper <channel> ...")
    try:
        sources = [parse_source(s) for s in specs]
    except ValueError as e:
        sys.exit(str(e))
    await asyncio.gather(*(watch(cfg, s) for s in sources))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
