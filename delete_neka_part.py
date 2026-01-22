import os
import json
import sys
import shutil
import re
import time
from config import DATA_DIR


def delete_part(kit_folder, part_y):
    """
    Deletes a part by removing its structured folders and re-indexing subsequent ones.
    part_y: The Y index (1-based index).
    Returns (success: bool, message: str)
    """
    # Helper to remove read-only files
    def handle_remove_readonly(func, path, exc):
        import stat
        excvalue = exc[1]
        if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == 5:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        else:
            raise

    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 1. Identify and remove folders for the target part
        structured_dir = os.path.join(DATA_DIR, kit_folder)


        if not os.path.exists(structured_dir):
            return False, f"Structured directory not found at {structured_dir}"

        print(f"DEBUG: Deleting folders for part Y index: {part_y}")

        # 2. Rename/Delete structured folders
        structured_dir = os.path.join(DATA_DIR, kit_folder)


        if os.path.exists(structured_dir):
            # Find the X of the part being deleted
            target_x = None
            target_pattern = re.compile(rf"^(\d+)-{part_y}$")
            
            all_entries = os.listdir(structured_dir)
            for entry in all_entries:
                match = target_pattern.match(entry)
                if match:
                    target_x = int(match.group(1))
                    folder_path = os.path.join(structured_dir, entry)
                    print(f"DEBUG: Removing folder: {entry} (target_x: {target_x})")
                    if os.path.isdir(folder_path):
                        # Use handle_remove_readonly to force delete read-only files
                        shutil.rmtree(folder_path, ignore_errors=False, onerror=handle_remove_readonly)
            
            if target_x is None:
                return False, f"Could not find folder with Y index {part_y}"

            # Re-index ALL remaining folders
            folder_info = []
            for entry in os.listdir(structured_dir):
                match = re.match(r"^(\d+)-(\d+)$", entry)
                if match:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    # Only add if it needs to change (X > target_x OR Y > target_y)
                    if x > target_x or y > part_y:
                        folder_info.append({'name': entry, 'x': x, 'y': y})

            # Sort by Y ascending to avoid collisions during sequential renaming
            # Although with both X and Y changing, we might need a safer move logic
            folder_info.sort(key=lambda x: (x['y'], x['x']))

            for info in folder_info:
                new_x = info['x'] - 1 if info['x'] > target_x else info['x']
                new_y = info['y'] - 1 if info['y'] > part_y else info['y']
                new_name = f"{new_x}-{new_y}"
                old_path = os.path.join(structured_dir, info['name'])
                new_path = os.path.join(structured_dir, new_name)
                
                if os.path.exists(old_path):
                    # Robust rename with retries for Windows
                    retry_count = 5
                    success = False
                    for i in range(retry_count):
                        try:
                            if os.path.exists(new_path):
                                if os.path.isdir(new_path):
                                    shutil.rmtree(new_path, ignore_errors=False, onerror=handle_remove_readonly)
                                else:
                                    os.remove(new_path)
                                time.sleep(0.3)
                            
                            print(f"DEBUG: Renaming {info['name']} -> {new_name}")
                            # Use shutil.move which is more resilient than os.rename
                            shutil.move(old_path, new_path)
                            success = True
                            break
                        except Exception as e:
                            print(f"DEBUG: Error renaming (Attempt {i+1}): {e}")
                            time.sleep(1.0)
            
            # 3. Synchronize separated_layers.json
            sep_layers_path = os.path.join(DATA_DIR, kit_folder, "separated_layers.json")

            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_layers = json.load(f)
                    
                    new_separated_layers = []
                    for folder_name in separated_layers:
                        match = re.match(r"^(\d+)-(\d+)$", folder_name)
                        if match:
                            x = int(match.group(1))
                            y = int(match.group(2))
                            
                            if y == part_y:
                                continue
                            
                            new_x = x - 1 if x > target_x else x
                            new_y = y - 1 if y > part_y else y
                            new_separated_layers.append(f"{new_x}-{new_y}")
                        else:
                            new_separated_layers.append(folder_name)
                    
                    with open(sep_layers_path, 'w', encoding='utf-8') as f:
                        json.dump(new_separated_layers, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"ERROR: Failed to update separated_layers.json: {e}")

        return True, f"Successfully deleted folders for part index {part_y} and updated both X and Y indices."

    except Exception as e:
        import traceback
        return False, f"Unexpected error: {str(e)}\n{traceback.format_exc()}"

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python delete_neka_part.py <kit_folder_name> <part_index_y>")
        sys.exit(1)
    else:
        kit_folder = sys.argv[1]
        try:
            part_y = int(sys.argv[2])
            success, message = delete_part(kit_folder, part_y)
            print(message)
            sys.exit(0 if success else 1)
        except ValueError:
            print("Error: part_index_y must be an integer.")
            sys.exit(1)
