# Kích hoạt AppVideoAI

Cập nhật theo yêu cầu mới: bỏ nhập tên/mã máy trong công cụ cấp key. Chọn thời lượng sẵn 5h, 12h, 1/2/3/7/30 ngày. Key ký machine="*", dùng nhiều máy, hạn tuyệt đối tính từ lúc tạo. Client vẫn đọc được key gắn máy cũ. Không thay cặp khóa ký. Gửi release-simple, công cụ chủ CapKey.exe.

Người dùng yêu cầu thêm key trước khi gửi bản thử cho người khác.

## Chung

- Màn hình kích hoạt trước khi mở chức năng xuất video.
- Key riêng cho người nhận, ràng buộc mã máy và ngày hết hạn.
- Công cụ cấp key của chủ phần mềm tách khỏi thư mục phát hành.
- Dùng thư viện cryptography với chữ ký Ed25519; client chỉ giữ public key.
- Kiểm tra sai chữ ký, sai máy, hết hạn, dữ liệu không hợp lệ; không ghi key vào log.
- Các bản EXE đã phát hành trước đó không tự trở thành bản có khóa.

## Quyết định đã duyệt

Người dùng chọn offline, gắn mã máy và ngày hết hạn. Client Ed25519 public key; owner tool DPAPI bảo vệ private key dưới tài khoản Windows của chủ. Mã máy là hash MachineGuid Windows; có thể đổi khi cài lại Windows và không chống clone hệ điều hành.

Kiểm tra lúc mở app, mỗi lần xuất và mỗi 15 giây trong tiến trình xử lý. Đồng hồ trước ngày cấp bị từ chối; không chống hoàn toàn can thiệp đồng hồ offline. Không giới hạn số tập trong đợt này.

Phát hành client riêng và tool owner riêng. Chạy tests/test_licensing.py và tests/check_owner_flow.py (dưới tài khoản chủ, không giữ lại license test).

## Các lựa chọn đã cân nhắc

Offline: xác thực chữ ký tại máy; không thu hồi từ xa, đồng hồ hệ thống có thể bị can thiệp.
Online: cần địa chỉ server HTTPS, lưu trạng thái kích hoạt và thu hồi phía server; cần chọn nơi triển khai và chính sách khi mất mạng.

## Giới hạn

Key không ngăn trích xuất hoặc sửa code của ứng dụng desktop. Không mô tả đây là cơ chế chống sao chép tuyệt đối.
