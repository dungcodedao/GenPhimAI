import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import hashlib
from functools import lru_cache
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
    subtitle_options: tuple = ()
    available_subtitles: tuple = ()


def episode_folder(episode, output):
    return Path(output).resolve() / (safe_name(episode.series) + '_' + safe_name(episode.series_id))


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
        language_codes = {'en': 'en', 'vi': 'vi', 'fr': 'fr', 'es': 'es', 'pt': 'pt', 'ja': 'ja',
                          'ko': 'ko', 'de': 'de', 'th': 'th', 'id': 'id', 'tl': 'tl'}
        available = {}
        manifest = folder / 'complete.json'
        if manifest.exists():
            try:
                completed = json.loads(manifest.read_text(encoding='utf-8-sig'))
                for item in completed.get('subtitles', []):
                    local = (folder / str(item.get('local', ''))).resolve()
                    code = str(item.get('language', '')).lower().split('-')[0]
                    code = 'tl' if code in ('fil', 'tl') else code
                    if (code in language_codes and local.is_relative_to(folder.resolve()) and
                            local.is_file() and local.suffix.lower() == '.srt'):
                        available.setdefault(code, local)
            except (ValueError, OSError, AttributeError, TypeError):
                pass
        for path in subtitles:
            match = re.search(r'(^|[._-])(en|eng|english|us|vi|fr|es|pt|ja|ko|de|th|id|tl|fil)([._-]|$)',
                              path.stem, re.I)
            if match:
                code = match.group(2).lower()
                code = {'eng': 'en', 'english': 'en', 'us': 'en', 'fil': 'tl'}.get(code, code)
                available.setdefault(code, path.resolve())
        subtitle = available.get('en')
        if subtitle is None and len(subtitles) == 1:
            subtitle = subtitles[0].resolve()
        episodes.append(Episode(data.get('name', folder.parent.name),
                                str(data.get('id', folder.parent.name)),
                                int(number[1]) if number else len(episodes) + 1,
                                playlist.resolve(), subtitle, tuple(subtitles), tuple(sorted(available.items()))))
    return sorted(episodes, key=lambda e: (e.series, e.series_id, e.number))


def validate_playlist(playlist):
    root = playlist.parent.resolve()
    seen = set()
    resources = {playlist.resolve()}

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
            resources.add(target)
            if target.suffix.lower() == '.m3u8':
                visit(target)
    visit(playlist)
    return sorted(resources)


@lru_cache(maxsize=4096)
def file_digest(path, size, modified):
    # Size/mtime are cache keys only; persisted identity uses file contents.
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def export_identity(resources, subtitle, mode, language):
    values = ['subtitles-v4-font72', mode, language]
    for path in [*resources, subtitle]:
        stat = path.stat()
        values.append(file_digest(path, stat.st_size, stat.st_mtime_ns))
    return hashlib.sha256('\n'.join(values).encode()).hexdigest()


def versioned_target(folder, number, identity):
    for revision in range(1, 1001):
        suffix = '' if revision == 1 else f'_v{revision}'
        path = folder / f'Tap_{number:03d}{suffix}.mp4'
        if not path.exists() and not path.with_suffix('.srt').exists():
            return path, False
        try:
            saved = json.loads(path.with_suffix('.export.json').read_text(encoding='utf-8'))
            if path.exists() and path.stat().st_size > 0 and saved.get('identity') == identity:
                if saved.get('mode') != 'sidecar' or path.with_suffix('.srt').exists():
                    return path, True
        except (OSError, ValueError, AttributeError):
            pass
    raise ValueError('Quá nhiều bản xuất của tập này. Hãy chọn nơi lưu mới.')


def binary(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    bundled = base / 'vendor' / (name + '.exe')
    found = str(bundled) if bundled.exists() else shutil.which(name)
    if not found:
        raise ValueError(f'Không tìm thấy {name}. Đặt {name}.exe vào folder vendor.')
    return found


def run_process(args, cwd, log_path, cancel):
    with log_path.open('a', encoding='utf-8') as log:
        process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            while True:
                check_cancel(cancel)
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


def export_episode(episode, output, mode, cancel, language=None):
    if mode == 'both':
        results = []
        for variant in ('clean', 'burn'):
            check_cancel(cancel)
            try:
                status, path = export_episode(episode, output, variant, cancel, language)
                results.append(f'{variant}: {status}')
            except Cancelled:
                raise
            except Exception as exc:
                results.append(f'{variant}: Lỗi: {exc}')
        summary = '; '.join(results)
        if any('Lỗi:' in result for result in results):
            raise ValueError(summary)
        return summary, Path(output).resolve()
    resources = validate_playlist(episode.playlist)
    if mode not in ('sidecar', 'embedded', 'burn', 'clean'):
        raise ValueError('Chế độ phụ đề không hợp lệ')
    if mode != 'clean' and not episode.subtitle:
        raise ValueError('Tập này thiếu SRT, cần bổ sung phụ đề trước khi xuất')
    if language is not None and language not in ('en', 'vi', 'fr', 'es', 'pt', 'ja', 'ko', 'de', 'th', 'id', 'tl'):
        raise ValueError('Mã ngôn ngữ không hợp lệ.')
    folder = episode_folder(episode, output) / mode
    identity = None
    if language and mode != 'clean':
        folder = folder / language
        identity = export_identity(resources, episode.subtitle, mode, language)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'Tap_{episode.number:03d}.mp4'
    if identity:
        target, existing = versioned_target(folder, episode.number, identity)
        if existing:
            return 'Bỏ qua: đã có bản này', target
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
            write_ass(sub, work / 'subtitle.ass', language or 'en')
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
            iso = {'en': 'eng', 'vi': 'vie', 'fr': 'fra', 'es': 'spa', 'pt': 'por', 'ja': 'jpn',
                   'ko': 'kor', 'de': 'deu', 'th': 'tha', 'id': 'ind', 'tl': 'fil'}
            args += ['-map', '1:0', '-c:s', 'mov_text', '-disposition:s:0', 'default',
                     '-metadata:s:s:0', 'language=' + iso.get(language, 'eng')]
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
        if identity:
            metadata = target.with_suffix('.export.json')
            temporary = metadata.with_suffix('.tmp')
            temporary.write_text(json.dumps({'identity': identity, 'mode': mode}), encoding='utf-8')
            temporary.replace(metadata)
    warning = log.stat().st_size > 0
    return ('Hoàn tất (có cảnh báo, xem log)' if warning else 'Hoàn tất'), target
