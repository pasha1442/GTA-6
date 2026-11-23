import tempfile
import unittest
from pathlib import Path

import numpy as np

from clipper import faces
from clipper.faces import Face


class FollowTests(unittest.TestCase):
    def setUp(self):
        self.size, self.bounds, self.fps = (400, 300), (0, 0, 1920, 1080), 30.0

    def path(self, targets, cuts=(), step=5):
        frame_of = [i * step for i in range(len(targets))]
        return faces.follow(targets, list(cuts), frame_of, len(targets) * step, self.size, self.bounds, self.fps)

    def test_small_jitter_keeps_the_camera_still(self):
        xs, ys = self.path([(500 + (i % 2) * 6, 200 - (i % 2) * 4) for i in range(40)])
        self.assertLessEqual(max(xs) - min(xs), 2)
        self.assertLessEqual(max(ys) - min(ys), 2)

    def test_eases_toward_a_move_without_jumping(self):
        xs, _ = self.path([(500, 200)] * 10 + [(900, 200)] * 30)
        steps = np.abs(np.diff(xs))
        self.assertLess(steps.max(), 40)          # no single-frame jump
        self.assertGreater(xs[-1], 850)           # but it gets there

    def test_jumps_at_a_scene_cut(self):
        xs, _ = self.path([(300, 200)] * 10 + [(1300, 200)] * 10, cuts=[10])
        self.assertLess(xs[49], 320)
        self.assertGreater(xs[50], 1280)

    def test_stays_inside_bounds_and_holds_when_face_is_lost(self):
        bounds = (100, 50, 600, 400)
        frame_of = [i * 5 for i in range(20)]
        targets = [(-500, -500)] * 5 + [None] * 15
        xs, ys = faces.follow(targets, [], frame_of, 100, (400, 300), bounds, 30.0)
        self.assertTrue(all(100 <= x <= 300 for x in xs))
        self.assertTrue(all(50 <= y <= 150 for y in ys))

    def test_no_face_at_all_centres_the_crop(self):
        xs, ys = faces.follow([None] * 5, [], [0, 5, 10, 15, 20], 25, (400, 300), (0, 0, 1000, 500), 30.0)
        self.assertEqual(set(xs), {300})
        self.assertEqual(set(ys), {100})

    def test_sendcmd_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = faces.write_sendcmd(Path(d) / "m.txt", {"fps": 25.0, "x": [10, 10, 12], "y": [5, 5, 5]})
            lines = p.read_text().splitlines()
        self.assertEqual(lines, ["0.0000 crop@face x 10, crop@face y 5;", "0.0800 crop@face x 12, crop@face y 5;"])


class TypeTests(unittest.TestCase):
    W, H = 1920, 1080

    def stats(self, per_frame):
        return faces.face_stats(per_frame, self.W, self.H)

    def test_static_small_face_is_a_webcam(self):
        per = [[Face(1600, 80, 100, 130, 0.9)] for _ in range(20)] + [[] for _ in range(4)]
        s = self.stats(per)
        self.assertEqual(s["cam_face"]["hits"], round(20 / 24, 3))
        self.assertTrue(s["cam_face"]["off_center"])
        self.assertEqual(faces.classify(s, (1450, 0, 470, 320), self.W, self.H)[0], "gaming_facecam")
        # Without a webcam box it still counts when the face is off-centre in most frames.
        self.assertEqual(faces.classify(s, None, self.W, self.H)[0], "gaming_facecam")

    def test_small_face_in_the_middle_without_box_is_not_a_webcam(self):
        per = [[Face(920, 600, 90, 110, 0.9), Face(400, 500, 80, 100, 0.9)] for _ in range(20)]
        self.assertEqual(faces.classify(self.stats(per), None, self.W, self.H)[0], "group")

    def test_big_single_face_is_talking_head(self):
        per = [[Face(800, 200, 300, 380, 0.95)] for _ in range(20)]
        self.assertEqual(faces.classify(self.stats(per), None, self.W, self.H)[0], "talking_head")

    def test_no_faces_is_gameplay(self):
        per = [[] for _ in range(18)] + [[Face(100, 100, 60, 70, 0.8)]] * 2
        self.assertEqual(faces.classify(self.stats(per), None, self.W, self.H)[0], "gameplay")


class WebcamFinderTests(unittest.TestCase):
    def test_finds_a_still_box_over_changing_gameplay(self):
        rng = np.random.default_rng(1)
        room = rng.integers(60, 120, (150, 220)).astype(np.uint8)   # webcam: same picture every frame
        grays = []
        for _ in range(20):
            g = rng.integers(0, 255, (540, 960)).astype(np.uint8)  # gameplay: different every frame
            g[0:150, 740:960] = room
            g[40:100, 820:870] = rng.integers(100, 200, (60, 50))  # the face moves a bit
            grays.append(g)
        face = [820 * 2, 40 * 2, 50 * 2, 60 * 2]                    # source is 1920x1080, grays are half size
        box = faces.find_webcam(grays, face, (1920, 1080))
        self.assertIsNotNone(box)
        x, y, w, h = box
        self.assertAlmostEqual(x, 1480, delta=24)
        self.assertEqual(y, 0)
        self.assertAlmostEqual(x + w, 1920, delta=24)
        self.assertAlmostEqual(h, 300, delta=24)

    def test_still_camera_is_not_a_webcam(self):
        rng = np.random.default_rng(2)
        still = rng.integers(0, 255, (540, 960)).astype(np.uint8)
        grays = [still.copy() for _ in range(12)]
        self.assertIsNone(faces.find_webcam(grays, [900, 500, 100, 120], (1920, 1080)))


if __name__ == "__main__":
    unittest.main()
