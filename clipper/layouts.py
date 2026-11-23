"""How a short is framed in 9:16, and the layout.json file that the frame selector edits.

Modes (source boxes are [x, y, w, h] in source-video pixels):
    split  the "face" box on top, the "game" box below, edge to edge. `split` is the face
           panel's share of the height. With track on, the face box follows the face but
           stays inside "cam" (the webcam area).
    crop   one 9:16 "box" filling the screen; with track on it follows the face.
    fit    the whole frame on a blurred background.

layout.json:
    {"video_type": "gaming_facecam", "type_source": "auto" | "claude" | "user",
     "analysis": {... faces.analyze() ...},
     "default": {layout used by every short},
     "shorts": {"3": {layout for short 3 only}},
     "edited": true once a person saved it in the frame selector}
"""
from __future__ import annotations

import json
from pathlib import Path

W, H = 1080, 1920
MODES = ("split", "crop", "fit")
DEFAULT_MODE = {"gaming_facecam": "split", "gameplay": "fit", "talking_head": "crop", "group": "fit"}
SPLIT = 0.40
SPLIT_RANGE = (0.25, 0.55)

Box = list[int]


def _even(v: float) -> int:
    return int(round(v / 2)) * 2


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), max(lo, hi))


def panel_heights(split: float) -> tuple[int, int]:
    """Output heights of the face panel and the game panel."""
    face = _even(H * _clamp(split, *SPLIT_RANGE))
    return face, H - face


def aspects(layout: dict) -> dict[str, float]:
    """Width/height each box must have so it fills its panel exactly."""
    if layout["mode"] == "split":
        fh, gh = panel_heights(layout.get("split", SPLIT))
        return {"face": W / fh, "game": W / gh}
    if layout["mode"] == "crop":
        return {"box": W / H}
    return {}


def inner_box(rect: Box, aspect: float, centre: tuple[float, float] | None = None) -> Box:
    """The biggest box of `aspect` inside `rect`, as close to `centre` as it can be."""
    x, y, w, h = rect
    if w / h > aspect:
        bh, bw = h, h * aspect
    else:
        bw, bh = w, w / aspect
    cx, cy = centre or (x + w / 2, y + h / 2)
    bx = _clamp(cx - bw / 2, x, x + w - bw)
    by = _clamp(cy - bh / 2, y, y + h - bh)
    return [_even(bx), _even(by), _even(bw), _even(bh)]


def with_aspect(box: Box, aspect: float, frame: tuple[int, int]) -> Box:
    """Reshape `box` to `aspect` around its centre (keeping its width), inside the frame."""
    fw, fh = frame
    x, y, w, h = (float(v) for v in box)
    cx, cy = x + w / 2, y + h / 2
    w = max(w, 32.0)
    h = w / aspect
    if h > fh:
        h, w = fh, fh * aspect
    if w > fw:
        w, h = fw, fw / aspect
    x = _clamp(cx - w / 2, 0, fw - w)
    y = _clamp(cy - h / 2, 0, fh - h)
    return [_even(x), _even(y), _even(w), _even(h)]


def inside(box: Box, frame: tuple[int, int]) -> Box:
    fw, fh = frame
    x, y, w, h = box
    w, h = min(max(w, 16), fw), min(max(h, 16), fh)
    return [_even(_clamp(x, 0, fw - w)), _even(_clamp(y, 0, fh - h)), _even(w), _even(h)]


def _overlap(a: Box, b: Box) -> float:
    """Share of box a that lies inside box b."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(a[2] * a[3], 1)


def cam_bounds(layout: dict, frame: tuple[int, int]) -> Box:
    """Where a tracked face box may move: the webcam area if the box is in it, else a bit around the box."""
    face = layout["face"]
    cam = layout.get("cam")
    if cam and _overlap(face, cam) >= 0.85:
        return inside([min(cam[0], face[0]), min(cam[1], face[1]),
                       max(cam[0] + cam[2], face[0] + face[2]) - min(cam[0], face[0]),
                       max(cam[1] + cam[3], face[1] + face[3]) - min(cam[1], face[1])], frame)
    x, y, w, h = face
    return inside([x - w * 0.2, y - h * 0.2, w * 1.4, h * 1.4], frame)


# ---------------------------------------------------------------- suggestions per mode

def _face_area(analysis: dict) -> tuple[Box | None, Box | None]:
    """(webcam area, face box) from the analysis, whichever are known."""
    fw, fh = analysis["frame"]
    stats = analysis.get("stats") or {}
    face = (stats.get("cam_face") or {}).get("box") or stats.get("main_face")
    cam = analysis.get("webcam")
    if cam is None and (stats.get("cam_face") or {}).get("box"):
        x, y, w, h = stats["cam_face"]["box"]  # no webcam edges found: head and shoulders around the face
        cw = w * 3.2
        ch = cw * 3 / 4
        cam = inside([x + w / 2 - cw / 2, y + h * 0.75 - ch / 2, cw, ch], (fw, fh))
    return cam, face


def suggest(analysis: dict, mode: str, split: float = SPLIT) -> dict:
    """A sensible layout of `mode` for this video, from the face analysis."""
    frame = tuple(analysis["frame"])
    fw, fh = frame
    stats = analysis.get("stats") or {}
    if mode == "fit":
        return {"mode": "fit"}
    if mode == "crop":
        main = stats.get("main_face") or (stats.get("cam_face") or {}).get("box")
        cx = main[0] + main[2] / 2 if main else fw / 2
        box = inner_box([0, 0, fw, fh], W / H, (cx, fh / 2))
        return {"mode": "crop", "box": box, "track": bool(main) and stats.get("any_face", 0) >= 0.2}
    # split
    layout = {"mode": "split", "split": split, "track": True}
    a = aspects(layout)
    cam, face = _face_area(analysis)
    if cam is None:
        cam = [0, 0, _even(fw / 3), _even(fh / 3)]
    centre = (face[0] + face[2] / 2, face[1] + face[3] * 0.6) if face else None
    layout["cam"] = cam
    layout["face"] = inner_box(cam, a["face"], centre)
    game = inner_box([0, 0, fw, fh], a["game"])
    # Keep the webcam out of the gameplay panel when a small shift does it.
    if _overlap(cam, game) > 0:
        left_gap = cam[0] + cam[2] - game[0]      # shift right by this to clear a cam on the left
        right_gap = game[0] + game[2] - cam[0]    # shift left by this to clear a cam on the right
        if cam[0] + cam[2] / 2 < fw / 2 and left_gap <= 0.15 * fw:
            game[0] = _even(min(game[0] + left_gap, fw - game[2]))
        elif cam[0] + cam[2] / 2 >= fw / 2 and right_gap <= 0.15 * fw:
            game[0] = _even(max(game[0] - right_gap, 0))
    layout["game"] = game
    return layout


def normalize(layout: dict, frame: tuple[int, int]) -> dict:
    """Clean a layout from a file or the selector: known mode, boxes of the right shape inside the frame."""
    mode = layout.get("mode") if layout.get("mode") in MODES else "fit"
    out: dict = {"mode": mode}
    if mode == "fit":
        return out
    out["track"] = bool(layout.get("track", False))
    if mode == "split":
        out["split"] = round(_clamp(float(layout.get("split", SPLIT)), *SPLIT_RANGE), 3)
    a = aspects(out)
    fw, fh = frame
    for key, aspect in a.items():
        box = layout.get(key)
        if not (isinstance(box, list) and len(box) == 4):
            box = [0, 0, fw, fh]
        out[key] = with_aspect([float(v) for v in box], aspect, frame)
    if mode == "split" and isinstance(layout.get("cam"), list) and len(layout["cam"]) == 4:
        out["cam"] = inside([int(v) for v in layout["cam"]], frame)
    return out


def margins(layout: dict) -> tuple[int, int]:
    """(subtitle distance from the bottom, headline distance from the top) for this layout."""
    if layout["mode"] == "split":
        face_h, _ = panel_heights(layout.get("split", SPLIT))
        return H - face_h - 48, 110     # subtitles sit on the seam between the two panels
    if layout["mode"] == "crop":
        return 560, 230
    return 520, 300


# ---------------------------------------------------------------- layout.json

def path(out_dir: Path) -> Path:
    return out_dir / "layout.json"


def load(out_dir: Path) -> dict | None:
    p = path(out_dir)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def save(out_dir: Path, data: dict) -> None:
    path(out_dir).write_text(json.dumps(data, indent=2), encoding="utf-8")


def build(analysis: dict, video_type: str | None = None, source: str = "auto") -> dict:
    vtype = video_type or analysis["type"]
    return {"video_type": vtype, "type_source": source, "analysis": analysis,
            "default": suggest(analysis, DEFAULT_MODE.get(vtype, "fit")), "shorts": {}, "edited": False}


def set_type(data: dict, vtype: str, source: str) -> dict:
    """Change the video type; the default layout follows unless a person already edited it."""
    if vtype == data.get("video_type"):
        return data
    data["video_type"], data["type_source"] = vtype, source
    if not data.get("edited"):
        data["default"] = suggest(data["analysis"], DEFAULT_MODE.get(vtype, "fit"))
    return data


def for_short(data: dict, n: int) -> tuple[dict, str]:
    """(layout, "short" or "default") for short number n."""
    frame = tuple(data["analysis"]["frame"])
    own = (data.get("shorts") or {}).get(str(n))
    if own:
        return normalize(own, frame), "short"
    return normalize(data["default"], frame), "default"
