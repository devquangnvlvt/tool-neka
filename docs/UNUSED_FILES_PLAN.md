# Kế hoạch Điều phối: Rà soát Tệp tin Không sử dụng

**Mục tiêu**: Xác định và liệt kê các tệp tin không còn được tham chiếu hoặc không cần thiết cho hoạt động của dự án để tối ưu hóa không gian lưu trữ và duy trì sự sạch chiến (cleanliness) của mã nguồn.

---

## 🎭 Ma trận Lựa chọn Agent

| Agent                | Vai trò                    | Trách nhiệm                                                                                                      |
| -------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `project-planner`    | **Điều phối viên chính**   | Xác định sơ đồ phụ thuộc, ánh xạ các điểm đầu vào và tổng hợp kết quả cuối cùng.                                 |
| `backend-specialist` | **Kiểm toán viên Tài sản** | Quét thư mục `downloads/`, xác minh tính toàn vẹn của kit so với metadata và ánh xạ việc sử dụng tài sản nội bộ. |
| `clean-code`         | **Người dọn dẹp Mã nguồn** | Kiểm tra các script ở thư mục gốc, các đoạn mã (snippets) và các tệp tạm thời (PoC, Zips).                       |

---

## 📋 Phạm vi Rà soát

### 1. Tài sản Kit (`downloads/`)

- Các thư mục "mồ côi" không liên kết với bất kỳ ID Kit nào đã biết.
- Thư mục `cache_blobs` và các tệp tải xuống tạm thời.
- Cấu trúc thư mục không hoàn chỉnh (ví dụ: thiếu `items_structured`).

### 2. Các Script & Snippets của Dự án

- Các mẩu mã Python (`*_snippet.py`) có thể đã được tích hợp vào `app_server.py`.
- Các script hỗ trợ không được sử dụng trong quy trình làm việc chính.

### 3. Các Tệp Tạm thời & Sản phẩm Build

- Các tệp `.zip` lớn trong thư mục gốc.
- Các script PoC cũ trong thư mục `docs/` không còn cần thiết để xác minh.

---

## 🔄 Phương pháp thực hiện

1.  **Ánh xạ Điểm đầu vào**: Xác định `app_server.py` và `character-creator.html` là các điểm đầu vào chính.
2.  **Phân tích Phụ thuộc**:
    - Truy vết các lời gọi API trong HTML đến các điểm cuối của server.
    - Truy vết các câu lệnh `import` trong các script Python.
    - Truy vết các mẫu truy cập tệp (ví dụ: các thư mục mà `app_server.py` tìm kiếm).
3.  **Xác định Tệp mồ côi**: Đối chiếu sơ đồ phụ thuộc "đang hoạt động" với hệ thống tệp vật lý.
4.  **Báo cáo**: Tạo danh sách các tệp "Không sử dụng" theo danh mục kèm theo các hành động đề xuất (Giữ lại/Lưu trữ/Xóa).

---

## 🛡️ Rào chắn An toàn

- **Sẽ không có việc xóa tệp** nào xảy ra trong quá trình rà soát.
- Kết quả sẽ được trình bày dưới dạng danh sách đề xuất để người dùng phê duyệt.
- Các tài sản lớn sẽ được đề xuất chuyển vào thư mục `archive/` thay vì xóa ngay lập tức.
