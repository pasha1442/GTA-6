"""Cut Shorts / Reels with subtitles out of a video that is already on YouTube (or on disk).

    python -m clipper.shorts <youtube link or video file> [options]

Options:
    --count N        how many shorts to make (default 5)
    --min S --max S  length of each short in seconds (default 20 to 60)
    --lang hi|en     force the spoken language (default: detect)
    --layout L       auto: from the video type and layout.json (the frame selector's file)
                     split: webcam on top, gameplay below, the face followed (alias: facecam)
                     track: 9:16 crop that follows the face
                     crop: 9:16 crop from the centre, standing still
                     fit: whole frame on a blurred background  (default auto)
    --only N[,N]     render only these shorts (numbers as in plan.json)
    --no-subs        no subtitles
    --upper          subtitles in CAPITALS
    --no-hook        no headline at the top (default: plan.json's hook_text, else the title)
    --force          ignore the saved plan.json and pick the moments again
    --auto           never stop for Claude Code: pick by "most replayed" / loudness and
                     use the built-in Hinglish romanizer

Run it again and again; each run does the next step that is possible and stops when it
needs a decision. All files are in clips/shorts-<video id>/:

  0. Decides the video type from the faces in it (gaming_facecam, gameplay, talking_head,
     group), finds the streamer's webcam, and writes layout.json plus scene.jpg (sampled
     frames with the faces and webcam marked). The frame selector (python -m clipper.frames)
     edits layout.json: which part of the frame goes where, per video or per short.
  1. Downloads source.mp4, transcribes it (word timings), writes transcript.txt.
  2. Needs plan.json: which moments become shorts. Without it the run stops (exit code 2).
     Claude Code writes it after reading transcript.txt (see the /make-shorts skill);
     with ANTHROPIC_API_KEY set, the Claude API writes it instead.
  3. Hindi only: needs work/short-NN.hinglish.txt, one line per line of
     work/short-NN.captions.txt. The run writes the captions files and stops (exit code 2).
  4. Renders short-NN-<title>.mp4 (9:16, subtitles burned in) plus a .json with the
     title, caption and hashtags.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from . import faces, layouts, subtitles, vertical
from .llm import ask_json, has_api_credentials
from .vod import YTDLP, audio_energy, hms, rank_moments

log = logging.getLogger("clipper.shorts")



# ---------------------------------------------------------------- source video

def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def fetch_youtube(url: str, root: Path) -> tuple[Path, dict]:
    """Download the video (up to 1080p) once. Returns (path, info)."""
    got = _run(YTDLP + ["-J", url])
    if got.returncode != 0:
        sys.exit(f"Could not read that video: {got.stderr.strip()[-300:]}")
    full = json.loads(got.stdout)
    info = {k: full.get(k) for k in ("id", "title", "description", "duration", "channel", "chapters", "heatmap")}
    info["source"] = url
    out_dir = root / f"shorts-{info['id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / "source.mp4"
    log.info("video: %s (%s, %s)", info["title"], hms(info["duration"] or 0), info.get("channel"))
    if not video.exists():
        log.info("downloading the video (up to 1080p)...")
        got = _run(YTDLP + ["-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
                            "-o", str(out_dir / "source.%(ext)s"), url])
        if got.returncode != 0 or not video.exists():
            sys.exit(f"Download failed: {got.stderr.strip()[-300:]}")
    return video, info


def local_video(path: Path, root: Path) -> tuple[Path, dict]:
    name = re.sub(r"[^\w\-]+", "-", path.stem)[:40].strip("-") or "video"
    probe = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    info = {"id": name, "title": path.stem, "description": "", "duration": float(probe.stdout.strip() or 0),
            "source": str(path)}
    (root / f"shorts-{name}").mkdir(parents=True, exist_ok=True)
    return path, info


# ---------------------------------------------------------------- picking moments

PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "description": "Main spoken language: 'hi' (Hindi/Hinglish) or 'en'."},
        "shorts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "start": {"type": "number", "description": "Start, seconds into the video (a segment start)."},
                "end": {"type": "number", "description": "End, seconds into the video (a segment end)."},
                "score": {"type": "integer", "description": "0-100: how well this works as a Short."},
                "hook": {"type": "string", "description": "What grabs the viewer in the first 3 seconds."},
                "hook_text": {"type": "string", "description": "On-screen headline shown at the top for the "
                              "whole short: 3-8 words, under 40 characters, no emoji, makes people stay."},
                "why": {"type": "string", "description": "Why this moment works on its own."},
                "title": {"type": "string", "description": "Short title, under 60 characters."},
                "caption": {"type": "string", "description": "One-line caption for the post."},
                "hashtags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["start", "end", "score", "hook", "hook_text", "why", "title", "caption", "hashtags"],
            "additionalProperties": False,
        }},
    },
    "required": ["language", "shorts"],
    "additionalProperties": False,
}

PICK_SYSTEM = """You are a short-form video editor. From the transcript of a long YouTube video \
you choose the moments to cut out as YouTube Shorts and Instagram Reels.

A good short:
- makes sense to someone who never saw the full video (no "as I said earlier");
- grabs attention in its first 3 seconds (a bold claim, a question, a reaction, a punchline setup);
- has one complete idea, story, joke or reveal, and ends right after its payoff;
- is between {min_s} and {max_s} seconds long.

Rules:
- Start every short at the start time of a transcript line and end it at the end time of a \
transcript line. Never cut in the middle of a sentence.
- Shorts must not overlap.
- If "most replayed" data is given, viewers rewatched those parts most; prefer them when the \
content there also works on its own.
- Return up to {count} shorts, best first. Return fewer if the video does not have that many \
good moments; do not pad with weak ones.
- Write title, caption and hashtags in the style the video's audience uses: Hinglish (Hindi in \
Roman letters) for a Hindi video, English for an English video."""


def _clock(t: float) -> str:
    return f"{int(t) // 60}:{t % 60:04.1f}"


def pick_with_claude(info: dict, transcript: dict, count: int, min_s: int, max_s: int, model: str) -> dict:
    system = PICK_SYSTEM.format(count=count, min_s=min_s, max_s=max_s)
    return ask_json(system, context_text(info, transcript), PICK_SCHEMA, model=model, effort="high")


def context_text(info: dict, transcript: dict, scene: dict | None = None) -> str:
    """Everything an editor needs to pick moments: title, chapters, most replayed, transcript."""
    lines = [f"Title: {info.get('title')}", f"Duration: {hms(info.get('duration') or 0)} "
             f"({info.get('duration') or 0:.0f} seconds)"]
    if scene:
        a = scene["analysis"]
        lines.append(f"Video type: {scene['video_type']} ({scene['type_source']}; detected: {a['type']}, "
                     f"because {a['reason']}). Sampled frames with faces marked: scene.jpg. "
                     f"Types: {', '.join(faces.VIDEO_TYPES)}.")
    if info.get("description"):
        lines.append(f"Description: {info['description'][:1500]}")
    if info.get("chapters"):
        lines.append("Chapters: " + "; ".join(f"{_clock(c['start_time'])} {c['title']}" for c in info["chapters"]))
    peaks = _heatmap_peaks(info.get("heatmap"), 8)
    if peaks:
        lines.append("Most replayed parts: " + ", ".join(f"{_clock(a)}-{_clock(b)}" for a, b, _ in peaks))
    lines.append(f"\nTranscript (detected language: {transcript.get('language')}; times in seconds; "
                 "speech recognition makes mistakes):")
    lines += [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript["segments"]]
    return "\n".join(lines) + "\n"


def _heatmap_peaks(heatmap: list[dict] | None, top: int) -> list[tuple[float, float, float]]:
    """The most replayed stretches of a YouTube video: (start, end, value), most replayed first."""
    if not heatmap:
        return []
    marks = sorted(heatmap, key=lambda m: -m["value"])
    peaks = []
    for m in marks:
        if len(peaks) >= top:
            break
        if all(abs(m["start_time"] - p[0]) > 45 for p in peaks):
            peaks.append((m["start_time"], m["end_time"], m["value"]))
    return peaks


def pick_without_claude(video: Path, info: dict, count: int, max_s: int) -> list[dict]:
    """Fallback: centre each short on a most-replayed peak, or on the loudest moments."""
    peaks = [(a + b) / 2 for a, b, _ in _heatmap_peaks(info.get("heatmap"), count)]
    signal = "most replayed"
    if not peaks:
        signal = "loudest audio"
        peaks = [m["time"] for m in rank_moments(audio_energy(video), 5, count, warmup=10, min_gap=max_s, min_z=0.0)]
    if not peaks:
        signal = "spread through the video"
        duration = info.get("duration") or 0
        peaks = [duration * (i + 0.5) / count for i in range(count)]
    return [{"start": t - max_s * 0.4, "end": t + max_s * 0.6, "score": 0, "hook": "", "why": signal,
             "title": f"{info.get('title', '')[:45]} #{i + 1}", "caption": "", "hashtags": []}
            for i, t in enumerate(peaks)]


def snap(shorts: list[dict], segments: list[dict], min_s: float, max_s: float, duration: float) -> list[dict]:
    """Move each short's edges to sentence boundaries, keep its length in range, drop overlaps."""
    starts = sorted(s["start"] for s in segments) or [0.0]
    ends = sorted(s["end"] for s in segments) or [duration]
    nearest = lambda values, t: min(values, key=lambda v: abs(v - t))
    kept: list[dict] = []
    for sh in shorts:
        start = nearest(starts, sh["start"])
        fitting = [e for e in ends if min_s <= e - start <= max_s]
        end = nearest(fitting, sh["end"]) if fitting else min(start + max_s, max(sh["end"], start + min_s))
        start, end = max(start - 0.15, 0.0), min(end + 0.35, duration or end + 0.35)
        if end - start < min_s * 0.5:
            continue
        if any(start < k["end"] and k["start"] < end for k in kept):
            continue
        kept.append({**sh, "start": round(start, 2), "end": round(end, 2)})
    return kept


# ---------------------------------------------------------------- rendering

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "short"


def cut(src: Path, start: float, end: float, dst: Path) -> bool:
    """Frame-accurate cut (re-encoded, so the subtitles line up exactly)."""
    r = _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "aac", "-b:a", "192k", str(dst)])
    if r.returncode != 0:
        log.error("cut failed: %s", r.stderr.strip()[-300:])
    return r.returncode == 0


_detector: faces.Detector | None = None


def _faces() -> faces.Detector:
    global _detector
    if _detector is None:
        _detector = faces.Detector(0.6)
    return _detector


def scene(out_dir: Path, video: Path) -> dict:
    """layout.json for this video: its type and the default layout. Made once (takes ~15 s)."""
    data = layouts.load(out_dir)
    if data and data.get("analysis"):
        return data
    log.info("looking at the faces in the video to decide its type...")
    analysis = faces.analyze(video, sheet=out_dir / "scene.jpg", detector=_faces())
    data = layouts.build(analysis)
    layouts.save(out_dir, data)
    return data


def resolve_layout(n: int, clip: Path, data: dict, flag: str) -> tuple[dict, str]:
    """The layout for short n and why: from --layout, from layout.json, or switched for this short."""
    analysis = data["analysis"]
    frame = tuple(analysis["frame"])
    if flag != "auto":
        mode = {"facecam": "split", "track": "crop"}.get(flag, flag)
        spec = layouts.suggest(analysis, mode)
        if flag in ("crop", "track"):
            spec["track"] = flag == "track"
        return layouts.normalize(spec, frame), f"--layout {flag}"
    spec, source = layouts.for_short(data, n)
    if source == "default" and not data.get("edited") and data["video_type"] in ("gaming_facecam", "gameplay"):
        # A stream that switches to a full-screen camera: follow the face for this short.
        if faces.big_face_share(clip, detector=_faces()) >= 0.6:
            spec = layouts.normalize({**layouts.suggest(analysis, "crop"), "track": True}, frame)
            return spec, "full-screen camera in this short"
    return spec, "layout.json " + source


def follow_face(clip: Path, spec: dict, frame: tuple[int, int], path: Path) -> Path | None:
    """Track the face and write the crop moves for ffmpeg. None if the face is hardly ever seen."""
    if spec["mode"] == "split":
        box, bounds, face_at = spec["face"], layouts.cam_bounds(spec, frame), 0.45
        x, y, w, h = bounds
        search = layouts.inside([x - w * 0.1, y - h * 0.1, w * 1.2, h * 1.2], frame)
    else:
        box, bounds, face_at = spec["box"], [0, 0, frame[0], frame[1]], 0.38
        search = bounds
    prefer = (box[0] + box[2] / 2, box[1] + box[3] / 2)
    tracked = faces.track(clip, (box[2], box[3]), tuple(bounds), tuple(search), prefer, face_at,
                          detector=_faces())
    log.info("   face tracking: face seen in %.0f%% of the clip, %d scene cuts", tracked["found"] * 100,
             tracked["cuts"])
    if tracked["found"] < 0.15:
        return None
    return faces.write_sendcmd(path, tracked)


def _work(out_dir: Path, n: int, kind: str) -> Path:
    return out_dir / "work" / f"short-{n:02d}.{kind}"


def make_short(n: int, sh: dict, video: Path, transcript: dict, out_dir: Path, opts: dict,
               scene_data: dict) -> dict | None:
    title = sh.get("title") or f"short {n}"
    name = f"short-{n:02d}-{_slug(title)}"
    raw = _work(out_dir, n, "mp4")
    raw.parent.mkdir(exist_ok=True)
    log.info("[%s] %s to %s (%.0fs) %s", name, hms(sh["start"]), hms(sh["end"]), sh["end"] - sh["start"], title)
    if not cut(video, sh["start"], sh["end"], raw):
        return None
    spec, why = resolve_layout(n, raw, scene_data, opts["layout"])
    log.info("   layout: %s%s (%s)", spec["mode"], " + face tracking" if spec.get("track") else "", why)
    frame = tuple(scene_data["analysis"]["frame"])
    moves = None
    if spec.get("track") and spec["mode"] in ("split", "crop"):
        moves = follow_face(raw, spec, frame, _work(out_dir, n, "moves.txt"))
    sub_margin, hook_margin = layouts.margins(spec)
    hook = (sh.get("hook_text") or title) if opts["hook"] else None
    subs = None
    if opts["subtitles"]:
        hfile = _work(out_dir, n, "hinglish.txt")
        hinglish = _read_lines(hfile) if hfile.exists() else None
        made = subtitles.make_subtitles(transcript, sh["start"], sh["end"], _work(out_dir, n, "ass"),
                                        language=opts["language"], margin_v=sub_margin,
                                        model=opts["model"], use_claude=opts["use_claude"], upper=opts["upper"],
                                        hinglish=hinglish, hook=hook, hook_margin=hook_margin)
        if made:
            subs, cues = made
            sh["subtitles"] = " ".join(c.get("text") or " ".join(w["word"] for w in c["words"]) for c in cues)
    if subs is None and hook:
        subs = subtitles.write_ass([], _work(out_dir, n, "ass"), hook=hook, hook_margin=hook_margin,
                                   duration=sh["end"] - sh["start"])
    final = out_dir / f"{name}.mp4"
    if not vertical.render_layout(raw, final, spec, subs, moves):
        return None
    raw.unlink(missing_ok=True)
    sh.update({"file": str(final), "layout": spec["mode"], "face_tracking": bool(moves), "frame": spec,
               "layout_source": why})
    final.with_suffix(".json").write_text(json.dumps(sh, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("[%s] saved: %s", name, final)
    return sh


def _read_lines(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def missing_hinglish(plan: dict, transcript: dict, out_dir: Path) -> list[int]:
    """Write work/short-NN.captions.txt for every short; return the shorts whose
    work/short-NN.hinglish.txt is missing or no longer has one line per caption line."""
    missing = []
    for n, sh in enumerate(plan["shorts"], 1):
        lines = subtitles.caption_lines(transcript, sh["start"], sh["end"])
        cfile = _work(out_dir, n, "captions.txt")
        cfile.parent.mkdir(exist_ok=True)
        cfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
        hfile = _work(out_dir, n, "hinglish.txt")
        if lines and (not hfile.exists() or len(_read_lines(hfile)) != len(lines)):
            missing.append(n)
    return missing


def needs_claude(message: str) -> None:
    """Stop here: Claude Code (or a person) has to write a file before the next run."""
    print("\nNEEDS CLAUDE: " + message, flush=True)
    sys.exit(2)


# ---------------------------------------------------------------- main

def parse_args(argv: list[str], cfg: dict) -> tuple[str, dict]:
    opts = {"count": cfg["count"], "min": cfg["min_seconds"], "max": cfg["max_seconds"], "language": None,
            "layout": cfg["layout"], "subtitles": cfg["subtitles"], "upper": False, "force": False, "auto": False,
            "hook": True, "only": None}
    args = list(argv)
    flags = {"--no-subs": ("subtitles", False), "--upper": ("upper", True), "--force": ("force", True),
             "--auto": ("auto", True), "--no-hook": ("hook", False)}
    values = {"--count": ("count", int), "--min": ("min", int), "--max": ("max", int),
              "--lang": ("language", str), "--layout": ("layout", str),
              "--only": ("only", lambda v: {int(x) for x in v.split(",") if x.strip()})}
    rest = []
    while args:
        a = args.pop(0)
        if a in flags:
            opts[flags[a][0]] = flags[a][1]
        elif a in values and args:
            opts[values[a][0]] = values[a][1](args.pop(0))
        else:
            rest.append(a)
    if len(rest) != 1 or opts["layout"] not in ("auto", "fit", "crop", "track", "split", "facecam"):
        sys.exit(__doc__)
    return rest[0], opts


def main() -> None:
    from .__main__ import ROOT, load_config
    from .transcribe import transcribe

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config()
    scfg = cfg["shorts"]
    target, opts = parse_args(sys.argv[1:], scfg)
    opts["model"] = scfg["model"]
    opts["use_claude"] = has_api_credentials()
    root = ROOT / cfg["clips_dir"]

    if Path(target).is_dir() and (Path(target) / "info.json").exists():   # a folder from an earlier run
        out_dir = Path(target)
        info = json.loads((out_dir / "info.json").read_text(encoding="utf-8"))
        video = Path(info["video"])
    elif Path(target).is_file():
        video, info = local_video(Path(target), root)
        out_dir = root / f"shorts-{info['id']}"
    elif re.match(r"https?://", target):
        video, info = fetch_youtube(target, root)
        out_dir = root / f"shorts-{info['id']}"
    else:
        sys.exit(f"Not a file, a link or a shorts folder: {target}")
    info["video"] = str(video.resolve())
    (out_dir / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    # 0. What kind of video is this? Its faces decide the layout (webcam on top, follow the face, ...).
    scene_data = scene(out_dir, video)
    log.info("video type: %s (%s)", scene_data["video_type"],
             scene_data["analysis"]["reason"] if scene_data["type_source"] == "auto" else scene_data["type_source"])

    # 1. Transcript with word timings, kept so a re-run skips this slow step.
    tpath = out_dir / "transcript.json"
    transcript = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else None
    if transcript is None or (opts["language"] and transcript.get("forced_language") != opts["language"]):
        log.info("transcribing the whole video (this is the slow part)...")
        transcript = transcribe(video, scfg["whisper_model"], opts["language"] or cfg["whisper_language"], words=True)
        transcript["forced_language"] = opts["language"]
        tpath.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(context_text(info, transcript, scene_data), encoding="utf-8")
    log.info("transcript: %s, %d lines, language %s", transcript["model"], len(transcript["segments"]),
             transcript["language"])
    if not transcript["segments"]:
        sys.exit("No speech found in this video.")
    opts["language"] = opts["language"] or transcript["language"]
    hindi = opts["language"] in subtitles.HINGLISH_LANGUAGES
    if hindi:
        log.info("Hindi speech: subtitles will be in Hinglish")

    # 2. Pick the moments.
    ppath = out_dir / "plan.json"
    plan = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() and not opts["force"] else None
    if plan and plan.get("shorts"):
        log.info("using %s (%d shorts)", ppath, len(plan["shorts"]))
    else:
        plan = None
        if opts["use_claude"]:
            log.info("asking the Claude API to pick the best %d moments...", opts["count"])
            plan = pick_with_claude(info, transcript, opts["count"], opts["min"], opts["max"], scfg["model"])
            if "error" in plan:
                log.warning("Claude could not pick moments (%s)", plan["error"])
                plan = None
        if plan is None and not opts["auto"]:
            needs_claude(f"write {ppath} after reading {out_dir / 'transcript.txt'}. "
                         f"Pick up to {opts['count']} shorts of {opts['min']}-{opts['max']} seconds. "
                         "Format: see the /make-shorts skill. Then run this command again.")
        if plan is None:
            log.info("picking by most-replayed / loudness (--auto)")
            plan = {"language": opts["language"], "shorts": pick_without_claude(video, info, opts["count"], opts["max"])}
    # Claude Code may correct the video type after looking at scene.jpg.
    if (plan.get("video_type") in faces.VIDEO_TYPES and scene_data.get("type_source") != "user"
            and plan["video_type"] != scene_data["video_type"]):
        log.info("video type set to %s by plan.json", plan["video_type"])
        scene_data = layouts.set_type(scene_data, plan["video_type"], "claude")
        layouts.save(out_dir, scene_data)
    # Edges always go to sentence boundaries, also for a hand-written plan.
    plan["shorts"] = snap(plan["shorts"], transcript["segments"], opts["min"], opts["max"], info["duration"] or 0)
    ppath.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    if not plan["shorts"]:
        sys.exit("No good moments found.")

    # 3. Hinglish subtitle lines, written by Claude Code.
    if opts["subtitles"] and hindi and not opts["use_claude"] and not opts["auto"]:
        missing = missing_hinglish(plan, transcript, out_dir)
        if missing:
            files = ", ".join(f"short-{n:02d}" for n in missing)
            needs_claude(f"Hindi video. For {files}: read work/short-NN.captions.txt in {out_dir} and write "
                         "work/short-NN.hinglish.txt with exactly one Hinglish line per caption line "
                         "(rules: see the /make-shorts skill). Then run this command again.")

    # 4. Render.
    wanted = [n for n in range(1, len(plan["shorts"]) + 1) if not opts["only"] or n in opts["only"]]
    made = []
    for n in wanted:
        sh = plan["shorts"][n - 1]
        try:
            if make_short(n, sh, video, transcript, out_dir, opts, scene_data):
                made.append(sh)
        except Exception:
            log.exception("short %d failed", n)
    log.info("done: %d of %d shorts in %s", len(made), len(wanted), out_dir)


if __name__ == "__main__":
    main()
