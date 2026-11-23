import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from clipper import frames, layouts

ANALYSIS = {
    "type": "gaming_facecam", "reason": "test", "frame": [1920, 1080], "webcam": [1440, 0, 480, 320],
    "stats": {"cam_face": {"box": [1620, 80, 100, 130], "hits": 0.9, "off_center": True},
              "main_face": None, "any_face": 0.9, "big_face": 0.0, "multi_face": 0.0},
}


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class SelectorServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        d = root / "shorts-test"
        d.mkdir()
        video = d / "source.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=3:r=25",
                        "-pix_fmt", "yuv420p", str(video)], check=True)
        (d / "info.json").write_text(json.dumps({"title": "Test video", "duration": 3.0, "video": str(video)}))
        (d / "plan.json").write_text(json.dumps({"shorts": [{"start": 0.5, "end": 2.5, "title": "One",
                                                             "hook_text": "Hook one"}]}))
        layouts.save(d, layouts.build(ANALYSIS))
        (d / "short-01-one.mp4").write_bytes(b"0123456789" * 100)
        cls.projects = frames.Projects(root)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), frames.make_handler(cls.projects))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.dir = d

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        layouts.save(self.dir, layouts.build(ANALYSIS))   # every test starts from the detected layout

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers, r.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def test_page_and_project_list(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Frame Selector", body)
        items = json.loads(self.get("/api/projects")[2])
        self.assertEqual([p["id"] for p in items], ["shorts-test"])

    def test_state_and_frame(self):
        state = json.loads(self.get("/api/state?p=shorts-test")[2])
        self.assertEqual(state["video_type"], "gaming_facecam")
        self.assertEqual(state["default"]["mode"], "split")
        self.assertEqual(state["shorts"][0]["file"], "short-01-one.mp4")
        status, headers, body = self.get("/api/frame?p=shorts-test&t=1.0")
        self.assertEqual(headers["Content-Type"], "image/jpeg")
        self.assertTrue(body.startswith(b"\xff\xd8"))

    def test_save_cleans_the_layout(self):
        state = self.post("/api/save?p=shorts-test", {
            "video_type": "talking_head",
            "default": {"mode": "crop", "box": [1700, 0, 300, 300], "track": True},
            "shorts": {"1": {"mode": "fit"}, "9": {"mode": "fit"}, "x": {}}})
        self.assertEqual(state["video_type"], "talking_head")
        box = state["default"]["box"]
        self.assertAlmostEqual(box[2] / box[3], 9 / 16, delta=0.02)
        self.assertLessEqual(box[0] + box[2], 1920)
        self.assertEqual(list(state["shorts_layout"]), ["1"])
        saved = layouts.load(self.dir)
        self.assertTrue(saved["edited"])
        self.assertEqual(saved["type_source"], "user")

    def test_video_range_and_bad_paths(self):
        status, headers, body = self.get("/video?p=shorts-test&f=short-01-one.mp4", {"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(body, b"0123456789")
        self.assertEqual(headers["Content-Range"], "bytes 10-19/1000")
        for bad in ("/api/state?p=../shorts-test", "/video?p=shorts-test&f=../info.json", "/api/state?p=nope"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.get(bad)
            self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
