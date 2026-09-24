"""Offline signed licenses. Only the public verification key ships to testers."""
import base64
import hashlib
import json
import os
import re
import time
import winreg
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class LicenseError(ValueError):
    pass


def machine_id():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid = winreg.QueryValueEx(key, 'MachineGuid')[0]
        if not isinstance(guid, str) or not guid.strip():
            raise ValueError('Empty machine identifier')
        return hashlib.sha256(('AppVideoAI/v1/' + guid.strip().lower()).encode()).hexdigest()[:32].upper()
    except (OSError, ValueError) as exc:
        raise LicenseError('Không đọc được mã máy Windows. Vui lòng liên hệ người cấp key.') from exc


def verify_token(token, public_key, machine, now=None):
    now = time.time() if now is None else now
    try:
        if not isinstance(token, str) or not 20 <= len(token) <= 8192:
            raise ValueError()
        encoded, signature = token.strip().split('.')
        payload = base64.b64decode(encoded, altchars=b'-_', validate=True)
        sig = base64.b64decode(signature, altchars=b'-_', validate=True)
        public_key.verify(sig, payload)
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get('v') != 1 or data.get('product') != 'AppVideoAI':
            raise ValueError()
        if not isinstance(data.get('machine'), str) or not re.fullmatch(r'(?:[A-F0-9]{32}|\*)', data['machine']):
            raise ValueError()
        if any(type(data.get(field)) is not int for field in ('issued_at', 'expires_at')):
            raise ValueError()
        if data['expires_at'] <= data['issued_at']:
            raise ValueError()
        if not isinstance(data.get('customer'), str) or not 1 <= len(data['customer']) <= 120:
            raise ValueError()
        if not isinstance(data.get('license_id'), str) or not 1 <= len(data['license_id']) <= 80:
            raise ValueError()
    except (ValueError, TypeError, KeyError, InvalidSignature, UnicodeError) as exc:
        raise LicenseError('Key không hợp lệ hoặc đã bị thay đổi.') from exc
    if data['machine'] != '*' and data['machine'] != machine:
        raise LicenseError('Key này được cấp cho máy khác.')
    if now < data['issued_at'] - 300:
        raise LicenseError('Ngày giờ máy đang trước thời điểm cấp key. Hãy kiểm tra lại đồng hồ.')
    if now >= data['expires_at']:
        raise LicenseError('Key đã hết hạn. Hãy xin key mới từ người cấp.')
    return data


def public_key():
    try:
        return load_pem_public_key((Path(__file__).parent / 'license_public.pem').read_bytes())
    except (OSError, ValueError) as exc:
        raise LicenseError('Thiếu hoặc hỏng bộ xác thực key. Hãy giải nén lại bản app đầy đủ.') from exc


def license_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AppVideoAI' / 'license.key'


def require_license():
    try:
        path = license_path()
        if path.stat().st_size > 8192:
            raise LicenseError('File key không hợp lệ.')
        token = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise LicenseError('App chưa được kích hoạt trên tài khoản Windows này.') from exc
    return verify_token(token, public_key(), machine_id())


def activate(token):
    token = token.strip()
    data = verify_token(token, public_key(), machine_id())
    path = license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(token, encoding='utf-8')
    temporary.replace(path)
    return data
