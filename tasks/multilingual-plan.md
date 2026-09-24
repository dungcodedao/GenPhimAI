# Kế hoạch: phụ đề nhiều ngôn ngữ cho AppVideoAI

## Quyết định triển khai 24/09/2026

Người dùng đã đồng ý dùng Google Cloud Translation. Bản đầu chọn Basic v2, model NMT, nguồn `en`, đích `vi/fr/es/pt/ja/ko/de/th/id/tl`. API key nhập trong app và có thể lưu bằng Windows DPAPI. Không cần cài SDK mới.

Điều chỉnh so với đề xuất ban đầu: Basic NMT nhận một danh sách câu văn bản, không nhận chỉ dẫn kiểu chatbot hay từ điển nhân vật. Vì vậy bản này không hứa giữ ngữ cảnh liên tập/tên riêng tự động; người dùng xem và sửa SRT trước khi render. Tiếng Bồ Đào Nha dùng mã chung `pt`; Filipino dùng `tl` (Tagalog). Gửi tối đa 60 câu/5.000 ký tự mỗi cụm, tối đa 3 lần thử cho lỗi mạng hoặc quá tải.

API chỉ nhận lời thoại; mốc thời gian, số câu và video được xử lý ở máy. Bản dịch lỗi cấu trúc bị chặn. Cache theo nguồn/ngôn ngữ được lưu sau từng cụm; SRT đã sửa được ưu tiên khi xuất lại. Video có phụ đề đổi nội dung sẽ tạo `_v2`, `_v3` thay vì ghi đè.

Tài liệu triển khai: https://docs.cloud.google.com/translate/docs/reference/rest/v2/translate ; https://docs.cloud.google.com/docs/authentication/api-keys-use ; https://docs.cloud.google.com/translate/quotas .

Các phần dưới ghi lại đề xuất ban đầu; quyết định ở trên được ưu tiên khi có khác biệt.

## Mục tiêu

Từ SRT tiếng Anh của mỗi tập, tạo SRT cho các ngôn ngữ được chọn và có thể xuất video gắn chữ tương ứng. Giữ chế độ xuất video không phụ đề hiện có. Người dùng chọn tập và ngôn ngữ ngay trên giao diện; một tập lỗi không dừng cả hàng đợi.

## Phạm vi bản đầu

- Ngôn ngữ đích: Pháp, Tây Ban Nha, Bồ Đào Nha, Nhật, Hàn, Đức, Thái, Indonesia, Filipino và Việt Nam. Giữ SRT tiếng Anh gốc để đối chiếu.
- Dùng dịch vụ dịch qua mạng với API key do chủ tool nhập; không nhúng key dịch vụ vào EXE. Chọn dịch vụ cụ thể trước khi code phần kết nối. Tool kiểm tra key và báo rõ khi hết hạn mức/mất mạng.
- Dịch theo cụm câu có ngữ cảnh, giữ nguyên mốc thời gian, số thứ tự và tên riêng đã khai báo. Lưu bản dịch thành SRT để người dùng có thể sửa trước khi gắn lên video.
- Mặc định xuất một bản video không phụ đề cho mỗi tập và chỉ xuất video gắn chữ cho những ngôn ngữ đã chọn. Có tùy chọn chỉ tạo SRT để rà soát trước khi render.
- Không tự sửa lời thoại tiếng Anh nguồn. Không tự nhận bản dịch là chính xác tuyệt đối.

## Luồng xử lý

1. Quét ZIP/folder như hiện tại; xác định SRT tiếng Anh cho từng tập. Nếu có nhiều SRT, chọn theo nhãn/tên file và cho người dùng xem lựa chọn; không lấy file đầu tiên một cách ngẫu nhiên.
2. Đọc, kiểm tra SRT: thời gian tăng hợp lệ, không có câu trống, mã UTF-8. Báo riêng tập thiếu hoặc lỗi SRT.
3. Chia phụ đề thành cụm vừa đủ ngữ cảnh; gửi dịch từng ngôn ngữ. Yêu cầu dịch giữ tên riêng, đại từ, chính tả và cách xưng hô nhất quán. Dùng từ điển tên riêng/ngữ cảnh phim khi có.
4. Ghép câu dịch với ID và mốc thời gian gốc. Kiểm tra đủ số câu, đúng thứ tự, không có câu trống; thử lại cụm lỗi rồi báo lỗi rõ nếu vẫn hỏng. Lưu tiến độ theo tập/ngôn ngữ để có thể tiếp tục.
5. Lưu `subtitles/<lang>/Tap_001.srt`. Người dùng có thể mở/sửa SRT. Khi render, dùng SRT đã lưu; không gọi API lại nếu dữ liệu nguồn và tùy chọn chưa đổi.
6. Xuất `clean/Tap_001.mp4` một lần và `burn/<lang>/Tap_001.mp4` cho từng ngôn ngữ đã chọn. Tái sử dụng đường xuất FFmpeg và kiểu chữ ASS hai dòng hiện có.
7. Báo trạng thái riêng cho từng tập/ngôn ngữ và ghi kết quả vào report hiện có. Dừng an toàn giữa các công đoạn.

## Thay đổi dự kiến

- `subtitles.py`: thêm bộ đọc/ghi/kiểm tra SRT dùng chung; giữ hàm chuyển SRT sang ASS hiện có.
- `translation.py`: giao diện dịch vụ, chia cụm, ghép kết quả, kiểm tra và lưu cache. Chỉ module này gọi dịch vụ ngoài.
- `engine.py`: nhận SRT theo ngôn ngữ và đường đầu ra theo ngôn ngữ; giữ nguyên các chế độ xuất cũ.
- `app.py`: chọn ngôn ngữ bằng ô tích, nút tạo SRT, lựa chọn xuất video, tiến độ tập/ngôn ngữ và thông báo lỗi dễ hiểu.
- `README.md`, `CLIENT-GUIDE.txt`: hướng dẫn API key, chi phí, nơi lưu SRT/video và cách tiếp tục khi gián đoạn.
- `build.ps1`/spec: đóng gói thư viện cần thiết, giữ API key và cache ngoài mã nguồn/EXE.

## Thứ tự làm

1. Chốt dịch vụ dịch, cách nhập API key và biến thể tiếng Bồ Đào Nha/Filipino.
2. Xây bộ đọc/ghi SRT và quy tắc tên file; kiểm tra trên vài tập thật.
3. Tích hợp dịch theo cụm, kiểm tra kết quả, lưu/tiếp tục khi gián đoạn.
4. Nối luồng xuất video cho từng ngôn ngữ; tránh xuất lại bản clean nhiều lần.
5. Thêm giao diện và hướng dẫn; đóng gói EXE thử trên ZIP mẫu.

## Tiêu chí hoàn thành

- Chọn một hoặc nhiều tập, một hoặc nhiều ngôn ngữ và chạy không cần thao tác lặp theo từng tập.
- Mỗi SRT đích có cùng số câu và mốc thời gian với SRT nguồn; câu tiếng Việt/Nhật/Hàn/Thái không lỗi mã chữ.
- Có thể sửa SRT rồi xuất lại video của đúng ngôn ngữ đó; file đầu ra cũ không bị ghi đè âm thầm.
- Mỗi tập có tối đa một bản clean; video burn đúng SRT ngôn ngữ đã chọn, có hình và tiếng.
- Lỗi mạng, hết hạn mức, phụ đề nguồn hỏng và hủy giữa chừng đều có thông báo; phần đã hoàn tất vẫn được giữ.

## Điểm cần chốt trước khi tích hợp API

Chọn dịch vụ dịch và ai cung cấp API key. Chất lượng dịch cho phim cần người rà soát, nhất là tên riêng, ngôi xưng và câu thiếu ngữ cảnh.
