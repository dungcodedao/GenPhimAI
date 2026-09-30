"""Shared subtitle language catalog; default choices remain unchanged."""
DEFAULT_LANGUAGES = {
    'en': 'Anh', 'vi': 'Việt Nam', 'fr': 'Pháp', 'es': 'Tây Ban Nha',
    'pt': 'Bồ Đào Nha', 'ja': 'Nhật', 'ko': 'Hàn', 'de': 'Đức',
    'th': 'Thái Lan', 'id': 'Indonesia', 'tl': 'Filipino (Tagalog)',
}
EXTRA_LANGUAGES = {
    'zh': 'Trung Quốc (giản thể)', 'ru': 'Nga', 'it': 'Ý', 'tr': 'Thổ Nhĩ Kỳ',
    'pl': 'Ba Lan', 'ro': 'Romania', 'cs': 'Séc', 'uk': 'Ukraina',
    'nl': 'Hà Lan', 'sv': 'Thụy Điển', 'da': 'Đan Mạch', 'fi': 'Phần Lan',
    'ms': 'Malaysia', 'ar': 'Ả Rập', 'hi': 'Hindi (Ấn Độ)', 'bn': 'Bengali',
    'ta': 'Tamil', 'te': 'Telugu', 'el': 'Hy Lạp',
}
LANGUAGES = {**DEFAULT_LANGUAGES, **EXTRA_LANGUAGES}
ISO_CODES = dict(zip(
    LANGUAGES,
    'eng vie fra spa por jpn kor deu tha ind fil zho rus ita tur pol ron ces ukr nld swe dan fin msa ara hin ben tam tel ell'.split()))
