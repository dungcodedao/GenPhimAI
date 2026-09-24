- [x] Tạo project AppVideoAI và ghi kế hoạch.
- [x] Quét ZIP/folder, chặn đường dẫn không an toàn, kiểm tra segment.
- [x] Xuất MP4 theo playlist với audio và ba chế độ phụ đề.
- [x] Giao diện tiếng Việt, chọn tập, hàng đợi, hủy, báo cáo.
- [x] Kiểm tra 4 tình huống đầu vào; giải nén và quét ZIP thật đủ 30 tập.
- [x] Xuất thử tập 1 ở cả ba chế độ; ffprobe xác nhận stream đầu ra.
- [x] Đóng gói EXE độc lập cho máy khác.

## Phụ đề nhiều ngôn ngữ (24/09/2026)

- [x] Google Translation Basic: 10 ngôn ngữ, gồm Filipino/Tagalog.
- [x] Đọc/ghi SRT giữ số câu và thời gian; báo lỗi nếu thiếu câu.
- [x] Lưu cụm dịch để tiếp tục; giữ bản SRT người dùng đã chỉnh sửa.
- [x] Một bản clean và các bản burn/embedded/sidecar theo ngôn ngữ.
- [x] Lưu API key bằng Windows DPAPI, ngoài folder phát hành.
- [x] Giao diện chọn ngôn ngữ, tạo SRT, cài đặt Google và chọn SRT nguồn.
- [x] 30 kiểm tra tự động qua; 5 video mẫu render và decode được bằng FFmpeg.
- [ ] Dịch trực tiếp một tập bằng API key của người dùng; rà soát chất lượng ngôn ngữ.
