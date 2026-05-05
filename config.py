import os

# Đường dẫn thư mục dữ liệu mạng (UNC Path)
# Lưu ý: Chắc chắn rằng máy tính chạy server có quyền truy cập vào đường dẫn này.
DATA_DIR  = r"D:\web\laragon\www\tool-neka\downloads"
TRASH_DIR = r"D:\web\laragon\www\tool-neka\downloads\thung_rac"

# Đảm bảo thư mục tồn tại (nếu có quyền)
for folder in [DATA_DIR, TRASH_DIR]:
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
            print(f"Created directory: {folder}")
        except Exception as e:
            print(f"Warning: Could not create directory {folder}: {e}")
