# AppVideoAI

## Dùng và gửi người thử
- Bản mới nhất: release-simple/AppVideoAI/AppVideoAI.exe.
- File gửi người thử: release-simple/AppVideoAI-Tester.zip.
- Công cụ cấp key riêng của chủ: ../AppVideoAI-Owner/CapKey.exe. Không gửi folder Owner.
- Chọn hạn 5 giờ, 12 giờ, 1/2/3/7/30 ngày -> Tạo key -> Sao chép. Hạn tính từ lúc tạo. Key mới không gắn máy, có thể dùng nhiều máy; không thu hồi từ xa.

## Xuất phim
Chọn ZIP hoặc folder, quét tập, tích các tập muốn xuất rồi bấm Xuất. Chế độ Hai bản tạo clean (không thêm chữ) và burn (chữ cố định). Nếu nguồn đã có chữ trên hình, clean không xóa được chữ đó.
Phụ đề burn: Arial trắng viền đen, tối đa 2 dòng, câu dài chia đoạn trong thời gian gốc. Không tự sửa chính tả/ngữ pháp. File đã có được bỏ qua; chọn nơi lưu mới để xuất lại.
Video và mẫu từ các bản cũ được giữ trong VideoDaXuat. Log ghi thông báo xử lý, không cần gửi kèm phim.

## Mã nguồn và build
app.py: giao diện; engine.py: xử lý video; subtitles.py: phụ đề; licensing.py: xác thực key; admin_tools/key_manager.py: công cụ chủ.
Start.cmd chạy mã nguồn. build.ps1 đóng gói client và ZIP vào release-simple. .build-deps, vendor và các file spec phục vụ build; không gửi chúng cho người thử.
Kiểm tra: python -m unittest discover -s tests.
Khóa chủ được DPAPI bảo vệ theo tài khoản Windows. Không xóa owner-private.dpapi hoặc license_public.pem.

## Dịch phụ đề sang 10 ngôn ngữ

Google Cloud Translation Basic (NMT) dịch từ SRT tiếng Anh sang Việt, Pháp, Tây Ban Nha, Bồ Đào Nha, Nhật, Hàn, Đức, Thái, Indonesia và Filipino/Tagalog.

1. Tạo một Google Cloud project, bật thanh toán và **Cloud Translation API**, rồi tạo API key dành cho API này: [hướng dẫn Google](https://docs.cloud.google.com/translate/docs/setup). Nên giới hạn key chỉ dùng Cloud Translation API. Key Google khác key kích hoạt phần mềm; key Gemini/AI Studio không thay thế bước cấu hình Google Cloud này.
2. Trong app, mở **Cài đặt Google**, dán key, chọn **Dịch thử 1 câu**, sau đó **Lưu và đóng**. Dịch thử gửi một câu ngắn, có thể tính vào phí sử dụng.
3. Chọn ZIP/folder, quét tập, tích tập và ngôn ngữ cần dịch. Mặc định chỉ tích Anh (gốc), không phát sinh lời gọi dịch.
4. Bấm **Tạo SRT / tiếp tục**. Nút này chỉ tạo phụ đề, không render video. Hoặc bấm **Xuất video** để tự dịch và xuất theo chế độ đang chọn.
5. Nhấp vào dòng tập rồi bấm **Mở SRT của tập**, mở SRT bằng trình soạn thảo nếu muốn sửa. Giữ số câu và thời gian; chỉ sửa lời thoại. Bấm **Xuất video** để dùng SRT đã sửa.

Google tính phí theo cách dùng của tài khoản; xem [giá hiện hành](https://cloud.google.com/products/translate/pricing) và đặt hạn mức trong Google Cloud. Chỉ lời thoại được gửi tới Google; không tải video lên. Máy cần Internet khi dịch mới. Key có thể lưu mã hóa bằng Windows DPAPI ở `%LOCALAPPDATA%/AppVideoAI/google-api.dpapi`, ngoài folder phát hành. Không cần gửi key trong chat. Chọn **Quên key** để xóa key đã lưu.

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

Mã mới: `translation.py` gọi Google/lưu tiến độ; `jobs.py` hàng đợi ngôn ngữ; `google_settings.py` cài đặt và lưu key. Kiểm tra render thật (không gọi Google): `python tests/check_multilingual_render.py`. Bộ kiểm tra tự động dùng dữ liệu dịch giả lập, không chứng minh chất lượng dịch thực tế.
