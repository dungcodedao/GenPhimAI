import json
import os
import sys
import queue
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from engine import Cancelled, episode_folder, extract_zip, scan
from api_settings import load_settings, settings_summary, show_settings
from jobs import episode_jobs, run_episode
from translation import HybridTranslator, LANGUAGES, NVIDIA_CODES
from subtitles import read_srt


# Local Tcl scripts avoid the bundled runtime's failing library lookup.
_tcl = Path(__file__).parent / 'vendor' / 'tcl'
if (_tcl / 'tcl8.6' / 'init.tcl').exists():
    os.environ['TCL_LIBRARY'] = str(_tcl / 'tcl8.6')
    os.environ['TK_LIBRARY'] = str(_tcl / 'tk8.6')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AppVideoAI • Xuất phim và phụ đề')
        height = max(640, min(820, self.winfo_screenheight() - 80))
        width = max(1000, min(1200, self.winfo_screenwidth() - 80))
        self.geometry(f'{width}x{height}')
        self.minsize(1000, min(720, height))
        self.checked = set()
        self.selection_count = tk.StringVar(value='Chưa có tập phim')
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.episodes = []
        self.temp = None
        self.busy = False
        self.source = tk.StringVar()
        app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        self.output = tk.StringVar(value=str(app_dir / 'output_v2'))
        self.mode = tk.StringVar(value='Hai bản: có và không phụ đề')
        self.status = tk.StringVar(value='Chọn ZIP hoặc folder phim để bắt đầu.')
        self.api_settings = {'mode': 'auto', 'beeknoee_key': '', 'nvidia_key': ''}
        self.api_status = tk.StringVar(value='Chưa có API key dịch')
        try:
            self.api_settings = load_settings()
            self.api_status.set(settings_summary(self.api_settings))
        except (ValueError, OSError) as exc:
            self.api_status.set(str(exc))
        self.languages = {code: tk.BooleanVar(value=code == 'en') for code in LANGUAGES}
        style = ttk.Style(self)
        style.theme_use('clam')
        self.configure(background='#f3f6fa')
        style.configure('.', font=('Segoe UI', 10), background='#f3f6fa', foreground='#172b40')
        style.configure('TButton', padding=(10, 6), background='#e4ebf3', borderwidth=0)
        style.configure('Accent.TButton', background='#176a64', foreground='white')
        style.map('Accent.TButton', background=[('active', '#125750'), ('disabled', '#91aaa7')])
        style.configure('Treeview', rowheight=38, background='white', fieldbackground='white', borderwidth=0)
        style.configure('Treeview.Heading', background='#e4ebf3', padding=10, font=('Segoe UI', 10, 'bold'))
        style.map('Treeview', background=[('selected', '#e0f2ef')], foreground=[('selected', '#172b40')])
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'))
        body = ttk.Frame(self, padding=16)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='AppVideoAI', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='XUẤT PHIM HÀNG LOẠT  /  PHỤ ĐỀ 10 NGÔN NGỮ').pack(anchor='w', pady=(0, 10))
        self.controls = []
        for label, variable, actions in [
            ('Nguồn phim', self.source, [('Chọn ZIP', self.choose_zip), ('Chọn folder', self.choose_folder)]),
            ('Nơi lưu video', self.output, [('Chọn nơi lưu', self.choose_output)])]:
            row = ttk.Frame(body)
            row.pack(fill='x', pady=5)
            ttk.Label(row, text=label, width=15).pack(side='left')
            entry = ttk.Entry(row, textvariable=variable)
            entry.pack(side='left', fill='x', expand=True)
            self.controls.append(entry)
            for text, command in actions:
                button = ttk.Button(row, text=text, command=command)
                button.pack(side='left', padx=(8, 0))
                self.controls.append(button)
        row = ttk.Frame(body)
        row.pack(fill='x', pady=10)
        ttk.Label(row, text='Kiểu phụ đề', width=15).pack(side='left')
        self.combo = ttk.Combobox(row, textvariable=self.mode, state='readonly', width=33,
                                 values=['Hai bản: có và không phụ đề', 'Chỉ video không phụ đề', 'Phụ đề cố định trên phim', 'Phụ đề bật/tắt trong MP4', 'MP4 + SRT rời'])
        self.combo.pack(side='left')
        ttk.Label(row, text='Chữ nhỏ hơn • Tối đa 2 dòng • Trắng, viền đen').pack(side='left', padx=12)
        translation = ttk.LabelFrame(body, text='Ngôn ngữ phụ đề • SRT nguồn là tiếng Anh', padding=10)
        translation.pack(fill='x', pady=(0, 6))
        language_grid = ttk.Frame(translation)
        language_grid.pack(fill='x')
        for index, (code, label) in enumerate(LANGUAGES.items()):
            button = ttk.Checkbutton(language_grid, text=label, variable=self.languages[code])
            button.grid(row=index // 6, column=index % 6, sticky='w', padx=(0, 12), pady=3)
            self.controls.append(button)
        for col in range(6):
            language_grid.columnconfigure(col, weight=1)
        api_row = ttk.Frame(translation)
        api_row.pack(fill='x', pady=(6, 0))
        for text, command in [('Cài đặt NVIDIA + Beeknoee', lambda: show_settings(self)),
                              ('Chọn hết ngôn ngữ', lambda: self.set_languages(True)),
                              ('Bỏ chọn', lambda: self.set_languages(False))]:
            button = ttk.Button(api_row, text=text, command=command)
            button.pack(side='left', padx=(0, 6))
            self.controls.append(button)
        ttk.Label(api_row, textvariable=self.api_status, wraplength=420).pack(side='left', padx=8)
        ttk.Label(translation, text='Tự động: NVIDIA miễn phí là chính; Beeknoee dịch Filipino và dự phòng khi lỗi.',
                  wraplength=1100).pack(anchor='w', pady=(5, 0))
        row = ttk.Frame(body)
        row.pack(fill='x', pady=7)
        for text, command in [('1. Quét tập phim', self.start_scan),
                              ('2. Tạo SRT / tiếp tục', lambda: self.start_export(srt_only=True)),
                              ('3. Xuất video', self.start_export),
                              ('Chọn tất cả', self.select_all), ('Bỏ chọn tất cả', self.clear_all)]:
            button = ttk.Button(row, text=text, command=command, style='Accent.TButton' if text.startswith('3.') else 'TButton')
            button.pack(side='left', padx=(0, 8))
            self.controls.append(button)
        self.stop = ttk.Button(row, text='Dừng', command=self.cancel.set, state='disabled')
        self.stop.pack(side='left')
        ttk.Button(row, text='Mở nơi lưu', command=self.open_output).pack(side='right')

        # Reserve the footer before the expanding table so progress and status
        # stay visible on small screens and with Windows display scaling.
        footer = ttk.Frame(body)
        footer.pack(side='bottom', fill='x', pady=(4, 0))
        source_row = ttk.Frame(footer)
        source_row.pack(fill='x')
        ttk.Label(source_row, textvariable=self.selection_count, font=('Segoe UI', 10, 'bold')).pack(side='left')
        for text, command in [('Chọn SRT nguồn', self.choose_source_srt), ('Mở SRT của tập', self.open_subtitles)]:
            button = ttk.Button(source_row, text=text, command=command)
            button.pack(side='right', padx=(6, 0))
            self.controls.append(button)
        ttk.Label(footer, text='Tích ô ☐ / ☑ để chọn tập. Nhấp dòng tập để chọn SRT nguồn hoặc mở phụ đề đã dịch.').pack(anchor='w', pady=(4, 0))
        self.progress = ttk.Progressbar(footer, mode='determinate')
        self.progress.pack(fill='x', pady=(8, 5))
        ttk.Label(footer, textvariable=self.status, wraplength=950).pack(anchor='w')

        table_frame = ttk.Frame(body)
        table_frame.pack(fill='both', expand=True, pady=(6, 4))
        self.table = ttk.Treeview(table_frame, columns=('check', 'series', 'episode', 'sub', 'state'), show='headings', selectmode='browse')
        for col, title, width in [('check', 'Chọn', 65), ('series', 'Bộ phim', 290), ('episode', 'Tập', 60), ('sub', 'Phụ đề', 135), ('state', 'Trạng thái', 350)]:
            self.table.heading(col, text=title)
            self.table.column(col, width=width)
        self.table.column('check', width=65, stretch=False, anchor='center')
        self.table.column('episode', width=60, stretch=False, anchor='center')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(side='left', fill='both', expand=True)
        self.table.bind('<Button-1>', self.toggle_click)
        self.table.bind('<space>', self.toggle_space)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def choose_zip(self):
        path = filedialog.askopenfilename(filetypes=[('ZIP', '*.zip')])
        if path:
            self.source.set(path)

    def choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.source.set(path)

    def choose_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output.set(path)

    def open_output(self):
        path = Path(self.output.get())
        if path.is_dir():
            os.startfile(path)
        else:
            messagebox.showinfo('Nơi lưu', 'Folder sẽ được tạo khi xuất video.')

    def select_all(self):
        if not self.busy:
            self.checked = set(self.table.get_children())
            self.refresh_checks()

    def set_languages(self, selected):
        if not self.busy:
            for variable in self.languages.values():
                variable.set(selected)

    def choose_source_srt(self):
        item = self.table.focus()
        if not item:
            messagebox.showinfo('Chọn một dòng tập', 'Nhấp vào dòng tập muốn đổi SRT nguồn trước.')
            return
        episode = self.episodes[int(item)]
        path = filedialog.askopenfilename(title='Chọn SRT tiếng Anh của tập',
                                         initialdir=episode.playlist.parent, filetypes=[('Phụ đề SRT', '*.srt')])
        if path:
            try:
                read_srt(Path(path))
                self.episodes[int(item)] = replace(episode, subtitle=Path(path))
                self.table.set(item, 'sub', Path(path).name)
            except (ValueError, OSError) as exc:
                messagebox.showerror('SRT chưa hợp lệ', str(exc))

    def open_subtitles(self):
        item = self.table.focus()
        if not item:
            messagebox.showinfo('Chọn một dòng tập', 'Nhấp vào dòng tập muốn xem phụ đề trước.')
            return
        path = episode_folder(self.episodes[int(item)], self.output.get()) / 'subtitles'
        if path.is_dir():
            os.startfile(path)
        else:
            messagebox.showinfo('Chưa có phụ đề đã xuất', 'Chọn ngôn ngữ rồi bấm Tạo SRT trước.')

    def clear_all(self):
        if not self.busy:
            self.checked.clear()
            self.refresh_checks()

    def refresh_checks(self):
        for item in self.table.get_children():
            self.table.set(item, 'check', '☑' if item in self.checked else '☐')
        self.selection_count.set(f'Đã chọn {len(self.checked)} / {len(self.episodes)} tập')

    def toggle(self, item):
        if item and not self.busy:
            if item in self.checked:
                self.checked.remove(item)
            else:
                self.checked.add(item)
            self.refresh_checks()

    def toggle_click(self, event):
        if self.table.identify_column(event.x) == '#1':
            self.toggle(self.table.identify_row(event.y))

    def toggle_space(self, event):
        self.toggle(self.table.focus())
        return 'break'

    def launch(self, worker):
        self.busy = True
        self.cancel.clear()
        for control in self.controls:
            control.configure(state='disabled')
        self.combo.configure(state='disabled')
        self.stop.configure(state='normal')

        def run():
            try:
                worker()
            except Cancelled:
                self.events.put(('status', 'Đã dừng. Những tập hoàn tất vẫn được giữ.'))
            except Exception as exc:
                self.events.put(('error', str(exc)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def start_scan(self):
        if not self.source.get().strip():
            messagebox.showinfo('Chọn nguồn', 'Hãy chọn file ZIP hoặc folder phim.')
            return
        source = Path(self.source.get()).resolve()
        if not source.exists():
            messagebox.showerror('Nguồn không tồn tại', str(source))
            return
        self.episodes = []
        self.checked.clear()
        self.table.delete(*self.table.get_children())
        self.refresh_checks()
        self.progress.configure(value=0)
        self.status.set('Đang đọc nguồn; giải nén ZIP có thể mất vài phút…')

        def work():
            if self.temp:
                self.temp.cleanup()
                self.temp = None
            root = source
            if source.is_file():
                if source.suffix.lower() != '.zip':
                    raise ValueError('Hãy chọn ZIP hoặc folder.')
                self.temp = tempfile.TemporaryDirectory(prefix='AppVideoAI-')
                root = Path(self.temp.name)
                extract_zip(source, root, self.cancel)
            episodes = scan(root)
            self.events.put(('scanned', episodes))
        self.launch(work)

    def start_export(self, srt_only=False):
        selected = [(i, self.episodes[int(i)]) for i in sorted(self.checked, key=int)]
        if not selected:
            messagebox.showinfo('Chọn tập', 'Quét phim và chọn các tập cần xuất trước.')
            return
        if not self.output.get().strip():
            messagebox.showinfo('Nơi lưu', 'Hãy chọn folder lưu video.')
            return
        output = Path(self.output.get()).resolve()
        mode = {'Hai bản: có và không phụ đề': 'both', 'Chỉ video không phụ đề': 'clean', 'Phụ đề cố định trên phim': 'burn', 'Phụ đề bật/tắt trong MP4': 'embedded', 'MP4 + SRT rời': 'sidecar'}[self.mode.get()]
        if srt_only:
            mode = 'srt'
        languages = [code for code, variable in self.languages.items() if variable.get()]
        if mode != 'clean' and not languages:
            messagebox.showinfo('Chọn ngôn ngữ', 'Tích ít nhất một ngôn ngữ phụ đề cần xuất.')
            return
        if mode != 'clean':
            needs_ai = [(ep, code) for _, ep in selected for code in languages if code != 'en'
                        and not (episode_folder(ep, output) / 'subtitles' / code / f'Tap_{ep.number:03d}.srt').exists()
                        and code not in dict(getattr(ep, 'available_subtitles', ()))]
            missing = bool(needs_ai)
            mode_key = self.api_settings['mode']
            needs_nvidia = any(code in NVIDIA_CODES for _, code in needs_ai)
            needs_beeknoee = any(code not in NVIDIA_CODES for _, code in needs_ai)
            missing_key = ((mode_key == 'auto' and
                            ((needs_nvidia and not self.api_settings['nvidia_key']) or
                             (needs_beeknoee and not self.api_settings['beeknoee_key']))) or
                           (mode_key == 'beeknoee' and not self.api_settings['beeknoee_key']) or
                           (mode_key == 'nvidia' and not self.api_settings['nvidia_key']))
            if missing and missing_key:
                messagebox.showinfo('Nhập API key dịch', 'Cần API key phù hợp với ngôn ngữ đã chọn. Mở Cài đặt NVIDIA + Beeknoee, '
                                    'nhập key rồi chạy lại.')
                show_settings(self)
                return
        try:
            client = HybridTranslator(self.api_settings['beeknoee_key'], self.api_settings['nvidia_key'],
                                      self.api_settings['mode'])
        except ValueError as exc:
            messagebox.showerror('API key', str(exc))
            return
        self.progress.configure(maximum=len(selected) * len(episode_jobs(mode, languages)), value=0)
        self.status.set('Đang xử lý phụ đề và các bản xuất đã chọn…')

        def work():
            output.mkdir(parents=True, exist_ok=True)
            report = []
            try:
                for item, episode in selected:
                    if self.cancel.is_set():
                        raise Cancelled()
                    self.events.put(('row', (item, 'Đang xử lý…')))

                    def notify(kind, value):
                        if kind == 'result':
                            report.append(value)
                            self.events.put(('progress', len(report)))
                        else:
                            self.events.put(('row', (item, value)))
                            self.events.put(('status', f'Tập {episode.number}: {value}'))

                    try:
                        results = run_episode(episode, output, mode, languages, client, self.cancel, notify)
                    except Cancelled:
                        self.events.put(('row', (item, 'Đã dừng • bấm lại để tiếp tục')))
                        raise
                    errors = sum(r['status'].startswith('Lỗi') for r in results)
                    summary = f'{len(results) - errors}/{len(results)} bản sẵn sàng'
                    if errors:
                        first_error = next(r for r in results if r['status'].startswith('Lỗi'))
                        summary += ' • ' + first_error['status']
                    self.events.put(('row', (item, summary)))
                errors = sum(r['status'].startswith('Lỗi') for r in report)
                self.events.put(('status', f'Đã xử lý {len(selected)} tập: {len(report) - errors} bản sẵn sàng, '
                                 f'{errors} lỗi. Mở nơi lưu để xem SRT, video và báo cáo.'))
            finally:
                name = 'report-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json'
                (output / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.launch(work)

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'scanned':
                    self.episodes = value
                    for i, ep in enumerate(value):
                        available = dict(getattr(ep, 'available_subtitles', ()))
                        subtitle = (f'{len(available)} ngôn ngữ có sẵn' if len(available) > 1 else
                                    ep.subtitle.name if ep.subtitle else
                                    'Chọn SRT nguồn' if ep.subtitle_options else 'Thiếu SRT')
                        self.table.insert('', 'end', iid=str(i), values=('☑', ep.series, ep.number, subtitle, 'Sẵn sàng'))
                    self.checked = set(self.table.get_children())
                    self.refresh_checks()
                    self.status.set(f'Tìm thấy {len(value)} tập. Chọn ngôn ngữ rồi tạo SRT hoặc xuất video.' if value else 'Không tìm thấy master.m3u8 trong nguồn.')
                elif event == 'row':
                    item, status = value
                    short = status
                    if not status.startswith('Lỗi') and 'clean:' in status:
                        short = 'Đã xử lý 2 bản' + (' • có cảnh báo trong log' if 'cảnh báo' in status else '')
                    self.table.set(item, 'state', short)
                    self.table.see(item)
                elif event == 'progress':
                    self.progress.configure(value=value)
                elif event == 'status':
                    self.status.set(value)
                elif event == 'error':
                    self.status.set('Lỗi: ' + value)
                    messagebox.showerror('Không thực hiện được', value)
                elif event == 'done':
                    self.busy = False
                    for control in self.controls:
                        control.configure(state='normal')
                    self.combo.configure(state='readonly')
                    self.stop.configure(state='disabled')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set('Đang dừng an toàn. Bạn có thể đóng cửa sổ khi xử lý đã dừng.')
            return
        if self.temp:
            self.temp.cleanup()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
