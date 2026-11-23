"""Turn a landscape clip into a 9:16 reel: streamer's face on top, full gameplay below."""
from __future__ import annotations

import logging
import statistics
import subprocess
from pathlib import Path

import cv2

log = logging.getLogger("clipper.vertical")

W, H = 1080, 1920          # output size
FACE_H = 810               # top panel, 4:3
GAME_H = 608               # bottom panel, 16:9 (the whole gameplay frame)
TOP = 200                  # space left above for the Shorts / Reels interface


def sample_frames(video: Path, count: int) -> list:
    """Return `count` frames spread evenly through the video."""
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in range(count):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / count))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


OVERLAY_MAX_FACE = 0.12  # a face wider than this share of the frame is a full-screen camera


def find_facecam(video: Path, samples: int = 30) -> tuple[str, tuple[int, int, int, int]] | None:
    """Locate the streamer's camera. Returns (mode, crop) or None.

    mode "overlay": a small webcam box over the gameplay; crop is a 4:3 area around the face.
    mode "fullcam": the camera fills the screen for most of the clip; crop is a 9:16 column.

    A webcam overlay stays in one place, so the face that shows up at the same
    spot in many sampled frames is the streamer; faces of game characters move.
    """
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    frames = sample_frames(video, samples)
    if not frames:
        return None
    fh, fw = frames[0].shape[:2]
    scale = 1280 / fw
    clusters: list[list[tuple[int, tuple[float, float, float, float]]]] = []
    for idx, frame in enumerate(frames):
        gray = cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        for (x, y, w, h) in detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28)):
            box = (x / scale, y / scale, w / scale, h / scale)
            cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
            for cluster in clusters:
                bx, by, bw, bh = cluster[0][1]
                if abs(cx - (bx + bw / 2)) < bw * 0.7 and abs(cy - (by + bh / 2)) < bh * 0.7:
                    cluster.append((idx, box))
                    break
            else:
                clusters.append([(idx, box)])
    hits = lambda c: len({i for i, _ in c})
    median = lambda c: tuple(statistics.median(b[k] for _, b in c) for k in range(4))
    even = lambda v: int(v) // 2 * 2
    small = [c for c in clusters if median(c)[2] <= fw * OVERLAY_MAX_FACE]
    large = [c for c in clusters if median(c)[2] > fw * OVERLAY_MAX_FACE]

    # Camera filling the screen for most of the clip: keep a 9:16 column around the face.
    if large:
        best = max(large, key=hits)
        if hits(best) >= len(frames) * 0.6:
            x, y, w, h = median(best)
            cw = fh * 9 / 16
            left = min(max(x + w / 2 - cw / 2, 0), fw - cw)
            return "fullcam", (even(left), 0, even(cw), even(fh))

    # Small webcam box over the gameplay.
    if small:
        best = max(small, key=hits)
        if hits(best) >= max(4, len(frames) * 0.2):
            x, y, w, h = median(best)
            # Grow the face box into a 4:3 head-and-shoulders crop, kept inside the frame.
            cw = w * 3.0
            ch = cw * 3 / 4
            cx, cy = x + w / 2, y + h / 2 + h * 0.25
            left = min(max(cx - cw / 2, 0), fw - cw)
            top = min(max(cy - ch / 2, 0), fh - ch)
            return "overlay", (even(left), even(top), even(cw), even(ch))
    return None


def render_layout(src: Path, dst: Path, layout: dict, subtitles: Path | None = None,
                  moves: Path | None = None) -> bool:
    """Write the 9:16 version of `src` for a layout from clipper.layouts (split, crop or fit).

    moves: an ffmpeg sendcmd file that moves the crop named "face" (face tracking).
    subtitles and moves must sit in the same folder.
    """
    from .layouts import panel_heights

    mode = layout["mode"]
    send = f"sendcmd=f={moves.name}," if moves else ""
    if mode == "crop":
        x, y, w, h = layout["box"]
        graph = f"[0:v]{send}crop@face=w={w}:h={h}:x={x}:y={y},scale={W}:{H}:flags=lanczos,setsar=1[v]"
    elif mode == "split":
        face_h, game_h = panel_heights(layout["split"])
        fx, fy, fw, fh = layout["face"]
        gx, gy, gw, gh = layout["game"]
        graph = (f"[0:v]split=2[a][b];"
                 f"[a]{send}crop@face=w={fw}:h={fh}:x={fx}:y={fy},scale={W}:{face_h}:flags=lanczos,setsar=1[f];"
                 f"[b]crop=w={gw}:h={gh}:x={gx}:y={gy},scale={W}:{game_h}:flags=lanczos,setsar=1[g];"
                 f"[f][g]vstack[v]")
    else:
        return render_vertical(src, dst, None, subtitles)
    folder = None
    if subtitles:
        graph = graph[: -len("[v]")] + f"[pre];[pre]ass={subtitles.name}[v]"
        folder = subtitles.parent
    if moves:
        if folder and moves.parent.resolve() != folder.resolve():
            raise ValueError("subtitles and moves must be in the same folder")
        folder = moves.parent
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src.resolve()),
         "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst.resolve())],
        capture_output=True, text=True, cwd=str(folder) if folder else None,
    )
    if r.returncode != 0:
        log.error("vertical render failed: %s", r.stderr.strip()[-500:])
        return False
    return True


def render_vertical(src: Path, dst: Path, facecam: tuple[str, tuple[int, int, int, int]] | None,
                    subtitles: Path | None = None) -> bool:
    """Write the 9:16 version of `src` to `dst`, with an optional .ass subtitle file burned in."""
    background = (f"scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,"
                  f"crop={W // 4}:{H // 4},boxblur=8:2,scale={W}:{H},eq=brightness=-0.25")
    if facecam and facecam[0] == "fullcam":
        x, y, w, h = facecam[1]
        graph = f"[0:v]crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos[v]"
    elif facecam:
        x, y, w, h = facecam[1]
        graph = (f"[0:v]split=3[a][b][c];[a]{background}[bg];"
                 f"[b]crop={w}:{h}:{x}:{y},scale={W}:{FACE_H}:flags=lanczos[face];"
                 f"[c]scale={W}:{GAME_H}[game];"
                 f"[bg][face]overlay=0:{TOP}[t];[t][game]overlay=0:{TOP + FACE_H}[v]")
    else:  # no webcam found: gameplay centred on the blurred background
        graph = (f"[0:v]split=2[a][c];[a]{background}[bg];[c]scale={W}:{GAME_H}[game];"
                 f"[bg][game]overlay=0:{(H - GAME_H) // 2}[v]")
    cwd = None
    if subtitles:
        # ffmpeg's filter syntax chokes on Windows paths ("C:\..."), so run from the
        # subtitle's folder and pass only its file name.
        graph = graph[: -len("[v]")] + f"[pre];[pre]ass={subtitles.name}[v]"
        cwd = str(subtitles.parent)
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src.resolve()),
         "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst.resolve())],
        capture_output=True, text=True, cwd=cwd,
    )
    if r.returncode != 0:
        log.error("vertical render failed: %s", r.stderr.strip()[-500:])
        return False
    return True
