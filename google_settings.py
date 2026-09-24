"""Store the user's translation key with Windows DPAPI, outside the distributable."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path


def key_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AppVideoAI' / 'google-api.dpapi'


def protect(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Chỉ lưu API key an toàn trên Windows. Có thể dùng key trong phiên hiện tại.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError('Windows không đọc/lưu được API key. Hãy nhập lại key.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(output.data)


def load_key():
    path = key_path()
    if not path.exists():
        return ''
    if path.stat().st_size > 16384:
        raise ValueError('File API key không hợp lệ. Hãy quên key rồi nhập lại.')
    try:
        return protect(path.read_bytes(), decrypt=True).decode('utf-8')
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Không đọc được API key đã lưu. Mở Cài đặt Google và nhập lại key.') from None


def save_key(key):
    encrypted = protect(key.encode('utf-8'))
    path = key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def forget_key():
    key_path().unlink(missing_ok=True)


def show_settings(app):
    import threading
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox, ttk
    from translation import GoogleTranslator

    dialog = tk.Toplevel(app)
    dialog.title('Google dịch phụ đề')
    dialog.geometry('700x405')
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Kết nối Google Cloud Translation', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
    ttk.Label(body, text='Đây là key dịch phụ đề, khác với key kích hoạt AppVideoAI.',
              wraplength=655).pack(anchor='w', pady=(6, 14))
    value = tk.StringVar(value=app.api_key)
    ttk.Label(body, text='API key Google Cloud').pack(anchor='w')
    entry = ttk.Entry(body, textvariable=value, show='•')
    entry.pack(fill='x', pady=(5, 8))
    remember = tk.BooleanVar(value=True)
    ttk.Checkbutton(body, text='Lưu an toàn cho tài khoản Windows này', variable=remember).pack(anchor='w')
    ttk.Label(body, text='Nội dung lời thoại sẽ được gửi tới Google. Dịch có thể phát sinh phí theo tài khoản Google Cloud. '
              'Video không được tải lên.', wraplength=650).pack(anchor='w', pady=12)
    status = tk.StringVar(value='Dịch thử sẽ gửi một câu ngắn để kiểm tra kết nối.')
    ttk.Label(body, textvariable=status, wraplength=650).pack(anchor='w', pady=(0, 12))
    row = ttk.Frame(body)
    row.pack(fill='x')

    def save():
        try:
            client = GoogleTranslator(value.get())
            if not client.api_key:
                raise ValueError('Hãy nhập API key Google trước khi lưu.')
            if remember.get():
                save_key(client.api_key)
            else:
                forget_key()
            app.api_key = client.api_key
            app.google_status.set('Google: đã nhập key • Chưa dịch thử' if not tested[0] else 'Google: đã dịch thử thành công')
            dialog.destroy()
        except (OSError, ValueError) as exc:
            messagebox.showerror('Chưa lưu được', str(exc), parent=dialog)

    def forget():
        try:
            forget_key()
            app.api_key = ''
            app.google_status.set('Google: chưa có API key')
            value.set('')
            tested[0] = False
            status.set('Đã quên key trên máy này.')
        except OSError:
            status.set('Chưa xóa được key đã lưu. Hãy kiểm tra quyền thư mục AppVideoAI.')

    tested = [False]
    value.trace_add('write', lambda *_: tested.__setitem__(0, False))
    result = []

    def poll_test():
        if not dialog.winfo_exists():
            return
        if not result:
            app.after(100, poll_test)
            return
        success, message = result.pop()
        tested[0] = success
        status.set(message)
        for button in buttons:
            button.configure(state='normal')
        entry.configure(state='normal')

    def test():
        try:
            client = GoogleTranslator(value.get())
        except ValueError as exc:
            status.set(str(exc))
            return
        for button in buttons:
            button.configure(state='disabled')
        entry.configure(state='disabled')
        status.set('Đang dịch thử một câu sang tiếng Việt…')

        def work():
            try:
                answer = client.translate(['Hello, my friend.'], 'vi')[0]
                result.append((True, 'Kết nối thành công: ' + answer))
            except Exception as exc:
                result.append((False, str(exc)))
        threading.Thread(target=work, daemon=True).start()
        app.after(100, poll_test)

    buttons = []
    for text, command in [('Lưu và đóng', save), ('Dịch thử 1 câu', test), ('Quên key', forget)]:
        button = ttk.Button(row, text=text, command=command)
        button.pack(side='left', padx=(0, 8))
        buttons.append(button)
    ttk.Button(body, text='Hướng dẫn tạo API key trên Google', command=lambda: webbrowser.open(
        'https://docs.cloud.google.com/translate/docs/setup')).pack(anchor='w', pady=(12, 0))
