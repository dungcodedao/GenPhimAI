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
BEEKNOEE_MODEL = 'bee/gemini-3.5-flash-lite'
BEEKNOEE_URL = 'https://platform.beeknoee.com/v1/chat/completions'


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
            # Riva sometimes joins document lines. Split the batch until each
            # response maps safely to the original subtitle cues.
            middle = len(texts) // 2
            return (self.translate(texts[:middle], target, cancel) +
                    self.translate(texts[middle:], target, cancel))
        return lines


class BeeknoeeTranslator:
    name = 'Beeknoee'

    def __init__(self, api_key, opener=None):
        self.api_key = _clean_key(api_key, 'Beeknoee')
        self.opener = opener or build_opener(NoRedirect())

    def translate(self, texts, target, cancel=None):
        return self.translate_many(texts, [target], cancel)[target]

    def translate_many(self, texts, targets, cancel=None):
        check_cancel(cancel)
        if not self.api_key:
            raise TranslationError('Chưa có API key Beeknoee.')
        targets = list(dict.fromkeys(targets))
        if not texts:
            return {target: [] for target in targets}
        if not targets or any(target not in LANGUAGES or target == 'en' for target in targets):
            raise TranslationError('Ngôn ngữ dịch không hợp lệ.')
        language_list = ', '.join(f'{code}={LANGUAGES[code]}' for code in targets)
        prompt = (
            'Translate the English subtitle array into every requested language. Preserve meaning, names, '
            'pronouns, tone, and continuity. Return ONLY one valid JSON object. Each key must be the requested '
            'language code and each value must contain exactly the same number of strings as the input, in the '
            'same order. Never merge, omit, explain, or add timestamps.\n'
            f'LANGUAGES: {language_list}\nINPUT JSON:\n{json.dumps(texts, ensure_ascii=False)}'
        )
        payload = json.dumps({
            'model': BEEKNOEE_MODEL,
            'messages': [{'role': 'system', 'content': 'You are a precise professional subtitle translator.'},
                         {'role': 'user', 'content': prompt}],
            'temperature': 0, 'max_tokens': 65536, 'stream': False,
        }, ensure_ascii=False).encode('utf-8')
        request = Request(BEEKNOEE_URL, data=payload, headers={
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }, method='POST')
        data = _post_json(self.opener, request, self.name, cancel)
        try:
            content = data['choices'][0]['message']['content'].strip()
            if content.startswith('```'):
                content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content, flags=re.IGNORECASE)
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError):
            raise TranslationError('Beeknoee trả dữ liệu dịch không hợp lệ.') from None
        if not isinstance(result, dict) or set(result) != set(targets):
            raise TranslationError('Beeknoee trả thiếu ngôn ngữ.')
        for target in targets:
            items = result[target]
            if (not isinstance(items, list) or len(items) != len(texts) or
                    any(not isinstance(item, str) or not item.strip() for item in items)):
                raise TranslationError(f'Beeknoee trả thiếu câu {LANGUAGES[target]}.')
            result[target] = [' '.join(item.split()) for item in items]
        return result


class HybridTranslator:
    """Use free NVIDIA first; Beeknoee handles unsupported languages and failures."""
    def __init__(self, beeknoee_key='', nvidia_key='', mode='auto', opener=None):
        if mode not in ('auto', 'beeknoee', 'nvidia'):
            raise TranslationError('Chế độ API không hợp lệ.')
        self.mode = mode
        self.beeknoee = BeeknoeeTranslator(beeknoee_key, opener)
        self.nvidia = NvidiaTranslator(nvidia_key, opener)
        self.last_provider = ''

    def cache_identity(self, target):
        return f'{self.mode}:beeknoee-{BEEKNOEE_MODEL}:nvidia-riva-v2'

    def translate(self, texts, target, cancel=None):
        if self.mode == 'beeknoee':
            self.last_provider = 'Beeknoee'
            return self.beeknoee.translate(texts, target, cancel)
        if self.mode == 'nvidia':
            self.last_provider = 'NVIDIA Riva'
            return self.nvidia.translate(texts, target, cancel)
        if target not in NVIDIA_CODES:
            self.last_provider = 'Beeknoee'
            return self.beeknoee.translate(texts, target, cancel)
        try:
            self.last_provider = 'NVIDIA Riva'
            return self.nvidia.translate(texts, target, cancel)
        except TranslationError as nvidia_error:
            check_cancel(cancel)
            if not self.beeknoee.api_key:
                raise TranslationError(str(nvidia_error) + ' Không có Beeknoee để dịch thay thế.') from None
            self.last_provider = 'Beeknoee dự phòng'
            return self.beeknoee.translate(texts, target, cancel)

    def translate_many(self, texts, targets, cancel=None):
        if self.mode in ('auto', 'nvidia'):
            return {target: self.translate(texts, target, cancel) for target in targets}
        try:
            self.last_provider = 'Beeknoee'
            return self.beeknoee.translate_many(texts, targets, cancel)
        except TranslationError:
            if self.mode == 'beeknoee':
                raise
            results = {}
            for target in targets:
                results[target] = self.translate(texts, target, cancel)
            return results


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def translate_srt_many(source, destinations, client, cancel=None, progress=None):
    """Create all missing language SRTs with one Beeknoee request per episode."""
    missing = {target: path for target, path in destinations.items() if not path.exists()}
    if not missing:
        return
    check_cancel(cancel)
    cues = read_srt(source)
    texts = [plain_text(c.text) for c in cues]
    if progress:
        names = ', '.join(LANGUAGES[target] for target in missing)
        progress(f'Đang dịch một lượt bằng Beeknoee: {names}')
    results = client.translate_many(texts, list(missing), cancel)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    for target, destination in missing.items():
        translated = results.get(target)
        if (not isinstance(translated, list) or len(translated) != len(cues) or
                any(not isinstance(text, str) or not text.strip() for text in translated)):
            raise TranslationError(f'Kết quả {LANGUAGES[target]} thiếu câu. Chưa lưu phụ đề.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        identity = {'version': 2, 'provider': client.cache_identity(target), 'source': 'en',
                    'target': target, 'source_sha256': source_hash}
        atomic_json(destination.with_suffix('.translation.json'),
                    {'identity': identity, 'translated': translated})
        temporary = destination.with_suffix('.srt.tmp')
        write_srt([replace(cue, text=text) for cue, text in zip(cues, translated)], temporary)
        temporary.replace(destination)
    if progress:
        progress(f'Đã nhận {len(missing)} ngôn ngữ từ {client.last_provider}')


def translate_srt(source, destination, target, client, cancel=None, progress=None, batch_size=40):
    check_cancel(cancel)
    if target not in LANGUAGES or target == 'en':
        raise TranslationError('Ngôn ngữ dịch không được hỗ trợ.')
    if not 1 <= batch_size <= 100:
        raise ValueError('Số câu mỗi cụm không hợp lệ.')
    cues = read_srt(source)
    if destination.exists():
        # Bundled human subtitles can segment and time dialogue differently
        # from the English source. A valid destination is authoritative.
        read_srt(destination)
        return destination
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
