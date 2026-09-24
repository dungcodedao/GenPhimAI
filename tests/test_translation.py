import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

from subtitles import read_srt
from translation import GoogleTranslator, TranslationError, translate_srt


SOURCE = '1\n00:00:00,123 --> 00:00:01,234\nHello, Jack.\n\n2\n00:00:01,500 --> 00:00:03,000\nMy friend!\n'


class TranslationTests(unittest.TestCase):
    def test_google_request_and_response_keep_order_and_hide_key_from_url(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'data': {'translations': [
            {'translatedText': 'Kumusta, Jack.'}, {'translatedText': 'Kaibigan ko!'}
        ]}}).encode()
        opener = Mock()
        opener.open.return_value = response
        client = GoogleTranslator('test-key-not-a-real-google-key', opener=opener)
        self.assertEqual(client.translate(['Hello, Jack.', 'My friend!'], 'tl'),
                         ['Kumusta, Jack.', 'Kaibigan ko!'])
        request = opener.open.call_args.args[0]
        self.assertNotIn('test-key', request.full_url)
        self.assertEqual(json.loads(request.data)['source'], 'en')
        self.assertEqual(json.loads(request.data)['target'], 'tl')
        self.assertEqual(json.loads(request.data)['format'], 'text')

    def test_http_error_does_not_expose_key_or_response(self):
        opener = Mock()
        opener.open.side_effect = HTTPError('https://example.invalid/?key=SECRET', 403,
                                           'SECRET', {}, io.BytesIO(b'SECRET'))
        client = GoogleTranslator('test-key-not-a-real-google-key', opener=opener)
        with self.assertRaises(TranslationError) as caught:
            client.translate(['Hello'], 'vi')
        self.assertNotIn('SECRET', str(caught.exception))
        self.assertIn('403', str(caught.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_missing_response_cue_is_rejected(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":{"translations":[]}}'
        opener = Mock()
        opener.open.return_value = response
        with self.assertRaises(TranslationError):
            GoogleTranslator('test-key-not-a-real-google-key', opener=opener).translate(['Hello'], 'vi')

    def test_resume_keeps_completed_batch_and_preserves_edited_srt(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / 'en.srt', Path(td) / 'vi.srt'
            source.write_text(SOURCE, encoding='utf-8')
            client = Mock()
            client.translate.side_effect = [['Xin chào, Jack.'], TranslationError('Mất mạng')]
            with self.assertRaises(TranslationError):
                translate_srt(source, target, 'vi', client, batch_size=1)
            self.assertFalse(target.exists())
            client.translate.side_effect = None
            client.translate.return_value = ['Bạn tôi!']
            client.translate.reset_mock()
            translate_srt(source, target, 'vi', client, batch_size=1)
            self.assertEqual(client.translate.call_count, 1)
            cues = read_srt(target)
            self.assertEqual([(c.number, c.start, c.end) for c in cues],
                             [(1, 123, 1234), (2, 1500, 3000)])
            target.write_text(target.read_text(encoding='utf-8').replace('Bạn tôi!', 'Bạn của tôi!'), encoding='utf-8')
            client.translate.reset_mock()
            translate_srt(source, target, 'vi', client)
            client.translate.assert_not_called()
            self.assertEqual(read_srt(target)[1].text, 'Bạn của tôi!')

    def test_changed_source_does_not_reuse_old_translation_or_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / 'en.srt', Path(td) / 'fr.srt'
            source.write_text(SOURCE, encoding='utf-8')
            client = Mock()
            client.translate.return_value = ['Bonjour, Jack.', 'Mon ami !']
            translate_srt(source, target, 'fr', client)
            before = target.read_bytes()
            source.write_text(SOURCE.replace('Hello', 'Goodbye'), encoding='utf-8')
            with self.assertRaises(TranslationError):
                translate_srt(source, target, 'fr', client)
            self.assertEqual(target.read_bytes(), before)

    def test_cancel_prevents_request(self):
        from engine import Cancelled
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'en.srt'
            source.write_text(SOURCE, encoding='utf-8')
            cancel = threading.Event()
            cancel.set()
            client = Mock()
            with self.assertRaises(Cancelled):
                translate_srt(source, Path(td) / 'vi.srt', 'vi', client, cancel)
            client.translate.assert_not_called()

    def test_malformed_source_is_not_silently_partially_translated(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'en.srt'
            source.write_text(SOURCE + '\n3\nbroken timestamp\nLost line\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_srt(source)


if __name__ == '__main__':
    unittest.main()
