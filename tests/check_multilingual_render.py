"""Optional real FFmpeg smoke check; uses authored subtitle fixtures, no Google calls."""
import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Episode, binary, export_episode


def main():
    root = Path('validation-output/multilingual').resolve()
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'color=c=0x182c40:s=360x640:r=24:d=3',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                    '-f', 'hls', '-hls_time', '1', '-hls_list_size', '0',
                    '-hls_segment_filename', str(root / 'segment%02d.ts'), str(root / 'master.m3u8')], check=True)
    samples = {'vi': 'Xin chào, Jack. Bạn khỏe không?', 'ja': 'こんにちは、ジャック。お元気ですか？',
               'ko': '안녕하세요, 잭. 잘 지내세요?', 'th': 'สวัสดี แจ็ค คุณสบายดีไหม',
               'tl': 'Kumusta, Jack. Mabuti ka ba?'}
    outputs = []
    for language, text in samples.items():
        srt = root / f'{language}.srt'
        srt.write_text('1\n00:00:00,000 --> 00:00:03,000\n' + text + '\n', encoding='utf-8')
        episode = Episode('Render check', 'fixture', 1, root / 'master.m3u8', srt)
        _, video = export_episode(episode, root / 'output', 'burn', threading.Event(), language)
        subprocess.run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-i', str(video),
                        '-f', 'null', '-'], check=True)
        subprocess.run([binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', '-ss', '0.5',
                        '-i', str(video), '-frames:v', '1', str(root / f'{language}.png')], check=True)
        outputs.append({'language': language, 'video': str(video)})
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
