import json
import os
import re
from config import DATA_DIR

def generate_kits_list():
    folder_json_path = 'folder.json'
    kits_json_path = 'kits.json'
    
    parent_folders = []
    
    # Lấy danh sách thư mục mẹ từ folder.json
    if os.path.exists(folder_json_path):
        try:
            with open(folder_json_path, 'r', encoding='utf-8') as f:
                parent_folders = json.load(f)
            print(f"Loaded parent folders from {folder_json_path}: {parent_folders}")
        except Exception as e:
            print(f"Error reading {folder_json_path}: {e}")
            parent_folders = []

    kits = []
    
    # Nếu có thư mục mẹ, quét bên trong từng thư mục
    if parent_folders:
        for parent in parent_folders:
            parent_path = os.path.join(DATA_DIR, parent)
            if os.path.exists(parent_path) and os.path.isdir(parent_path):
                print(f"Scanning parent folder: {parent}")
                for entry in sorted(os.listdir(parent_path)):
                    full_path = os.path.join(parent_path, entry)
                    if os.path.isdir(full_path):
                        if entry == "cache_blobs": continue
                        
                        match = re.search(r"(\d+)$", entry)
                        kit_id = match.group(1) if match else entry
                        kits.append({
                            "id": kit_id,
                            "name": entry,
                            "folder": f"{parent}/{entry}",
                            "parent": parent
                        })
            else:
                print(f"Warning: Parent folder {parent} not found in {DATA_DIR}")
    else:
        # Fallback: Quét trực tiếp thư mục downloads nếu không có folder.json
        if os.path.exists(DATA_DIR):
            print(f"No parent folders defined, scanning {DATA_DIR} directly.")
            for entry in sorted(os.listdir(DATA_DIR)):
                full_path = os.path.join(DATA_DIR, entry)
                if os.path.isdir(full_path):
                    if entry == "cache_blobs": continue
                    match = re.search(r"(\d+)$", entry)
                    kit_id = match.group(1) if match else entry
                    kits.append({
                        "id": kit_id,
                        "name": entry,
                        "folder": entry,
                        "parent": "None"
                    })

    # Write to kits.json
    output_data = {
        "success": True,
        "kits": kits,
        "parents": parent_folders
    }
    
    try:
        with open(kits_json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully generated {kits_json_path} with {len(kits)} kits.")
    except Exception as e:
        print(f"Error writing {kits_json_path}: {e}")

if __name__ == "__main__":
    generate_kits_list()
