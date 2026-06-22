# Kiến trúc hệ thống — Phiên bản 2.0 (Client-Server)

## 1. Tổng quan

Hệ thống chuyển từ kiến trúc đứng độc lập (standalone) sang
**Client-Server tập trung**, giải quyết bài toán mở rộng nhiều camera.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Camera Client 1 │     │  Camera Client 2 │     │  Camera Client N │
│  (Cổng chính)     │     │  (Cổng phụ)       │     │  (Khối văn phòng)│
│                  │     │                  │     │                  │
│  client_main.py  │     │  client_main.py  │     │  client_main.py  │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │   HTTP POST /api/checkin  (gửi embedding 512-dim)
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                   │
                          ┌────────▼─────────┐
                          │   Mạng LAN/WiFi    │
                          └────────┬─────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     SERVER TRUNG TÂM          │
                    │       server.py (Flask)        │
                    │                                │
                    │  • InsightFace load 1 lần      │
                    │  • Cosine similarity matching   │
                    │  • SQLAlchemy ORM               │
                    └──────────────┬──────────────┘
                                   │
                          ┌────────▼─────────┐
                          │  database.db        │
                          │  (SQLite)            │
                          └──────────────────┘
```

## 2. Lý do thiết kế Client-Server

### Vấn đề của kiến trúc cũ (standalone)
Mỗi camera chạy độc lập 1 instance ứng dụng đầy đủ:
- Mỗi máy phải load InsightFace riêng (~500MB RAM/máy)
- 4 camera = 4 database riêng biệt → dữ liệu không đồng bộ
- Thêm nhân viên mới phải đăng ký lại trên TỪNG máy

### Giải pháp Client-Server
| | Standalone (cũ) | Client-Server (mới) |
|---|---|---|
| Model AI load | Mỗi máy 1 lần | Server 1 lần duy nhất |
| RAM cho 4 camera | ~2GB (4×500MB) | ~500MB (chỉ trên server) |
| Database | Tách rời từng máy | Tập trung 1 nơi |
| Đăng ký nhân viên | Phải làm trên từng máy | Làm 1 lần, mọi camera đều thấy |
| Báo cáo tổng hợp | Phải gộp thủ công | Tự động vì cùng 1 DB |

## 3. Phân chia trách nhiệm

### Server (server.py)
- Chạy trên 1 máy tính trung tâm (có thể là máy chủ công ty)
- Load model InsightFace **một lần duy nhất** khi khởi động
- Nhận embedding (vector 512 chiều) từ client qua HTTP
- Thực hiện cosine similarity để nhận diện
- Ghi log vào SQLite Database
- KHÔNG có giao diện web (không HTML/CSS) — chỉ trả về JSON

### Client (client_main.py)
- Chạy trên từng máy đặt camera (cổng ra vào, từng xưởng...)
- Đọc camera, trích xuất embedding bằng InsightFace **local** (cần có model để detect mặt)
- Gửi embedding qua HTTP POST, KHÔNG gửi ảnh gốc (bảo mật + tiết kiệm băng thông)
- Nhận kết quả JSON từ server, hiển thị lên màn hình

> **Lưu ý quan trọng:** Client vẫn cần InsightFace để TRÍCH XUẤT embedding
> (bước detect mặt + tạo vector), nhưng KHÔNG cần Database và KHÔNG thực hiện
> bước SO SÁNH (matching) — đó là việc của server.

## 4. API Endpoints

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/health` | Kiểm tra server còn sống không |
| POST | `/api/register` | Đăng ký nhân viên mới (name, role, dept, embedding) |
| POST | `/api/checkin` | Gửi embedding để chấm công |
| GET | `/api/employees` | Lấy danh sách toàn bộ nhân viên |
| DELETE | `/api/employees/<name>` | Xóa nhân viên |
| GET | `/api/logs/today` | Lấy log chấm công hôm nay |

## 5. Luồng xử lý 1 lượt chấm công

```
1. Nhân viên đứng trước Camera Client
2. Client: InsightFace detect mặt → kiểm tra liveness (chống giả mạo)
3. Client: liveness PASS → trích xuất embedding (vector 512 số)
4. Client: gửi POST /api/checkin {embedding, camera_id} lên Server
5. Server: nhận embedding → so sánh cosine similarity với toàn bộ DB
6. Server: tìm thấy người khớp → kiểm tra cooldown → ghi log vào DB
7. Server: trả về JSON {name, confidence, event: CHECK_IN/CHECK_OUT}
8. Client: nhận kết quả → hiển thị tên + phát âm thanh
```

Thời gian toàn bộ luồng: **dưới 200ms** trong mạng LAN (embedding chỉ 2KB dữ liệu).

## 6. Bảo mật

- Dữ liệu khuôn mặt KHÔNG bao giờ truyền qua mạng dưới dạng ảnh — chỉ truyền vector số đã trích xuất, không thể khôi phục lại thành ảnh khuôn mặt gốc.
- Server và client nên cùng trong mạng LAN nội bộ công ty (không public ra internet) trong phiên bản hiện tại.

## 7. Hướng phát triển tiếp theo

- Thêm xác thực API key cho mỗi camera client (hiện tại chưa có)
- Mã hóa HTTPS thay vì HTTP thuần (cần với mạng WiFi)
- Load balancing nếu số lượng camera tăng lên hàng chục
