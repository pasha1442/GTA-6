"""Post-process a clip: transcribe it, review it for reel-worthiness, render it 9:16.

Runs automatically after each clip is cut. To (re)process clips by hand:
    python -m clipper.process clips/some-channel            # every clip in a folder
    python -m clipper.process path/to/clip.mp4 --force      # redo one clip
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from . import vertical

log = logging.getLogger("clipper.process")


def has_api_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _settle_facecam(clip: Path, found, name: str):
    """Check a detected webcam position against where this channel's webcam usually is.

    A webcam overlay sits in the same place all stream, while a single clip can fool
    the detector (face hidden, or a game character's face standing still). So each
    channel folder keeps its past detections, and the most common position wins.
    """
    memory = clip.parent / "facecam.json"
    try:
        seen = [tuple(c) for c in json.loads(memory.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        seen = []
    same = lambda a, b: abs(a[0] - b[0]) < a[2] * 0.5 and abs(a[1] - b[1]) < a[3] * 0.5

    if found and found[0] == "fullcam":
        return found
    if found:
        seen = (seen + [found[1]])[-20:]
        memory.write_text(json.dumps(seen), encoding="utf-8")
    if not seen:
        return None
    usual = max(seen, key=lambda c: sum(same(c, o) for o in seen))
    votes = sum(same(usual, o) for o in seen)
    if found and (same(usual, found[1]) or votes < 2):
        return found
    if found is None and votes < 2 and len(seen) > 1:
        return None  # past detections disagree with each other; nothing to trust
    log.info("[%s] using this channel's usual webcam position", name)
    return "overlay", usual


def process_clip(cfg: dict, clip: Path, force: bool = False) -> dict:
    """Returns the clip's updated metadata (also saved next to the clip as .json)."""
    sidecar = clip.with_suffix(".json")
    meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    if meta.get("status") and not force:
        return meta
    name = clip.stem

    transcript = None
    if cfg["transcribe"]:
        from .transcribe import transcribe
        try:
            transcript = transcribe(clip, cfg["whisper_model"], cfg["whisper_language"])
            meta["transcript"] = transcript
            log.info("[%s] transcript (%s): %s", name, transcript["language"], transcript["text"][:120] or "(no speech)")
        except Exception as e:
            log.warning("[%s] transcription failed: %s", name, e)
            meta["transcript_error"] = str(e)[:300]

    # Decide whether this clip deserves a reel.
    status = "unreviewed"
    if cfg["review"] and has_api_credentials():
        from .review import review_clip
        review = review_clip(vertical.sample_frames(clip, 3), transcript, meta,
                             cfg["game"], cfg["game_notes"], cfg["review_model"])
        meta["review"] = review
        if "error" in review:
            log.warning("[%s] review failed: %s", name, review["error"])
        else:
            good = review["is_target_game"] and review["upload"] and review["score"] >= cfg["review_min_score"]
            status = "approved" if good else "rejected"
            log.info("[%s] review: %s, score %d, %s: %s (saw: %s). %s", name, status.upper(), review["score"],
                     cfg["game"], review["is_target_game"], review["game_seen"], review["reason"])
    elif cfg["review"]:
        meta["review"] = {"error": "no Anthropic API key set (ANTHROPIC_API_KEY)"}

    # Render the 9:16 version unless the review rejected the clip.
    if status != "rejected" or cfg["render_rejected"]:
        facecam = _settle_facecam(clip, vertical.find_facecam(clip), name)
        meta["facecam"] ={"mode": facecam[0], "crop": list(facecam[1])} if facecam else None
        layout = {"overlay": "face + gameplay", "fullcam": "full-screen camera"}[facecam[0]] if facecam else "gameplay only"
        reel = clip.parent / "reels" / status / f"{name}-9x16.mp4"
        if vertical.render_vertical(clip, reel, facecam):
            meta["reel"] = str(reel)
            log.info("[%s] reel saved (%s): %s", name, layout, reel)
    meta["status"] = status
    sidecar.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main() -> None:
    from .__main__ import load_config

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if not args:
        sys.exit(__doc__)
    clips: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            clips += sorted(c for c in p.rglob("*.mp4") if "reels" not in c.parts)
        elif p.is_file():
            clips.append(p)
        else:
            sys.exit(f"Not found: {a}")
    cfg = load_config()
    for clip in clips:
        try:
            process_clip(cfg, clip, force)
        except Exception:
            log.exception("[%s] processing failed", clip.stem)


if __name__ == "__main__":
    main()
