import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import time
from licensing import require_license
from subtitles import write_ass
from dataclasses import dataclass
from pathlib import Path


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('Đã dừng')


def safe_name(text):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text)).strip(' .')[:100]
    return 'Phim_' + (name or 'Khong_ten')


def extract_zip(source, destination, cancel=None):
    destination = Path(destination).resolve()
    allowed = {'.mp4', '.m3u8', '.srt', '.json', '.jpg', '.png', '.aac', '.ts', '.m4s', '.key'}
    with zipfile.ZipFile(source) as archive:
        items = []
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if not target.is_relative_to(destination) or ':' in info.filename:
                raise ValueError('ZIP chứa đường dẫn không an toàn')
            if '__MACOSX' in target.parts or target.name.startswith('._'):
                continue
            if not info.is_dir() and target.suffix.lower() in allowed:
                items.append((info, target))
        destination.mkdir(parents=True, exist_ok=True)
        if sum(i.file_size for i, _ in items) + 512 * 1024**2 > shutil.disk_usage(destination).free:
            raise ValueError('Không đủ dung lượng giải nén ZIP')
        for info, target in items:
            check_cancel(cancel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open('wb') as dst:
                while chunk := src.read(1024 * 1024):
                    check_cancel(cancel)
                    dst.write(chunk)


@dataclass
class Episode:
    series: str
    series_id: str
    number: int
    playlist: Path
    subtitle: Path | None


def scan(root):
    episodes = []
    for playlist in Path(root).resolve().rglob('master.m3u8'):
        if '__MACOSX' in playlist.parts:
            continue
        folder = playlist.parent
        metadata = folder.parent / 'series.json'
        if not metadata.exists():
            metadata = folder / 'episode.json'
        data = {}
        if metadata.exists():
            try:
                data = json.loads(metadata.read_text(encoding='utf-8-sig'))
            except (ValueError, OSError):
                pass
        number = re.match(r'(\d+)', folder.name)
        subtitles = sorted(folder.glob('*.srt'))
        episodes.append(Episode(data.get('name', folder.parent.name),
                                str(data.get('id', folder.parent.name)),
                                int(number[1]) if number else len(episodes) + 1,
                                playlist.resolve(), subtitles[0] if subtitles else None))
    return sorted(episodes, key=lambda e: (e.series, e.series_id, e.number))


def validate_playlist(playlist):
    root = playlist.parent.resolve()
    seen = set()

    def visit(path):
        if path in seen:
            return
        seen.add(path)
        content = path.read_text(encoding='utf-8-sig')
        if not content.startswith('#EXTM3U'):
            raise ValueError('Playlist không hợp lệ')
        refs = re.findall(r'URI="([^"]+)"', content)
        refs += [line.strip() for line in content.splitlines() if line.strip() and not line.startswith('#')]
        for ref in refs:
            if ':' in ref or ref.startswith(('/', '\\')):
                raise ValueError('Chỉ hỗ trợ playlist với file local trong thư mục tập')
            target = (path.parent / ref).resolve()
            if not target.is_relative_to(root):
                raise ValueError('Playlist tham chiếu ra ngoài thư mục tập')
            if not target.is_file():
                raise ValueError(f'Thiếu file: {target.name}')
            if target.suffix.lower() == '.m3u8':
                visit(target)
    visit(playlist)


def binary(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    bundled = base / 'vendor' / (name + '.exe')
    found = str(bundled) if bundled.exists() else shutil.which(name)
    if not found:
        raise ValueError(f'Không tìm thấy {name}. Đặt {name}.exe vào folder vendor.')
    return found


def run_process(args, cwd, log_path, cancel):
    require_license()
    next_license_check = time.monotonic() + 15
    with log_path.open('a', encoding='utf-8') as log:
        process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            while True:
                check_cancel(cancel)
                if time.monotonic() >= next_license_check:
                    require_license()
                    next_license_check = time.monotonic() + 15
                try:
                    code = process.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if code:
            raise ValueError(f'FFmpeg lỗi; xem {log_path.name}')


def export_episode(episode, output, mode, cancel):
    require_license()
    if mode == 'both':
        results = []
        for variant in ('clean', 'burn'):
            check_cancel(cancel)
            try:
                status, path = export_episode(episode, output, variant, cancel)
                results.append(f'{variant}: {status}')
            except Cancelled:
                raise
            except Exception as exc:
                results.append(f'{variant}: Lỗi: {exc}')
        summary = '; '.join(results)
        if any('Lỗi:' in result for result in results):
            raise ValueError(summary)
        return summary, Path(output).resolve()
    validate_playlist(episode.playlist)
    if mode not in ('sidecar', 'embedded', 'burn', 'clean'):
        raise ValueError('Chế độ phụ đề không hợp lệ')
    if mode != 'clean' and not episode.subtitle:
        raise ValueError('Tập này thiếu SRT, cần bổ sung phụ đề trước khi xuất')
    folder = Path(output).resolve() / (safe_name(episode.series) + '_' + safe_name(episode.series_id)) / mode
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'Tap_{episode.number:03d}.mp4'
    srt_target = target.with_suffix('.srt')
    if target.exists() or srt_target.exists():
        return 'Bỏ qua: đã có file', target
    log = target.with_suffix('.log')
    with tempfile.TemporaryDirectory(prefix='.working-', dir=folder) as td:
        work = Path(td)
        sub = work / 'subtitle.srt'
        if mode != 'clean':
            shutil.copyfile(episode.subtitle, sub)
        if mode == 'burn':
            write_ass(sub, work / 'subtitle.ass')
        partial = work / 'video.mp4'
        args = [binary('ffmpeg'), '-hide_banner', '-nostdin', '-y', '-loglevel', 'warning',
                '-protocol_whitelist', 'file,crypto,data', '-allowed_extensions', 'ALL',
                '-i', str(episode.playlist)]
        if mode == 'embedded':
            args += ['-i', str(sub)]
        args += ['-map', '0:v:0', '-map', '0:a:0']
        if mode == 'burn':
            args += ['-vf', 'ass=subtitle.ass', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-c:a', 'copy']
        else:
            args += ['-c:v', 'copy', '-c:a', 'copy']
        if mode == 'embedded':
            args += ['-map', '1:0', '-c:s', 'mov_text', '-disposition:s:0', 'default']
        args += ['-movflags', '+faststart', str(partial)]
        run_process(args, work, log, cancel)
        check_cancel(cancel)
        probe_file = work / 'probe.json'
        run_process([binary('ffprobe'), '-v', 'error', '-show_streams', '-show_format',
                     '-of', 'json', str(partial)], work, probe_file, cancel)
        data = json.loads(probe_file.read_text(encoding='utf-8'))
        types = {s['codec_type'] for s in data['streams']}
        required = {'video', 'audio'} | ({'subtitle'} if mode == 'embedded' else set())
        if not required <= types or float(data['format'].get('duration', 0)) <= 0:
            raise ValueError('Video đầu ra thiếu hình, tiếng hoặc phụ đề')
        # Create at the destination to inherit its ACL, not the private temp ACL.
        with target.open('xb') as destination, partial.open('rb') as source:
            try:
                shutil.copyfileobj(source, destination)
            except BaseException:
                destination.close()
                target.unlink(missing_ok=True)
                raise
        if mode == 'sidecar':
            with srt_target.open('xb') as destination, sub.open('rb') as source:
                shutil.copyfileobj(source, destination)
    warning = log.stat().st_size > 0
    return ('Hoàn tất (có cảnh báo, xem log)' if warning else 'Hoàn tất'), target
