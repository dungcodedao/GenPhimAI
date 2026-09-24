"""Google Cloud Translation Basic; source timings never leave the local SRT parser."""
import hashlib
import html
import json
import re
import socket
import threading
from dataclasses import replace
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from engine import check_cancel
from subtitles import plain_text, read_srt, write_srt


LANGUAGES = {
    'en': 'Anh (gốc)', 'vi': 'Việt Nam', 'fr': 'Pháp', 'es': 'Tây Ban Nha',
    'pt': 'Bồ Đào Nha', 'ja': 'Nhật', 'ko': 'Hàn', 'de': 'Đức',
    'th': 'Thái Lan', 'id': 'Indonesia', 'tl': 'Filipino (Tagalog)',
}
API_URL = 'https://translation.googleapis.com/language/translate/v2'


class TranslationError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the API key to a redirected host.
        return None


class GoogleTranslator:
    def __init__(self, api_key, opener=None):
        self.api_key = api_key.strip()
        if self.api_key and not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', self.api_key):
            raise TranslationError('API key Google không đúng định dạng. Hãy sao chép lại key.')
        self.opener = opener or build_opener(NoRedirect())
        self.blocked = None

    def translate(self, texts, target, cancel=None):
        check_cancel(cancel)
        if self.blocked:
            raise TranslationError(self.blocked)
        if not self.api_key:
            raise TranslationError('Chưa có API key Google. Mở Cài đặt Google để nhập key dịch.')
        if target not in LANGUAGES or target == 'en':
            raise TranslationError('Ngôn ngữ dịch không được hỗ trợ.')
        if not texts or len(texts) > 100 or sum(map(len, texts)) > 5000:
            raise TranslationError('Cụm phụ đề vượt giới hạn dịch; hãy kiểm tra SRT.')
        # https://docs.cloud.google.com/translate/docs/reference/rest/v2/translate
        # https://docs.cloud.google.com/docs/authentication/api-keys-use
        payload = json.dumps({'q': texts, 'source': 'en', 'target': target,
                              'format': 'text', 'model': 'nmt'}, ensure_ascii=False).encode('utf-8')
        request = Request(API_URL, data=payload, headers={
            'Content-Type': 'application/json; charset=utf-8', 'X-Goog-Api-Key': self.api_key,
        }, method='POST')
        waiter = cancel or threading.Event()
        for attempt in range(3):
            check_cancel(cancel)
            try:
                with self.opener.open(request, timeout=20) as response:
                    raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise TranslationError('Google trả kết quả quá lớn. Đã dừng cụm này.')
                data = json.loads(raw)
                result = [html.unescape(item['translatedText']) for item in data['data']['translations']]
                if len(result) != len(texts) or any(not isinstance(t, str) or not t.strip() for t in result):
                    raise TranslationError('Google trả thiếu câu dịch. Chưa lưu cụm này; có thể chạy lại.')
                # A translated cue cannot inject extra SRT blocks or timestamps.
                return [' '.join(t.split()) for t in result]
            except HTTPError as exc:
                code = exc.code
                exc.close()
                check_cancel(cancel)
                if (code == 429 or code >= 500) and attempt < 2:
                    waiter.wait(2 ** (attempt + 1))
                    continue
                if code in (400, 401, 403):
                    message = (f'Google từ chối (HTTP {code}). Kiểm tra API key, bật Cloud Translation API, '
                               'thanh toán và hạn mức trong Google Cloud; sau đó chạy lại.')
                elif code == 429:
                    message = 'Google đang giới hạn lượt dịch (429). Đợi một lúc rồi chạy lại để tiếp tục.'
                else:
                    message = f'Google chưa phục vụ được (HTTP {code}). Chạy lại sau để tiếp tục.'
                self.blocked = message
                raise TranslationError(message) from None
            except (URLError, TimeoutError, socket.timeout, OSError):
                check_cancel(cancel)
                if attempt < 2:
                    waiter.wait(2 ** (attempt + 1))
                    continue
                self.blocked = 'Không kết nối được Google. Kiểm tra mạng rồi chạy lại để tiếp tục.'
                raise TranslationError(self.blocked) from None
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                if isinstance(exc, TranslationError):
                    raise
                raise TranslationError('Google trả dữ liệu dịch không hợp lệ. Chưa lưu cụm này.') from None


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def translate_srt(source, destination, target, client, cancel=None, progress=None, batch_size=60):
    check_cancel(cancel)
    if target not in LANGUAGES or target == 'en':
        raise TranslationError('Ngôn ngữ dịch không được hỗ trợ.')
    if not 1 <= batch_size <= 100:
        raise ValueError('Số câu mỗi cụm không hợp lệ.')
    cues = read_srt(source)
    texts = [plain_text(c.text) for c in cues]
    if any(len(t) > 5000 for t in texts):
        raise TranslationError('Một câu SRT dài hơn 5.000 ký tự. Hãy chia lại câu nguồn.')
    identity = {'version': 1, 'provider': 'google-basic-nmt', 'source': 'en', 'target': target,
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    cache = destination.with_suffix('.translation.json')
    translated = []
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding='utf-8'))
            if not isinstance(saved, dict) or saved.get('identity') != identity:
                raise TranslationError('SRT nguồn đã đổi hoặc bản dịch thuộc nguồn khác. Hãy chọn nơi lưu mới.')
            translated = saved['translated']
            if not isinstance(translated, list) or len(translated) > len(cues) or any(
                    not isinstance(t, str) or not t.strip() or '\n' in t or '\r' in t for t in translated):
                raise ValueError()
        except (ValueError, KeyError, UnicodeError) as exc:
            if isinstance(exc, TranslationError):
                raise
            raise TranslationError('File tiến độ dịch bị hỏng. Hãy chọn nơi lưu mới; SRT hiện có vẫn được giữ.') from None
    if destination.exists():
        if not cache.exists():
            raise TranslationError('Đã có SRT nhưng thiếu thông tin nguồn. Hãy chọn nơi lưu mới để tránh ghi đè.')
        existing = read_srt(destination)
        if [(c.number, c.start, c.end) for c in existing] != [(c.number, c.start, c.end) for c in cues]:
            raise TranslationError('SRT đã lưu bị đổi số câu hoặc thời gian. Hãy sửa SRT trước khi xuất.')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    while len(translated) < len(cues):
        check_cancel(cancel)
        batch = []
        size = 0
        for text in texts[len(translated):len(translated) + batch_size]:
            if size + len(text) > 5000:
                break
            batch.append(text)
            size += len(text)
        if progress:
            progress(f'Đang dịch {LANGUAGES[target]}: câu {len(translated) + 1}–{len(translated) + len(batch)} / {len(cues)}')
        result = client.translate(batch, target, cancel)
        if len(result) != len(batch) or any(not isinstance(t, str) or not t.strip() for t in result):
            raise TranslationError('Kết quả dịch thiếu câu. Chưa lưu cụm này.')
        translated.extend(' '.join(t.split()) for t in result)
        # Save before honoring cancellation so a paid response is not lost.
        atomic_json(cache, {'identity': identity, 'translated': translated})
    check_cancel(cancel)
    temporary = destination.with_suffix('.srt.tmp')
    write_srt([replace(cue, text=text) for cue, text in zip(cues, translated)], temporary)
    temporary.replace(destination)
    return destination
