"""Faces: what kind of video this is, where the streamer's webcam is, and how to follow a face.

    analyze(video)      samples the video and decides its type (gaming_facecam, gameplay,
                        talking_head, group), finds the webcam box, writes a contact sheet.
    find_webcam(...)    the "frame finder": the webcam box around a face that stays in one place.
    track(clip, ...)    follows a face through a clip and returns a smooth crop position per frame.

Faces come from OpenCV's YuNet model (downloaded once, 230 KB); without it, from OpenCV's
built-in Haar detector, which misses more side-on faces.
"""
from __future__ import annotations

import logging
import statistics
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("clipper.faces")

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
MODEL_PATH = Path.home() / ".clipcreator" / "models" / "face_detection_yunet_2023mar.onnx"

VIDEO_TYPES = {
    "gaming_facecam": "Gaming with a facecam (the streamer's webcam over the gameplay)",
    "gameplay": "Gameplay or screen only (no face on screen)",
    "talking_head": "One person talking to the camera (vlog, solo podcast, just chatting)",
    "group": "Several people (podcast, show, stage, interview)",
}

Box = tuple[int, int, int, int]  # x, y, w, h in source pixels

BIG_FACE = 0.09      # a face wider than this share of the frame is a camera shot, not a webcam overlay
SMALL_FACE = 0.015   # smaller than this is noise (crowds, posters)
CUT_DIFF = 32.0      # mean grey-level change between samples that counts as a scene cut


@dataclass
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def box(self) -> Box:
        return int(self.x), int(self.y), int(self.w), int(self.h)


# ---------------------------------------------------------------- detection

def ensure_model() -> Path | None:
    """The YuNet model file, downloaded on first use. None if it can't be had."""
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 100_000:
        return MODEL_PATH
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading the face model (230 KB) from github.com/opencv/opencv_zoo ...")
        tmp = MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL_PATH)
        return MODEL_PATH
    except OSError as e:
        log.warning("could not download the face model (%s); using OpenCV's basic face detector", e)
        return None


class Detector:
    """Face detector. Boxes come back in the coordinates of the image passed in."""

    def __init__(self, min_score: float = 0.7):
        self.min_score = min_score
        self.yunet = None
        self.haar = None
        path = ensure_model()
        if path:
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(path), "", (320, 320), min_score, 0.3, 5000)
            except cv2.error as e:
                log.warning("face model failed to load (%s); using OpenCV's basic face detector", e)
        if self.yunet is None:
            self.haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    @property
    def name(self) -> str:
        return "yunet" if self.yunet is not None else "haar"

    def detect(self, img: np.ndarray, max_width: int = 1280) -> list[Face]:
        h, w = img.shape[:2]
        if w < 16 or h < 16:
            return []
        s = min(1.0, max_width / w)
        small = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else img
        if self.yunet is not None:
            self.yunet.setInputSize((small.shape[1], small.shape[0]))
            _, found = self.yunet.detect(small)
            rows = [] if found is None else [(r[0], r[1], r[2], r[3], float(r[-1])) for r in found]
        else:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            rows = [(x, y, fw, fh, 0.8) for x, y, fw, fh in
                    self.haar.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(24, 24))]
        faces = []
        for x, y, fw, fh, c in rows:
            if c < self.min_score or fw <= 0 or fh <= 0:
                continue
            x0, y0 = max(x, 0), max(y, 0)
            x1, y1 = min(x + fw, small.shape[1]), min(y + fh, small.shape[0])
            if x1 - x0 > 4 and y1 - y0 > 4:
                faces.append(Face(float(x0 / s), float(y0 / s), float((x1 - x0) / s), float((y1 - y0) / s), float(c)))
        return faces


def video_props(video: Path) -> dict:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    props = {"width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
             "fps": fps, "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    props["duration"] = props["frames"] / fps if fps else 0.0
    cap.release()
    return props


def grab_frame(video: Path, t: float, width: int, height: int) -> np.ndarray | None:
    """One frame at `t` seconds, scaled to width x height (ffmpeg seeks long videos far faster
    than OpenCV does)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0.0):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:{height}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True)
    need = width * height * 3
    if r.returncode != 0 or len(r.stdout) < need:
        return None
    return np.frombuffer(r.stdout[:need], np.uint8).reshape(height, width, 3)


def grab_frames(video: Path, times: list[float], width: int, height: int) -> list[tuple[float, np.ndarray]]:
    """Frames at several times, read in parallel; frames that can't be read are left out."""
    with ThreadPoolExecutor(max_workers=6) as pool:
        frames = list(pool.map(lambda t: grab_frame(video, t, width, height), times))
    return [(t, f) for t, f in zip(times, frames) if f is not None]


# ---------------------------------------------------------------- video type

def face_stats(per_frame: list[list[Face]], width: int, height: int) -> dict:
    """Numbers that describe where faces are across the sampled frames (no image work here)."""
    n = max(len(per_frame), 1)
    big, small_min = BIG_FACE * width, SMALL_FACE * width
    any_face = sum(any(f.w >= small_min for f in fs) for fs in per_frame) / n
    big_face = sum(any(f.w >= big for f in fs) for fs in per_frame) / n
    multi = sum(len([f for f in fs if f.w >= 0.035 * width]) >= 2 for fs in per_frame) / n

    # Small faces that keep showing up at the same spot: a webcam overlay.
    clusters: list[list[tuple[int, Face]]] = []
    for i, fs in enumerate(per_frame):
        for f in fs:
            if not small_min <= f.w < big:
                continue
            for c in clusters:
                mx = statistics.fmean(g.cx for _, g in c)
                my = statistics.fmean(g.cy for _, g in c)
                mw = statistics.fmean(g.w for _, g in c)
                if abs(f.cx - mx) < mw * 0.7 and abs(f.cy - my) < mw * 0.7 and 0.5 < f.w / mw < 2:
                    c.append((i, f))
                    break
            else:
                clusters.append([(i, f)])
    hits = lambda c: len({i for i, _ in c})
    cam = None
    if clusters:
        best = max(clusters, key=hits)
        med = [statistics.median(getattr(f, k) for _, f in best) for k in ("x", "y", "w", "h")]
        cx, cy = med[0] + med[2] / 2, med[1] + med[3] / 2
        cam = {"box": [int(round(v)) for v in med], "hits": round(hits(best) / n, 3),
               "off_center": bool(abs(cx - width / 2) > 0.2 * width or abs(cy - height / 2) > 0.2 * height)}

    # The main face of camera shots (for talking-head videos).
    bigs = [max(fs, key=lambda f: f.w) for fs in per_frame if fs and max(f.w for f in fs) >= big]
    main = [int(round(statistics.median(getattr(f, k) for f in bigs))) for k in ("x", "y", "w", "h")] if bigs else None
    return {"samples": len(per_frame), "any_face": round(any_face, 3), "big_face": round(big_face, 3),
            "multi_face": round(multi, 3), "cam_face": cam, "main_face": main}


def _where(box: list[float], width: int, height: int) -> str:
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    v = "top" if cy < height / 3 else "bottom" if cy > height * 2 / 3 else "middle"
    h = "left" if cx < width / 3 else "right" if cx > width * 2 / 3 else "centre"
    return "centre" if (v, h) == ("middle", "centre") else f"{v}-{h}" if v != "middle" else f"middle-{h}"


def classify(stats: dict, webcam: Box | None, width: int, height: int) -> tuple[str, str]:
    """Decide the video type from face_stats() and the webcam box (if one was found)."""
    cam = stats.get("cam_face")
    if cam and stats["big_face"] < 0.5 and (
            (webcam and cam["hits"] >= 0.25) or (cam["hits"] >= 0.5 and cam["off_center"])):
        where = _where(cam["box"], width, height)
        box = " inside a webcam box" if webcam else ""
        return "gaming_facecam", f"the same small face sits at the {where}{box} in {cam['hits']:.0%} of the frames"
    if stats["big_face"] >= 0.45 and stats["multi_face"] < 0.35:
        return "talking_head", f"one large face in {stats['big_face']:.0%} of the frames"
    if stats["multi_face"] >= 0.25:
        return "group", f"two or more faces in {stats['multi_face']:.0%} of the frames"
    if stats["any_face"] >= 0.35:
        return "group", f"faces in {stats['any_face']:.0%} of the frames, in different places"
    return "gameplay", f"a face in only {stats['any_face']:.0%} of the frames"


# ---------------------------------------------------------------- frame finder (webcam box)

def find_webcam(grays: list[np.ndarray], face: list[float], frame_size: tuple[int, int]) -> Box | None:
    """Find the webcam box around a face that stays in one place.

    grays: sampled frames, greyscale, all the same size (any scale). face: the face box in
    source pixels. A webcam's edge is where the picture stops changing like gameplay does:
    outside it the pixels change a lot from sample to sample, inside (the room) they don't,
    and often a border line sits right on it in every sample.
    """
    if len(grays) < 6:
        return None
    width, height = frame_size
    h, w = grays[0].shape[:2]
    s = w / width
    stack = np.stack(grays).astype(np.float32)
    std = stack.std(axis=0)
    ev = np.zeros((h, w), np.float32)
    eh = np.zeros((h, w), np.float32)
    for im in grays:
        gx = cv2.Sobel(im, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(im, cv2.CV_32F, 0, 1, ksize=3)
        ev += (np.abs(gx) > 60) & (np.abs(gx) > 2 * np.abs(gy))
        eh += (np.abs(gy) > 60) & (np.abs(gy) > 2 * np.abs(gx))
    ev /= len(grays)
    eh /= len(grays)
    norm = float(np.median(std)) + 1.0
    if norm < 6:  # nothing moves outside the face: a still camera, not gameplay
        return None
    fx, fy, fw, fh = (v * s for v in face)
    edge_snap = 0.02 * w

    def best(direction: str) -> float | None:
        vertical = direction in ("left", "right")
        if vertical:
            a, b = int(max(0, fy - 0.6 * fh)), int(min(h, fy + 2.2 * fh))
            near, far, size = (fx - 0.15 * fw, fx - 4.5 * fw, fw) if direction == "left" else \
                (fx + 1.15 * fw, fx + 5.5 * fw, fw)
            limit = w
        else:
            a, b = int(max(0, fx - 1.0 * fw)), int(min(w, fx + 2.0 * fw))
            near, far, size = (fy - 0.15 * fh, fy - 3.5 * fh, fh) if direction == "top" else \
                (fy + 1.15 * fh, fy + 5.0 * fh, fh)
            limit = h
        if b - a < 4:
            return None
        step = -1 if far < near else 1
        top_score, top_pos = 0.0, None
        for p in range(int(near), int(far), step):
            if p < 9 or p > limit - 10:
                continue
            if vertical:
                line = float(ev[a:b, p - 1:p + 2].mean(axis=0).max())
                lo, hi = std[a:b, p - 8:p - 2], std[a:b, p + 3:p + 9]
            else:
                line = float(eh[p - 1:p + 2, a:b].mean(axis=1).max())
                lo, hi = std[p - 8:p - 2, a:b], std[p + 3:p + 9, a:b]
            outside, inside = (lo, hi) if step < 0 else (hi, lo)
            jump = (float(np.median(outside)) - float(np.median(inside))) / norm
            if jump < 0.15:
                continue
            score = line + 0.5 * min(jump, 1.5)
            if score > top_score:
                top_score, top_pos = score, p
        if top_pos is not None and top_score >= 0.45:
            pos = float(top_pos)
        else:
            edge = 0.0 if step < 0 else float(limit)
            # No border found: fine if the frame's edge is within reach (webcam in a corner).
            if abs(edge - near) > abs(far - near):
                return None
            pos = edge
        if pos < edge_snap:
            pos = 0.0
        elif pos > limit - edge_snap:
            pos = float(limit)
        return pos

    sides = {d: best(d) for d in ("left", "right", "top", "bottom")}
    if any(v is None for v in sides.values()):
        return None
    x0, x1, y0, y1 = sides["left"] / s, sides["right"] / s, sides["top"] / s, sides["bottom"] / s
    bw, bh = x1 - x0, y1 - y0
    if not (1.4 * face[2] <= bw <= 9 * face[2] and 1.2 * face[3] <= bh <= 7 * face[3]):
        return None
    if not 0.6 <= bw / bh <= 2.6 or bw * bh > 0.35 * width * height:
        return None
    return int(x0) // 2 * 2, int(y0) // 2 * 2, int(bw) // 2 * 2, int(bh) // 2 * 2


# ---------------------------------------------------------------- whole-video analysis

def analyze(video: Path, samples: int = 48, sheet: Path | None = None, detector: Detector | None = None) -> dict:
    """Sample the video, find its faces and webcam, and decide what type of video it is."""
    props = video_props(video)
    width, height, duration = props["width"], props["height"], props["duration"]
    det = detector or Detector(0.7)
    per_frame, grays, thumbs = [], [], []
    rw = min(width, 1280) // 2 * 2
    rh = int(round(rw * height / width / 2)) * 2 if width else 720
    gw = 960
    gh = int(round(gw * height / width)) if width else 540
    back = width / rw if rw else 1.0
    times = [duration * (i + 0.5) / samples for i in range(samples)]
    for t, frame in grab_frames(video, times, rw, rh):
        faces = [Face(f.x * back, f.y * back, f.w * back, f.h * back, f.score) for f in det.detect(frame)]
        per_frame.append(faces)
        grays.append(cv2.cvtColor(cv2.resize(frame, (gw, gh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY))
        thumbs.append((t, cv2.resize(frame, (480, int(480 * height / width)), interpolation=cv2.INTER_AREA), faces))
    if not per_frame:
        return {"type": "gameplay", "reason": "could not read frames", "frame": [width, height],
                "webcam": None, "stats": {}, "detector": det.name}
    stats = face_stats(per_frame, width, height)
    webcam = None
    if stats["cam_face"] and stats["cam_face"]["hits"] >= 0.25:
        webcam = find_webcam(grays, stats["cam_face"]["box"], (width, height))
    vtype, reason = classify(stats, webcam, width, height)
    result = {"type": vtype, "reason": reason, "frame": [width, height], "duration": round(duration, 2),
              "webcam": list(webcam) if webcam else None, "stats": stats, "detector": det.name}
    if sheet:
        contact_sheet(thumbs, result, sheet)
    return result


def contact_sheet(thumbs: list, result: dict, path: Path, count: int = 12) -> None:
    """12 sampled frames with the faces (green) and the webcam box (red) drawn on, for checking."""
    if not thumbs:
        return
    pick = [thumbs[int(i * len(thumbs) / count)] for i in range(min(count, len(thumbs)))]
    width = result["frame"][0]
    tiles = []
    for t, img, faces in pick:
        img = img.copy()
        k = img.shape[1] / width
        for f in faces:
            x, y, w, h = (int(v * k) for v in (f.x, f.y, f.w, f.h))
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 220, 0), 2)
        if result.get("webcam"):
            x, y, w, h = (int(v * k) for v in result["webcam"])
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
        stamp = f"{int(t // 3600):02d}:{int(t // 60 % 60):02d}:{int(t % 60):02d}"
        cv2.putText(img, stamp, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(img, stamp, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        tiles.append(img)
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    grid = np.vstack(rows)
    band = np.full((44, grid.shape[1], 3), 24, np.uint8)
    label = f"type: {result['type']}  -  {result['reason']}"
    cv2.putText(band, label[:150], (10, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imwrite(str(path), np.vstack([band, grid]), [cv2.IMWRITE_JPEG_QUALITY, 85])


def big_face_share(clip: Path, samples: int = 8, detector: Detector | None = None) -> float:
    """Share of a clip's frames that show a camera shot (one big face) rather than gameplay."""
    props = video_props(clip)
    if not props["width"] or not props["duration"]:
        return 0.0
    det = detector or Detector(0.7)
    rw = min(props["width"], 1280) // 2 * 2
    rh = int(round(rw * props["height"] / props["width"] / 2)) * 2
    times = [props["duration"] * (i + 0.5) / samples for i in range(samples)]
    frames = grab_frames(clip, times, rw, rh)
    big = sum(any(f.w >= 0.12 * rw for f in det.detect(img)) for _, img in frames)
    return big / max(len(frames), 1)


# ---------------------------------------------------------------- tracking

def _pick(faces: list[Face], current: tuple[float, float] | None, prefer: tuple[float, float] | None) -> Face | None:
    if not faces:
        return None
    if current is not None:
        near = min(faces, key=lambda f: (f.cx - current[0]) ** 2 + (f.cy - current[1]) ** 2)
        if abs(near.cx - current[0]) < 1.5 * near.w and abs(near.cy - current[1]) < 1.5 * near.h:
            return near
        return None
    if prefer is not None:
        return min(faces, key=lambda f: ((f.cx - prefer[0]) ** 2 + (f.cy - prefer[1]) ** 2) / max(f.w, 1))
    return max(faces, key=lambda f: f.w * f.score)


def follow(targets: list[tuple[float, float] | None], cut_at: list[int], frame_of: list[int], frames: int,
           size: tuple[int, int], bounds: Box, fps: float, dead_zone: float = 0.06,
           ease: float = 0.45, smooth_s: float = 0.5) -> tuple[list[int], list[int]]:
    """Turn per-sample crop targets (top-left x, y or None) into a smooth per-frame camera path.

    The camera holds still while the face stays near where it is, then eases toward it
    (no jitter); at a scene cut it jumps straight to the new spot; the crop never leaves `bounds`.
    """
    cw, ch = size
    bx, by, bw, bh = bounds
    clamp = lambda v, lo, hi: min(max(v, lo), max(lo, hi))
    centre = (bx + (bw - cw) / 2, by + (bh - ch) / 2)
    if frames <= 0:
        return [], []
    if not targets or all(t is None for t in targets):
        x, y = int(clamp(centre[0], bx, bx + bw - cw)), int(clamp(centre[1], by, by + bh - ch))
        return [x] * frames, [y] * frames
    # Fill gaps: hold the last known spot; before the first one, use the first one.
    first = next(t for t in targets if t is not None)
    filled, last = [], first
    for t in targets:
        last = t if t is not None else last
        filled.append(last)
    cuts = set(cut_at)
    cam = []
    cx, cy = filled[0]
    dzx, dzy = dead_zone * cw, dead_zone * ch
    for i, (tx, ty) in enumerate(filled):
        if i in cuts:
            cx, cy = tx, ty
        else:
            dx, dy = tx - cx, ty - cy
            if abs(dx) > dzx:
                cx += (dx - np.sign(dx) * dzx) * ease
            if abs(dy) > dzy:
                cy += (dy - np.sign(dy) * dzy) * ease
        cam.append((cx, cy))
    # Per frame: interpolate between samples of the same shot, then smooth within each shot.
    seg_starts = sorted({0, *(c for c in cuts if 0 < c < len(cam))})
    xs = np.zeros(frames)
    ys = np.zeros(frames)
    for k, si in enumerate(seg_starts):
        ei = seg_starts[k + 1] if k + 1 < len(seg_starts) else len(cam)
        f0 = 0 if k == 0 else frame_of[si]
        f1 = frame_of[ei] if ei < len(cam) else frames
        if f1 <= f0:
            continue
        idx = np.arange(f0, f1)
        sf = np.array(frame_of[si:ei], float)
        sx = np.array([c[0] for c in cam[si:ei]])
        sy = np.array([c[1] for c in cam[si:ei]])
        seg_x, seg_y = np.interp(idx, sf, sx), np.interp(idx, sf, sy)
        win = int(max(1, smooth_s * fps)) | 1
        if win > 1 and len(idx) > 2:
            pad = win // 2
            kern = np.ones(win) / win
            seg_x = np.convolve(np.pad(seg_x, pad, mode="edge"), kern, mode="valid")
            seg_y = np.convolve(np.pad(seg_y, pad, mode="edge"), kern, mode="valid")
        xs[f0:f1], ys[f0:f1] = seg_x[: f1 - f0], seg_y[: f1 - f0]
    out_x = [int(clamp(v, bx, bx + bw - cw)) for v in xs]
    out_y = [int(clamp(v, by, by + bh - ch)) for v in ys]
    return out_x, out_y


def track(clip: Path, size: tuple[int, int], bounds: Box, search: Box | None = None,
          prefer: tuple[float, float] | None = None, face_at: float = 0.42, rate: float = 6.0,
          detector: Detector | None = None) -> dict:
    """Follow a face through `clip` with a crop of `size` that stays inside `bounds`.

    search: the area to look for faces in (default: bounds). prefer: follow the face nearest
    to this point (e.g. the centre of the box the user drew). face_at: where the face sits in
    the crop, as a share of its height from the top.
    Returns {"fps", "frames", "x": [...], "y": [...], "found": share of samples with the face}.
    """
    cw, ch = size
    sx, sy, sw, sh = search or bounds
    det = detector or Detector(0.6)
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / rate))
    targets, frame_of, cut_at = [], [], []
    current, prev, missing = None, None, 0
    idx = 0
    while cap.grab():
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            region = frame[sy:sy + sh, sx:sx + sw]
            thumb = cv2.resize(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY), (32, 18),
                               interpolation=cv2.INTER_AREA).astype(np.float32)
            if prev is not None and float(np.abs(thumb - prev).mean()) > CUT_DIFF:
                cut_at.append(len(targets))
                current = None
            prev = thumb
            faces = [Face(f.x + sx, f.y + sy, f.w, f.h, f.score) for f in det.detect(region, max_width=960)]
            face = _pick(faces, current, prefer if current is None and not cut_at else None)
            if face is None and current is not None:
                missing += 1
                if missing >= rate * 0.8 and faces:   # the face we followed is gone: take the new one
                    face = _pick(faces, None, None)
            if face is not None:
                missing = 0
                current = (face.cx, face.cy)
                targets.append((face.cx - cw / 2, face.cy - face_at * ch))
            else:
                targets.append(None)
            frame_of.append(idx)
        idx += 1
    cap.release()
    found = sum(t is not None for t in targets) / max(len(targets), 1)
    xs, ys = follow(targets, cut_at, frame_of, idx, size, bounds, fps)
    return {"fps": fps, "frames": idx, "x": xs, "y": ys, "found": round(found, 3), "cuts": len(cut_at)}


def write_sendcmd(path: Path, tracked: dict, target: str = "crop@face") -> Path:
    """ffmpeg sendcmd file that moves the crop named `target` along the tracked path."""
    fps = tracked["fps"]
    lines, last = [], None
    for i, (x, y) in enumerate(zip(tracked["x"], tracked["y"])):
        if (x, y) != last:
            lines.append(f"{i / fps:.4f} {target} x {x}, {target} y {y};")
            last = (x, y)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
