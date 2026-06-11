import os
import json
from pathlib import Path
from config import DATA_DIR

def check_missing_thumbnails():
    """
    Kiểm tra các folder nào trong kits đang thiếu thumbnail.
    Thumbnail được coi là các file có pattern thumb_*.png
    """
    
    missing_thumbnails = []
    total_folders = 0
    
    # Scan qua tất cả kit folders trong DATA_DIR
    if not os.path.exists(DATA_DIR):
        print(f"❌ DATA_DIR không tồn tại: {DATA_DIR}")
        return
    
    kit_folders = [f for f in os.listdir(DATA_DIR) 
                   if os.path.isdir(os.path.join(DATA_DIR, f)) 
                   and not f.startswith('.')]
    
    print(f"🔍 Đang kiểm tra {len(kit_folders)} kit folders...")
    print("=" * 80)
    
    for kit_name in sorted(kit_folders):
        kit_path = os.path.join(DATA_DIR, kit_name)
        
        # Bỏ qua các folder không phải kit (như thung_rac, cache_blobs, ly)
        if kit_name in ['thung_rac', 'cache_blobs', 'ly', 'thuong', 'tram']:
            continue
        
        # Lấy danh sách các subfolder (phần folders)
        subfolders = []
        try:
            for item in os.listdir(kit_path):
                item_path = os.path.join(kit_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    # Chỉ lấy folder có dạng số-số (ví dụ: 1-9, 10-5)
                    if '-' in item:
                        subfolders.append(item)
        except PermissionError:
            continue
        
        if not subfolders:
            continue
        
        kit_missing = []
        
        for subfolder in sorted(subfolders, key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1]))):
            subfolder_path = os.path.join(kit_path, subfolder)
            total_folders += 1
            
            # Kiểm tra xem có file thumb_*.png hay không
            has_thumbnail = False
            try:
                files = os.listdir(subfolder_path)
                for f in files:
                    if f.startswith('thumb_') and f.endswith('.png'):
                        has_thumbnail = True
                        break
            except PermissionError:
                continue
            
            if not has_thumbnail:
                kit_missing.append(subfolder)
                missing_thumbnails.append({
                    'kit': kit_name,
                    'folder': subfolder,
                    'path': subfolder_path
                })
        
        if kit_missing:
            print(f"⚠️  {kit_name}")
            print(f"   📁 Thiếu thumbnail ({len(kit_missing)}/{len(subfolders)} subfolder):")
            for folder in kit_missing[:10]:  # Hiển thị tối đa 10 folder
                print(f"      - {folder}")
            if len(kit_missing) > 10:
                print(f"      ... và {len(kit_missing) - 10} folder khác")
            print()
    
    # Tóm tắt
    print("=" * 80)
    print(f"📊 TỔNG KẾT:")
    print(f"   • Tổng subfolders kiểm tra: {total_folders}")
    print(f"   • Thiếu thumbnail: {len(missing_thumbnails)} ({100*len(missing_thumbnails)/total_folders if total_folders > 0 else 0:.1f}%)")
    
    if missing_thumbnails:
        print(f"\n💾 Chi tiết đầy đủ:")
        for item in missing_thumbnails:
            print(f"   {item['kit']} / {item['folder']}")
        
        # Lưu report vào file
        report_path = os.path.join(DATA_DIR, "missing_thumbnails_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total_missing': len(missing_thumbnails),
                'total_scanned': total_folders,
                'missing_items': missing_thumbnails
            }, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Report đã lưu: {report_path}")
    else:
        print("\n✅ Tất cả các folder đều có thumbnail!")

if __name__ == "__main__":
    check_missing_thumbnails()
