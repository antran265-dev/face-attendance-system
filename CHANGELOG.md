# Nhật ký thay đổi (CHANGELOG)

Tất cả thay đổi quan trọng của dự án được ghi lại tại đây.

---

## [Unreleased]

---

## [0.2.0] — Tuần 2: Core modules hoàn chỉnh

### Thêm mới
- `src/liveness.py`: Motion liveness detector chống giả mạo
- `src/attendance.py`: Logic CHECK_IN/OUT, cooldown, âm thanh tiếng Việt
- `src/recognizer.py`: InsightFace buffalo_sc, dual-thread pipeline
- `src/ui_register.py`: Cửa sổ đăng ký nhân viên, dropdown chức vụ
- `src/main.py`: Giao diện chính, đồng hồ realtime, log hôm nay
- `docs/architecture.md`: Tài liệu kiến trúc hệ thống
- `tests/test_liveness.py`: Unit test cho module chống giả mạo

### Sửa lỗi
- BUG-018: Liveness có thể bị kẹt vĩnh viễn sau soft-reject — phát hiện qua unit test

### Kỹ thuật
- Cosine similarity thay SVM — thêm nhân viên không cần train lại
- subprocess riêng cho âm thanh — không block UI
- threading.Event cho camera reader — fix bug bật lần 2 không quét

---

## [0.1.0] — Tuần 1: Khởi tạo dự án

### Thêm mới
- Khởi tạo cấu trúc thư mục dự án
- `requirements.txt` với đầy đủ thư viện
- `src/config.py` tập trung toàn bộ cấu hình
- `README.md` mô tả dự án
- `.gitignore` bảo vệ dữ liệu nhạy cảm
