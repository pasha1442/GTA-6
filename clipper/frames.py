"""Frame selector: a page in your browser where you choose what each short shows.

    python -m clipper.frames                      # list of all clips/shorts-* folders
    python -m clipper.frames clips/shorts-<id>    # open one folder straight away
    python -m clipper.frames --port 8765

Then open http://127.0.0.1:8765 . Pick the video type, choose a layout (split: webcam on top and
gameplay below; crop: one 9:16 area; fit: whole frame), drag the boxes over a frame of the
video, turn face tracking on or off, for all shorts or one short. Save writes layout.json in
the folder; "Save & render" re-renders the shorts with it. Only this computer can open the page.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import webbrowser
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2

from . import faces, layouts

log = logging.getLogger("clipper.frames")
PAGE = Path(__file__).with_name("frames.html")
PROJECT_RE = re.compile(r"^shorts-[\w\-]+$")
SHORT_FILE_RE = re.compile(r"^short-(\d{2})-[\w\-]*\.mp4$")


class Projects:
    """The clips/shorts-* folders, and the work going on in them."""

    def __init__(self, root: Path):
        self.root = root
        self.renders: dict[str, dict] = {}
        self.frames: OrderedDict = OrderedDict()   # small cache of decoded frames
        self.lock = threading.Lock()
        self._detector: faces.Detector | None = None

    def detector(self) -> faces.Detector:
        if self._detector is None:
            self._detector = faces.Detector(0.6)
        return self._detector

    def folder(self, pid: str | None) -> Path | None:
        if not pid or not PROJECT_RE.match(pid):
            return None
        d = self.root / pid
        return d if (d / "info.json").exists() else None

    def list(self) -> list[dict]:
        out = []
        for d in sorted(self.root.glob("shorts-*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not (d / "info.json").exists():
                continue
            info = _read_json(d / "info.json") or {}
            plan = _read_json(d / "plan.json") or {}
            lay = layouts.load(d) or {}
            out.append({"id": d.name, "title": info.get("title") or d.name, "duration": info.get("duration"),
                        "video_type": lay.get("video_type"), "shorts": len(plan.get("shorts") or []),
                        "edited": bool(lay.get("edited"))})
        return out

    def layout_data(self, d: Path) -> dict:
        data = layouts.load(d)
        if data and data.get("analysis"):
            return data
        info = _read_json(d / "info.json") or {}
        log.info("analysing %s (first time only)...", d.name)
        analysis = faces.analyze(Path(info["video"]), sheet=d / "scene.jpg", detector=self.detector())
        data = layouts.build(analysis)
        layouts.save(d, data)
        return data

    def state(self, d: Path) -> dict:
        info = _read_json(d / "info.json") or {}
        plan = _read_json(d / "plan.json") or {}
        data = self.layout_data(d)
        analysis = data["analysis"]
        files = {int(m.group(1)): f.name for f in d.glob("short-*.mp4") if (m := SHORT_FILE_RE.match(f.name))}
        shorts = []
        for n, sh in enumerate(plan.get("shorts") or [], 1):
            shorts.append({"n": n, "start": sh["start"], "end": sh["end"], "title": sh.get("title") or f"Short {n}",
                           "hook_text": sh.get("hook_text") or sh.get("title") or "", "file": files.get(n),
                           "mtime": (d / files[n]).stat().st_mtime if n in files else None})
        return {
            "id": d.name, "title": info.get("title") or d.name, "duration": info.get("duration") or analysis.get("duration"),
            "frame": analysis["frame"], "video_type": data["video_type"], "type_source": data.get("type_source"),
            "types": faces.VIDEO_TYPES, "default_mode": layouts.DEFAULT_MODE,
            "detected": {"type": analysis["type"], "reason": analysis["reason"], "webcam": analysis.get("webcam")},
            "suggest": {m: layouts.normalize(layouts.suggest(analysis, m), tuple(analysis["frame"]))
                        for m in layouts.MODES},
            "default": layouts.normalize(data["default"], tuple(analysis["frame"])),
            "shorts_layout": {k: layouts.normalize(v, tuple(analysis["frame"]))
                              for k, v in (data.get("shorts") or {}).items()},
            "edited": bool(data.get("edited")), "shorts": shorts,
            "split_range": layouts.SPLIT_RANGE, "has_scene": (d / "scene.jpg").exists(),
            "render": self.render_status(d.name),
        }

    def save(self, d: Path, body: dict) -> dict:
        data = self.layout_data(d)
        frame = tuple(data["analysis"]["frame"])
        if body.get("video_type") in faces.VIDEO_TYPES and body["video_type"] != data["video_type"]:
            data["video_type"], data["type_source"] = body["video_type"], "user"
        if isinstance(body.get("default"), dict):
            data["default"] = layouts.normalize(body["default"], frame)
        if isinstance(body.get("shorts"), dict):
            count = len((_read_json(d / "plan.json") or {}).get("shorts") or [])
            data["shorts"] = {str(int(k)): layouts.normalize(v, frame) for k, v in body["shorts"].items()
                              if str(k).isdigit() and 1 <= int(k) <= max(count, 1) and isinstance(v, dict)}
        data["edited"] = True
        layouts.save(d, data)
        return self.state(d)

    def frame_jpeg(self, d: Path, t: float) -> bytes | None:
        key = (d.name, round(t, 2))
        with self.lock:
            if key in self.frames:
                self.frames.move_to_end(key)
                return self.frames[key]
        info = _read_json(d / "info.json") or {}
        data = layouts.load(d) or {}
        fw, fh = (data.get("analysis") or {}).get("frame") or (1920, 1080)
        w = min(fw, 1280) // 2 * 2
        h = int(round(w * fh / fw / 2)) * 2
        img = faces.grab_frame(Path(info["video"]), t, w, h)
        if img is None:
            return None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 86])
        if not ok:
            return None
        jpg = buf.tobytes()
        with self.lock:
            self.frames[key] = jpg
            while len(self.frames) > 40:
                self.frames.popitem(last=False)
        return jpg

    def faces_at(self, d: Path, t: float) -> list[list[float]]:
        info = _read_json(d / "info.json") or {}
        data = layouts.load(d) or {}
        fw, fh = (data.get("analysis") or {}).get("frame") or (1920, 1080)
        w = min(fw, 1280) // 2 * 2
        h = int(round(w * fh / fw / 2)) * 2
        img = faces.grab_frame(Path(info["video"]), t, w, h)
        if img is None:
            return []
        k = fw / w
        with self.lock:
            found = self.detector().detect(img)
        return [[round(f.x * k), round(f.y * k), round(f.w * k), round(f.h * k), round(f.score, 2)] for f in found]

    def start_render(self, d: Path, only: list[int]) -> dict:
        cur = self.renders.get(d.name)
        if cur and cur["proc"].poll() is None:
            return {"started": False, "error": "A render is already running for this video."}
        work = d / "work"
        work.mkdir(exist_ok=True)
        logf = work / "render.log"
        cmd = [sys.executable, "-m", "clipper.shorts", str(d)]
        if only:
            cmd += ["--only", ",".join(str(n) for n in only)]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        handle = open(logf, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent.parent), stdout=handle,
                                stderr=subprocess.STDOUT, env=env)
        self.renders[d.name] = {"proc": proc, "log": logf, "handle": handle, "only": only}
        return {"started": True}

    def render_status(self, pid: str) -> dict | None:
        cur = self.renders.get(pid)
        if not cur:
            return None
        code = cur["proc"].poll()
        if code is not None and not cur["handle"].closed:
            cur["handle"].close()
        try:
            lines = [l for l in cur["log"].read_text(encoding="utf-8", errors="replace").splitlines()
                     if "HTTP Request" not in l]
        except OSError:
            lines = []
        needs = next((l[len("NEEDS CLAUDE: "):] for l in lines if l.startswith("NEEDS CLAUDE: ")), None)
        return {"running": code is None, "exit": code, "log": lines[-14:], "needs_claude": needs,
                "only": cur["only"]}


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def make_handler(projects: Projects):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FrameSelector/1"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        # ---- helpers
        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, code: int, msg: str):
            self._json({"error": msg}, code)

        def _query(self):
            u = urlparse(self.path)
            return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}

        def _folder(self, q) -> Path | None:
            d = projects.folder(q.get("p"))
            if d is None:
                self._error(404, "No such shorts folder.")
            return d

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2_000_000:
                return {}
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        # ---- routes
        def do_GET(self):
            path, q = self._query()
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                if path == "/api/projects":
                    return self._json(projects.list())
                if path == "/api/state":
                    d = self._folder(q)
                    return d and self._json(projects.state(d))
                if path == "/api/frame":
                    d = self._folder(q)
                    if not d:
                        return
                    jpg = projects.frame_jpeg(d, float(q.get("t", 0)))
                    return self._send(200, jpg, "image/jpeg") if jpg else self._error(404, "No frame there.")
                if path == "/api/faces":
                    d = self._folder(q)
                    return d and self._json({"faces": projects.faces_at(d, float(q.get("t", 0)))})
                if path == "/api/render":
                    d = self._folder(q)
                    return d and self._json(projects.render_status(d.name) or {})
                if path == "/scene.jpg":
                    d = self._folder(q)
                    if d and (d / "scene.jpg").exists():
                        return self._send(200, (d / "scene.jpg").read_bytes(), "image/jpeg")
                    return d and self._error(404, "No scene.jpg yet.")
                if path == "/video":
                    d = self._folder(q)
                    name = q.get("f", "")
                    if d and SHORT_FILE_RE.match(name) and (d / name).exists():
                        return self._video(d / name)
                    return d and self._error(404, "No such short.")
                return self._error(404, "Not found.")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # show the problem in the page instead of hanging
                log.exception("request failed")
                self._error(500, str(e))

        do_HEAD = do_GET

        def do_POST(self):
            path, q = self._query()
            d = self._folder(q)
            if not d:
                return
            body = self._body()
            try:
                if path == "/api/save":
                    return self._json(projects.save(d, body))
                if path == "/api/render":
                    only = [int(n) for n in body.get("only") or [] if str(n).isdigit()]
                    return self._json(projects.start_render(d, only))
                return self._error(404, "Not found.")
            except Exception as e:
                log.exception("request failed")
                self._error(500, str(e))

        def _video(self, f: Path):
            size = f.stat().st_size
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                elif m.group(2):
                    start = max(size - int(m.group(2)), 0)
            end = min(end, size - 1)
            length = max(end - start + 1, 0)
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(f, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(left, 1 << 16))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

    return Handler


def main() -> None:
    from .__main__ import ROOT, load_config

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    args = sys.argv[1:]
    port = 8765
    if "--port" in args:
        i = args.index("--port")
        port = int(args[i + 1])
        del args[i:i + 2]
    no_browser = "--no-browser" in args
    args = [a for a in args if a != "--no-browser"]
    cfg = load_config()
    root = ROOT / cfg["clips_dir"]
    projects = Projects(root)
    start = ""
    if args:
        d = projects.folder(Path(args[0]).resolve().name)
        if d is None or d.resolve() != Path(args[0]).resolve():
            sys.exit(f"Not a shorts folder inside {root}: {args[0]}  (expected clips/shorts-<id> with info.json)")
        start = f"/?p={d.name}"
        projects.layout_data(d)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(projects))
    url = f"http://127.0.0.1:{port}{start}"
    print(f"Frame selector running: {url}   (Ctrl+C to stop)", flush=True)
    if not no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
