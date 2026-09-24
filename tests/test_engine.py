import tempfile
import unittest
import zipfile
from pathlib import Path

from engine import extract_zip, validate_playlist, scan


class InputTests(unittest.TestCase):
    def test_zip_cannot_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with zipfile.ZipFile(root / 'bad.zip', 'w') as z:
                z.writestr('../escape.mp4', b'bad')
            with self.assertRaises(ValueError):
                extract_zip(root / 'bad.zip', root / 'out')
            self.assertFalse((root / 'escape.mp4').exists())

    def test_missing_segment_detected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'master.m3u8'
            p.write_text('#EXTM3U\nmissing.mp4\n')
            with self.assertRaises(ValueError):
                validate_playlist(p)

    def test_remote_playlist_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'master.m3u8'
            p.write_text('#EXTM3U\nhttps://example.com/a.mp4\n')
            with self.assertRaises(ValueError):
                validate_playlist(p)

    def test_episodes_sorted_numerically(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ['0010-b', '0002-a']:
                (root / name).mkdir()
                (root / name / 'master.m3u8').write_text('#EXTM3U\n')
            self.assertEqual([e.number for e in scan(root)], [2, 10])
