import unittest

from clipper.chatscore import message_weight


class ChatScoreTests(unittest.TestCase):
    def test_noise_counts_nothing(self):
        for user, text in [("@a", "W"), ("@a", "ww"), ("@a", "hello"), ("@a", "HELLO HELLO"),
                           ("@a", "97k"), ("@a", "100k likes"), ("@a", "claim"),
                           ("@a", "please give me ps5 bro"), ("@a", "PS 5 PLEASE"),
                           ("@a", "giveaway"), ("@a", "mera birthday hai kal"),
                           ("@nightbot", "Hello @x! Welcome to the stream"), ("@a", ""),
                           ("@a", "mute"), ("@a", "MUTE"), ("@a", "muteee"), ("@a", "bhai unmute"),
                           ("@a", "bhai tu mutee hainnn"), ("@a", "no sound"), ("@a", "sound"),
                           ("@a", "mic"), ("@a", "muted"), ("@a", "lagging bro"),
                           ("@a", "brightness 2000 karlou bhaiya"), ("@a", "mute lol")]:
            self.assertEqual(message_weight(user, text), 0.0, text)

    def test_reactions_count_double(self):
        for text in ["hahahahah", "lol", "LMAO", "risky bhai", "bhai kya kar diya",
                     "😂😂", ":face_with_tears_of_joy::face_with_tears_of_joy:", "OMG", "clip it"]:
            self.assertEqual(message_weight("@a", text), 2.0, text)

    def test_normal_message_counts_once(self):
        self.assertEqual(message_weight("@a", "visit beach please"), 1.0)
        self.assertEqual(message_weight("@a", "show me map bro"), 1.0)

    def test_channel_emotes_count_half(self):
        self.assertEqual(message_weight("@a", ":_BakchodianSASTENASHE::_BakchodianSASTENASHE:"), 0.5)


if __name__ == "__main__":
    unittest.main()
