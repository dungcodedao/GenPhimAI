"""Convert SRT into explicitly wrapped, two-line ASS subtitles."""
import html
import re
import textwrap
import unicodedata
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class Cue:
    number: int
    start: int
    end: int
    text: str


def plain_text(text):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', '', text)).split())


def read_srt(source):
    if source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('SRT quá lớn (tối đa 4 MB mỗi tập).')
    content = source.read_text(encoding='utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').strip()
    cues = []
    seen = set()
    pattern = r'(\d{1,3}:[0-5]\d:[0-5]\d[,.]\d{3})\s*-->\s*(\d{1,3}:[0-5]\d:[0-5]\d[,.]\d{3})(?:[ \t]+[^\n]*)?'
    for block in re.split(r'\n[ \t]*\n', content):
        lines = block.strip().splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f'SRT lỗi ở đoạn {len(cues) + 1}: cần số thứ tự, thời gian và lời thoại.')
        match = re.fullmatch(pattern, lines[1].strip())
        if not match:
            raise ValueError(f'SRT sai mốc thời gian ở câu {lines[0]}.')
        cue = Cue(int(lines[0]), timestamp(match[1]), timestamp(match[2]), '\n'.join(lines[2:]).strip())
        if cue.number in seen or cue.end <= cue.start or (cues and cue.start < cues[-1].start):
            raise ValueError(f'SRT trùng số câu hoặc sai thứ tự thời gian ở câu {cue.number}.')
        if not plain_text(cue.text):
            raise ValueError(f'SRT có câu trống: {cue.number}.')
        seen.add(cue.number)
        cues.append(cue)
    if not cues:
        raise ValueError('SRT không có lời thoại.')
    return cues


def srt_time(ms):
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'


def write_srt(cues, destination):
    content = '\n\n'.join(f'{c.number}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}' for c in cues)
    destination.write_text(content + '\n', encoding='utf-8-sig')


def timestamp(value):
    h, m, s, ms = map(int, re.split('[:,.]', value))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def ass_time(ms):
    cs = ms // 10
    return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'


def wrapped_lines(text, language='en'):
    if language not in ('ja', 'th'):
        return textwrap.wrap(text, width=28, break_long_words=True, break_on_hyphens=False)
    # Keep combining vowel/tone marks on their base character, including Thai.
    clusters = []
    for char in text:
        if unicodedata.category(char).startswith('M') and clusters:
            clusters[-1] += char
        else:
            clusters.append(char)
    lines, line, width = [], '', 0
    for cluster in clusters:
        size = 2 if unicodedata.east_asian_width(cluster[0]) in ('W', 'F') else 1
        if width + size > 28 and line:
            lines.append(line.rstrip())
            line, width = '', 0
        line += cluster
        width += size
    if line.strip():
        lines.append(line.strip())
    return lines


def segments(text, start, end, language='en'):
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    text = ' '.join(text.split())
    lines = wrapped_lines(text, language)
    groups = [lines[i:i + 2] for i in range(0, len(lines), 2)]
    weights = [len(' '.join(group)) for group in groups]
    total = sum(weights)
    elapsed = 0
    for group, weight in zip(groups, weights):
        left = start + (end - start) * elapsed // total
        elapsed += weight
        right = start + (end - start) * elapsed // total
        if right - left < 10:
            raise ValueError('Câu phụ đề quá dài so với thời gian hiển thị')
        yield left, right, group


def write_ass(source, destination, language='en'):
    font = {'ja': 'Yu Gothic', 'ko': 'Malgun Gothic', 'th': 'Leelawadee UI'}.get(language, 'Arial')
    if os.name == 'nt' and language in ('ja', 'ko', 'th'):
        fonts = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
        choices = {'ja': [('YuGothM.ttc', 'Yu Gothic'), ('YuGothR.ttc', 'Yu Gothic'), ('msgothic.ttc', 'MS Gothic')],
                   'ko': [('malgun.ttf', 'Malgun Gothic')], 'th': [('LeelawUI.ttf', 'Leelawadee UI'), ('tahoma.ttf', 'Tahoma')]}
        font = next((family for filename, family in choices[language] if (fonts / filename).exists()), None)
        if font is None:
            raise ValueError('Windows thiếu font cho phụ đề ' + language + '. Cài phông chữ bổ sung cho ngôn ngữ này '
                             'trong Windows, hoặc chọn chỉ tạo SRT trước.')
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,70,70,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    header = header.replace('Style: Default,Arial,', f'Style: Default,{font},')
    events = []
    for cue in read_srt(source):
        for left, right, lines in segments(cue.text, cue.start, cue.end, language):
            # Disable automatic wrapping; explicit line breaks never exceed two.
            # Conservatively shrink exceptionally wide text to fit horizontal margins.
            width = max(sum(0 if unicodedata.category(c).startswith('M') else
                            1 if c in 'WM@#%&' or unicodedata.east_asian_width(c) in ('W', 'F') else
                            .68 if c.isupper() else .55 for c in line) for line in lines)
            size = min(72, int(960 / max(width, 1)))
            safe = [line.replace('\\', '＼').replace('{', '｛').replace('}', '｝') for line in lines]
            text = '{\\q2\\fs' + str(size) + '}' + '\\N'.join(safe)
            events.append(f'Dialogue: 0,{ass_time(left)},{ass_time(right)},Default,,0,0,0,,{text}')
    if not events:
        raise ValueError('Không đọc được câu phụ đề trong SRT')
    destination.write_text(header + '\n'.join(events) + '\n', encoding='utf-8-sig')
