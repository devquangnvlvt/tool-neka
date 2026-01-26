import http.server
import socketserver
import json
import os
import shutil
import zipfile
import subprocess
import re
import tempfile
from urllib.parse import urlparse, parse_qs
import mimetypes
from config import DATA_DIR


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
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
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
        
        # Static file proxy for DATA_DIR
        # This replaces the need for the browser to access UNC paths directly
        if parsed_path.path.startswith('/downloads/'):
            try:
                # Remove '/downloads/' prefix to get the relative path
                rel_path = parsed_path.path[len('/downloads/'):].lstrip('/')
                # Clean up query params if any
                rel_path = rel_path.split('?')[0]
                
                # Full path on the network/custom storage
                full_path = os.path.join(DATA_DIR, rel_path.replace('/', os.sep))
                
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    # Basic security: ensure target is within DATA_DIR
                    if not os.path.abspath(full_path).startswith(os.path.abspath(DATA_DIR)):
                         self.send_error(403, "Access denied")
                         return

                    content_type, _ = mimetypes.guess_type(full_path)
                    if not content_type:
                        content_type = 'application/octet-stream'
                    
                    with open(full_path, 'rb') as f:
                        content = f.read()
                        
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', len(content))
                    # Cache for 1 hour to speed up UI
                    self.send_header('Cache-Control', 'public, max-age=3600')
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.send_error(404, f"File not found: {rel_path}")
            except Exception as e:
                self.send_error(500, str(e))
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
            '/api/auto_create_thumbs': self.handle_auto_create_thumbs,
            '/api/delete_all_thumbs': self.handle_delete_all_thumbs,
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
            '/api/delete_color_folders': self.handle_delete_color_folders,
            '/api/download_kit': self.handle_download_kit,
            '/api/check_progress': self.handle_check_progress,
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
            base_dir = DATA_DIR
            kits = []
            if os.path.exists(base_dir):

                for entry in os.listdir(base_dir):
                    full_path = os.path.join(base_dir, entry)
                    if os.path.isdir(full_path):
                        if entry == "cache_blobs" or not os.path.isdir(full_path):

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
            kit_path = safe_join(DATA_DIR, kit_folder)

            structured_dir = safe_join(kit_path, "")
            if not os.path.exists(kit_path):

                self.send_api_response(False, "Kit structure not found")
                return
            separated_folders = []
            sep_layers_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_folders = json.load(f)
                except: pass
            # Load metadata ONCE at the beginning
            meta_data = {}
            meta_path = os.path.join(kit_path, "metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta_data = json.load(f)
                except Exception as e:
                    print(f"Error loading metadata: {e}")

            parts = []
            for entry in os.listdir(structured_dir):
                entry_path = os.path.join(structured_dir, entry)
                if not os.path.isdir(entry_path): continue
                
                match = re.match(r"^(\d+)-(\d+)$", entry)
                
                if not match:
                    x, y = 9999, 9999
                else:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    
                # Count layers and items per item from metadata
                item_layer_counts = {}
                expected_num_items = 0
                try:
                    match_y = re.match(r"^\d+-(\d+)$", entry)
                    if match_y:
                        part_idx_for_meta = int(match_y.group(1)) - 1
                        parts_data = meta_data.get('data', {}).get('parts', [])
                        if 0 <= part_idx_for_meta < len(parts_data):
                            items_meta = parts_data[part_idx_for_meta].get('items', [])
                            expected_num_items = len(items_meta)
                            for im_idx, item_layers in enumerate(items_meta):
                                if not isinstance(item_layers, list): item_layers = [item_layers]
                                l_count = 0
                                for layer in item_layers:
                                    if isinstance(layer, dict):
                                        if layer.get('blob'): l_count += 1
                                        addon_textures = layer.get('addonTextures', [])
                                        l_count += len(addon_textures)
                                item_layer_counts[im_idx + 1] = l_count
                except Exception as e:
                    print(f"Error processing metadata for {entry}: {e}")

                item_indices = []
                image_indices = [] # Indices of N.png in main folder
                thumb_pattern = re.compile(r"^thumb_(\d+)\.png$")
                image_pattern = re.compile(r"^(\d+)\.png$")
                
                # Use os.scandir for better performance on network drives
                colors = []
                try:
                    with os.scandir(entry_path) as it:
                        for entry_file in it:
                            if entry_file.is_file():
                                fname = entry_file.name
                                m_thumb = thumb_pattern.match(fname)
                                if m_thumb: item_indices.append(int(m_thumb.group(1)))
                                m_img = image_pattern.match(fname)
                                if m_img: image_indices.append(int(m_img.group(1)))
                            elif entry_file.is_dir():
                                colors.append(entry_file.name)
                except Exception as e:
                    print(f"Error scanning directory {entry_path}: {e}")

                # Use max of (existing files, expected from metadata)
                num_items = max(expected_num_items, max(image_indices) if image_indices else 0, max(item_indices) if item_indices else 0)
                
                # Check for gaps in N.png (main folder)
                missing_images = []
                if not colors and image_indices:
                    max_img = max(image_indices)
                    for i in range(1, max_img + 1):
                        if i not in image_indices:
                            missing_images.append(i)

                color_gaps = {} # color_name -> missing_indices
                if colors:
                    for sub in colors:
                        sub_path = os.path.join(entry_path, sub)
                        sub_indices = []
                        try:
                            with os.scandir(sub_path) as sit:
                                for sf_entry in sit:
                                    if sf_entry.is_file():
                                        sm = image_pattern.match(sf_entry.name)
                                        if sm: sub_indices.append(int(sm.group(1)))
                        except: pass
                        
                        if sub_indices:
                            gaps = []
                            max_sub = max(sub_indices)
                            for i in range(1, max_sub + 1):
                                if i not in sub_indices:
                                    gaps.append(i)
                            if gaps:
                                color_gaps[sub] = gaps
                
                if missing_images or color_gaps:
                    print(f"  [GAP DETECTED] Folder {entry}: missing_images={missing_images}, color_gaps={list(color_gaps.keys())}")

                parts.append({
                    "x": x, "y": y, "folder": entry,
                    "items_count": num_items, "colors": colors,
                    "is_separated": entry in separated_folders,
                    "item_layer_counts": item_layer_counts,
                    "has_colors": len(colors) > 0,
                    "missing_images": missing_images,
                    "color_gaps": color_gaps
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
            kit_path = safe_join(DATA_DIR, kit_folder)

            
            struct_base = safe_join(kit_path, "")

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
            kit_path = safe_join(DATA_DIR, kit_folder)

            
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
            kit_path = safe_join(DATA_DIR, kit_folder)

            
            # Target structured folder
            struct_base = safe_join(kit_path, folder_name)

            
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
                                "url": f"/downloads/{kit_folder}/{folder_name}/{p_file}",
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
            kit_path = safe_join(DATA_DIR, kit_folder)

            
            # Determine directory
            struct_base = safe_join(kit_path, folder_name)

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
            kit_path = safe_join(DATA_DIR, kit_folder)

            struct_base = safe_join(kit_path, folder_name)

            
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
            kit_path = safe_join(DATA_DIR, kit_folder)

            struct_base = safe_join(kit_path, folder_name)

            
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
            kit_path = safe_join(DATA_DIR, kit_folder)

            structured_dir = safe_join(kit_path, folder_name)


            if not os.path.exists(structured_dir):
                self.send_api_response(False, "Folder not found")
                return

            print(f"[Merge] Stacking {selected_files} into {dest_name}.png in {folder_name}")

            # Load metadata for offsets and canvas size
            canvas_width, canvas_height = 1436, 1902 # Defaults
            offsets = data.get('offsets', {}) # Prioritize offsets from frontend
            local_offsets = {}
            try:
                found_config = False
                
                # Check for p_config.json (Picrew)
                p_config_path = os.path.join(kit_path, "p_config.json")
                if os.path.exists(p_config_path):
                    with open(p_config_path, 'r', encoding='utf-8') as f:
                        p_conf = json.load(f)
                        if 'w' in p_conf and 'h' in p_conf:
                            canvas_width = int(p_conf['w'])
                            canvas_height = int(p_conf['h'])
                        
                        match = re.search(r"-(\d+)$", folder_name)
                        if match:
                            p_idx = int(match.group(1)) - 1
                            p_list = p_conf.get('pList', [])
                            if 0 <= p_idx < len(p_list):
                                part = p_list[p_idx]
                                part_x = part.get('x', 0)
                                part_y = part.get('y', 0)
                                items = part.get('items', [])
                                for idx, _ in enumerate(items):
                                   local_offsets[f"{idx + 1}.png"] = {"x": part_x, "y": part_y}
                                found_config = True

                # Fallback to metadata.json (Neka)
                if not found_config:
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
                print(f"[Merge] Metadata/Config error: {e}")
            
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
            target_dir = os.path.join(DATA_DIR, kit_folder, folder_name)



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
            kit_path = os.path.join(DATA_DIR, kit_folder)

            target_dir = os.path.join(kit_path, folder_name)


            if color and color != 'default':
                target_dir = os.path.join(target_dir, color)

            if not os.path.exists(target_dir):
                self.send_api_response(False, "Directory not found")
                return

            # Load metadata to find offsets
            # Load metadata/config to find offsets
            offsets = {} # filename -> {x, y}
            try:
                match = re.search(r"-(\d+)$", folder_name)
                part_idx = int(match.group(1)) - 1 if match else -1
                
                found_config = False
                
                # 1. p_config.json (Picrew)
                p_config_path = os.path.join(kit_path, "p_config.json")
                if os.path.exists(p_config_path) and part_idx >= 0:
                     with open(p_config_path, 'r', encoding='utf-8') as f:
                        p_conf = json.load(f)
                        p_list = p_conf.get('pList', [])
                        if 0 <= part_idx < len(p_list):
                            part = p_list[part_idx]
                            px = part.get('x', 0)
                            py = part.get('y', 0)
                            items = part.get('items', [])
                            for idx, _ in enumerate(items):
                                offsets[f"{idx + 1}.png"] = {"x": px, "y": py}
                            found_config = True

                # 2. metadata.json (Neka)
                if not found_config and part_idx >= 0:
                    meta_path = os.path.join(kit_path, "metadata.json")
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
                                   x = crop.get('x', 0)
                                   y = crop.get('y', 0)
                                   offsets[f"{idx + 1}.png"] = {"x": x, "y": y}
            except Exception as e:
                print(f"Metadata/Config read error: {e}")

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
            
            if not zip_path or not os.path.exists(zip_path):
                 self.send_api_response(False, "Failed to create zip archive")
                 return

            # Read the zip file content
            with open(zip_path, 'rb') as f:
                zip_data = f.read()

            # Send binary response
            self.send_response(200)
            self.send_header('Content-type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{kit_folder}.zip"')
            self.send_header('Content-Length', str(len(zip_data)))
            self.end_headers()
            self.wfile.write(zip_data)
            
            # Optional: Remove zip from server after sending to save space
            # os.remove(zip_path)

        except Exception as e:
            # If we already started sending headers, this might tail-fail, but usually okay for small zips
            try: self.send_api_response(False, f"Server Error: {str(e)}")
            except: pass

    def handle_download_kit(self, data):
            kit_id = data.get('id')
            if not kit_id:
                self.send_api_response(False, "Missing 'id' parameter")
                return

            try:
                # Cleanup old progress
                temp_dir = tempfile.gettempdir()
                progress_file = os.path.join(temp_dir, f"progress_{kit_id}.json")
                if os.path.exists(progress_file):
                    os.remove(progress_file)

                # Gọi script download_neka_kit.py
                subprocess.run(['python', 'download_neka_kit.py', str(kit_id)], check=True)

                # Đường dẫn thư mục sau khi tải
                kit_folder = f'neka_{kit_id}'
                kit_path = os.path.join(DATA_DIR, kit_folder)
                if not os.path.exists(kit_path):
                    self.send_api_response(False, f"Không tìm thấy dữ liệu cho kit {kit_id}")
                    return

                # Tạo file ZIP để tải về
                zip_path = os.path.join(DATA_DIR, f"{kit_folder}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(kit_path):
                        for file in files:
                            abs_path = os.path.join(root, file)
                            rel_path = os.path.relpath(abs_path, kit_path)
                            zipf.write(abs_path, rel_path)

                # Trả file zip về cho client
                with open(zip_path, 'rb') as f:
                    zip_data = f.read()

                self.send_response(200)
                self.send_header('Content-type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{kit_folder}.zip"')
                self.send_header('Content-Length', str(len(zip_data)))
                self.end_headers()
                self.wfile.write(zip_data)

                # Cleanup progress file after successful download
                temp_dir = tempfile.gettempdir()
                progress_file = os.path.join(temp_dir, f"progress_{kit_id}.json")
                if os.path.exists(progress_file):
                    try:
                        os.remove(progress_file)
                    except:
                        pass

                # Tùy chọn: xóa zip sau khi gửi để tiết kiệm dung lượng
                # os.remove(zip_path)

            except subprocess.CalledProcessError:
                self.send_api_response(False, f"Lỗi khi chạy download_neka_kit.py {kit_id}")
            except Exception as e:
                self.send_api_response(False, f"Server error: {str(e)}")

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
            kit_path = safe_join(DATA_DIR, kit_folder)

            struct_base = safe_join(kit_path, part_folder)

            
            old_path = safe_join(struct_base, old_color)
            new_path = safe_join(struct_base, new_color)

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

    
    def handle_check_progress(self, data):
        kit_id = data.get('id')
        if not kit_id:
            self.send_api_response(False, "Missing id")
            return
        
        temp_dir = tempfile.gettempdir()
        progress_file = os.path.join(temp_dir, f"progress_{kit_id}.json")
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                     prog_data = json.load(f)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "progress": prog_data}).encode('utf-8'))
            except:
                self.send_api_response(False, "Error reading progress")
        else:
             self.send_api_response(False, "No progress data yet")


    def handle_delete_color_folders(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')
        colors_to_delete = data.get('colors', []) # List of color folder names

        if not kit_folder or not part_folder or not colors_to_delete:
            self.send_api_response(False, "Missing parameters (kit, part_folder, colors)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            struct_base = safe_join(kit_path, part_folder)
            
            if not os.path.exists(struct_base):
                self.send_api_response(False, "Part folder not found")
                return

            deleted_count = 0
            errors = []

            for color in colors_to_delete:
                if color == 'default':
                    continue # Safety: never delete default
                
                color_path = safe_join(struct_base, color)
                if os.path.exists(color_path) and os.path.isdir(color_path):
                    try:
                        shutil.rmtree(color_path)
                        deleted_count += 1
                    except Exception as e:
                        errors.append(f"Could not delete {color}: {str(e)}")
                else:
                    errors.append(f"Color folder not found: {color}")

            msg = f"Successfully deleted {deleted_count} color folders."
            if errors:
                msg += " Warnings: " + "; ".join(errors)
            
            self.send_api_response(True, msg)

        except Exception as e:
            self.send_api_response(False, f"Error deleting colors: {str(e)}")


    def handle_auto_create_thumbs(self, data):
        from PIL import Image
        kit_folder = data.get('kit')
        if not kit_folder or not validate_id(kit_folder):
            return self.send_api_response(False, "Invalid kit parameter")
        
        kit_path = safe_join(DATA_DIR, kit_folder)
        if not os.path.exists(kit_path):
            return self.send_api_response(False, "Kit not found")
        
        results = {
            "total_folders": 0,
            "total_images": 0,
            "created_thumbs": 0,
            "skipped_thumbs": 0,
            "details": []
        }
        
        # Scan all folders X-Y
        for entry in os.listdir(kit_path):
            entry_path = os.path.join(kit_path, entry)
            if not os.path.isdir(entry_path):
                continue
            
            # Check format X-Y
            if not re.match(r"^\d+-\d+$", entry):
                continue
            
            results["total_folders"] += 1
            folder_created = 0
            folder_skipped = 0
            
            # Find all image files number.png (recursively in subfolders)
            # We want to map "1" -> "path/to/1.png"
            # If multiple exist (different colors), we just pick the first one we find to make the thumb.
            
            found_images = {} # number -> full_path
            
            # Walk the directory
            for root, dirs, files in os.walk(entry_path):
                for filename in files:
                    # Check for N.png
                    match = re.match(r"^(\d+)\.png$", filename)
                    if match:
                        num = match.group(1)
                        # If we haven't found a source for this number yet, record it
                        # Prioritize root images? os.walk yields root first, so yes.
                        if num not in found_images:
                            found_images[num] = os.path.join(root, filename)

            # Now process the found images
            for num, source_path in found_images.items():
                thumb_name = f"thumb_{num}.png"
                thumb_path = os.path.join(entry_path, thumb_name)
                
                results["total_images"] += 1
                
                # Check if thumb exists
                if os.path.exists(thumb_path):
                    folder_skipped += 1
                    results["skipped_thumbs"] += 1
                    continue
                
                # Create thumbnail
                try:
                    with Image.open(source_path) as img:
                        img.thumbnail((200, 200))
                        img.save(thumb_path)
                    folder_created += 1
                    results["created_thumbs"] += 1
                except Exception as e:
                    print(f"Error creating thumb for {source_path}: {e}")
            
            if folder_created > 0 or folder_skipped > 0:
                results["details"].append({
                    "folder": entry,
                    "created": folder_created,
                    "skipped": folder_skipped
                })
        
        return self.send_api_response(True, 
            f"Đã tạo {results['created_thumbs']} thumbnail, bỏ qua {results['skipped_thumbs']} (đã có sẵn)",
            {"stats": results})

    def handle_delete_all_thumbs(self, data):
        kit_folder = data.get('kit')
        if not kit_folder or not validate_id(kit_folder):
            return self.send_api_response(False, "Invalid kit parameter")
        
        kit_path = safe_join(DATA_DIR, kit_folder)
        if not os.path.exists(kit_path):
            return self.send_api_response(False, "Kit not found")
        
        deleted_count = 0
        
        # Scan all folders X-Y
        for entry in os.listdir(kit_path):
            entry_path = os.path.join(kit_path, entry)
            if not os.path.isdir(entry_path):
                continue
            
            # Check format X-Y
            if not re.match(r"^\d+-\d+$", entry):
                continue
            
            # Find all thumb_*.png files
            thumb_pattern = re.compile(r"^thumb_(\d+)\.png$")
            for filename in os.listdir(entry_path):
                if thumb_pattern.match(filename):
                    file_path = os.path.join(entry_path, filename)
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")
        
        return self.send_api_response(True, f"Đã xóa thành công {deleted_count} thumbnail.")

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
            kit_path = safe_join(DATA_DIR, kit_folder)

            
            # Target structured folder
            struct_base = safe_join(kit_path, folder_name)

            
            # Target directory logic
            target_dir = struct_base
            if color and color != 'default' and filename != 'nav.png':
                 target_dir = safe_join(struct_base, color)
                 if not os.path.exists(target_dir):
                     os.makedirs(target_dir)

            if not os.path.exists(struct_base):
                self.send_api_response(False, "Folder not found")
                return

            # Security Check: Ensure filename doesn't contain traversal characters
            if '/' in filename or '\\' in filename or filename == '..':
                self.send_api_response(False, "Invalid filename")
                return

            file_path = safe_join(target_dir, filename)

            # Decode base64
            if ',' in file_content:
                file_content = file_content.split(',')[1]
            
            file_bytes = base64.b64decode(file_content)
            
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            self.send_api_response(True, f"Uploaded {filename}")

        except Exception as e:
            self.send_api_response(False, f"Upload error: {str(e)}")



class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True

print(f"Server starting at http://localhost:{PORT}")
with ThreadedHTTPServer(("", PORT), KitHandler) as httpd:
    httpd.serve_forever()
