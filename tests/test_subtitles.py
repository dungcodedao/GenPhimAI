import unittest
from subtitles import segments, ass_time


class SubtitleTests(unittest.TestCase):
    def test_long_cue_has_two_lines_and_keeps_words_and_time(self):
        words = ' '.join(['You are my friend, Jack.'] * 12)
        result = list(segments(words, 1000, 9000))
        self.assertTrue(all(len(lines) <= 2 for _, _, lines in result))
        self.assertEqual(' '.join(line for _, _, lines in result for line in lines), words)
        self.assertEqual(result[0][0], 1000)
        self.assertEqual(result[-1][1], 9000)
        for previous, current in zip(result, result[1:]):
            self.assertEqual(previous[1], current[0])

    def test_existing_three_lines_reflowed(self):
        result = list(segments('You\nare my\nfriend, Jack.', 0, 2000))
        self.assertEqual(result[0][2], ['You are my friend, Jack.'])

    def test_time_format(self):
        self.assertEqual(ass_time(3661230), '1:01:01.23')
