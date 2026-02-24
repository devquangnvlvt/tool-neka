import os

# Đường dẫn thư mục dữ liệu mạng (UNC Path)
# Lưu ý: Chắc chắn rằng máy tính chạy server có quyền truy cập vào đường dẫn này.
DATA_DIR = r"\\MR-NQC155\data\data-test"

# Đảm bảo thư mục tồn tại (nếu có quyền)
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
        print(f"Created data directory: {DATA_DIR}")
    except Exception as e:
        print(f"Warning: Could not create data directory {DATA_DIR}: {e}")
