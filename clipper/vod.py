"""Make clips from a recorded video: a finished YouTube stream, or a video file on disk.

    python -m clipper.vod <youtube link or file> [--top 5] [--no-post]

For a YouTube link it reads the chat replay, finds the moments where chat spiked
hardest across the whole video, and downloads only those moments. If the video has
no chat replay (or is a local file), it uses the loudest moments in the audio instead.
Each clip then goes through the usual transcribe / review / 9:16 step.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

log = logging.getLogger("clipper.vod")
YTDLP = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist"]


def rank_moments(series: np.ndarray, window: int, top: int, min_value: float = 0.0,
                 baseline: int = 300, warmup: int = 60, min_gap: int = 90, min_z: float = 3.0) -> list[dict]:
    """Find the seconds where the last `window` seconds stand out most from the 5 minutes before.

    `series` holds one number per second (chat messages, or audio energy).
    Returns up to `top` moments, strongest first: {"time", "value", "normal", "score"}.
    """
    x = np.asarray(series, dtype=np.float64)
    n = len(x)
    if n < warmup + window + 1:
        return []
    c1 = np.concatenate([[0.0], np.cumsum(x)])
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    t = np.arange(warmup + window, n + 1)          # window covers seconds [t - window, t)
    recent = c1[t] - c1[t - window]
    b_end = t - window
    b_start = np.maximum(b_end - baseline, 0)
    length = b_end - b_start
    mean = (c1[b_end] - c1[b_start]) / length       # per-second average before the window
    var = np.maximum((c2[b_end] - c2[b_start]) / length - mean ** 2, 0.0)
    expected = mean * window
    spread = np.sqrt(var * window) + 1e-9 + 0.05 * expected
    z = (recent - expected) / spread
    z[recent < min_value] = -np.inf

    moments = []
    for i in np.argsort(-z):
        if z[i] < min_z or len(moments) >= top:
            break
        when = int(t[i])
        if all(abs(when - m["_t"]) >= min_gap for m in moments):
            moments.append({"_t": when, "time": when - window / 2, "value": float(recent[i]),
                            "normal": float(expected[i]), "score": float(recent[i] / max(expected[i], 1e-9))})
    for m in moments:
        del m["_t"]
    return moments


def audio_energy(path: Path) -> np.ndarray:
    """Loudness per second of a media file."""
    rate = 8000
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate),
                        "-f", "s16le", "-"], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace")[-300:])
    pcm = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float64)
    seconds = len(pcm) // rate
    return np.sqrt((pcm[: seconds * rate].reshape(seconds, rate) ** 2).mean(axis=1))


def read_chat_replay(path: Path) -> list[tuple[float, str]]:
    """Read yt-dlp's live_chat.json: returns (seconds into the video, "user: text")."""
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            replay = json.loads(line)["replayChatItemAction"]
            offset = int(replay["videoOffsetTimeMsec"]) / 1000
        except (ValueError, KeyError, TypeError):
            continue
        if offset < 0:
            continue
        for action in replay.get("actions", []):
            item = action.get("addChatItemAction", {}).get("item", {})
            for renderer in item.values():
                if isinstance(renderer, dict) and "timestampUsec" in renderer:
                    user = renderer.get("authorName", {}).get("simpleText", "")
                    text = "".join(r.get("text", "") for r in renderer.get("message", {}).get("runs", []))
                    out.append((offset, f"{user}: {text}"))
    return sorted(out)


def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}h{s % 3600 // 60:02d}m{s % 60:02d}s"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def from_youtube(url: str, cfg: dict, top: int, root: Path) -> list[Path]:
    info = _run(YTDLP + ["--skip-download", "--print", "%(id)s\t%(duration)s\t%(title)s", url])
    if info.returncode != 0:
        sys.exit(f"Could not read that video: {info.stderr.strip()[-300:]}")
    video_id, duration, title = info.stdout.strip().split("\t", 2)
    log.info("video: %s (%s)", title, hms(float(duration or 0)))
    name = f"yt-{video_id}"
    out_dir = root / cfg["clips_dir"] / name
    before, after = cfg["clip_before_seconds"], cfg["clip_after_seconds"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        log.info("reading chat replay...")
        _run(YTDLP + ["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                      "-o", str(tmp / "chat"), url])
        chat_files = list(tmp.glob("chat*.json"))
        chat = read_chat_replay(chat_files[0]) if chat_files else []
        if chat:
            log.info("%d chat messages; ranking spikes", len(chat))
            series = np.zeros(int(chat[-1][0]) + 2)
            for offset, _ in chat:
                series[int(offset)] += 1
            window, signal = cfg["spike"]["window"], "chat"
            moments = rank_moments(series, window, top, min_value=cfg["spike"]["min_messages"])
        else:
            log.info("no chat replay for this video; using the loudest moments instead (downloading audio)")
            got = _run(YTDLP + ["-f", "ba/b", "-o", str(tmp / "audio.%(ext)s"), url])
            audio = list(tmp.glob("audio.*"))
            if not audio:
                sys.exit(f"Could not download the audio: {got.stderr.strip()[-300:]}")
            window, signal = 5, "audio"
            moments = rank_moments(audio_energy(audio[0]), window, top)

    clips = []
    for m in moments:
        start, end = max(m["time"] - before, 0), m["time"] + after
        clip = out_dir / f"{name}-{hms(m['time'])}-x{m['score']:.1f}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s to %s (%s x%.1f)", hms(start), hms(end), signal, m["score"])
        got = _run(YTDLP + ["--download-sections", f"*{start:.0f}-{end:.0f}", "--force-keyframes-at-cuts",
                            "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                            "--force-overwrites", "-o", str(clip), url])
        if got.returncode != 0 or not clip.exists():
            log.error("download failed: %s", got.stderr.strip()[-300:])
            continue
        sample = [text for offset, text in chat if m["time"] - window <= offset <= m["time"] + window][:20]
        _write_sidecar(clip, name, m, signal, window, sample, f"{url} ({title})")
        clips.append(clip)
    return clips


def from_file(path: Path, cfg: dict, top: int, root: Path) -> list[Path]:
    name = re.sub(r"[^\w\-]+", "-", path.stem)[:40].strip("-") or "video"
    out_dir = root / cfg["clips_dir"] / name
    before, after = cfg["clip_before_seconds"], cfg["clip_after_seconds"]
    log.info("no chat for a local file; finding the loudest moments in the audio")
    moments = rank_moments(audio_energy(path), 5, top)
    clips = []
    for m in moments:
        start, end = max(m["time"] - before, 0), m["time"] + after
        clip = out_dir / f"{name}-{hms(m['time'])}-x{m['score']:.1f}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        r = _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(path), "-t", f"{end - start:.2f}",
                  "-c", "copy", "-movflags", "+faststart", str(clip)])
        if r.returncode != 0:
            log.error("cut failed: %s", r.stderr.strip()[-300:])
            continue
        _write_sidecar(clip, name, m, "audio", 5, [], str(path))
        clips.append(clip)
    return clips


def _write_sidecar(clip: Path, name: str, m: dict, signal: str, window: int, sample: list[str], source: str) -> None:
    meta = {"channel": name, "source": source, "signal": signal,
            "spike_time": hms(m["time"]), "score": round(m["score"], 2), "sample_messages": sample}
    if signal == "chat":
        meta["messages_in_window"] = int(m["value"])
        meta["baseline_per_window"] = round(m["normal"], 2)
    clip.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("clip saved: %s", clip)


def main() -> None:
    from .__main__ import ROOT, load_config
    from .process import process_clip

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    args = sys.argv[1:]
    post = "--no-post" not in args
    top = 5
    if "--top" in args:
        top = int(args[args.index("--top") + 1])
        del args[args.index("--top"): args.index("--top") + 2]
    args = [a for a in args if a != "--no-post"]
    if len(args) != 1:
        sys.exit(__doc__)
    cfg = load_config()
    target = args[0]
    if Path(target).is_file():
        clips = from_file(Path(target), cfg, top, ROOT)
    elif re.match(r"https?://", target):
        clips = from_youtube(target, cfg, top, ROOT)
    else:
        sys.exit(f"Not a file or a link: {target}")
    if not clips:
        log.info("no stand-out moments found")
    for clip in clips if post else []:
        try:
            process_clip(cfg, clip)
        except Exception:
            log.exception("[%s] processing failed", clip.stem)


if __name__ == "__main__":
    main()
