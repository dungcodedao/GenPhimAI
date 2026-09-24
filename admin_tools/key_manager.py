"""Owner-only license issuer. Never include this tool in the client release."""
import argparse
import base64
import ctypes
import json
import os
import re
import sys
import uuid
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
        raise OSError('Không mở được khóa chủ. Hãy dùng đúng tài khoản Windows đã tạo khóa.')
    try:
        return ctypes.string_at(destination.data, destination.size)
    finally:
        kernel.LocalFree(destination.data)


def initialize(private_path, public_path):
    if private_path.exists() or public_path.exists():
        raise ValueError('Khóa đã tồn tại; không tự thay khóa vì key đã cấp sẽ mất hiệu lực.')
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    protected = dpapi(key.private_bytes(serialization.Encoding.Raw,
                                      serialization.PrivateFormat.Raw, serialization.NoEncryption()))
    with private_path.open('xb') as stream:
        stream.write(protected)
    with public_path.open('xb') as stream:
        stream.write(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo))


def issue(private_path, machine, customer, expires_at):
    machine = machine.strip().upper()
    customer = customer.strip()
    if not re.fullmatch(r'(?:[A-F0-9]{32}|\*)', machine):
        raise ValueError('Mã máy phải gồm 32 ký tự. Hãy dùng nút Sao chép mã máy trong app khách.')
    if not 1 <= len(customer) <= 120:
        raise ValueError('Tên người nhận cần từ 1 đến 120 ký tự.')
    now = int(datetime.now().timestamp())
    if expires_at <= now:
        raise ValueError('Ngày hết hạn phải ở hiện tại hoặc tương lai.')
    key = Ed25519PrivateKey.from_private_bytes(dpapi(private_path.read_bytes(), decrypt=True))
    payload = dict(v=1, product='AppVideoAI', machine=machine, customer=customer,
                   issued_at=now, expires_at=expires_at, license_id=uuid.uuid4().hex)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    token = base64.urlsafe_b64encode(raw).decode() + '.' + base64.urlsafe_b64encode(key.sign(raw)).decode()
    return token, payload


def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    tcl = base / 'vendor' / 'tcl'
    if tcl.exists():
        os.environ['TCL_LIBRARY'] = str(tcl / 'tcl8.6')
        os.environ['TK_LIBRARY'] = str(tcl / 'tk8.6')
    home = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    root = tk.Tk()
    root.title('AppVideoAI • Cấp key — CHỈ DÀNH CHO CHỦ PHẦN MỀM')
    root.geometry('760x480')
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 11))
    style.configure('TButton', padding=10)
    body = ttk.Frame(root, padding=22)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Cấp key AppVideoAI', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
    ttk.Label(body, text='Giữ riêng folder này. Chỉ gửi key tạo ra cho người thử.', foreground='#ac2525').pack(anchor='w', pady=8)
    durations = {'5 giờ': 5, '12 giờ': 12, '1 ngày': 24, '2 ngày': 48,
                 '3 ngày': 72, '7 ngày': 168, '30 ngày': 720}
    duration = tk.StringVar(value='1 ngày')
    ttk.Label(body, text='Thời hạn key').pack(anchor='w', pady=(10, 4))
    ttk.Combobox(body, textvariable=duration, values=list(durations), state='readonly').pack(fill='x')
    ttk.Label(body, text='Tính từ lúc tạo key • Không cần mã máy • Dùng được trên nhiều máy').pack(anchor='w', pady=12)
    output = tk.Text(body, height=7, wrap='char', font=('Consolas', 10))
    output.pack(fill='both', expand=True)
    status = tk.StringVar(value='Chưa cấp key.')
    ttk.Label(body, textvariable=status, wraplength=760).pack(anchor='w', pady=10)

    def generate():
        try:
            expiry = int(datetime.now().timestamp()) + durations[duration.get()] * 3600
            token, payload = issue(home / 'owner-private.dpapi', '*', 'Key ' + duration.get(), expiry)
            issued = home / 'issued'
            issued.mkdir(exist_ok=True)
            safe = re.sub(r'[^\w-]', '_', payload['customer'])[:40]
            file = issued / f"{safe}_{payload['license_id'][:8]}.key"
            file.write_text(token, encoding='utf-8')
            file.with_suffix('.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            messagebox.showerror('Không cấp được key', str(exc))
            return
        output.delete('1.0', 'end')
        output.insert('1.0', token)
        status.set('Hết hạn: ' + datetime.fromtimestamp(expiry).strftime('%d/%m/%Y %H:%M') + ' • Đã lưu key. Bấm Sao chép key để gửi.')

    def copy():
        token = output.get('1.0', 'end').strip()
        if token:
            root.clipboard_clear()
            root.clipboard_append(token)
            status.set('Đã sao chép key.')

    def open_issued():
        (home / 'issued').mkdir(exist_ok=True)
        os.startfile(home / 'issued')
    row = ttk.Frame(body)
    row.pack(fill='x')
    for label, command in [('Tạo key', generate), ('Sao chép key', copy), ('Key đã cấp', open_issued)]:
        ttk.Button(row, text=label, command=command).pack(side='left', padx=(0, 10))
    root.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-private', type=Path)
    parser.add_argument('--public-output', type=Path)
    args = parser.parse_args()
    if args.init_private and args.public_output:
        initialize(args.init_private, args.public_output)
    else:
        run_gui()
