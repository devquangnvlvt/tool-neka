python download_neka_kit.py 14326
// nạp data
python generate_kits_list.py

Công cụ này hiện đang đọc và giải mã dữ liệu từ website Neka.cc theo các bước sau:

1. Thu thập dữ liệu thô (Fetching)
   Công cụ sử dụng Selenium để mở một trình duyệt ẩn danh (Chrome), truy cập vào đường dẫn bộ kit (ví dụ: https://www.neka.cc/composer/10980). Sau đó, nó thực thi mã JavaScript để lấy biến window.**NEXT_DATA**.

Biến này chứa toàn bộ thông tin của trang web dưới dạng JSON, bao gồm cả dữ liệu bộ kit nhưng ở trạng thái đã bóp nhỏ/mã hóa để giảm dung lượng tải.

2. Cấu trúc nén (Compression Structure)
   Dữ liệu bộ kit nằm trong props.pageProps.kitOnSale. Cấu trúc này gồm 2 phần chính:

Vocab (Từ điển): Một danh sách rất lớn các chuỗi ký tự, số, hoặc các đoạn mã thô.
Root Index: Một mã Base62 trỏ đến điểm bắt đầu của dữ liệu trong từ điển. 3. Giải mã Base62 (Decoding)
Neka sử dụng hệ cơ số 62 (0-9, A-Z, a-z) để mã hóa các con số (chỉ số index). Hàm
decode_b62_full
trong script chịu trách nhiệm chuyển các chuỗi như 1Rk, aB2 thành các số nguyên để truy xuất vào danh sách vocab.

4. Giải nén đệ quy (Recursive Decompression)
   Nội dung thực sự được giải mã thông qua hàm
   decompress
   . Neka sử dụng các tiền tố ký tự để đánh dấu kiểu dữ liệu:

n| (Number): Dữ liệu là một con số.
s| (String): Dữ liệu là một chuỗi văn bản.
a| (Array): Dữ liệu là một danh sách. Các phần tử bên trong sẽ tiếp tục được giải mã đệ quy.
o| (Object): Dữ liệu là một đối tượng (key-value). Nó chứa một chỉ số trỏ đến danh sách các "keys" và sau đó là các "values" tương ứng.
Tóm tắt quy trình:
Mở trình duyệt -> Lấy **NEXT_DATA**.
Tìm đến phần kitOnSale.
Dùng hàm
decompress
để đi xuyên qua các lớp mã hóa dựa trên các tiền tố n|, s|, a|, o|.
Kết quả cuối cùng là một file JSON (metadata.json) chứa đầy đủ thông tin về các bộ phận (parts), màu sắc (tonings), và các liên kết ảnh (blobs).
