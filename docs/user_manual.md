# Hướng dẫn sử dụng

## 1. Cài đặt

### Yêu cầu
- Python 3.9 trở lên
- Webcam hoặc camera USB
- Windows 10/11 hoặc Ubuntu 20.04+

### Các bước cài đặt

```bash
# Clone repo
git clone https://github.com/antran265-dev/ace-attendance-system.git
cd ace-attendance-system

# Tạo môi trường ảo
python -m venv venv
venv\Scripts\activate

# Cài thư viện
pip install -r requirements.txt
```

### Cài âm thanh tiếng Việt (tuỳ chọn)
```bash
pip install edge-tts
```
Nếu không cài, hệ thống vẫn chạy được nhưng không có thông báo bằng giọng nói.

## 2. Chạy ứng dụng

```bash
python src/main.py
```

Lần đầu chạy sẽ mất 10-30 giây để tải model AI.

## 3. Đăng ký nhân viên mới

1. Bấm nút **➕ ĐĂNG KÝ NHÂN VIÊN**
2. Nhập họ tên
3. Chọn chức vụ (Công nhân, Nhân viên văn phòng, Quản lý...)
4. Nhập phòng ban (không bắt buộc)
5. Bấm **▶ BẮT ĐẦU ĐĂNG KÝ**
6. Nhìn vào camera, xoay đầu chậm theo hướng dẫn trên màn hình
7. Hệ thống tự lưu khi đủ 30 mẫu

## 4. Chấm công

1. Bấm **▶ BẬT CAMERA**
2. Nhân viên đứng trước camera, nhúc nhích đầu nhẹ (chống giả mạo)
3. Hệ thống tự nhận diện và ghi nhận CHECK_IN / CHECK_OUT
4. Có âm thanh xác nhận (nếu đã cài edge-tts)

## 5. Quản lý nhân viên

- Bấm **👥 DANH SÁCH NHÂN VIÊN** để xem/lọc theo chức vụ
- Bấm **🗑 XÓA NHÂN VIÊN ĐÃ CHỌN** để xóa (cần xác nhận lại tên)

## 6. Xem log chấm công

- Bấm **📋 XEM LOG CHẤM CÔNG** để mở file CSV
- Panel "Hoạt động hôm nay" hiển thị realtime các lượt chấm công

## 7. Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Không tìm thấy Camera | Camera đang được app khác dùng | Đóng các app dùng camera khác |
| SyntaxError dict \| None | Python < 3.10 | Đảm bảo `from __future__ import annotations` ở đầu file |
| Không có âm thanh | Chưa cài edge-tts | `pip install edge-tts` |
| Nhận diện sai/chậm | Ánh sáng yếu | Tăng ánh sáng, điều chỉnh `SIMILARITY_THRESHOLD` trong config.py |
