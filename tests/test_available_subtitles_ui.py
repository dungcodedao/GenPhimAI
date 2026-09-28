import unittest
from pathlib import Path
from types import SimpleNamespace

from app import available_subtitle_details


class AvailableSubtitlesUiTests(unittest.TestCase):
    def test_details_include_vietnamese_label_code_and_filename(self):
        episode = SimpleNamespace(available_subtitles=(
            ('ko', Path('tap-1.Korean (ko-KR).srt')),
            ('en', Path('tap-1.English (en-US).srt')),
        ))

        self.assertEqual(available_subtitle_details(episode), [
            ('en', 'Anh', 'tap-1.English (en-US).srt'),
            ('ko', 'Hàn', 'tap-1.Korean (ko-KR).srt'),
        ])


if __name__ == '__main__':
    unittest.main()
