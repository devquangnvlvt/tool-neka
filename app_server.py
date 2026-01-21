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

# ================= SECURITY UTILITIES =================
def safe_join(base, *paths):
    """
    Safely joins paths and ensures the result is within the base directory.
    Prevents Path Traversal attacks.
    """
    base = os.path.abspath(base)
    # Filter out empty or None paths
    clean_paths = [p for p in paths if p and isinstance(p, str)]
    if not clean_paths:
        return base
    joined = os.path.abspath(os.path.join(base, *clean_paths))
    if not joined.startswith(base):
        raise ValueError("Security violation: Path traversal detected")
    return joined

def sanitize_error(message):
    """Removes sensitive system paths from error messages."""
    if not message: return ""
    # Replace absolute project root with a generic label
    root = os.path.dirname(os.path.abspath(__file__))
    return message.replace(root, "[PROJECT_ROOT]").replace("\\", "/")

def validate_id(id_str):
    """Validates that a kit or folder name is safe."""
    if not id_str: return False
    return bool(re.match(r"^[a-zA-Z0-9_\-\.]+$", str(id_str)))

# ======================================================

class KitHandler(http.server.SimpleHTTPRequestHandler):
    def send_api_response(self, success, message, extra=None):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        res = {"success": success, "message": sanitize_error(message)}
        if extra: res.update(extra)
        self.wfile.write(json.dumps(res).encode('utf-8'))
    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/zip_kit':
            query = parse_qs(parsed_path.query)
            kit_folder = query.get('kit', [None])[0]
            if kit_folder:
                if not validate_id(kit_folder):
                    self.send_api_response(False, "Invalid kit name")
                    return
                self.handle_zip_kit({"kit": kit_folder})
            else:
                self.send_api_response(False, "Missing kit parameter")
            return
        elif parsed_path.path == '/api/debug_folder_files':
            query = parse_qs(parsed_path.query)
            kit = query.get('kit', [None])[0]
            folder = query.get('folder', [None])[0]
            color = query.get('color', [None])[0]
            if kit and folder:
                self.handle_debug_folder_files({"kit": kit, "folder": folder, "color": color})
            else:
                self.send_api_response(False, "Missing kit or folder params")
            return
        
        # Security: Prevent listing directories via GET
        if parsed_path.path.endswith('/') and parsed_path.path != '/':
             self.send_error(403, "Directory listing forbidden")
             return

        return super().do_GET()

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
        except:
            self.send_api_response(False, "Invalid JSON data")
            return

        # Map endpoints to handlers
        endpoints = {
            '/api/delete_part': self.handle_delete_part,
            '/api/zip_kit': self.handle_zip_kit,
            '/api/rename_folder': self.handle_rename_folder,
            '/api/get_item_layers': self.handle_get_item_layers,
            '/api/create_thumb': self.handle_create_thumb,
            '/api/delete_file': self.handle_delete_file,
            '/api/rename_file': self.handle_rename_file,
            '/api/merge_layers': self.handle_merge_layers,
            '/api/get_kit_structure': self.handle_get_kit_structure,
            '/api/get_kits_list': self.handle_get_kits_list,
            '/api/flatten_colors': self.handle_flatten_colors,
            '/api/list_part_images': self.handle_list_part_images,
            '/api/rename_folder': self.handle_rename_folder,
            '/api/get_item_layers': self.handle_get_item_layers,
            '/api/upload_file': self.handle_upload_file,
            '/api/rename_color_folder': self.handle_rename_color_folder,
        }

        handler = endpoints.get(self.path)
        if handler:
            try:
                handler(data)
            except ValueError as ve:
                self.send_api_response(False, str(ve))
            except Exception as e:
                self.send_api_response(False, f"Internal Error: {str(e)}")
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
            kit_path = safe_join(base_path, "downloads", kit_folder)
            structured_dir = safe_join(kit_path, "items_structured")
            if not os.path.exists(structured_dir):
                self.send_api_response(False, "Kit structure not found")
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
                    "item_layer_counts": item_layer_counts,
                    "has_colors": len(colors) > 0
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
            
            # --- Get Global Canvas Dimensions ---
            canvas_width, canvas_height = 1436, 1902 # Defaults
            try:
                meta_path = os.path.join(kit_path, "metadata.json")
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        parts_data = meta.get('data', {}).get('parts', [])
                        if parts_data:
                            # Tìm item đầu tiên có crop data để lấy kích thước canvas gốc
                            for p_item in parts_data:
                                p_items = p_item.get('items', [])
                                if p_items and p_items[0]:
                                    f_layer = p_items[0]
                                    if isinstance(f_layer, list): f_layer = f_layer[0]
                                    if isinstance(f_layer, dict) and 'crop' in f_layer:
                                        c = f_layer['crop']
                                        canvas_width = c.get('ow', canvas_width)
                                        canvas_height = c.get('oh', canvas_height)
                                        break
            except Exception as e:
                print(f"Error detecting canvas size: {e}")
            
            
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
                "missing_y": missing_y,
                "canvas_width": canvas_width,
                "canvas_height": canvas_height
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
            kit_path = safe_join(base_path, "downloads", kit_folder)
            
            struct_base = safe_join(kit_path, "items_structured")
            merged_base = safe_join(kit_path, "items_merged")
            
            old_path = safe_join(struct_base, old_name)
            new_path = safe_join(struct_base, new_name)

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
            kit_path = safe_join(base_path, "downloads", kit_folder)
            
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

    def handle_debug_folder_files(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        color = data.get('color')

        if not kit_folder or not folder_name:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = safe_join(base_path, "downloads", kit_folder)
            
            # Target structured folder
            struct_base = safe_join(kit_path, "items_structured", folder_name)
            
            target_dir = struct_base
            is_subcolor = False
            if color and color != 'default':
                target_dir = safe_join(struct_base, color)
                is_subcolor = True

            if not os.path.exists(target_dir):
                self.send_api_response(False, f"Directory not found: {target_dir}")
                return

            file_list = []
            
            # Helper to add files
            def add_files_from(path, label_prefix=""):
                if not os.path.exists(path): return
                for entry in sorted(os.listdir(path)):
                    full_p = os.path.join(path, entry)
                    if os.path.isfile(full_p):
                        # Simple check for images
                        is_img = entry.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                        
                        relative_path = os.path.relpath(full_p, kit_path).replace("\\", "/")
                        url = f"/downloads/{kit_folder}/{relative_path}"
                        
                        file_list.append({
                            "name": entry,
                            "url": url,
                            "is_image": is_img,
                            "location": "current" if not label_prefix else label_prefix
                        })

            # 1. Add files from the target directory (color folder or main folder)
            add_files_from(target_dir, "Color/Sub" if is_subcolor else "Main")

            # 2. If inside a color subfolder, ALSO check the parent (Main) folder for specific files like nav.png or common thumbnails
            if is_subcolor:
                # Check for nav.png explicitly in parent
                parent_files_to_check = ["nav.png"]
                
                # Also check for ALL thumb_*.png in parent (since thumbnails are usually shared or stored in root)
                if os.path.exists(struct_base):
                    for entry in os.listdir(struct_base):
                        if entry == "nav.png" or entry.startswith("thumb_"):
                             parent_files_to_check.append(entry)

                # Remove duplicates if added strictly
                parent_files_to_check = list(set(parent_files_to_check))

                for p_file in parent_files_to_check:
                    p_path = os.path.join(struct_base, p_file)
                    if os.path.exists(p_path) and os.path.isfile(p_path):
                        # Avoid duplicates if they somehow exist in subfolder (unlikely but safe)
                        if not any(f['name'] == p_file for f in file_list):
                             file_list.append({
                                "name": p_file,
                                "url": f"/downloads/{kit_folder}/items_structured/{folder_name}/{p_file}",
                                "is_image": True,
                                "location": "Parent (Main)"
                            })



            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({"success": True, "files": file_list})
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            self.send_api_response(False, f"Error listing files: {str(e)}")

    def handle_create_thumb(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        source_file = data.get('source_file') # e.g. "1.png"
        target_file = data.get('target_file') # e.g. "thumb_1.png"
        color = data.get('color')

        if not kit_folder or not folder_name or not source_file or not target_file:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            from PIL import Image
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = safe_join(base_path, "downloads", kit_folder)
            
            # Determine directory
            struct_base = safe_join(kit_path, "items_structured", folder_name)
            target_dir = struct_base
            if color and color != 'default':
                target_dir = safe_join(struct_base, color)
            
            # Construct paths
            source_path = safe_join(target_dir, source_file)
            
            # If not found in target_dir (subcolor), check parent
            if not os.path.exists(source_path) and color and color != 'default':
                 source_path = safe_join(struct_base, source_file)

            if not os.path.exists(source_path):
                self.send_api_response(False, "Source file not found")
                return
            
            target_path = safe_join(struct_base, target_file)
            
            with Image.open(source_path) as img:
                img.thumbnail((200, 200))
                img.save(target_path)
            
            self.send_api_response(True, f"Created {target_file}")

        except Exception as e:
             self.send_api_response(False, f"Error creating thumbnail: {str(e)}")

    def handle_delete_file(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        filename = data.get('filename')
        color = data.get('color')

        if not kit_folder or not folder_name or not filename:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = safe_join(base_path, "downloads", kit_folder)
            struct_base = safe_join(kit_path, "items_structured", folder_name)
            
            # Simple resolution:
            path_primary = safe_join(struct_base, color if color and color != 'default' else "", filename)
            path_parent = safe_join(struct_base, filename)

            target_path = path_primary
            if not os.path.exists(target_path) and os.path.exists(path_parent):
                target_path = path_parent

            if not os.path.exists(target_path):
                self.send_api_response(False, "File not found")
                return

            os.remove(target_path)
            self.send_api_response(True, f"Deleted {filename}")

        except Exception as e:
            self.send_api_response(False, f"Error deleting file: {str(e)}")

    def handle_rename_file(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        old_name = data.get('old_name')
        new_name = data.get('new_name')
        color = data.get('color')

        if not kit_folder or not folder_name or not old_name or not new_name:
            self.send_api_response(False, "Missing parameters")
            return
            
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = safe_join(base_path, "downloads", kit_folder)
            struct_base = safe_join(kit_path, "items_structured", folder_name)
            
            # Path Logic
            path_primary = safe_join(struct_base, color if color and color != 'default' else "", old_name)
            path_parent = safe_join(struct_base, old_name)
            
            current_path = path_primary
            if not os.path.exists(current_path) and os.path.exists(path_parent):
                current_path = path_parent
                
            if not os.path.exists(current_path):
                self.send_api_response(False, "File not found")
                return
                
            # New path must be in the SAME directory as the old one
            new_path = safe_join(os.path.dirname(current_path), new_name)
            
            if os.path.exists(new_path):
                self.send_api_response(False, "Destination file already exists")
                return
                
            os.rename(current_path, new_path)
            self.send_api_response(True, f"Renamed to {new_name}")
            
        except Exception as e:
            self.send_api_response(False, f"Error renaming file: {str(e)}")


    def handle_merge_layers(self, data):
        from PIL import Image, ImageEnhance
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        selected_files = data.get('selected_files', [])
        dest_name = data.get('destination_name', '1')
        color = data.get('color', 'default')
        bulk_apply = data.get('bulk_apply', False)
        layer_adjustments_raw = data.get('layer_adjustments', {})  # {filename: {target_color, saturation, brightness}}

        # Convert layer_adjustments to proper format
        layer_adjustments = {}
        for filename, adj in layer_adjustments_raw.items():
            layer_adjustments[filename] = {
                'target_color': adj.get('target_color'),  # Hex color string like "FF0000"
                'saturation': float(adj.get('saturation', 1.0)),
                'brightness': float(adj.get('brightness', 1.0))
            }

        if not kit_folder or not folder_name or not selected_files:
            self.send_api_response(False, "Missing parameters (need kit, folder, selected_files)")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = safe_join(base_path, "downloads", kit_folder)
            structured_dir = safe_join(kit_path, "items_structured", folder_name)

            if not os.path.exists(structured_dir):
                self.send_api_response(False, "Folder not found")
                return

            print(f"[Merge] Stacking {selected_files} into {dest_name}.png in {folder_name}")

            # Load metadata for offsets and canvas size
            canvas_width, canvas_height = 1436, 1902 # Defaults
            offsets = data.get('offsets', {}) # Prioritize offsets from frontend
            local_offsets = {}
            try:
                meta_path = os.path.join(kit_path, "metadata.json")
                if os.path.exists(meta_path):
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        # Detect canvas size from metadata
                        parts_data = meta.get('data', {}).get('parts', [])
                        for p_item in parts_data:
                            p_items = p_item.get('items', [])
                            if p_items and p_items[0]:
                                f_layer = p_items[0]
                                if isinstance(f_layer, list): f_layer = f_layer[0]
                                if isinstance(f_layer, dict) and 'crop' in f_layer:
                                    c = f_layer['crop']
                                    canvas_width = c.get('ow', canvas_width)
                                    canvas_height = c.get('oh', canvas_height)
                                    break

                        match = re.search(r"-(\d+)$", folder_name)
                        if match:
                            part_idx = int(match.group(1)) - 1
                            if 0 <= part_idx < len(parts_data):
                                items = parts_data[part_idx].get('items', [])
                                for idx, item_layers in enumerate(items):
                                   if not isinstance(item_layers, list): item_layers = [item_layers]
                                   if not item_layers: continue
                                   first_layer = item_layers[0]
                                   crop = first_layer.get('crop', {})
                                   local_offsets[f"{idx + 1}.png"] = {"x": crop.get('x', 0), "y": crop.get('y', 0)}
            except Exception as e:
                print(f"[Merge] Metadata error: {e}")
            
            # Merge: Frontend offsets win, then local detected ones
            for k, v in local_offsets.items():
                if k not in offsets:
                    offsets[k] = v

            def apply_color_transform(img, target_color=None, saturation=1.0, brightness=1.0):
                """Apply color tint to an image - replaces all colors with target color while preserving luminosity"""
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                r, g, b, a = img.split()
                
                # If target_color is provided, apply color overlay
                if target_color:
                    # Parse hex color (e.g., "FF0000" or "#FF0000")
                    if isinstance(target_color, str):
                        target_color = target_color.lstrip('#')
                        if len(target_color) == 6:
                            target_r = int(target_color[0:2], 16)
                            target_g = int(target_color[2:4], 16)
                            target_b = int(target_color[4:6], 16)
                        else:
                            # Invalid color, skip
                            target_r, target_g, target_b = 255, 255, 255
                    else:
                        target_r, target_g, target_b = target_color
                    
                    # Convert to grayscale to get luminosity
                    gray_img = Image.merge('RGB', (r, g, b)).convert('L')
                    
                    # Create colored version by applying target color with grayscale as intensity
                    import numpy as np
                    gray_array = np.array(gray_img).astype(float) / 255.0
                    
                    # Apply target color scaled by luminosity
                    r_new = (gray_array * target_r).astype('uint8')
                    g_new = (gray_array * target_g).astype('uint8')
                    b_new = (gray_array * target_b).astype('uint8')
                    
                    rgb_img = Image.merge('RGB', (
                        Image.fromarray(r_new),
                        Image.fromarray(g_new),
                        Image.fromarray(b_new)
                    ))
                else:
                    rgb_img = Image.merge('RGB', (r, g, b))
                
                # Apply brightness and saturation
                if brightness != 1.0:
                    enhancer = ImageEnhance.Brightness(rgb_img)
                    rgb_img = enhancer.enhance(brightness)
                
                if saturation != 1.0:
                    enhancer = ImageEnhance.Color(rgb_img)
                    rgb_img = enhancer.enhance(saturation)
                
                # Merge back with alpha
                result = Image.merge('RGBA', (*rgb_img.split(), a))
                return result

            def perform_merge(src, target_fn, files_to_stack, is_default_color=False, layer_adjustments=None):
                if not os.path.exists(src): return False
                
                ow, oh = canvas_width, canvas_height
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
                                # Apply color adjustments if provided
                                if layer_adjustments and fn in layer_adjustments:
                                    adj = layer_adjustments[fn]
                                    target_col = adj.get('target_color')
                                    sat = adj.get('saturation', 1.0)
                                    bri = adj.get('brightness', 1.0)
                                    if target_col or sat != 1.0 or bri != 1.0:
                                        l_img = apply_color_transform(l_img, target_col, sat, bri)
                                
                                x, y = 0, 0
                                if fn in offsets:
                                    w, h = l_img.size
                                    if w < ow or h < oh:
                                        x = offsets[fn]['x']
                                        y = offsets[fn]['y']
                                img.paste(l_img.convert("RGBA"), (x, y), l_img.convert("RGBA"))
                            valid_merge = True
                        except Exception as e:
                            print(f"[Merge] Error loading {p}: {e}")
                
                if valid_merge:
                    temp_fn = f"_tmp_merge_{target_fn}.png"
                    temp_path = os.path.join(src, temp_fn)
                    img.save(temp_path)
                    
                    for fn in files_to_stack:
                        try:
                            p = os.path.join(src, fn)
                            if os.path.exists(p):
                                os.remove(p)
                            if is_default_color:
                                match = re.match(r"^(\d+)\.png$", fn)
                                if match:
                                    tid = match.group(1)
                                    tp = os.path.join(src, f"thumb_{tid}.png")
                                    if os.path.exists(tp):
                                        os.remove(tp)
                        except Exception as e:
                            print(f"[Merge] Warning: Could not delete {fn}: {e}")
                    
                    final_path = os.path.join(src, f"{target_fn}.png")
                    if os.path.exists(final_path):
                        try: os.remove(final_path)
                        except: pass
                    
                    try:
                        os.rename(temp_path, final_path)
                    except Exception as e:
                        shutil.copy2(temp_path, final_path)
                        os.remove(temp_path)

                    if is_default_color:
                        try:
                            thumb = img.copy()
                            thumb.thumbnail((200, 200))
                            thumb.save(os.path.join(src, f"thumb_{target_fn}.png"))
                        except Exception as e:
                            print(f"[Merge] Error generating thumbnail: {e}")
                    return True
                return False

            total_count = 0
            is_default = (not color or color == 'default')
            target_src = structured_dir
            if color and color != 'default':
                target_src = os.path.join(structured_dir, color)
            
            if perform_merge(target_src, dest_name, selected_files, is_default_color=is_default, layer_adjustments=layer_adjustments):
                total_count += 1
            
            if bulk_apply:
                if not is_default:
                    if perform_merge(structured_dir, dest_name, selected_files, is_default_color=True, layer_adjustments=layer_adjustments):
                        total_count += 1
                for d in os.listdir(structured_dir):
                    sub = os.path.join(structured_dir, d)
                    if os.path.isdir(sub) and (not color or d != color):
                        if perform_merge(sub, dest_name, selected_files, is_default_color=False, layer_adjustments=layer_adjustments):
                            total_count += 1
            self.send_api_response(True, f"Đã ghép xong {total_count} thư mục và lưu thay thế vào {dest_name}.png")

        except Exception as e:
            self.send_api_response(False, str(e))

    def handle_flatten_colors(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')

        if not kit_folder or not folder_name:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            target_dir = os.path.join(base_path, "downloads", kit_folder, "items_structured", folder_name)

            if not os.path.exists(target_dir):
                self.send_api_response(False, "Folder not found")
                return

            # 1. Collect all images from subfolders
            images_to_move = []
            subfolders = []

            items = os.listdir(target_dir)
            for item in items:
                item_path = os.path.join(target_dir, item)
                if os.path.isdir(item_path):
                    subfolders.append(item_path)
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            if file.lower().endswith('.png'):
                                images_to_move.append(os.path.join(root, file))

            if not images_to_move:
                 # Clean up empty folders anyway
                 cleaned = 0
                 for sub in subfolders:
                     try:
                         shutil.rmtree(sub)
                         cleaned += 1
                     except: pass
                 
                 msg = "No images to flatten."
                 if cleaned > 0: msg += f" Removed {cleaned} empty folders."
                 self.send_api_response(True, msg)
                 return

            # 2. Determine max index in root to avoid overwriting (optional, but requested sequential)
            # Actually, user wants "1.png, 2.png..." in root.
            # Best to move them all and rename to next available number.
            
            root_files = os.listdir(target_dir)
            indices = []
            for f in root_files:
                if f.endswith('.png'):
                    match = re.search(r"^(\d+)\.png$", f)
                    if match: indices.append(int(match.group(1)))
            
            next_idx = max(indices) + 1 if indices else 1
            moved_count = 0

            for old_path in images_to_move:
                new_fn = f"{next_idx}.png"
                new_path = os.path.join(target_dir, new_fn)
                
                # Check if new_path exists (unlikely given logic)
                while os.path.exists(new_path):
                    next_idx += 1
                    new_fn = f"{next_idx}.png"
                    new_path = os.path.join(target_dir, new_fn)
                
                shutil.move(old_path, new_path)
                moved_count += 1
                next_idx += 1

            # 3. Remove now empty (or all) color subfolders
            for sub in subfolders:
                try:
                    shutil.rmtree(sub)
                except Exception as e:
                    print(f"Error removing subfolder {sub}: {e}")

            self.send_api_response(True, f"Successfully moved {moved_count} images to root and removed empty folders.")

        except Exception as e:
            self.send_api_response(False, f"Flatten error: {str(e)}")

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
        if not validate_id(kit_folder):
            self.send_api_response(False, "Invalid kit name")
            return
        try:
            from zip_neka_kit import zip_kit
            zip_path = zip_kit(kit_folder)
            # Ensure zip_path is within project
            base_path = os.path.dirname(os.path.abspath(__file__))
            if not os.path.abspath(zip_path).startswith(base_path):
                 self.send_api_response(False, "Invalid zip archive path")
                 return
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")

    def handle_rename_color_folder(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')
        old_color = data.get('old_color')
        new_color = data.get('new_color')

        if not kit_folder or not part_folder or not old_color or not new_color:
            self.send_api_response(False, "Missing parameters")
            return
        
        if old_color == 'default':
             self.send_api_response(False, "Cannot rename default color (root folder)")
             return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            struct_base = os.path.join(kit_path, "items_structured", part_folder)
            
            old_path = os.path.join(struct_base, old_color)
            new_path = os.path.join(struct_base, new_color)

            if not os.path.exists(old_path):
                self.send_api_response(False, "Old color folder not found")
                return
            if os.path.exists(new_path):
                self.send_api_response(False, "New color folder name already exists")
                return
            
            # Simple rename
            os.rename(old_path, new_path)
            
            self.send_api_response(True, f"Renamed color to {new_color}")

        except Exception as e:
            self.send_api_response(False, f"Error renaming color: {str(e)}")

    def handle_upload_file(self, data):
        import base64
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        filename = data.get('filename', 'nav.png') # Default or forced
        file_content = data.get('file_content') # Base64 string
        color = data.get('color')

        if not kit_folder or not folder_name or not file_content:
            self.send_api_response(False, "Missing parameters (kit, folder, file_content)")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            kit_path = os.path.join(base_path, "downloads", kit_folder)
            
            # Target structured folder
            struct_base = os.path.join(kit_path, "items_structured", folder_name)
            
            # Target directory logic
            target_dir = struct_base
            if color and color != 'default' and filename != 'nav.png':
                 target_dir = os.path.join(struct_base, color)
                 if not os.path.exists(target_dir):
                     os.makedirs(target_dir)

            if not os.path.exists(struct_base):
                self.send_api_response(False, "Folder not found")
                return

            file_path = os.path.join(target_dir, filename)

            # Decode base64
            if ',' in file_content:
                file_content = file_content.split(',')[1]
            
            file_bytes = base64.b64decode(file_content)
            
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            self.send_api_response(True, f"Uploaded {filename}")

        except Exception as e:
            self.send_api_response(False, f"Upload error: {str(e)}")

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
