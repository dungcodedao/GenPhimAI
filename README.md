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
