import tempfile
import unittest
from pathlib import Path

from clipper.subtitles import hook_text, write_ass


class HookTests(unittest.TestCase):
    def test_hook_text_drops_emoji_and_capitalises(self):
        self.assertEqual(hook_text("Black coffee ya Americano? ☕\U0001F602 "), "BLACK COFFEE YA AMERICANO?")

    def test_hook_shown_for_whole_clip_with_pop_in(self):
        cues = [{"start": 0.5, "end": 1.5, "words": [{"start": 0.5, "end": 1.0, "word": "hi"},
                                                     {"start": 1.0, "end": 1.5, "word": "there"}]}]
        with tempfile.TemporaryDirectory() as d:
            text = write_ass(cues, Path(d) / "x.ass", hook="Map starts empty", hook_margin=300,
                             duration=30).read_text(encoding="utf-8")
        self.assertIn("Style: Hook,", text)
        line = [l for l in text.splitlines() if ",Hook," in l][0]
        self.assertTrue(line.startswith("Dialogue: 1,0:00:00.00,0:00:31.00,Hook"))
        self.assertIn(r"{\fscx70", line)
        self.assertTrue(line.endswith("MAP STARTS EMPTY"))

    def test_no_hook_line_without_hook(self):
        with tempfile.TemporaryDirectory() as d:
            text = write_ass([], Path(d) / "x.ass").read_text(encoding="utf-8")
        self.assertNotIn(",Hook,", text.split("[Events]")[1])


if __name__ == "__main__":
    unittest.main()
