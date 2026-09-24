"""Subtitle translation providers with resumable, provider-aware caching."""
import hashlib
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
    'en': 'Anh', 'vi': 'Việt Nam', 'fr': 'Pháp', 'es': 'Tây Ban Nha',
    'pt': 'Bồ Đào Nha', 'ja': 'Nhật', 'ko': 'Hàn', 'de': 'Đức',
    'th': 'Thái Lan', 'id': 'Indonesia', 'tl': 'Filipino (Tagalog)',
}
NVIDIA_CODES = {'vi': 'vi', 'fr': 'fr', 'es': 'es-es', 'pt': 'pt-pt', 'ja': 'ja',
                'ko': 'ko', 'de': 'de', 'th': 'th', 'id': 'id'}
NVIDIA_URL = 'https://integrate.api.nvidia.com/v1/chat/completions'
GEMINI_MODEL = 'gemini-2.5-flash-lite'
GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'


class TranslationError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _clean_key(value, provider):
    value = value.strip()
    if value and (len(value) < 20 or len(value) > 512 or re.search(r'\s', value)):
        raise TranslationError(f'API key {provider} không đúng định dạng. Hãy sao chép lại key.')
    return value


def _post_json(opener, request, provider, cancel):
    waiter = cancel or threading.Event()
    for attempt in range(3):
        check_cancel(cancel)
        try:
            with opener.open(request, timeout=30) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise TranslationError(f'{provider} trả kết quả quá lớn.')
            return json.loads(raw)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            check_cancel(cancel)
            if (code == 429 or code >= 500) and attempt < 2:
                waiter.wait(2 ** (attempt + 1))
                continue
            if code in (400, 401, 403):
                message = f'{provider} từ chối (HTTP {code}). Kiểm tra API key và hạn mức.'
            elif code == 429:
                message = f'{provider} đang giới hạn lượt dịch (429).'
            else:
                message = f'{provider} chưa phục vụ được (HTTP {code}).'
            raise TranslationError(message) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            check_cancel(cancel)
            if attempt < 2:
                waiter.wait(2 ** (attempt + 1))
                continue
            raise TranslationError(f'Không kết nối được {provider}. Kiểm tra mạng rồi chạy lại.') from None
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            if isinstance(exc, TranslationError):
                raise
            raise TranslationError(f'{provider} trả dữ liệu không hợp lệ.') from None


class NvidiaTranslator:
    name = 'NVIDIA Riva'

    def __init__(self, api_key, opener=None):
        self.api_key = _clean_key(api_key, 'NVIDIA')
        self.opener = opener or build_opener(NoRedirect())

    def translate(self, texts, target, cancel=None):
        check_cancel(cancel)
        if not self.api_key:
            raise TranslationError('Chưa có API key NVIDIA.')
        if target not in NVIDIA_CODES:
            raise TranslationError(f'NVIDIA không hỗ trợ {LANGUAGES.get(target, target)}.')
        if not texts:
            return []
        joined = '\n'.join(texts)
        if len(joined) > 1952:
            raise TranslationError('Cụm phụ đề vượt giới hạn 1.952 ký tự của NVIDIA.')
        payload = json.dumps({
            'model': 'nvidia/riva-translate-4b-instruct-v2',
            'messages': [{'role': 'system', 'content': f'en-{NVIDIA_CODES[target]}'},
                         {'role': 'user', 'content': joined}],
            'temperature': 0, 'max_tokens': 4096, 'stream': False,
        }, ensure_ascii=False).encode('utf-8')
        request = Request(NVIDIA_URL, data=payload, headers={
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }, method='POST')
        data = _post_json(self.opener, request, self.name, cancel)
        try:
            content = data['choices'][0]['message']['content'].strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            raise TranslationError('NVIDIA trả dữ liệu dịch không hợp lệ.') from None
        lines = [line.strip() for line in content.splitlines()]
        if len(lines) != len(texts) or any(not line for line in lines):
            if len(texts) == 1 and content:
                return [content]
            raise TranslationError('NVIDIA trả thiếu hoặc gộp câu phụ đề.')
        return lines


class GeminiTranslator:
    name = 'Gemini'

    def __init__(self, api_key, opener=None):
        self.api_key = _clean_key(api_key, 'Gemini')
        self.opener = opener or build_opener(NoRedirect())

    def translate(self, texts, target, cancel=None):
        check_cancel(cancel)
        if not self.api_key:
            raise TranslationError('Chưa có API key Gemini.')
        if target not in LANGUAGES or target == 'en' or not texts:
            raise TranslationError('Ngôn ngữ dịch không hợp lệ.')
        prompt = ('Translate each English subtitle into ' + LANGUAGES[target] + '. '
                  'Keep names and meaning consistent. Return exactly one translated string for each input item, '
                  'in the same order. Do not merge, omit, explain, or add timestamps.\nINPUT JSON:\n' +
                  json.dumps(texts, ensure_ascii=False))
        schema = {'type': 'ARRAY', 'items': {'type': 'STRING'},
                  'minItems': len(texts), 'maxItems': len(texts)}
        payload = json.dumps({
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json',
                                 'responseSchema': schema},
        }, ensure_ascii=False).encode('utf-8')
        request = Request(GEMINI_URL, data=payload, headers={
            'Content-Type': 'application/json', 'x-goog-api-key': self.api_key,
        }, method='POST')
        data = _post_json(self.opener, request, self.name, cancel)
        try:
            content = data['candidates'][0]['content']['parts'][0]['text']
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError):
            raise TranslationError('Gemini trả dữ liệu dịch không hợp lệ hoặc đã chặn nội dung.') from None
        if len(result) != len(texts) or any(not isinstance(item, str) or not item.strip() for item in result):
            raise TranslationError('Gemini trả thiếu câu phụ đề.')
        return [' '.join(item.split()) for item in result]


class HybridTranslator:
    """Use NVIDIA where supported; Gemini handles Filipino and NVIDIA failures."""
    def __init__(self, nvidia_key='', gemini_key='', mode='auto', opener=None):
        if mode not in ('auto', 'gemini', 'nvidia'):
            raise TranslationError('Chế độ API không hợp lệ.')
        self.mode = mode
        self.nvidia = NvidiaTranslator(nvidia_key, opener)
        self.gemini = GeminiTranslator(gemini_key, opener)
        self.last_provider = ''

    def cache_identity(self, target):
        return f'{self.mode}:nvidia-riva-v2:gemini-{GEMINI_MODEL}'

    def translate(self, texts, target, cancel=None):
        if self.mode == 'gemini':
            self.last_provider = 'Gemini'
            return self.gemini.translate(texts, target, cancel)
        if self.mode == 'nvidia':
            self.last_provider = 'NVIDIA Riva'
            return self.nvidia.translate(texts, target, cancel)
        if target == 'tl':
            self.last_provider = 'Gemini'
            return self.gemini.translate(texts, target, cancel)
        try:
            self.last_provider = 'NVIDIA Riva'
            return self.nvidia.translate(texts, target, cancel)
        except TranslationError as nvidia_error:
            check_cancel(cancel)
            if not self.gemini.api_key:
                raise TranslationError(str(nvidia_error) + ' Không có Gemini để dịch thay thế.') from None
            self.last_provider = 'Gemini dự phòng'
            return self.gemini.translate(texts, target, cancel)


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def translate_srt(source, destination, target, client, cancel=None, progress=None, batch_size=40):
    check_cancel(cancel)
    if target not in LANGUAGES or target == 'en':
        raise TranslationError('Ngôn ngữ dịch không được hỗ trợ.')
    if not 1 <= batch_size <= 100:
        raise ValueError('Số câu mỗi cụm không hợp lệ.')
    cues = read_srt(source)
    texts = [plain_text(c.text) for c in cues]
    identity = {'version': 2, 'provider': getattr(client, 'cache_identity', lambda _: 'translation-client')(target),
                'source': 'en', 'target': target,
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    cache = destination.with_suffix('.translation.json')
    translated = []
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding='utf-8'))
            if not isinstance(saved, dict) or saved.get('identity') != identity:
                raise TranslationError('Nguồn hoặc chế độ API đã đổi. Hãy chọn nơi lưu mới để tránh ghi đè.')
            translated = saved['translated']
            if not isinstance(translated, list) or len(translated) > len(cues) or any(
                    not isinstance(t, str) or not t.strip() or '\n' in t or '\r' in t for t in translated):
                raise ValueError()
        except (ValueError, KeyError, UnicodeError) as exc:
            if isinstance(exc, TranslationError):
                raise
            raise TranslationError('File tiến độ dịch bị hỏng. Hãy chọn nơi lưu mới.') from None
    if destination.exists():
        if not cache.exists():
            raise TranslationError('Đã có SRT nhưng thiếu thông tin nguồn. Hãy chọn nơi lưu mới.')
        existing = read_srt(destination)
        if [(c.number, c.start, c.end) for c in existing] != [(c.number, c.start, c.end) for c in cues]:
            raise TranslationError('SRT đã lưu bị đổi số câu hoặc thời gian.')
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    while len(translated) < len(cues):
        check_cancel(cancel)
        batch, size = [], 0
        for text in texts[len(translated):len(translated) + batch_size]:
            if batch and size + len(text) + 1 > 1800:
                break
            batch.append(text)
            size += len(text) + 1
        if progress:
            progress(f'Đang dịch {LANGUAGES[target]}: câu {len(translated) + 1}–{len(translated) + len(batch)} / {len(cues)}')
        result = client.translate(batch, target, cancel)
        if progress and getattr(client, 'last_provider', ''):
            progress(f'Đã nhận {LANGUAGES[target]} từ {client.last_provider}')
        if len(result) != len(batch) or any(not isinstance(t, str) or not t.strip() for t in result):
            raise TranslationError('Kết quả dịch thiếu câu. Chưa lưu cụm này.')
        translated.extend(' '.join(t.split()) for t in result)
        atomic_json(cache, {'identity': identity, 'translated': translated})
    check_cancel(cancel)
    temporary = destination.with_suffix('.srt.tmp')
    write_srt([replace(cue, text=text) for cue, text in zip(cues, translated)], temporary)
    temporary.replace(destination)
    return destination
