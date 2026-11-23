import unittest

from clipper import layouts

ANALYSIS = {
    "type": "gaming_facecam", "reason": "test", "frame": [1920, 1080], "webcam": [1440, 0, 480, 320],
    "stats": {"cam_face": {"box": [1620, 80, 100, 130], "hits": 0.9, "off_center": True},
              "main_face": None, "any_face": 0.9, "big_face": 0.0, "multi_face": 0.0},
}


def aspect(box):
    return box[2] / box[3]


class SuggestTests(unittest.TestCase):
    def test_split_boxes_fit_their_panels(self):
        lay = layouts.suggest(ANALYSIS, "split")
        face_h, game_h = layouts.panel_heights(lay["split"])
        self.assertAlmostEqual(aspect(lay["face"]), 1080 / face_h, delta=0.02)
        self.assertAlmostEqual(aspect(lay["game"]), 1080 / game_h, delta=0.02)
        x, y, w, h = lay["face"]
        self.assertTrue(1440 <= x and x + w <= 1920 and y >= 0 and y + h <= 320)   # inside the webcam
        gx, _, gw, _ = lay["game"]
        self.assertLessEqual(gx + gw, 1440)                                       # gameplay clears the webcam

    def test_crop_is_full_height_9_16(self):
        lay = layouts.suggest(ANALYSIS, "crop")
        self.assertEqual(lay["box"][3], 1080)
        self.assertAlmostEqual(aspect(lay["box"]), 9 / 16, delta=0.01)

    def test_default_mode_follows_type(self):
        self.assertEqual(layouts.build(ANALYSIS)["default"]["mode"], "split")
        self.assertEqual(layouts.build(ANALYSIS, "group")["default"]["mode"], "fit")


class NormalizeTests(unittest.TestCase):
    def test_fixes_shape_and_keeps_inside(self):
        lay = layouts.normalize({"mode": "crop", "box": [1800, -50, 300, 300], "track": 1}, (1920, 1080))
        x, y, w, h = lay["box"]
        self.assertAlmostEqual(w / h, 9 / 16, delta=0.02)
        self.assertTrue(x >= 0 and y >= 0 and x + w <= 1920 and y + h <= 1080)
        self.assertIs(lay["track"], True)

    def test_unknown_mode_becomes_fit(self):
        self.assertEqual(layouts.normalize({"mode": "zoom"}, (1920, 1080)), {"mode": "fit"})

    def test_split_ratio_is_kept_in_range(self):
        lay = layouts.normalize({"mode": "split", "split": 0.9, "face": [0, 0, 400, 300], "game": [500, 0, 900, 1080]},
                                (1920, 1080))
        self.assertEqual(lay["split"], layouts.SPLIT_RANGE[1])


class FileTests(unittest.TestCase):
    def test_short_override_and_type_change(self):
        data = layouts.build(ANALYSIS)
        data["shorts"]["2"] = {"mode": "fit"}
        self.assertEqual(layouts.for_short(data, 2), ({"mode": "fit"}, "short"))
        self.assertEqual(layouts.for_short(data, 1)[1], "default")
        layouts.set_type(data, "talking_head", "claude")
        self.assertEqual(data["default"]["mode"], "crop")
        data["edited"] = True
        layouts.set_type(data, "group", "claude")
        self.assertEqual(data["default"]["mode"], "crop")   # a person's edits are not replaced

    def test_margins_put_subtitles_on_the_seam(self):
        lay = layouts.suggest(ANALYSIS, "split")
        sub, hook = layouts.margins(lay)
        face_h, _ = layouts.panel_heights(lay["split"])
        self.assertEqual(1920 - sub, face_h + 48)
        self.assertLess(hook, face_h)

    def test_cam_bounds(self):
        lay = layouts.suggest(ANALYSIS, "split")
        self.assertEqual(layouts.cam_bounds(lay, (1920, 1080)), [1440, 0, 480, 320])
        lay["face"] = [100, 600, 300, 200]                   # moved out of the webcam: a margin around it
        self.assertEqual(layouts.cam_bounds(lay, (1920, 1080)), [40, 560, 420, 280])


if __name__ == "__main__":
    unittest.main()
