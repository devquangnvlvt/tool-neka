import http.server
import socketserver
import json
import os
import shutil
import zipfile
import subprocess
import re
from urllib.parse import urlparse, parse_qs

PORT = 8000

class KitHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/zip_kit':
            query = parse_qs(parsed_path.query)
            kit_folder = query.get('kit', [None])[0]
            if kit_folder:
                self.handle_zip_kit({"kit": kit_folder})
            else:
                self.send_api_response(False, "Missing kit parameter")
            return
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))

        if self.path == '/api/delete_part':
            self.handle_delete_part(data)
        elif self.path == '/api/zip_kit':
            self.handle_zip_kit(data)
        elif self.path == '/api/merge_layers':
            self.handle_merge_layers(data)
        elif self.path == '/api/get_kit_structure':
            self.handle_get_kit_structure(data)
        elif self.path == '/api/get_kits_list':
            self.handle_get_kits_list(data)
        elif self.path == '/api/list_part_images':
            self.handle_list_part_images(data)
        elif self.path == '/api/rename_folder':
            self.handle_rename_folder(data)
        elif self.path == '/api/get_item_layers':
            self.handle_get_item_layers(data)
        else:
            self.send_error(404, "Unknown API endpoint")

    def handle_get_kits_list(self, data):
        try:
            base_dir = "downloads"
            kits = []
            if os.path.exists(base_dir):
                for entry in os.listdir(base_dir):
                    full_path = os.path.join(base_dir, entry)
                    if os.path.isdir(full_path):
                        if entry == "cache_blobs" or not os.path.exists(os.path.join(full_path, "items_structured")):
                            continue
                        match = re.search(r"(\d+)$", entry)
                        kit_id = match.group(1) if match else entry
                        kits.append({
                            "id": kit_id,
                            "name": entry,
                            "folder": entry
                        })
            kits.sort(key=lambda x: x['name'])
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({"success": True, "kits": kits})
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")


    def handle_get_kit_structure(self, data):
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            structured_dir = os.path.join(kit_path, "items_structured")
            if not os.path.exists(structured_dir):
                self.send_api_response(False, f"Directory not found: {structured_dir}")
                return
            separated_folders = []
            sep_layers_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_folders = json.load(f)
                except: pass
            parts = []
            for entry in os.listdir(structured_dir):
                entry_path = os.path.join(structured_dir, entry)
                if not os.path.isdir(entry_path): continue
                
                # No alias resolution needed
                # real_name, is_aliased = self.resolve_real_folder_name(kit_path, entry)
                
                match = re.match(r"^(\d+)-(\d+)$", entry)
                
                # If not X-Y even after alias resolution, put it at end
                if not match:
                    x, y = 9999, 9999
                else:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    
                item_indices = []
                thumb_pattern = re.compile(r"^thumb_(\d+)\.png$")
                for f in os.listdir(entry_path):
                    m = thumb_pattern.match(f)
                    if m: item_indices.append(int(m.group(1)))
                num_items = max(item_indices) if item_indices else 0
                colors = []
                for sub in os.listdir(entry_path):
                    if os.path.isdir(os.path.join(entry_path, sub)):
                        colors.append(sub)
                
                # Count layers per item from metadata
                item_layer_counts = {}
                try:
                    match_y = re.match(r"^\d+-(\d+)$", entry)
                    if match_y:
                        part_idx = int(match_y.group(1)) - 1
                        meta_path = os.path.join(kit_path, "metadata.json")
                        if os.path.exists(meta_path):
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                                parts_data = meta.get('data', {}).get('parts', [])
                                if 0 <= part_idx < len(parts_data):
                                    items = parts_data[part_idx].get('items', [])
                                    for item_idx, item_layers in enumerate(items):
                                        if not isinstance(item_layers, list): item_layers = [item_layers]
                                        layer_count = 0
                                        for layer in item_layers:
                                            if isinstance(layer, dict):
                                                if layer.get('blob'): layer_count += 1
                                                addon_textures = layer.get('addonTextures', [])
                                                layer_count += len(addon_textures)
                                        item_layer_counts[item_idx + 1] = layer_count
                except Exception as e:
                    print(f"Error reading layer counts for {entry}: {e}")
                
                parts.append({
                    "x": x, "y": y, "folder": entry,
                    "items_count": num_items, "colors": colors,
                    "is_separated": entry in separated_folders,
                    "item_layer_counts": item_layer_counts
                })

            # Check for duplicate X values
            x_counts = {}
            for p in parts:
                x = p['x']
                if x != 9999: # Ignore invalid/non-standard folders
                    if x not in x_counts: x_counts[x] = []
                    x_counts[x].append(p['folder'])
            
            duplicate_warnings = []
            for x, folders in x_counts.items():
                if len(folders) > 1:
                    duplicate_warnings.append(f"X={x}: {', '.join(folders)}")

            parts.sort(key=lambda p: p['y'])
            
            # --- Check X-Y Continuity ---
            found_x = set()
            found_y = set()
            for p in parts:
                if p['x'] != 9999: found_x.add(p['x'])
                if p['y'] != 9999: found_y.add(p['y'])
            
            missing_x = []
            if found_x:
                max_x = max(found_x)
                for i in range(1, max_x + 1):
                    if i not in found_x:
                        missing_x.append(i)
            
            missing_y = []
            if found_y:
                max_y = max(found_y)
                for i in range(1, max_y + 1):
                    if i not in found_y:
                        missing_y.append(i)
            # ---------------------------

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "success": True, "parts": parts,
                "has_separated_layers": len(separated_folders) > 0,
                "separated_folders": separated_folders,
                "duplicates": duplicate_warnings,
                "missing_x": missing_x,
                "missing_y": missing_y
            })
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")


    def handle_rename_folder(self, data):
        kit_folder = data.get('kit')
        old_name = data.get('old_name')
        new_name = data.get('new_name')

        if not kit_folder or not old_name or not new_name:
            self.send_api_response(False, "Missing parameters")
            return

        # Enforce X-Y format
        if not re.match(r"^\d+-\d+$", new_name):
            self.send_api_response(False, "Tên mới phải đúng định dạng số X-Y (VD: 100-51) để sắp xếp layer.")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            
            struct_base = os.path.join(kit_path, "items_structured")
            merged_base = os.path.join(kit_path, "items_merged")
            
            old_path = os.path.join(struct_base, old_name)
            new_path = os.path.join(struct_base, new_name)

            if not os.path.exists(old_path):
                self.send_api_response(False, "Folder not found")
                return
            if os.path.exists(new_path):
                self.send_api_response(False, "New folder name already exists")
                return

            # Check for duplicate X (Layer Order conflict)
            # Extract new X
            match = re.match(r"^(\d+)-", new_name)
            if match:
                new_x = int(match.group(1))
                # Scan directory for any other folder starting with "{new_x}-"
                for entry in os.listdir(struct_base):
                    if entry == old_name: continue # Ignore self
                    if not os.path.isdir(os.path.join(struct_base, entry)): continue
                    
                    # Check X component
                    m = re.match(r"^(\d+)-", entry)
                    if m:
                        existing_x = int(m.group(1))
                        if existing_x == new_x:
                            self.send_api_response(False, f"Lỗi: Đã tồn tại thư mục '{entry}' có cùng thứ tự X={new_x}. Vui lòng chọn X khác.")
                            return

            # Rename physical directory
            shutil.move(old_path, new_path)
            
            # Rename in merged folder if exists
            old_merged = os.path.join(merged_base, old_name)
            new_merged = os.path.join(merged_base, new_name)
            if os.path.exists(old_merged):
                try: shutil.move(old_merged, new_merged)
                except: pass

            # Update separated_layers.json
            sep_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_path):
                with open(sep_path, 'r', encoding='utf-8') as f:
                    sep_list = json.load(f)
                if old_name in sep_list:
                    sep_list[sep_list.index(old_name)] = new_name
                    with open(sep_path, 'w', encoding='utf-8') as f:
                        json.dump(sep_list, f, ensure_ascii=False, indent=4)

            # We NO LONGER need folder_aliases.json because the user wants X-Y format ONLY.
            # The physical rename handles the sorting automatically since get_kit_structure reads X from the folder name.
            
            # Clean up old alias if exists
            alias_path = os.path.join(kit_path, "folder_aliases.json")
            if os.path.exists(alias_path):
                try:
                    with open(alias_path, 'r', encoding='utf-8') as f:
                        aliases = json.load(f)
                    if old_name in aliases:
                        del aliases[old_name]
                        with open(alias_path, 'w', encoding='utf-8') as f:
                            json.dump(aliases, f, ensure_ascii=False, indent=4)
                except: pass

            self.send_api_response(True, "Renamed successfully")

        except Exception as e:
            self.send_api_response(False, f"Error: {str(e)}")

    def handle_get_item_layers(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        item_number = data.get('item_number')

        if not kit_folder or not folder_name or item_number is None:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            
            # Get part index from folder name
            match = re.search(r"-(\d+)$", folder_name)
            if not match:
                self.send_api_response(False, "Invalid folder name format")
                return
            
            part_idx = int(match.group(1)) - 1
            meta_path = os.path.join(kit_path, "metadata.json")
            
            if not os.path.exists(meta_path):
                self.send_api_response(False, "Metadata not found")
                return
            
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                parts_data = meta.get('data', {}).get('parts', [])
                
                if part_idx < 0 or part_idx >= len(parts_data):
                    self.send_api_response(False, "Part index out of range")
                    return
                
                items = parts_data[part_idx].get('items', [])
                item_idx = item_number - 1
                
                if item_idx < 0 or item_idx >= len(items):
                    self.send_api_response(False, "Item index out of range")
                    return
                
                item_layers = items[item_idx]
                if not isinstance(item_layers, list):
                    item_layers = [item_layers]
                
                # Extract layer details
                layers_info = []
                for layer_idx, layer in enumerate(item_layers):
                    if not isinstance(layer, dict):
                        continue
                    
                    # Main blob
                    if layer.get('blob'):
                        crop = layer.get('crop', {})
                        layers_info.append({
                            'type': 'main',
                            'index': layer_idx,
                            'blob': layer.get('blob'),
                            'x': crop.get('x', 0),
                            'y': crop.get('y', 0),
                            'w': crop.get('w', 0),
                            'h': crop.get('h', 0)
                        })
                    
                    # Addon textures
                    addon_textures = layer.get('addonTextures', [])
                    for addon_idx, addon in enumerate(addon_textures):
                        if isinstance(addon, dict) and addon.get('blob'):
                            addon_crop = addon.get('crop', {})
                            layers_info.append({
                                'type': 'addon',
                                'index': f"{layer_idx}-{addon_idx}",
                                'blob': addon.get('blob'),
                                'layer_id': addon.get('layer', ''),
                                'x': addon_crop.get('x', 0),
                                'y': addon_crop.get('y', 0),
                                'w': addon_crop.get('w', 0),
                                'h': addon_crop.get('h', 0)
                            })
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = json.dumps({
                    "success": True,
                    "layers": layers_info,
                    "total_count": len(layers_info)
                })
                self.wfile.write(response.encode('utf-8'))
                
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")

    def handle_delete_part(self, data):
        kit_folder = data.get('kit')
        y_index = data.get('y')
        if not kit_folder or y_index is None:
            self.send_api_response(False, "Missing parameters")
            return
        try:
            from delete_neka_part import delete_part
            success, message = delete_part(kit_folder, int(y_index))
            self.send_api_response(success, message)
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")


    def handle_merge_layers(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        selected_files = data.get('selected_files')
        dest_name = data.get('destination_name', 'merged_result')
        bulk_apply = data.get('bulk_apply', False)
        color = data.get('color')

        if not kit_folder or not folder_name:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            from PIL import Image
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_dir = os.path.join(base_path, "downloads", kit_folder)
            structured_dir = os.path.join(kit_dir, "items_structured", folder_name)
            merged_base_dir = os.path.join(kit_dir, "items_merged", folder_name)
            
            if not os.path.exists(structured_dir):
                self.send_api_response(False, f"Directory not found: {folder_name}")
                return

            # Load metadata for offsets
            offsets = {} 
            try:
                # Resolve alias first to find the metadata index key
                match = re.search(r"-(\d+)$", folder_name)
                if match:
                    part_idx = int(match.group(1)) - 1
                    meta_path = os.path.join(kit_dir, "metadata.json")
                    if os.path.exists(meta_path):
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            parts = meta.get('data', {}).get('parts', [])
                            if 0 <= part_idx < len(parts):
                                items = parts[part_idx].get('items', [])
                                for idx, item_layers in enumerate(items):
                                   if not isinstance(item_layers, list): item_layers = [item_layers]
                                   if not item_layers: continue
                                   first_layer = item_layers[0]
                                   crop = first_layer.get('crop', {})
                                   offsets[f"{idx + 1}.png"] = {"x": crop.get('x', 0), "y": crop.get('y', 0)}
            except Exception as e:
                print(f"[Merge] Metadata error: {e}")

            def perform_merge(src, target_fn, files_to_stack, is_default_color=False):
                if not os.path.exists(src): 
                    print(f"[Merge] Directory not found: {src}")
                    return False
                
                print(f"[Merge] Starting in: {src}")
                print(f"[Merge] Stacking files: {files_to_stack} -> {target_fn}.png")
                
                ow, oh = 1436, 1902
                # Try to detect canvas size from full metadata if possible, or fallback to standard Neka
                # For now, keep 1436x1902 as default/target, but maybe expand if source images are bigger?
                # Actually, check the FIRST offset's expected parent size?
                # Safer: Use max dimension found + offset?
                # Simplest: If any image is 2048x2048, use that.
                for fn in files_to_stack:
                    p = os.path.join(src, fn)
                    if os.path.exists(p):
                        with Image.open(p) as test_img:
                             if test_img.width > ow: ow = test_img.width
                             if test_img.height > oh: oh = test_img.height
                
                img = Image.new("RGBA", (ow, oh), (0,0,0,0))
                valid_merge = False
                for fn in files_to_stack:
                    p = os.path.join(src, fn)
                    if os.path.exists(p):
                        try:
                            with Image.open(p) as l_img:
                                # Determine offset
                                x, y = 0, 0
                                if fn in offsets:
                                    # If metadata has offset, use it. 
                                    # BUT if image is full-size (1436x1902 or 2048x2048), usually offset is irrelevant or 0?
                                    # Actually, if cropped image is small, use offset.
                                    w, h = l_img.size
                                    if w < ow or h < oh:
                                        x = offsets[fn]['x']
                                        y = offsets[fn]['y']
                                
                                # Ensure we load the data before closing
                                img.paste(l_img.convert("RGBA"), (x, y), l_img.convert("RGBA"))
                            valid_merge = True
                        except Exception as e:
                            print(f"[Merge] Error loading {p}: {e}")
                
                if valid_merge:
                    temp_fn = f"_tmp_merge_{target_fn}.png"
                    temp_path = os.path.join(src, temp_fn)
                    img.save(temp_path)
                    print(f"[Merge] Temp file saved: {temp_path}")
                    
                    # Delete source files and their thumbnails (if in default color)
                    for fn in files_to_stack:
                        try:
                            p = os.path.join(src, fn)
                            if os.path.exists(p):
                                os.remove(p)
                                print(f"[Merge] Deleted source: {p}")
                            
                            if is_default_color:
                                match = re.match(r"^(\d+)\.png$", fn)
                                if match:
                                    tid = match.group(1)
                                    tp = os.path.join(src, f"thumb_{tid}.png")
                                    if os.path.exists(tp):
                                        os.remove(tp)
                        except Exception as e:
                            print(f"[Merge] Warning: Could not delete {fn}: {e}")
                    
                    # Save the merged file
                    final_path = os.path.join(src, f"{target_fn}.png")
                    if os.path.exists(final_path):
                        try:
                            os.remove(final_path)
                        except Exception as e:
                            print(f"[Merge] Warning: Could not remove existing target {final_path}: {e}")
                    
                    try:
                        os.rename(temp_path, final_path)
                        print(f"[Merge] Renamed temp to final: {final_path}")
                    except Exception as e:
                        print(f"[Merge] Error renaming temp to final: {e}")
                        # Fallback: try copy/remove
                        shutil.copy2(temp_path, final_path)
                        os.remove(temp_path)

                    # Generate new thumbnail if this is the default color folder
                    if is_default_color:
                        try:
                            thumb = img.copy()
                            thumb.thumbnail((200, 200))
                            thumb.save(os.path.join(src, f"thumb_{target_fn}.png"))
                            print(f"[Merge] Generated thumbnail: thumb_{target_fn}.png")
                        except Exception as e:
                            print(f"[Merge] Error generating thumbnail: {e}")

                    return True
                return False

            total_count = 0
            if selected_files:
                is_default = (not color or color == 'default')
                target_src = structured_dir
                if color and color != 'default':
                    target_src = os.path.join(structured_dir, color)
                
                if perform_merge(target_src, dest_name, selected_files, is_default_color=is_default):
                    total_count += 1
                
                if bulk_apply:
                    # Apply to default if we were in a subcolor
                    if not is_default:
                        if perform_merge(structured_dir, dest_name, selected_files, is_default_color=True):
                            total_count += 1
                    # Apply to all other subfolders
                    for d in os.listdir(structured_dir):
                        sub = os.path.join(structured_dir, d)
                        if os.path.isdir(sub) and (not color or d != color):
                            if perform_merge(sub, dest_name, selected_files, is_default_color=False):
                                total_count += 1
                self.send_api_response(True, f"Đã ghép xong {total_count} thư mục và lưu thay thế vào {dest_name}.png")
            else:
                self.send_api_response(False, "Cần chọn ít nhất một ảnh để ghép.")
        except Exception as e:
            self.send_api_response(False, str(e))

    def handle_list_part_images(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        color = data.get('color')

        if not kit_folder or not folder_name:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            target_dir = os.path.join(kit_path, "items_structured", folder_name)

            if color and color != 'default':
                target_dir = os.path.join(target_dir, color)

            if not os.path.exists(target_dir):
                self.send_api_response(False, "Directory not found")
                return

            # Load metadata to find offsets
            offsets = {} # filename -> {x, y}
            try:
                # 1. Identify part index from folder name
                # Resolve alias first
                # 1. Identify part index from folder name
                # No alias resolution
                
                match = re.search(r"-(\d+)$", folder_name)
                if match:
                    part_idx = int(match.group(1)) - 1
                    meta_path = os.path.join(kit_path, "metadata.json")
                    if os.path.exists(meta_path):
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            parts = meta.get('data', {}).get('parts', [])
                            if 0 <= part_idx < len(parts):
                                items = parts[part_idx].get('items', [])
                                for idx, item_layers in enumerate(items):
                                   # Ensure item_layers is a list
                                   if not isinstance(item_layers, list): item_layers = [item_layers]
                                   if not item_layers: continue
                                   
                                   # Get offset from first layer
                                   first_layer = item_layers[0]
                                   crop = first_layer.get('crop', {})
                                   x = crop.get('x', 0)
                                   y = crop.get('y', 0)
                                   offsets[f"{idx + 1}.png"] = {"x": x, "y": y}
            except Exception as e:
                print(f"Metadata read error: {e}")

            files = []
            for f in os.listdir(target_dir):
                if f.endswith('.png') and f != 'nav.png' and not f.startswith('thumb_'):
                    match = re.search(r"(\d+)", f)
                    order = int(match.group(1)) if match else 999
                    
                    # Verify if file is full canvas (merged) or cropped component
                    filepath = os.path.join(target_dir, f)
                    try:
                        with Image.open(filepath) as img:
                            w, h = img.size
                            # Standard Neka canvas is usually 1436x1902
                            if w == 1436 and h == 1902:
                                x, y = 0, 0
                            else:
                                # Fallback to metadata
                                off = offsets.get(f, {"x": 0, "y": 0})
                                x, y = off["x"], off["y"]
                    except:
                        x, y = 0, 0

                    files.append({
                        "filename": f, 
                        "order": order,
                        "x": x,
                        "y": y
                    })

            files.sort(key=lambda x: x['order'])
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({"success": True, "files": files})
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            self.send_api_response(False, str(e))

    def handle_zip_kit(self, data):
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return
        try:
            from zip_neka_kit import zip_kit
            zip_path = zip_kit(kit_folder)
            if os.path.exists(zip_path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(zip_path)}"')
                self.send_header('Content-Length', str(os.path.getsize(zip_path)))
                self.end_headers()
                with open(zip_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_api_response(False, "Failed to create ZIP file")
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")

    def send_api_response(self, success, message):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"success": success, "message": message}).encode('utf-8'))

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True

print(f"Server starting at http://localhost:{PORT}")
with ThreadedHTTPServer(("", PORT), KitHandler) as httpd:
    httpd.serve_forever()
