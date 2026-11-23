"""Go-live check, rolling segment recorder and clip cutter (streamlink + ffmpeg)."""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("clipper.recorder")

STREAMLINK = [sys.executable, "-m", "streamlink"]


def is_live(url: str, quality: str = "best") -> bool:
    """True if the URL has a playable stream right now."""
    try:
        r = subprocess.run(
            STREAMLINK + ["--stream-url", url, quality],
            capture_output=True, text=True, timeout=45,
        )
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and r.stdout.strip().startswith("http")


@dataclass
class Segment:
    path: Path
    start: float  # wall-clock time the segment began
    end: float    # wall-clock time the next segment began


class Recorder:
    """Records a live stream as short numbered .ts segments.

    Segment timing comes from file creation times, so a chat timestamp can be
    mapped straight onto the recording.
    """

    def __init__(self, channel: str, url: str, seg_dir: Path, quality: str = "best", segment_seconds: int = 4):
        self.channel = channel
        self.url = url
        self.seg_dir = seg_dir
        self.quality = quality
        self.segment_seconds = segment_seconds
        self._sl: subprocess.Popen | None = None
        self._ff: subprocess.Popen | None = None

    def start(self) -> None:
        self.seg_dir.mkdir(parents=True, exist_ok=True)
        for old in self.seg_dir.glob("*.ts"):
            old.unlink(missing_ok=True)
        self._sl = subprocess.Popen(
            STREAMLINK + ["--stdout", self.url, self.quality],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._ff = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-c", "copy", "-f", "segment", "-segment_time", str(self.segment_seconds),
             "-reset_timestamps", "1", str(self.seg_dir / "%07d.ts")],
            stdin=self._sl.stdout, stderr=subprocess.DEVNULL,
        )
        self._sl.stdout.close()  # ffmpeg owns the pipe now

    def wait(self) -> None:
        """Block until the stream ends (or stop() is called)."""
        if self._ff:
            self._ff.wait()
        if self._sl:
            self._sl.wait()

    def stop(self) -> None:
        for p in (self._sl, self._ff):
            if p and p.poll() is None:
                p.terminate()
        for p in (self._sl, self._ff):
            if p:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()

    def segments(self) -> list[Segment]:
        """Finished segments only (the one still being written is left out)."""
        files = sorted(self.seg_dir.glob("*.ts"))
        times = []
        for f in files:
            try:
                times.append((f, f.stat().st_ctime))  # creation time on Windows
            except FileNotFoundError:
                pass
        return [Segment(f, t, times[i + 1][1]) for i, (f, t) in enumerate(times[:-1])]

    def covered_until(self) -> float:
        segs = self.segments()
        return segs[-1].end if segs else 0.0

    def cleanup(self, keep_seconds: int) -> None:
        cutoff = time.time() - keep_seconds
        for s in self.segments():
            if s.end < cutoff:
                s.path.unlink(missing_ok=True)

    def cut(self, start: float, end: float, out: Path) -> bool:
        """Join the segments covering [start, end] into one mp4 (no re-encode)."""
        segs = [s for s in self.segments() if s.end > start and s.start < end]
        if not segs:
            log.warning("[%s] no recorded video for that moment", self.channel)
            return False
        out.parent.mkdir(parents=True, exist_ok=True)
        listing = self.seg_dir / f"concat-{out.stem}.txt"
        listing.write_text(
            "".join(f"file '{s.path.as_posix()}'\n" for s in segs), encoding="utf-8"
        )
        try:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", str(listing),
                 "-c", "copy", "-movflags", "+faststart", str(out)],
                capture_output=True, text=True,
            )
        finally:
            listing.unlink(missing_ok=True)
        if r.returncode != 0:
            log.error("[%s] ffmpeg failed: %s", self.channel, r.stderr.strip()[-500:])
            return False
        return True
