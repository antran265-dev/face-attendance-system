# Kiến trúc hệ thống

## Tổng quan
Hệ thống chấm công nhận diện khuôn mặt gồm 6 module chính,
chạy hoàn toàn trên CPU không cần GPU.

## Các module

| Module | File | Chức năng |
|---|---|---|
| Cấu hình | config.py | Tập trung toàn bộ tham số |
| Nhận diện | recognizer.py | InsightFace + đa luồng |
| Chống giả mạo | liveness.py | Motion detection |
| Chấm công | attendance.py | CHECK_IN/OUT + âm thanh |
| Đăng ký | ui_register.py | Form + quét mặt |
| Giao diện | main.py | UI chính |

## Luồng dữ liệu
Camera → AI Worker → Cosine Similarity → Ghi log CSV