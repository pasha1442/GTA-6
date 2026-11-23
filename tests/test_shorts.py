import tempfile
import unittest
from pathlib import Path

from clipper.shorts import snap
from clipper.subtitles import build_cues, romanize, write_ass


def words(text, start=0.0, step=0.4):
    return [{"start": start + i * step, "end": start + i * step + 0.3, "word": w} for i, w in enumerate(text.split())]


class RomanizeTests(unittest.TestCase):
    def test_common_hindi_words(self):
        cases = {"क्या": "kya", "है": "hai", "करना": "karna", "समझना": "samajhna", "भाई": "bhai",
                 "कम": "kam", "आप": "aap", "बदलता": "badalta", "ज़िंदगी": "zindagi"}
        for hindi, expected in cases.items():
            self.assertEqual(romanize(hindi), expected, hindi)

    def test_english_and_digits_pass_through(self):
        self.assertEqual(romanize("GTA 6 बहुत अच्छा"), "GTA 6 bahut achchha")


class CueTests(unittest.TestCase):
    def test_groups_words_and_uses_clip_time(self):
        cues = build_cues(words("one two three four five six seven", start=100), 100, 110)
        self.assertEqual([len(c["words"]) for c in cues], [3, 3, 1])
        self.assertAlmostEqual(cues[0]["start"], 0.0)
        self.assertEqual(cues[1]["words"][0]["word"], "four")

    def test_breaks_at_pause_and_sentence_end(self):
        ws = words("hello there.") + words("again", start=5)
        cues = build_cues(ws, 0, 10)
        self.assertEqual([[w["word"] for w in c["words"]] for c in cues], [["hello", "there."], ["again"]])

    def test_ass_highlights_each_word(self):
        cues = build_cues(words("ye kya hua"), 0, 5)
        cues[0]["text"] = "ye kya hua"
        with tempfile.TemporaryDirectory() as d:
            text = write_ass(cues, Path(d) / "s.ass").read_text(encoding="utf-8")
        self.assertEqual(text.count("Dialogue:"), 3)
        self.assertIn("\\c&H0000E5FF&}kya", text)


class SnapTests(unittest.TestCase):
    def test_snaps_to_sentences_and_drops_overlaps(self):
        segs = [{"start": float(s), "end": float(s + 9)} for s in range(0, 200, 10)]
        out = snap([{"start": 21, "end": 58}, {"start": 40, "end": 70}, {"start": 102, "end": 200}],
                   segs, 20, 60, 200)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["start"], 19.85)
        self.assertAlmostEqual(out[0]["end"], 59.35)
        self.assertLessEqual(out[1]["end"] - out[1]["start"], 61)


if __name__ == "__main__":
    unittest.main()
