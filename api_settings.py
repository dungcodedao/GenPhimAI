"""Encrypted NVIDIA and Gemini API settings plus their configuration dialog."""
import json
import os
from pathlib import Path

from google_settings import protect


MODES = {
    'Tự động: NVIDIA + Gemini dự phòng': 'auto',
    'Chỉ Gemini': 'gemini',
    'Chỉ NVIDIA (không có Filipino)': 'nvidia',
}


def settings_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AppVideoAI' / 'translation-apis.dpapi'


def load_settings():
    path = settings_path()
    default = {'mode': 'auto', 'nvidia_key': '', 'gemini_key': ''}
    if not path.exists():
        return default
    if path.stat().st_size > 32768:
        raise ValueError('File cài đặt API không hợp lệ. Hãy nhập lại key.')
    try:
        data = json.loads(protect(path.read_bytes(), decrypt=True).decode('utf-8'))
        if not isinstance(data, dict) or data.get('mode') not in MODES.values():
            raise ValueError()
        return {key: str(data.get(key, default[key])) for key in default}
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError('Không đọc được API key đã lưu. Mở Cài đặt API và nhập lại.') from None


def save_settings(data):
    payload = {key: str(data.get(key, '')) for key in ('mode', 'nvidia_key', 'gemini_key')}
    if payload['mode'] not in MODES.values():
        raise ValueError('Chế độ API không hợp lệ.')
    encrypted = protect(json.dumps(payload).encode('utf-8'))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def forget_settings():
    settings_path().unlink(missing_ok=True)


def settings_summary(data):
    mode = next((label for label, value in MODES.items() if value == data.get('mode')), 'Tự động')
    available = []
    if data.get('nvidia_key'):
        available.append('NVIDIA')
    if data.get('gemini_key'):
        available.append('Gemini')
    return mode + ' • ' + (', '.join(available) if available else 'chưa có API key')


def show_settings(app):
    import threading
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox, ttk
    from translation import GeminiTranslator, HybridTranslator, NvidiaTranslator

    dialog = tk.Toplevel(app)
    dialog.title('API dịch phụ đề')
    dialog.geometry('760x570')
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='NVIDIA + Gemini', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(body, text='NVIDIA dịch 9 ngôn ngữ. Gemini dịch Filipino và tự thay thế khi NVIDIA lỗi.',
              wraplength=710).pack(anchor='w', pady=(5, 14))

    mode_label = next((label for label, value in MODES.items() if value == app.api_settings['mode']), next(iter(MODES)))
    mode = tk.StringVar(value=mode_label)
    nvidia = tk.StringVar(value=app.api_settings['nvidia_key'])
    gemini = tk.StringVar(value=app.api_settings['gemini_key'])
    ttk.Label(body, text='Chế độ dịch').pack(anchor='w')
    ttk.Combobox(body, textvariable=mode, values=list(MODES), state='readonly').pack(fill='x', pady=(4, 10))
    ttk.Label(body, text='NVIDIA API key').pack(anchor='w')
    nvidia_entry = ttk.Entry(body, textvariable=nvidia, show='•')
    nvidia_entry.pack(fill='x', pady=(4, 9))
    ttk.Label(body, text='Gemini API key').pack(anchor='w')
    gemini_entry = ttk.Entry(body, textvariable=gemini, show='•')
    gemini_entry.pack(fill='x', pady=(4, 8))
    remember = tk.BooleanVar(value=True)
    ttk.Checkbutton(body, text='Lưu mã hóa cho tài khoản Windows này', variable=remember).pack(anchor='w')
    ttk.Label(body, text='Chỉ lời thoại được gửi tới API; video và mốc thời gian SRT vẫn ở trên máy. '
              'NVIDIA Free Endpoint dành cho phát triển/thử nghiệm.', wraplength=710).pack(anchor='w', pady=10)
    status = tk.StringVar(value='Bạn có thể kiểm tra riêng từng key trước khi lưu.')
    ttk.Label(body, textvariable=status, wraplength=710).pack(anchor='w', pady=(0, 10))
    buttons = []

    def current():
        client = HybridTranslator(nvidia.get(), gemini.get(), MODES[mode.get()])
        return client, {'mode': client.mode, 'nvidia_key': client.nvidia.api_key,
                        'gemini_key': client.gemini.api_key}

    def save():
        try:
            _, data = current()
            if data['mode'] == 'auto' and (not data['nvidia_key'] or not data['gemini_key']):
                raise ValueError('Chế độ tự động cần cả NVIDIA key và Gemini key.')
            if data['mode'] == 'gemini' and not data['gemini_key']:
                raise ValueError('Hãy nhập Gemini key.')
            if data['mode'] == 'nvidia' and not data['nvidia_key']:
                raise ValueError('Hãy nhập NVIDIA key.')
            if remember.get():
                save_settings(data)
            else:
                forget_settings()
            app.api_settings = data
            app.api_status.set(settings_summary(data))
            dialog.destroy()
        except (OSError, ValueError) as exc:
            messagebox.showerror('Chưa lưu được', str(exc), parent=dialog)

    def forget():
        try:
            forget_settings()
            data = {'mode': 'auto', 'nvidia_key': '', 'gemini_key': ''}
            app.api_settings = data
            app.api_status.set(settings_summary(data))
            nvidia.set('')
            gemini.set('')
            status.set('Đã quên cả hai API key trên máy này.')
        except OSError:
            status.set('Chưa xóa được key đã lưu.')

    pending = []

    def poll():
        if not dialog.winfo_exists():
            return
        if not pending:
            app.after(100, poll)
            return
        success, message = pending.pop()
        status.set(message)
        for button in buttons:
            button.configure(state='normal')
        nvidia_entry.configure(state='normal')
        gemini_entry.configure(state='normal')

    def test(provider):
        try:
            client = NvidiaTranslator(nvidia.get()) if provider == 'NVIDIA' else GeminiTranslator(gemini.get())
        except ValueError as exc:
            status.set(str(exc))
            return
        for button in buttons:
            button.configure(state='disabled')
        nvidia_entry.configure(state='disabled')
        gemini_entry.configure(state='disabled')
        status.set(f'Đang kiểm tra {provider}…')

        def work():
            try:
                answer = client.translate(['Hello, my friend.'], 'vi')[0]
                pending.append((True, f'{provider} kết nối thành công: {answer}'))
            except Exception as exc:
                pending.append((False, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        app.after(100, poll)

    row = ttk.Frame(body)
    row.pack(fill='x')
    for text, command in [('Lưu và đóng', save), ('Thử NVIDIA', lambda: test('NVIDIA')),
                          ('Thử Gemini', lambda: test('Gemini')), ('Quên key', forget)]:
        button = ttk.Button(row, text=text, command=command)
        button.pack(side='left', padx=(0, 7))
        buttons.append(button)
    ttk.Button(body, text='Lấy NVIDIA API key', command=lambda: webbrowser.open(
        'https://build.nvidia.com/nvidia/riva-translate-4b-instruct-v2')).pack(anchor='w', pady=(13, 3))
    ttk.Button(body, text='Lấy Gemini API key', command=lambda: webbrowser.open(
        'https://aistudio.google.com/app/apikey')).pack(anchor='w')
