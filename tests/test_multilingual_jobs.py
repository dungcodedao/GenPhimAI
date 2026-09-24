import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from engine import Episode, episode_folder, scan, versioned_target
from google_settings import load_key, save_key, forget_key
from jobs import run_episode, episode_jobs
from subtitles import read_srt, write_ass, wrapped_lines
from translation import TranslationError


class JobTests(unittest.TestCase):
    @patch('jobs.export_episode')
    def test_both_exports_clean_once_and_continues_after_one_language_fails(self, export):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'en.srt'
            source.write_text('1\n00:00:00,000 --> 00:00:02,000\nHello\n', encoding='utf-8')
            ep = Episode('Film', 'id', 1, root / 'master.m3u8', source)
            export.return_value = ('Hoàn tất', root / 'video.mp4')
            client = Mock()
            client.translate.side_effect = [TranslationError('Dịch vi lỗi'), ['Bonjour']]
            result = run_episode(ep, root / 'out', 'both', ['vi', 'fr'], client, threading.Event())
            self.assertEqual(len(result), 3)
            self.assertTrue(result[1]['status'].startswith('Lỗi'))
            self.assertEqual(result[2]['status'], 'Hoàn tất')
            self.assertEqual([call.args[2] for call in export.call_args_list], ['clean', 'burn'])
            self.assertEqual(export.call_args.kwargs['language'], 'fr')
            output = episode_folder(ep, root / 'out') / 'subtitles/fr/Tap_001.srt'
            self.assertEqual(read_srt(output)[0].text, 'Bonjour')

    def test_invalid_language_is_rejected_before_path_creation(self):
        with self.assertRaises(ValueError):
            episode_jobs('srt', ['../../elsewhere'])

    def test_scan_requires_choice_when_multiple_unnamed_subtitles_exist(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / '0001'
            folder.mkdir()
            (folder / 'master.m3u8').write_text('#EXTM3U\n')
            (folder / 'subtitle-0.srt').write_text('one')
            (folder / 'subtitle-1.srt').write_text('two')
            self.assertIsNone(scan(Path(td))[0].subtitle)
            (folder / 'subtitle-en.srt').write_text('english')
            self.assertEqual(scan(Path(td))[0].subtitle.name, 'subtitle-en.srt')

    def test_edited_subtitle_creates_new_video_revision_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            first, exists = versioned_target(folder, 1, 'original')
            self.assertFalse(exists)
            first.write_bytes(b'old video')
            first.with_suffix('.export.json').write_text(json.dumps({'identity': 'original', 'mode': 'burn'}))
            same, exists = versioned_target(folder, 1, 'original')
            self.assertEqual(same, first)
            self.assertTrue(exists)
            revised, exists = versioned_target(folder, 1, 'edited')
            self.assertEqual(revised.name, 'Tap_001_v2.mp4')
            self.assertEqual(first.read_bytes(), b'old video')

    def test_windows_key_is_encrypted_and_can_be_forgotten(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'google-api.dpapi'
            with patch('google_settings.key_path', return_value=path):
                save_key('test-key-not-a-real-google-key')
                self.assertNotIn(b'test-key', path.read_bytes())
                self.assertEqual(load_key(), 'test-key-not-a-real-google-key')
                forget_key()
                self.assertEqual(load_key(), '')

    def test_asian_subtitles_use_matching_fonts_and_no_more_than_two_lines(self):
        samples = {'ja': ('こんにちは、私の友達です。' * 4, 'Yu Gothic'),
                   'ko': ('안녕하세요 친구 여러분. ' * 4, 'Malgun Gothic'),
                   'th': ('สวัสดีเพื่อนของฉัน' * 4, 'Leelawadee UI')}
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / 'test.srt', Path(td) / 'test.ass'
            for language, (text, font) in samples.items():
                source.write_text('1\n00:00:00,000 --> 00:00:08,000\n' + text + '\n', encoding='utf-8')
                write_ass(source, target, language)
                result = target.read_text(encoding='utf-8-sig')
                self.assertIn('Default,' + font + ',', result)
                for event in result.splitlines():
                    if event.startswith('Dialogue:'):
                        self.assertLessEqual(event.count('\\N'), 1)
            self.assertEqual(''.join(wrapped_lines(samples['th'][0], 'th')), samples['th'][0])


if __name__ == '__main__':
    unittest.main()
