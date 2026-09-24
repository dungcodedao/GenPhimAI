"""One episode -> one clean video and independently resumable subtitle languages."""
import shutil
from dataclasses import replace

from engine import Cancelled, check_cancel, episode_folder, export_episode
from subtitles import read_srt
from translation import LANGUAGES, translate_srt, translate_srt_many


def episode_jobs(mode, languages):
    if mode not in ('both', 'clean', 'srt', 'burn', 'embedded', 'sidecar'):
        raise ValueError('Chế độ xuất không hợp lệ.')
    if any(language not in LANGUAGES for language in languages):
        raise ValueError('Ngôn ngữ xuất không hợp lệ.')
    languages = list(dict.fromkeys(languages))
    jobs = [('clean', None)] if mode in ('both', 'clean') else []
    if mode != 'clean':
        jobs += [('burn' if mode == 'both' else mode, language) for language in languages]
    return jobs


def run_episode(episode, output, mode, languages, client, cancel, notify=None):
    results = []

    def progress(message):
        if notify:
            notify('status', message)

    targets = [language for language in dict.fromkeys(languages) if language != 'en']
    if mode != 'clean' and targets and getattr(client, 'mode', '') != 'nvidia':
        if not episode.subtitle:
            raise ValueError('Chưa có SRT nguồn. Chọn dòng tập rồi bấm Chọn SRT nguồn.')
        read_srt(episode.subtitle)
        destinations = {language: episode_folder(episode, output) / 'subtitles' / language /
                        f'Tap_{episode.number:03d}.srt' for language in targets}
        try:
            translate_srt_many(episode.subtitle, destinations, client, cancel, progress)
        except Cancelled:
            raise
        except Exception as exc:
            progress(f'Dịch chung chưa thành công, đang thử từng ngôn ngữ: {exc}')

    for variant, language in episode_jobs(mode, languages):
        check_cancel(cancel)
        label = LANGUAGES.get(language, 'Không phụ đề')
        result = {'series': episode.series, 'episode': episode.number,
                  'language': language, 'mode': variant, 'file': ''}

        try:
            progress(f'Đang xử lý {label}…')
            if variant == 'clean':
                status, path = export_episode(episode, output, variant, cancel)
            else:
                if not episode.subtitle:
                    raise ValueError('Chưa có SRT nguồn. Chọn dòng tập rồi bấm Chọn SRT nguồn.')
                read_srt(episode.subtitle)
                path = episode_folder(episode, output) / 'subtitles' / language / f'Tap_{episode.number:03d}.srt'
                if language == 'en':
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists() and path.read_bytes() != episode.subtitle.read_bytes():
                        raise ValueError('SRT gốc tại nơi lưu khác nguồn. Hãy chọn nơi lưu mới.')
                    if not path.exists():
                        with path.open('xb') as destination, episode.subtitle.open('rb') as source:
                            shutil.copyfileobj(source, destination)
                else:
                    translate_srt(episode.subtitle, path, language, client, cancel, progress)
                result['subtitle'] = str(path)
                if variant == 'srt':
                    status = 'SRT sẵn sàng'
                else:
                    progress(f'Đang xuất video • {label}…')
                    status, path = export_episode(replace(episode, subtitle=path), output, variant, cancel,
                                                  language=language)
            result.update(status=status, file=str(path))
        except Cancelled:
            raise
        except Exception as exc:
            result['status'] = 'Lỗi: ' + str(exc)
        results.append(result)
        if notify:
            notify('result', result)
    return results
