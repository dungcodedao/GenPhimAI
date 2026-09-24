# AppVideoAI — bản đầu

Người dùng đã duyệt bắt đầu từ kế hoạch tool Windows, đặt folder AppVideoAI.

Mục tiêu: chọn ZIP/folder chứa các bộ phim, quét tập, xuất hàng loạt MP4 với phụ đề. Xử lý dữ liệu local theo playlist, không suy đoán thứ tự từ tên segment.

Công nghệ: Python 3, Tkinter (có sẵn trên máy), FFmpeg/ffprobe từ PATH hoặc vendor. Thay PySide6 trong đề xuất để không cần cài thư viện cho bản đầu.

Luồng: giải nén vào thư mục tạm → quét master.m3u8 → kiểm tra tài nguyên local → xuất tuần tự → kiểm tra stream đầu ra → lưu báo cáo. Một tập lỗi không chặn các tập còn lại. Hủy dừng tiến trình đang chạy. Không ghi đè file đầu ra có sẵn.

Phụ đề: SRT rời, mov_text trong MP4, hoặc burn bằng libx264. Thiếu SRT khi chọn phụ đề thì báo lỗi tập. Giữ nguyên ngôn ngữ nguồn.

Cấu trúc: app.py giao diện; engine.py quét/xuất; tests/ kiểm tra an toàn ZIP và playlist; tasks/ kế hoạch; README.md hướng dẫn; Start.cmd mở tool.

Quy ước: pathlib, tên snake_case, subprocess truyền list đối số, không shell=True. Dữ liệu JSON/m3u8 chỉ là dữ liệu.

Kiểm tra: python -m unittest discover -s tests; xuất tập 1 ở cả ba chế độ và dùng ffprobe đọc stream. Kiểm tra GUI khởi tạo. Các tập còn lại do người dùng chọn xuất.

Ranh giới: giữ nguyên nguồn; chỉ giải nén media/metadata; chặn ZIP traversal và playlist ra ngoài thư mục tập hoặc truy cập mạng; không tải nguồn ngoài, không tạo cảnh phim AI. Không tự xóa đầu ra người dùng.

Chạy: Start.cmd hoặc python app.py. Chấp nhận hoàn thành khi quét được ZIP mẫu 30 tập, xuất mẫu có hình/tiếng/phụ đề và GUI chạy.
