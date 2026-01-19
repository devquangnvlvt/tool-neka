import os
import json
import sys
import shutil
import re
import time

def delete_part(kit_folder, part_y):
    """
    Deletes a part by removing its structured folders and re-indexing subsequent ones.
    part_y: The Y index (1-based index).
    Returns (success: bool, message: str)
    """
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 1. Identify and remove folders for the target part
        structured_dir = os.path.join(base_path, "downloads", kit_folder, "items_structured")
        if not os.path.exists(structured_dir):
            return False, f"Structured directory not found at {structured_dir}"

        print(f"DEBUG: Deleting folders for part Y index: {part_y}")

        # 2. Rename/Delete structured folders
        structured_dir = os.path.join(base_path, "downloads", kit_folder, "items_structured")
        if os.path.exists(structured_dir):
            # Regex to match X-Y exactly
            # We want to match folders that end with -{part_y}
            # e.g. if part_y is 1, match "12-1", "0-1", but NOT "12-11"
            target_pattern = re.compile(rf"^\d+-{part_y}$")
            
            all_entries = os.listdir(structured_dir)
            
            # Delete target folders
            for entry in all_entries:
                if target_pattern.match(entry):
                    folder_path = os.path.join(structured_dir, entry)
                    if os.path.isdir(folder_path):
                        print(f"DEBUG: Removing folder: {entry}")
                        shutil.rmtree(folder_path)

            # Re-index folders with Y > part_y
            # We must sort by Y to avoid overwriting folders we haven't moved yet
            folder_info = []
            for entry in os.listdir(structured_dir):
                match = re.match(r"^(\d+)-(\d+)$", entry)
                if match:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    if y > part_y:
                        folder_info.append({'name': entry, 'x': x, 'y': y})

            # Sort by Y ascending to safely move down
            folder_info.sort(key=lambda x: x['y'])

            for info in folder_info:
                new_y = info['y'] - 1
                new_name = f"{info['x']}-{new_y}"
                old_path = os.path.join(structured_dir, info['name'])
                new_path = os.path.join(structured_dir, new_name)
                
                if os.path.exists(old_path):
                    # Robust rename with retries for Windows
                    retry_count = 5
                    success = False
                    for i in range(retry_count):
                        try:
                            if os.path.exists(new_path):
                                print(f"DEBUG: Removing existing target {new_path} (Attempt {i+1})")
                                if os.path.isdir(new_path):
                                    shutil.rmtree(new_path)
                                else:
                                    os.remove(new_path)
                                time.sleep(0.3) # Small delay for Windows to release handles
                            
                            print(f"DEBUG: Renaming {info['name']} -> {new_name} (Attempt {i+1})")
                            os.rename(old_path, new_path)
                            success = True
                            break
                        except Exception as e:
                            print(f"DEBUG: Error renaming (Attempt {i+1}): {e}")
                            time.sleep(1.0) # Longer delay between retries
                    
                    if not success:
                        print(f"CRITICAL: Failed to rename {old_path} after {retry_count} attempts.")
            
            # 3. Synchronize separated_layers.json if it exists
            sep_layers_path = os.path.join(base_path, "downloads", kit_folder, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                print(f"DEBUG: Updating {sep_layers_path}")
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_layers = json.load(f)
                    
                    new_separated_layers = []
                    for folder_name in separated_layers:
                        # Parse X-Y
                        match = re.match(r"^(\d+)-(\d+)$", folder_name)
                        if match:
                            x = int(match.group(1))
                            y = int(match.group(2))
                            
                            if y == part_y:
                                # This part is being deleted, skip it
                                continue
                            elif y > part_y:
                                # Re-index down
                                new_separated_layers.append(f"{x}-{y-1}")
                            else:
                                # Keep as is
                                new_separated_layers.append(folder_name)
                        else:
                            # Not matching X-Y pattern, just keep it (safety)
                            new_separated_layers.append(folder_name)
                    
                    with open(sep_layers_path, 'w', encoding='utf-8') as f:
                        json.dump(new_separated_layers, f, ensure_ascii=False, indent=2)
                    print(f"DEBUG: Updated separated_layers.json with {len(new_separated_layers)} entries.")
                except Exception as e:
                    print(f"ERROR: Failed to update separated_layers.json: {e}")

        return True, f"Successfully deleted folders for part index {part_y} and updated separated_layers.json."

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
