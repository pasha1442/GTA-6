import unittest

from clipper.sources import parse_source


class SourceTests(unittest.TestCase):
    def check(self, spec, platform, ident, name):
        s = parse_source(spec)
        self.assertEqual((s.platform, s.ident, s.name), (platform, ident, name))

    def test_twitch_forms(self):
        self.check("XQC", "twitch", "xqc", "xqc")
        self.check("twitch:Shroud", "twitch", "shroud", "shroud")
        self.check("https://www.twitch.tv/Shroud", "twitch", "shroud", "shroud")

    def test_youtube_forms(self):
        self.check("@CarryMinati", "youtube", "@CarryMinati", "yt-carryminati")
        self.check("youtube:@CarryMinati", "youtube", "@CarryMinati", "yt-carryminati")
        self.check("yt:IShowSpeed", "youtube", "@IShowSpeed", "yt-ishowspeed")
        self.check("https://www.youtube.com/@IShowSpeed/live", "youtube", "@IShowSpeed", "yt-ishowspeed")
        cid = "UC" + "a" * 22
        self.check(cid, "youtube", f"channel/{cid}", f"yt-{cid.lower()}")
        self.check(f"https://youtube.com/channel/{cid}", "youtube", f"channel/{cid}", f"yt-{cid.lower()}")

    def test_youtube_video_links(self):
        for url in ("https://www.youtube.com/live/hwG3bvxkSJQ?si=abc",
                    "https://www.youtube.com/watch?v=hwG3bvxkSJQ",
                    "https://www.youtube.com/watch?app=desktop&v=hwG3bvxkSJQ",
                    "https://youtu.be/hwG3bvxkSJQ"):
            self.check(url, "youtube", "watch?v=hwG3bvxkSJQ", "yt-hwG3bvxkSJQ")

    def test_bad_names_rejected(self):
        with self.assertRaises(ValueError):
            parse_source("twitch:bad name")
        with self.assertRaises(ValueError):
            parse_source("youtube:../etc")


if __name__ == "__main__":
    unittest.main()
