import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from clipper.vod import hms, rank_moments, read_chat_replay


class VodTests(unittest.TestCase):
    def test_ranks_strongest_spike_first(self):
        rng = np.random.default_rng(1)
        series = rng.poisson(2, 3600).astype(float)
        series[1000:1010] += 10   # medium spike
        series[2500:2510] += 30   # big spike
        moments = rank_moments(series, window=10, top=5, min_value=15)
        self.assertGreaterEqual(len(moments), 2)
        self.assertAlmostEqual(moments[0]["time"], 2505, delta=6)
        self.assertAlmostEqual(moments[1]["time"], 1005, delta=6)
        self.assertGreater(moments[0]["score"], moments[1]["score"])

    def test_steady_series_has_no_moments(self):
        rng = np.random.default_rng(2)
        self.assertEqual(rank_moments(rng.poisson(5, 3600).astype(float), 10, 5, min_value=15), [])

    def test_top_limits_and_spacing(self):
        series = np.full(4000, 2.0)
        for start in (500, 520, 1500, 2500, 3500):
            series[start:start + 10] += 25
        moments = rank_moments(series, 10, top=3)
        self.assertEqual(len(moments), 3)
        times = sorted(m["time"] for m in moments)
        self.assertTrue(all(b - a >= 90 for a, b in zip(times, times[1:])))

    def test_reads_chat_replay(self):
        def line(ms, user, text):
            return json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(ms), "actions": [
                {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
                    "timestampUsec": "1", "authorName": {"simpleText": user},
                    "message": {"runs": [{"text": text}]}}}}}]}})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "chat.live_chat.json"
            f.write_text("\n".join([line(65000, "b", "second"), line(-5000, "x", "before start"),
                                    "not json", line(12000, "a", "first")]), encoding="utf-8")
            self.assertEqual(read_chat_replay(f), [(12.0, "a: first"), (65.0, "b: second")])

    def test_hms(self):
        self.assertEqual(hms(3725.4), "01h02m05s")


if __name__ == "__main__":
    unittest.main()
