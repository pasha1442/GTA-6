import random
import unittest

from clipper.spikes import SpikeDetector


def run(rate_at, duration, **kw):
    """Feed synthetic chat (rate_at(t) msgs/sec) and return spike times."""
    random.seed(1)
    d = SpikeDetector(**kw)
    t0 = 1_000_000.0
    spikes = []
    for sec in range(duration):
        for _ in range(rate_at(sec)):
            d.add(t0 + sec + random.random())
        s = d.check(t0 + sec + 1)
        if s:
            spikes.append((sec, s))
    return spikes


class SpikeTests(unittest.TestCase):
    def test_steady_chat_has_no_spike(self):
        self.assertEqual(run(lambda t: random.choice([1, 2, 2, 3]), 600), [])

    def test_burst_is_detected_once(self):
        spikes = run(lambda t: 15 if 200 <= t < 212 else 2, 400)
        self.assertEqual(len(spikes), 1)
        sec, s = spikes[0]
        self.assertTrue(200 <= sec <= 212, sec)
        self.assertGreater(s.score, 3)

    def test_quiet_chat_small_burst_ignored(self):
        # 8 messages in a dead chat is below min_messages
        self.assertEqual(run(lambda t: 4 if 200 <= t < 202 else 0, 400), [])

    def test_no_spike_during_warmup(self):
        self.assertEqual(run(lambda t: 20 if t < 30 else 1, 60), [])

    def test_late_batched_chat_needs_delay(self):
        """Chat delivered in 5s batches: the newest seconds are always missing."""
        def feed(delay):
            random.seed(2)
            d = SpikeDetector(delay=delay)
            t0, spikes, ratios, pending = 1_000_000.0, [], [], []
            for sec in range(400):
                rate = 60 if 250 <= sec < 262 else 20
                pending += [t0 + sec + random.random() for _ in range(rate)]
                if sec % 5 == 4:  # a batch arrives
                    for ts in pending:
                        d.add(ts)
                    pending = []
                now = t0 + sec + 1
                recent, mean, _, n = d.stats(now)
                if n >= 6 and sec < 240:
                    ratios.append(recent / mean)
                if d.check(now):
                    spikes.append(sec)
            return spikes, sum(ratios) / len(ratios)

        _, ratio_no_delay = feed(0)
        spikes, ratio = feed(8)
        self.assertLess(ratio_no_delay, 0.9)       # undercounts without the delay
        self.assertAlmostEqual(ratio, 1.0, delta=0.05)
        self.assertEqual(len(spikes), 1)

    def test_cooldown_separates_spikes(self):
        spikes = run(lambda t: 20 if (200 <= t < 210 or 300 <= t < 310) else 2, 400)
        self.assertEqual(len(spikes), 2)


if __name__ == "__main__":
    unittest.main()
