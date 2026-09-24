"""Convert SRT into explicitly wrapped, two-line ASS subtitles."""
import html
import re
import textwrap


def timestamp(value):
    h, m, s, ms = map(int, re.split('[:,.]', value))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def ass_time(ms):
    cs = ms // 10
    return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'


def segments(text, start, end):
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    text = ' '.join(text.split())
    lines = textwrap.wrap(text, width=28, break_long_words=True, break_on_hyphens=False)
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


def write_ass(source, destination):
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,70,70,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    content = source.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    pattern = r'(\d+:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
    events = []
    for match in re.finditer(pattern, content, re.S):
        start, end = timestamp(match[1]), timestamp(match[2])
        if end <= start:
            raise ValueError('Thời gian SRT không hợp lệ')
        for left, right, lines in segments(match[3], start, end):
            # Disable automatic wrapping; explicit line breaks never exceed two.
            # Conservatively shrink exceptionally wide text to fit horizontal margins.
            width = max(sum(1 if c in 'WM@#%&' else .68 if c.isupper() else .55 for c in line) for line in lines)
            size = min(64, int(900 / max(width, 1)))
            safe = [line.replace('\\', '＼').replace('{', '｛').replace('}', '｝') for line in lines]
            text = '{\\q2\\fs' + str(size) + '}' + '\\N'.join(safe)
            events.append(f'Dialogue: 0,{ass_time(left)},{ass_time(right)},Default,,0,0,0,,{text}')
    if not events:
        raise ValueError('Không đọc được câu phụ đề trong SRT')
    destination.write_text(header + '\n'.join(events) + '\n', encoding='utf-8-sig')
