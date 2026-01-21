# Kế hoạch Kiểm tra Bảo mật - Tool Neka

## Tổng quan

Kế hoạch này nhằm thực hiện một cuộc rà soát bảo mật toàn diện cho ứng dụng Tool Neka, tập trung vào các rủi ro liên quan đến xử lý file, bảo mật server và an toàn API.

## Loại dự án: BACKEND / WEB

## Tiêu chí thành công

- [ ] Hoàn thành rà soát mã nguồn cho tất cả các endpoint API.
- [ ] Chạy thành công các script quét lỗ hổng tự động.
- [ ] Xác định và đề xuất giải pháp cho ít nhất các lỗ hổng nghiêm trọng (Critical/High).
- [ ] Đảm bảo không còn tồn tại các lỗi Path Traversal cơ bản trong xử lý file.

## Tech Stack

- **Ngôn ngữ:** Python (Backend), HTML/JS (Frontend).
- **Thư viện chính:** Pillow (xử lý ảnh), http.server (HTTP server).
- **Công cụ kiểm tra:** `security_scan.py`, `penetration_tester` script.

## Cấu trúc file rà soát

- `docs/security_report.md`: Báo cáo chi tiết các lỗ hổng.
- `docs/remediation_steps.md`: Các bước khắc phục đề xuất.

## Phân công Task

### Phase 1: Phân tích & Quét lỗ hổng (Analysis & Scanning)

- **Task ID:** SEC-01
- **Tên:** Rà soát mã nguồn tĩnh (Static Analysis)
- **Agent:** `security-auditor`
- **Độ ưu tiên:** Cao
- **Input:** Toàn bộ mã nguồn `.py` và `.html`
- **Output:** Danh sách các điểm nghi vấn bảo mật.
- **Verify:** Chạy script `security_scan.py` và kiểm tra kết quả.

### Phase 2: Kiểm thử xâm nhập (Penetration Testing)

- **Task ID:** SEC-02
- **Tên:** Kiểm tra các lỗi Path Traversal & Injection
- **Agent:** `penetration-tester`
- **Độ ưu tiên:** Cao
- **Dependencies:** SEC-01
- **Input:** Các API endpoint chính (`/api/merge_layers`, `/api/rename_file`, v.v.)
- **Output:** Báo cáo các điểm có thể khai thác.
- **Verify:** Thử nghiệm gửi các payload độc hại (ví dụ: `../`, `; rm -rf`) và kiểm tra phản hồi của server.

### Phase 3: Củng cố & Khắc phục (Hardening & Remediation)

- **Task ID:** SEC-03
- **Tên:** Áp dụng các biện pháp bảo mật bổ sung
- **Agent:** `backend-specialist`
- **Độ ưu tiên:** Trung bình
- **Dependencies:** SEC-02
- **Input:** Kết quả từ Phase 1 & 2.
- **Output:** Các bản vá lỗi và cấu hình server an toàn hơn.
- **Verify:** Chạy lại toàn bộ bộ test bảo mật.

## Phase X: Xác minh cuối cùng

- [ ] Chạy `python .agent/skills/vulnerability-scanner/scripts/security_scan.py .`
- [ ] Chạy `python .agent/scripts/verify_all.py .`
- [ ] Kiểm tra thủ công các lỗ hổng đã phát hiện.
