# AppVideoAI

## Dùng và gửi người thử
- Bản mới nhất: release-simple/AppVideoAI/AppVideoAI.exe.
- File gửi người thử: release-simple/AppVideoAI-Tester.zip.
- App mở và sử dụng trực tiếp, không cần key kích hoạt phần mềm.

## Xuất phim
Chọn ZIP hoặc folder, quét tập, tích các tập muốn xuất rồi bấm Xuất. Chế độ Hai bản tạo clean (không thêm chữ) và burn (chữ cố định). Nếu nguồn đã có chữ trên hình, clean không xóa được chữ đó.
Phụ đề burn: Arial trắng viền đen, tối đa 2 dòng, câu dài chia đoạn trong thời gian gốc. Không tự sửa chính tả/ngữ pháp. File đã có được bỏ qua; chọn nơi lưu mới để xuất lại.
Video và mẫu từ các bản cũ được giữ trong VideoDaXuat. Log ghi thông báo xử lý, không cần gửi kèm phim.

## Mã nguồn và build
app.py: giao diện; engine.py: xử lý video; subtitles.py: phụ đề; translation.py: dịch NVIDIA/Gemini.
Start.cmd chạy mã nguồn. build.ps1 đóng gói client và ZIP vào release-simple. .build-deps, vendor và các file spec phục vụ build; không gửi chúng cho người thử.
Kiểm tra: python -m unittest discover -s tests.

## Dịch phụ đề sang 10 ngôn ngữ

Chế độ mặc định kết hợp NVIDIA Riva và Gemini: NVIDIA dịch 9 ngôn ngữ được hỗ trợ; Gemini dịch Filipino/Tagalog và tự thay thế khi NVIDIA lỗi hoặc bị giới hạn.

1. Lấy NVIDIA key tại https://build.nvidia.com/nvidia/riva-translate-4b-instruct-v2 và Gemini key tại https://aistudio.google.com/app/apikey.
2. Trong app, mở **Cài đặt NVIDIA + Gemini**, dán hai key, kiểm tra từng key rồi **Lưu và đóng**.
3. Chọn ZIP/folder, quét tập, tích tập và ngôn ngữ cần dịch. Mặc định chỉ tích Anh (gốc), không phát sinh lời gọi dịch.
4. Bấm **Tạo SRT / tiếp tục**. Nút này chỉ tạo phụ đề, không render video. Hoặc bấm **Xuất video** để tự dịch và xuất theo chế độ đang chọn.
5. Nhấp vào dòng tập rồi bấm **Mở SRT của tập**, mở SRT bằng trình soạn thảo nếu muốn sửa. Giữ số câu và thời gian; chỉ sửa lời thoại. Bấm **Xuất video** để dùng SRT đã sửa.

Chỉ lời thoại được gửi tới NVIDIA hoặc Gemini; video không được tải lên. Máy cần Internet khi dịch mới. Key có thể lưu mã hóa bằng Windows DPAPI ở `%LOCALAPPDATA%/AppVideoAI/translation-apis.dpapi`, ngoài folder phát hành. Không cần gửi key trong chat. Chọn **Quên key** để xóa cả hai key đã lưu. NVIDIA Free Endpoint dành cho phát triển/thử nghiệm và có thể giới hạn tốc độ.

Đầu ra theo từng bộ phim:

```text
clean/Tap_001.mp4             video không thêm phụ đề, tạo một lần
subtitles/en/Tap_001.srt      phụ đề gốc
subtitles/vi/Tap_001.srt      phụ đề tiếng Việt, có thể sửa
subtitles/tl/Tap_001.srt      phụ đề Filipino/Tagalog
burn/vi/Tap_001.mp4           video gắn chữ tiếng Việt
burn/tl/Tap_001.mp4           video gắn chữ Filipino/Tagalog
```

Chọn 10 ngôn ngữ và chế độ Hai bản sẽ có 1 bản clean + 10 bản burn mỗi tập; nếu tích thêm Anh (gốc), có thêm bản burn tiếng Anh. `embedded` và `sidecar` cũng phân thư mục theo ngôn ngữ.

File `.translation.json` cạnh SRT lưu tiến độ/nhận diện nguồn; giữ file này để tiếp tục và tránh dịch lại. File `.export.json` cạnh video giúp nhận ra bản đã xuất. Không sửa/xóa hai loại file này. Nếu sửa lời SRT, lần xuất tiếp theo tự tạo `Tap_001_v2.mp4`, không ghi đè bản cũ. Nếu đổi SRT nguồn, chọn nơi lưu mới. Một ngôn ngữ lỗi không xóa kết quả ngôn ngữ khác. Khi Dừng trong lúc đợi Google, app có thể cần tới khoảng 20 giây để kết thúc lời gọi hiện tại; các cụm đã nhận được lưu lại.

Nếu nhiều SRT và không xác định được file tiếng Anh, tool hiển thị **Chọn SRT nguồn**: nhấp dòng tập rồi bấm nút cùng tên. Kiểm tra SRT bạn chọn thật sự là tiếng Anh.

Tên riêng, đại từ và ngữ cảnh cần rà soát: bản đầu dùng NMT, chưa có glossary nhân vật hay dịch theo ngữ cảnh cả bộ. Bản SRT giữ nguyên mốc thời gian nguồn; khi burn, câu dài có thể chia nhỏ trong cùng khoảng thời gian để giữ tối đa hai dòng. Font Nhật/Hàn/Thái dùng font Windows; nếu máy thiếu font, app báo cách xử lý.

`translation.py` gọi NVIDIA/Gemini và lưu tiến độ; `jobs.py` quản lý hàng đợi ngôn ngữ; `api_settings.py` cài đặt và lưu key. Bản dịch tự động vẫn cần rà soát trước khi phát hành.
