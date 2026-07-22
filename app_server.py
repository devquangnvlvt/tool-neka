import http.server
import socketserver
import socket
import json
import os
import shutil
import zipfile
import subprocess
import re
import tempfile
import mimetypes
import base64
import traceback
from urllib.parse import urlparse, parse_qs
from PIL import Image, ImageEnhance, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
import numpy as np
from config import DATA_DIR, TRASH_DIR
import time

def move_to_trash(path, kit_folder=None, part_folder=None):
    """Moves a file or directory to the trash folder with a timestamp and context info."""
    if not os.path.exists(path):
        return
    
    if not os.path.exists(TRASH_DIR):
        os.makedirs(TRASH_DIR)
        
    base_name = os.path.basename(path)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    
    # Build a descriptive name
    name_parts = [timestamp]
    if kit_folder:
        # Replace separators with underscores for filename safety
        clean_kit = str(kit_folder).replace('\\', '_').replace('/', '_')
        name_parts.append(clean_kit)
    if part_folder and part_folder != base_name:
        name_parts.append(str(part_folder))
    name_parts.append(base_name)
    
    trash_name = "_".join(name_parts)
    trash_path = os.path.join(TRASH_DIR, trash_name)
    
    try:
        shutil.move(path, trash_path)
        print(f"DEBUG: Moved to trash: {path} -> {trash_path}")
    except Exception as e:
        print(f"ERROR: Failed to move to trash: {e}")
from delete_neka_part import delete_part
from zip_neka_kit import zip_kit


PORT = 8000

# ================= SECURITY UTILITIES =================
def safe_join(base, *paths):
    """Safely joins paths and ensures the result is within the base directory."""
    # Convert all to forward slashes for uniform processing
    clean_paths = [str(p).replace('\\', '/').lstrip('/') for p in paths]
    joined = os.path.abspath(os.path.join(base, *clean_paths))
    base_abs = os.path.abspath(base)
    
    # Ensure base ends with a separator for startswith check
    prefix = base_abs if base_abs.endswith(os.sep) else base_abs + os.sep
    
    if not (joined + os.sep).startswith(prefix):
        raise ValueError(f"Security violation: Path traversal detected ({joined} vs {prefix})")
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
    return bool(re.match(r"^[a-zA-Z0-9_\-\.\/]+$", str(id_str)))

def get_local_ip():
    """Gets the local IP address of the machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def natural_sort_key(s):
    """Sorts strings with numbers in natural order (e.g. '2.png' before '10.png')."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]

# ======================================================

class KitHandler(http.server.SimpleHTTPRequestHandler):
    def send_api_response(self, success, message, extra=None):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Cache-Control', 'public, max-age=31536000')
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
        
        elif parsed_path.path == '/api/get_ip':
            self.send_api_response(True, "Current IP retrieved", {"ip": get_local_ip()})
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

                    mimetypes.init()
                    mimetypes.add_type('image/webp', '.webp')
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
            '/api/merge_folders': self.handle_merge_folders,
            '/api/merge_multiple_folders': self.handle_merge_multiple_folders,
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
            '/api/create_nav': self.handle_create_nav,
            '/api/batch_delete_reorder': self.handle_batch_delete_reorder,
            '/api/crop_batch_thumbs': self.handle_crop_batch_thumbs,
            '/api/batch_merge_layers': self.handle_batch_merge_layers,
            '/api/reorder_parts': self.handle_reorder_parts,
            '/api/fix_color_code': self.handle_fix_color_code,
            '/api/fix_all_part_colors': self.handle_fix_all_part_colors,
            '/api/fix_colors_by_point': self.handle_fix_colors_by_point,
            '/api/reorder_images': self.handle_reorder_images,
            '/api/check_missing_thumbnails': self.handle_check_missing_thumbnails,
            '/api/check_corrupted_images': self.handle_check_corrupted_images,
            '/api/check_invalid_filenames': self.handle_check_invalid_filenames,
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

    def handle_check_corrupted_images(self, data):
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return
            
        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            if not os.path.exists(kit_path):
                self.send_api_response(False, "Kit not found")
                return
                
            corrupted_files = []
            import struct
            for root, dirs, files in os.walk(kit_path):
                for f in files:
                    if f.lower().endswith('.png'):
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, kit_path).replace('\\', '/')
                        
                        try:
                            with open(full_path, 'rb') as pf:
                                pf.seek(0, 2)
                                file_size = pf.tell()
                                if file_size < 12: continue
                                
                                pf.seek(0)
                                signature = pf.read(8)
                                if signature != b'\x89PNG\r\n\x1a\n': continue
                                
                                pos = 8
                                is_corrupted = False
                                while pos < file_size:
                                    pf.seek(pos)
                                    lb = pf.read(4)
                                    if len(lb) < 4: break
                                    l = struct.unpack('>I', lb)[0]
                                    ct = pf.read(4).decode('ascii', errors='ignore')
                                    pos += 8 + l + 4
                                    if ct == 'IEND':
                                        remaining = file_size - pos
                                        if remaining > 0:
                                            is_corrupted = True
                                        break
                                
                                if is_corrupted:
                                    corrupted_files.append(rel_path)
                        except Exception as e:
                            pass
                            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "success": True,
                "corrupted_files": corrupted_files
            })
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")

   



    def handle_get_kits_list(self, data):
        try:
            folder_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'folder.json')
            parent_folders = []
            if os.path.exists(folder_json_path):
                try:
                    with open(folder_json_path, 'r', encoding='utf-8') as f:
                        parent_folders = json.load(f)
                except:
                    parent_folders = []

            kits = []
            if parent_folders:
                for parent in parent_folders:
                    parent_path = safe_join(DATA_DIR, parent)
                    if os.path.exists(parent_path) and os.path.isdir(parent_path):
                        for entry in os.listdir(parent_path):
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
            
            # Always scan for loose kits directly in DATA_DIR ignoring parent folders
            if os.path.exists(DATA_DIR):
                for entry in os.listdir(DATA_DIR):
                    if parent_folders and entry in parent_folders:
                        continue # Skip parent directories (thuong, tram, etc.)
                        
                    full_path = os.path.join(DATA_DIR, entry)
                    if os.path.isdir(full_path):
                        if entry == "cache_blobs": continue
                        match = re.search(r"(\d+)$", entry)
                        kit_id = match.group(1) if match else entry
                        kits.append({
                            "id": kit_id,
                            "name": entry,
                            "folder": entry,
                            "parent": "Mặc định (Ngoài)"
                        })

            kits.sort(key=lambda x: x['name'])
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "success": True, 
                "kits": kits, 
                "parents": parent_folders
            })
            self.wfile.write(response.encode('utf-8'))
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")


    def handle_get_kit_structure(self, data):
        kit_folder = data.get('kit')
        print(f"DEBUG: Processing kit_structure for: {kit_folder}")
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return
        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            print(f"DEBUG: Kit path: {kit_path}")

            if not os.path.exists(kit_path):
                self.send_api_response(False, f"Kit structure not found at {kit_folder}")
                return
            
            separated_folders = []
            sep_layers_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_folders = json.load(f)
                except: pass

            meta_data = {}
            meta_path = os.path.join(kit_path, "metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta_data = json.load(f)
                except Exception as e:
                    print(f"Error loading metadata: {e}")

            parts = []
            for entry in os.listdir(kit_path):
                entry_path = os.path.join(kit_path, entry)
                if not os.path.isdir(entry_path): continue
                
                # print(f"DEBUG: Found folder entry: {entry}")
                match = re.match(r"^(\d+)-(\d+)(?:-(.*))?$", entry)
                if not match:
                    x, y = 9999, len(parts) + 1
                else:
                    x = int(match.group(1))
                    y = int(match.group(2))

                # --- Per-folder Analysis ---
                # Count layers and items per item from metadata
                item_layer_counts = {}
                expected_num_items = 0
                try:
                    if match:
                        part_idx_for_meta = y - 1
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
                thumb_pattern = re.compile(r"^thumb_(\d+)\.(png|webp)$")
                image_pattern = re.compile(r"^(\d+)\.(png|webp)$")
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
                except: pass

                # Also scan color subfolders to get max image count
                # (needed when root has no images/thumbs but color folders do)
                color_max_items = 0
                if colors and not image_indices:
                    color_img_pattern = re.compile(r"^(\d+)\.(png|webp)$")
                    for color_sub in colors:
                        color_sub_path = os.path.join(entry_path, color_sub)
                        try:
                            with os.scandir(color_sub_path) as cit:
                                for cf in cit:
                                    if cf.is_file():
                                        cm = color_img_pattern.match(cf.name)
                                        if cm:
                                            idx = int(cm.group(1))
                                            if idx > color_max_items:
                                                color_max_items = idx
                        except Exception:
                            pass

                num_items = max(expected_num_items, max(image_indices) if image_indices else 0, max(item_indices) if item_indices else 0, color_max_items)
                
                missing_images = []
                if not colors and image_indices:
                    max_img = max(image_indices)
                    for i in range(1, max_img + 1):
                        if i not in image_indices:
                            missing_images.append(i)

                color_gaps = {}
                color_image_counts = {}
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
                        color_image_counts[sub] = len(sub_indices)
                        if sub_indices:
                            gaps = [i for i in range(1, max(sub_indices) + 1) if i not in sub_indices]
                            if gaps: color_gaps[sub] = gaps
                
                parts.append({
                    "x": x, "y": y,
                    "folder": entry,
                    "display_name": entry, # Use full entry name
                    "items_count": num_items,
                    "colors": colors,
                    "is_separated": entry in separated_folders,
                    "has_colors": len(colors) > 0,
                    "missing_images": missing_images,
                    "color_gaps": color_gaps,
                    "color_image_counts": color_image_counts,
                    "item_layer_counts": item_layer_counts
                })

            # Check for duplicate X values (on merged parts)
            x_counts = {}
            for p in parts:
                x = p['x']
                if x != 9999:
                    if x not in x_counts: x_counts[x] = []
                    x_counts[x].append(p['folder'])
            
            duplicate_warnings = []
            for x, folders in x_counts.items():
                if len(folders) > 1:
                    duplicate_warnings.append(f"X={x}: {', '.join(folders)}")

            parts.sort(key=lambda p: p['y'])
            print(f"DEBUG: Found {len(parts)} parts for {kit_folder}", flush=True)

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
                "api_version": "v3-xyz-grouping",
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

        # Enforce X-Y(-Z) format
        if not re.match(r"^\d+-\d+(?:-.*)?$", new_name):
            self.send_api_response(False, "Tên mới phải đúng định dạng số X-Y (hoặc X-Y-Z) (VD: 100-51-test) để sắp xếp layer.")
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

            
            # Get part index from folder name (the second numeric part in X-Y-Z)
            match = re.match(r"^\d+-(\d+)(?:-.*)?$", folder_name)
            if not match:
                self.send_api_response(False, f"Invalid folder name format: {folder_name}")
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
                parent_files_to_check = ["nav.png", "nav.webp"]
                
                # Also check for ALL thumb_*.png in parent (since thumbnails are usually shared or stored in root)
                if os.path.exists(struct_base):
                    for entry in os.listdir(struct_base):
                        if entry in ["nav.png", "nav.webp"] or entry.startswith("thumb_"):
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
                img = img.resize((200, 200), Image.LANCZOS)
                img.save(target_path)
            
            self.send_api_response(True, f"Created {target_file}")

        except Exception as e:
             self.send_api_response(False, f"Error creating thumbnail: {str(e)}")

    def handle_create_nav(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        item_number = data.get('item_number')
        color = data.get('color')

        if not kit_folder or not folder_name:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, folder_name)
            
            source_path = None
            source_filename = None

            # 1. Ưu tiên tìm thumbnail (thumb_N.png) trước vì nó đã được resize/crop đẹp
            if item_number:
                thumb_name = f"thumb_{item_number}.png"
                potential_thumb = os.path.join(part_path, thumb_name)
                if os.path.exists(potential_thumb):
                    source_path = potential_thumb
                    source_filename = thumb_name
                else:
                    # Nếu không có thumbnail, mới tìm file ảnh gốc
                    search_id = str(item_number)
                    # Thử tìm trong color folder (nếu có chọn màu)
                    if color and color != 'default':
                        color_path = os.path.join(part_path, color)
                        if os.path.exists(color_path):
                            for ext in ['.png', '.webp']:
                                if os.path.exists(os.path.join(color_path, search_id + ext)):
                                    source_path = os.path.join(color_path, search_id + ext)
                                    source_filename = search_id + ext
                                    break
                    
                    # Nếu không thấy trong color folder, thử ở main folder
                    if not source_path:
                        for ext in ['.png', '.webp']:
                            if os.path.exists(os.path.join(part_path, search_id + ext)):
                                source_path = os.path.join(part_path, search_id + ext)
                                source_filename = search_id + ext
                                break

            # 2. Logic cũ (Fallback)
            if not source_path:
                if os.path.exists(os.path.join(part_path, "1.png")):
                    source_path = os.path.join(part_path, "1.png")
                    source_filename = "1.png"
                elif os.path.exists(os.path.join(part_path, "1.webp")):
                    source_path = os.path.join(part_path, "1.webp")
                    source_filename = "1.webp"

                if not source_path:
                    for entry in sorted(os.listdir(part_path)):
                        sub_path = os.path.join(part_path, entry)
                        if os.path.isdir(sub_path):
                            if os.path.exists(os.path.join(sub_path, "1.png")):
                                source_path = os.path.join(sub_path, "1.png")
                                source_filename = "1.png"
                                break
                            elif os.path.exists(os.path.join(sub_path, "1.webp")):
                                source_path = os.path.join(sub_path, "1.webp")
                                source_filename = "1.webp"
                                break

            if not source_path or not os.path.exists(source_path):
                self.send_api_response(False, "Không tìm thấy file ảnh nguồn phù hợp để làm nav")
                return
            
            # Determine target filename
            ext = os.path.splitext(source_filename)[1].lower()
            target_filename = f"nav{ext}"
            target_path = os.path.join(part_path, target_filename)
            
            # Copy source to nav
            shutil.copy2(source_path, target_path)
            
            self.send_api_response(True, f"Đã tạo {target_filename} từ {source_filename}", {"filename": target_filename})

        except Exception as e:
            self.send_api_response(False, f"Lỗi khi tạo nav: {str(e)}")

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

            move_to_trash(target_path, kit_folder=kit_folder, part_folder=folder_name)
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

    def handle_merge_folders(self, data):
        kit_folder = data.get('kit')
        folder1 = data.get('folder1')
        folder2 = data.get('folder2')
        new_folder = data.get('new_folder')

        if not kit_folder or not folder1 or not folder2 or not new_folder:
            self.send_api_response(False, "Thiếu tham số (kit, folder1, folder2, new_folder)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            path1 = safe_join(kit_path, folder1)
            path2 = safe_join(kit_path, folder2)
            path_new = safe_join(kit_path, new_folder)

            if not os.path.exists(path1) or not os.path.isdir(path1):
                self.send_api_response(False, f"Thư mục 1 '{folder1}' không tồn tại hoặc không phải là thư mục.")
                return

            if not os.path.exists(path2) or not os.path.isdir(path2):
                self.send_api_response(False, f"Thư mục 2 '{folder2}' không tồn tại hoặc không phải là thư mục.")
                return

            # Allow new_folder to equal folder1 or folder2, but if it's different and already exists, raise error
            if os.path.exists(path_new) and new_folder != folder1 and new_folder != folder2:
                self.send_api_response(False, f"Thư mục mới '{new_folder}' đã tồn tại. Vui lòng chọn tên khác.")
                return

            if not validate_id(new_folder):
                self.send_api_response(False, f"Tên thư mục mới '{new_folder}' không hợp lệ (chỉ chấp nhận chữ cái, số, gạch ngang, gạch dưới, chấm, slash).")
                return

            # Create a temporary directory for merging to avoid conflicts (especially when new_folder is one of the sources)
            path_new_tmp = os.path.join(kit_path, f"{new_folder}_merge_tmp_{os.getpid()}")
            if os.path.exists(path_new_tmp):
                shutil.rmtree(path_new_tmp)
            os.makedirs(path_new_tmp, exist_ok=True)

            def scan_image_indices(base_path):
                indices = set()
                # 1. Quét các file ở thư mục gốc của part
                for item in os.listdir(base_path):
                    item_path = os.path.join(base_path, item)
                    if os.path.isfile(item_path):
                        m = re.match(r"^(?:thumb_)?(\d+)\.(png|webp)$", item, re.IGNORECASE)
                        if m:
                            indices.add(int(m.group(1)))
                    elif os.path.isdir(item_path):
                        # Quét các file trong các thư mục màu con
                        for sub_item in os.listdir(item_path):
                            sub_item_path = os.path.join(item_path, sub_item)
                            if os.path.isfile(sub_item_path):
                                m = re.match(r"^(?:thumb_)?(\d+)\.(png|webp)$", sub_item, re.IGNORECASE)
                                if m:
                                    indices.add(int(m.group(1)))
                return sorted(list(indices))

            indices1 = scan_image_indices(path1)
            indices2 = scan_image_indices(path2)

            # Khởi tạo ánh xạ index cũ sang index mới tuần tự từ 1 đến N
            mapping1 = {old_idx: i + 1 for i, old_idx in enumerate(indices1)}
            offset = len(indices1)
            mapping2 = {old_idx: i + 1 + offset for i, old_idx in enumerate(indices2)}

            def copy_and_rename_by_index(src_dir, dst_dir, mapping):
                if not os.path.exists(src_dir):
                    return
                os.makedirs(dst_dir, exist_ok=True)
                for item in os.listdir(src_dir):
                    item_path = os.path.join(src_dir, item)
                    if os.path.isfile(item_path):
                        m = re.match(r"^(thumb_)?(\d+)\.(png|webp)$", item, re.IGNORECASE)
                        if m:
                            is_thumb = m.group(1) is not None
                            old_idx = int(m.group(2))
                            ext = m.group(3)
                            if old_idx in mapping:
                                new_idx = mapping[old_idx]
                                new_name = f"thumb_{new_idx}.{ext}" if is_thumb else f"{new_idx}.{ext}"
                                shutil.copy2(item_path, os.path.join(dst_dir, new_name))

            # 1. Copy Folder 1 files (gốc) sang thư mục tạm
            copy_and_rename_by_index(path1, path_new_tmp, mapping1)

            # 2. Copy Folder 2 files (gốc) sang thư mục tạm
            copy_and_rename_by_index(path2, path_new_tmp, mapping2)

            # 3. Quét tất cả các folder màu hiện có ở cả 2 bên
            color_subfolders = set()
            for item in os.listdir(path1) + os.listdir(path2):
                if os.path.isdir(os.path.join(path1, item)) and item != "cache_blobs":
                    color_subfolders.add(item)
                if os.path.isdir(os.path.join(path2, item)) and item != "cache_blobs":
                    color_subfolders.add(item)

            for color in color_subfolders:
                color_path1 = os.path.join(path1, color)
                color_path2 = os.path.join(path2, color)
                color_path_new = os.path.join(path_new_tmp, color)
                copy_and_rename_by_index(color_path1, color_path_new, mapping1)
                copy_and_rename_by_index(color_path2, color_path_new, mapping2)

            # 4. Copy tệp nav.png/nav.webp ngẫu nhiên từ một trong hai thư mục cũ nếu tồn tại
            nav_files = []
            for path_src in [path1, path2]:
                for ext in ["png", "webp"]:
                    nav_path = os.path.join(path_src, f"nav.{ext}")
                    if os.path.exists(nav_path) and os.path.isfile(nav_path):
                        nav_files.append(nav_path)
            
            if nav_files:
                import random
                selected_nav = random.choice(nav_files)
                ext = selected_nav.split('.')[-1]
                shutil.copy2(selected_nav, os.path.join(path_new_tmp, f"nav.{ext}"))

            # 5. Di chuyển 2 thư mục cũ vào thùng rác để dọn dẹp
            # Chú ý: Di chuyển trước khi đổi tên thư mục tạm để giải phóng tên (nếu new_folder trùng với folder1/folder2)
            move_to_trash(path1, kit_folder=kit_folder, part_folder=folder1)
            move_to_trash(path2, kit_folder=kit_folder, part_folder=folder2)

            # 6. Đổi tên thư mục tạm thành thư mục đích cuối cùng
            if os.path.exists(path_new):
                if os.path.isdir(path_new):
                    shutil.rmtree(path_new)
                else:
                    os.remove(path_new)
            shutil.move(path_new_tmp, path_new)

            # 7. Cập nhật file separated_layers.json nếu có
            sep_layers_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_layers = json.load(f)
                    
                    if not isinstance(separated_layers, list):
                        separated_layers = []

                    was_separated = (folder1 in separated_layers) or (folder2 in separated_layers)
                    new_sep_layers = [x for x in separated_layers if x != folder1 and x != folder2]
                    
                    if was_separated:
                        new_sep_layers.append(new_folder)
                    
                    with open(sep_layers_path, 'w', encoding='utf-8') as f:
                        json.dump(new_sep_layers, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"Error updating separated_layers.json: {e}")

            self.send_api_response(True, f"Gộp thành công thư mục '{folder1}' và '{folder2}' thành '{new_folder}'. Tổng số {len(indices1) + len(indices2)} ảnh.")

        except Exception as e:
            # Dọn dẹp thư mục tạm nếu có lỗi xảy ra
            try:
                if 'path_new_tmp' in locals() and os.path.exists(path_new_tmp):
                    shutil.rmtree(path_new_tmp)
            except:
                pass
            self.send_api_response(False, f"Lỗi trong quá trình gộp thư mục: {str(e)}")


    def handle_merge_multiple_folders(self, data):
        kit_folder = data.get('kit')
        folders = data.get('folders', []) # List of folders to merge, e.g. ["1-1-Hair", "2-2-HairBack"]
        new_folder_name = data.get('new_folder_name', '').strip()

        if not kit_folder or not folders or len(folders) < 2 or not new_folder_name:
            self.send_api_response(False, "Thiếu tham số hoặc danh sách thư mục cần gộp hợp lệ (< 2 thư mục)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            
            # Resolve physical paths and indices
            folder_info_list = []
            for f in folders:
                f_path = safe_join(kit_path, f)
                if not os.path.exists(f_path) or not os.path.isdir(f_path):
                    self.send_api_response(False, f"Thư mục '{f}' không tồn tại hoặc không phải là thư mục.")
                    return
                
                # Parse current X and Y from folder name
                match = re.match(r"^(\d+)-(\d+)(?:-(.*))?$", f)
                if not match:
                    self.send_api_response(False, f"Định dạng thư mục '{f}' không hợp lệ (phải là X-Y-Tên)")
                    return
                
                x = int(match.group(1))
                y = int(match.group(2))
                suffix = match.group(3) or ""
                
                folder_info_list.append({
                    'name': f,
                    'path': f_path,
                    'x': x,
                    'y': y,
                    'suffix': suffix
                })
            
            # Sort by Y ascending to find the insertion/merge point
            folder_info_list.sort(key=lambda item: item['y'])
            
            # Target position Y and X will take the values of the first folder in the sorted list
            target_y = folder_info_list[0]['y']
            target_x = folder_info_list[0]['x']
            
            # Assemble the new folder name
            new_folder = new_folder_name
            path_new = safe_join(kit_path, new_folder)
            
            # If new_folder already exists physically but is NOT one of the folders being merged
            if os.path.exists(path_new) and new_folder not in folders:
                self.send_api_response(False, f"Thư mục mới '{new_folder}' đã tồn tại vật lý. Vui lòng chọn tên khác.")
                return

            if not validate_id(new_folder):
                self.send_api_response(False, f"Tên thư mục mới '{new_folder}' chứa ký tự không hợp lệ.")
                return

            # Temporary merge directory to compile files
            path_new_tmp = os.path.join(kit_path, f"{new_folder}_merge_tmp_{os.getpid()}")
            if os.path.exists(path_new_tmp):
                shutil.rmtree(path_new_tmp)
            os.makedirs(path_new_tmp, exist_ok=True)

            # Helper to scan image indices inside a part directory
            def scan_image_indices(base_path):
                indices = set()
                if not os.path.exists(base_path) or not os.path.isdir(base_path):
                    return []
                for item in os.listdir(base_path):
                    item_path = os.path.join(base_path, item)
                    if os.path.isfile(item_path):
                        m = re.match(r"^(?:thumb_)?(\d+)\.(png|webp)$", item, re.IGNORECASE)
                        if m:
                            indices.add(int(m.group(1)))
                    elif os.path.isdir(item_path) and item != "cache_blobs":
                        for sub_item in os.listdir(item_path):
                            sub_item_path = os.path.join(item_path, sub_item)
                            if os.path.isfile(sub_item_path):
                                m = re.match(r"^(?:thumb_)?(\d+)\.(png|webp)$", sub_item, re.IGNORECASE)
                                if m:
                                    indices.add(int(m.group(1)))
                return sorted(list(indices))

            # Helper to copy and rename indices based on mapping
            def copy_and_rename_by_index(src_dir, dst_dir, mapping):
                if not os.path.exists(src_dir) or not os.path.isdir(src_dir):
                    return
                os.makedirs(dst_dir, exist_ok=True)
                for item in os.listdir(src_dir):
                    item_path = os.path.join(src_dir, item)
                    if os.path.isfile(item_path):
                        m = re.match(r"^(thumb_)?(\d+)\.(png|webp)$", item, re.IGNORECASE)
                        if m:
                            is_thumb = m.group(1) is not None
                            old_idx = int(m.group(2))
                            ext = m.group(3)
                            if old_idx in mapping:
                                new_idx = mapping[old_idx]
                                new_name = f"thumb_{new_idx}.{ext}" if is_thumb else f"{new_idx}.{ext}"
                                shutil.copy2(item_path, os.path.join(dst_dir, new_name))



            # Build sequential mappings for all folders being merged
            mappings = [] # list of dicts
            total_images_mapped = 0
            offset = 0
            
            for info in folder_info_list:
                indices = scan_image_indices(info['path'])
                mapping = {old_idx: i + 1 + offset for i, old_idx in enumerate(indices)}
                mappings.append(mapping)
                offset += len(indices)
                total_images_mapped += len(indices)

            # 1. Copy main folder files
            for idx, info in enumerate(folder_info_list):
                copy_and_rename_by_index(info['path'], path_new_tmp, mappings[idx])

            # 2. Gather and copy color subfolders
            color_subfolders = set()
            for info in folder_info_list:
                for item in os.listdir(info['path']):
                    sub_p = os.path.join(info['path'], item)
                    if os.path.isdir(sub_p) and item != "cache_blobs":
                        color_subfolders.add(item)

            for color in color_subfolders:
                for idx, info in enumerate(folder_info_list):
                    color_src = os.path.join(info['path'], color)
                    color_dst = os.path.join(path_new_tmp, color)
                    copy_and_rename_by_index(color_src, color_dst, mappings[idx])

            # 3. Copy nav.png/nav.webp from first folder that has it, fallback to others
            nav_copied = False
            for info in folder_info_list:
                for ext in ["png", "webp"]:
                    nav_path = os.path.join(info['path'], f"nav.{ext}")
                    if os.path.exists(nav_path) and os.path.isfile(nav_path):
                        shutil.copy2(nav_path, os.path.join(path_new_tmp, f"nav.{ext}"))
                        nav_copied = True
                        break
                if nav_copied:
                    break

            # 4. Synchronize metadata.json
            meta_path = os.path.join(kit_path, "metadata.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta_data = json.load(f)
                    
                    parts = meta_data.get('data', {}).get('parts', [])
                    
                    # Ensure indices map correctly
                    first_part_idx = folder_info_list[0]['y'] - 1
                    
                    if 0 <= first_part_idx < len(parts):
                        first_part = parts[first_part_idx]
                        merged_items = []
                        
                        # Accumulate all items in order
                        for info in folder_info_list:
                            part_idx = info['y'] - 1
                            if 0 <= part_idx < len(parts):
                                p_items = parts[part_idx].get('items', [])
                                merged_items.extend(p_items)
                        
                        # Update first part
                        first_part['items'] = merged_items
                        match_suffix = re.match(r"^\d+-\d+-(.*)$", new_folder_name)
                        suffix_name = match_suffix.group(1) if match_suffix else new_folder_name
                        first_part['name'] = suffix_name
                        
                        # Clear items lists of all other merged parts to mark them as empty
                        for info in folder_info_list[1:]:
                            part_idx = info['y'] - 1
                            if 0 <= part_idx < len(parts):
                                parts[part_idx]['items'] = []
                    
                    # Compact the parts array: remove any part that has items = []
                    indices_to_remove = [info['y'] - 1 for info in folder_info_list[1:]]
                    compacted_parts = [p for p_idx, p in enumerate(parts) if p_idx not in indices_to_remove]
                    
                    meta_data['data']['parts'] = compacted_parts
                    
                    with open(meta_path, 'w', encoding='utf-8') as f:
                        json.dump(meta_data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"ERROR: Failed to update metadata.json: {e}")

            # 5. Synchronize separated_layers.json
            sep_layers_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_layers = json.load(f)
                    if not isinstance(separated_layers, list):
                        separated_layers = []
                    
                    # Check if any of merged folders were separated
                    was_separated = any(info['name'] in separated_layers for info in folder_info_list)
                    # Remove all merged folders
                    new_sep_layers = [x for x in separated_layers if x not in [info['name'] for info in folder_info_list]]
                    if was_separated:
                        new_sep_layers.append(new_folder)
                    
                    with open(sep_layers_path, 'w', encoding='utf-8') as f:
                        json.dump(new_sep_layers, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"ERROR: Failed to update separated_layers.json: {e}")

            # 6. Safe swap with transaction (renaming to backup folders first)
            backups = []
            for info in folder_info_list:
                bak_path = f"{info['path']}_bak_{os.getpid()}"
                shutil.move(info['path'], bak_path)
                backups.append((bak_path, info['name']))
            
            try:
                # Place new merged folder
                if os.path.exists(path_new):
                    if os.path.isdir(path_new):
                        shutil.rmtree(path_new)
                    else:
                        os.remove(path_new)
                shutil.move(path_new_tmp, path_new)
                
                # Move backups to trash
                for bak_path, origin_name in backups:
                    move_to_trash(bak_path, kit_folder=kit_folder, part_folder=origin_name)
            except Exception as ex:
                # Rollback backups if moving path_new_tmp to path_new fails
                for bak_path, origin_name in backups:
                    if os.path.exists(bak_path):
                        shutil.move(bak_path, os.path.join(kit_path, origin_name))
                raise ex

            # 7. AUTOMATICALLY RE-INDEX X-Y FOR ALL REMAINING FOLDERS IN THE KIT (RELATIVE SHIFT)
            # Parse new folder coordinates to identify kept coordinates
            new_folder_x = None
            new_folder_y = None
            match_new = re.match(r"^(\d+)-(\d+)(?:-(.*))?$", new_folder)
            if match_new:
                new_folder_x = int(match_new.group(1))
                new_folder_y = int(match_new.group(2))

            deleted_coords = []
            for info in folder_info_list:
                # If this merged folder's coordinates match the new folder's coordinates, it's NOT deleted/vacated
                if new_folder_x is not None and new_folder_y is not None:
                    if info['x'] == new_folder_x and info['y'] == new_folder_y:
                        continue
                deleted_coords.append((info['x'], info['y']))

            remaining_folders = []
            for entry in os.listdir(kit_path):
                entry_path = os.path.join(kit_path, entry)
                if not os.path.isdir(entry_path) or entry == "cache_blobs" or entry == "items_merged":
                    continue
                # Skip the new folder to keep its name exactly as typed!
                if entry == new_folder:
                    continue
                match = re.match(r"^(\d+)-(\d+)(?:-(.*))?$", entry)
                if match:
                    x = int(match.group(1))
                    y = int(match.group(2))
                    suffix = match.group(3) or ""
                    remaining_folders.append({
                        'old_name': entry,
                        'old_path': entry_path,
                        'x': x,
                        'y': y,
                        'suffix': suffix
                    })
            
            # Sort by (y, x) ascending to rename lower indices first, avoiding conflicts when shifting down
            remaining_folders.sort(key=lambda item: (item['y'], item['x']))
            
            # Calculate new shifted coordinates and rename
            renamed_map = {} # old_name -> new_name
            for info in remaining_folders:
                new_x = info['x'] - sum(1 for dx, dy in deleted_coords if dx < info['x'])
                new_y = info['y'] - sum(1 for dx, dy in deleted_coords if dy < info['y'])
                
                new_name = f"{new_x}-{new_y}"
                if info['suffix']:
                    new_name += f"-{info['suffix']}"
                
                renamed_map[info['old_name']] = new_name
                
                if info['old_name'] != new_name:
                    old_p = info['old_path']
                    new_p = os.path.join(kit_path, new_name)
                    
                    if os.path.exists(new_p):
                        move_to_trash(new_p, kit_folder=kit_folder)
                        time.sleep(0.1)
                    
                    try:
                        shutil.move(old_p, new_p)
                    except Exception as e:
                        print(f"WARNING: Rename failed, retrying: {e}")
                        time.sleep(0.5)
                        shutil.move(old_p, new_p)
            
            # 8. Update separated_layers.json again with the final renamed folder names
            if os.path.exists(sep_layers_path):
                try:
                    with open(sep_layers_path, 'r', encoding='utf-8') as f:
                        separated_layers = json.load(f)
                    
                    final_sep_layers = []
                    for folder_name in separated_layers:
                        if folder_name in renamed_map:
                            final_sep_layers.append(renamed_map[folder_name])
                        else:
                            final_sep_layers.append(folder_name)
                    
                    with open(sep_layers_path, 'w', encoding='utf-8') as f:
                        json.dump(final_sep_layers, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"ERROR: Failed to finalize separated_layers.json: {e}")

            self.send_api_response(True, f"Gộp thành công {len(folders)} thư mục bộ phận thành '{new_folder}' và tự động đánh lại số thứ tự X-Y.")

        except Exception as e:
            try:
                if 'path_new_tmp' in locals() and os.path.exists(path_new_tmp):
                    shutil.rmtree(path_new_tmp)
            except:
                pass
            import traceback
            print(traceback.format_exc())
            self.send_api_response(False, f"Lỗi khi gộp nhiều thư mục: {str(e)}")


    def handle_merge_layers(self, data):
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
                        
                        match = re.match(r"^\d+-(\d+)(?:-.*)?$", folder_name)
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

                            match = re.match(r"^\d+-(\d+)(?:-.*)?$", folder_name)
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
                                # Only apply offsets if the image is not already full-size
                                if fn in offsets:
                                    w, h = l_img.size
                                    if w < ow and h < oh:
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
                                move_to_trash(p, kit_folder=kit_folder, part_folder=folder_name)
                            if is_default_color:
                                match = re.match(r"^(\d+)\.png$", fn)
                                if match:
                                    tid = match.group(1)
                                    tp = os.path.join(src, f"thumb_{tid}.png")
                                    if os.path.exists(tp):
                                        move_to_trash(tp, kit_folder=kit_folder, part_folder=folder_name)
                        except Exception as e:
                            print(f"[Merge] Warning: Could not delete {fn}: {e}")
                    
                    final_path = os.path.join(src, f"{target_fn}.png")
                    if os.path.exists(final_path):
                        try: move_to_trash(final_path, kit_folder=kit_folder, part_folder=folder_name)
                        except: pass
                    
                    try:
                        os.rename(temp_path, final_path)
                    except Exception as e:
                        shutil.copy2(temp_path, final_path)
                        move_to_trash(temp_path, kit_folder=kit_folder, part_folder=folder_name)

                    if is_default_color:
                        try:
                            thumb = img.copy()
                            thumb = thumb.resize((200, 200), Image.LANCZOS)
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

    def handle_batch_merge_layers(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        tasks = data.get('tasks', []) # List of {selected_files, destination_name, layer_adjustments, offsets}
        color = data.get('color', 'default')
        bulk_apply = data.get('bulk_apply', False)

        if not kit_folder or not folder_name or not tasks:
            self.send_api_response(False, "Missing parameters (need kit, folder, tasks)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            structured_dir = safe_join(kit_path, folder_name)
            if not os.path.exists(structured_dir):
                self.send_api_response(False, "Folder not found")
                return

            # Helper functions (duplicated for scope/simplicity in this context or could be moved to class level)
            def apply_color_transform(img, target_color=None, saturation=1.0, brightness=1.0):
                if img.mode != 'RGBA': img = img.convert('RGBA')
                r, g, b, a = img.split()
                if target_color:
                    if isinstance(target_color, str):
                        target_color = target_color.lstrip('#')
                        target_r = int(target_color[0:2], 16) if len(target_color) == 6 else 255
                        target_g = int(target_color[2:4], 16) if len(target_color) == 6 else 255
                        target_b = int(target_color[4:6], 16) if len(target_color) == 6 else 255
                    else: target_r, target_g, target_b = target_color
                    gray_img = Image.merge('RGB', (r, g, b)).convert('L')
                    gray_array = np.array(gray_img).astype(float) / 255.0
                    r_new = (gray_array * target_r).astype('uint8')
                    g_new = (gray_array * target_g).astype('uint8')
                    b_new = (gray_array * target_b).astype('uint8')
                    rgb_img = Image.merge('RGB', (Image.fromarray(r_new), Image.fromarray(g_new), Image.fromarray(b_new)))
                else: rgb_img = Image.merge('RGB', (r, g, b))
                if brightness != 1.0: rgb_img = ImageEnhance.Brightness(rgb_img).enhance(brightness)
                if saturation != 1.0: rgb_img = ImageEnhance.Color(rgb_img).enhance(saturation)
                return Image.merge('RGBA', (*rgb_img.split(), a))

            def perform_merge(src, target_fn, files_to_stack, is_default_color, layer_adjustments, offsets, canvas_width=1436, canvas_height=1902):
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
                                if layer_adjustments and fn in layer_adjustments:
                                    adj = layer_adjustments[fn]
                                    l_img = apply_color_transform(l_img, adj.get('target_color'), adj.get('saturation', 1.0), adj.get('brightness', 1.0))
                                x, y = 0, 0
                                # Only apply offsets if the image is not already full-size
                                if fn in offsets:
                                    w, h = l_img.size
                                    if w < ow and h < oh:
                                        x = offsets[fn]['x']; y = offsets[fn]['y']
                                img.paste(l_img.convert("RGBA"), (x, y), l_img.convert("RGBA"))
                            valid_merge = True
                        except Exception as e: print(f"[BatchMerge] Error loading {p}: {e}")
                if valid_merge:
                    temp_fn = f"_tmp_batch_{target_fn}.png"
                    temp_path = os.path.join(src, temp_fn)
                    img.save(temp_path)
                    for fn in files_to_stack:
                        try:
                            p = os.path.join(src, fn)
                            if os.path.exists(p): move_to_trash(p, kit_folder=kit_folder, part_folder=folder_name)
                            if is_default_color:
                                match = re.match(r"^(\d+)\.png$", fn)
                                if match:
                                    tp = os.path.join(src, f"thumb_{match.group(1)}.png")
                                    if os.path.exists(tp): move_to_trash(tp, kit_folder=kit_folder, part_folder=folder_name)
                        except: pass
                    final_path = os.path.join(src, f"{target_fn}.png")
                    if os.path.exists(final_path):
                        try: move_to_trash(final_path, kit_folder=kit_folder, part_folder=folder_name)
                        except: pass
                    try: os.rename(temp_path, final_path)
                    except: shutil.copy2(temp_path, final_path); move_to_trash(temp_path, kit_folder=kit_folder, part_folder=folder_name)
                    if is_default_color:
                        thumb = img.copy(); thumb = thumb.resize((200, 200), Image.LANCZOS); thumb.save(os.path.join(src, f"thumb_{target_fn}.png"))
                    return True
                return False

            # Load metadata for offsets and canvas size
            canvas_width, canvas_height = 1436, 1902 # Defaults
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
                        match = re.match(r"^\d+-(\d+)(?:-.*)?$", folder_name)
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
                            match = re.match(r"^\d+-(\d+)(?:-.*)?$", folder_name)
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
                print(f"[BatchMerge] Metadata/Config error: {e}")

            results_count = 0
            is_default = (not color or color == 'default')
            
            for task in tasks:
                dest_name = task.get('destination_name', '1')
                selected_files = task.get('selected_files', [])
                task_layer_adj = task.get('layer_adjustments', {})
                task_offsets_frontend = task.get('offsets', {})
                
                # Merge: Frontend offsets win, then local detected ones
                task_offsets = local_offsets.copy()
                task_offsets.update(task_offsets_frontend)

                target_src = structured_dir
                if color and color != 'default': target_src = os.path.join(structured_dir, color)
                
                if perform_merge(target_src, dest_name, selected_files, is_default, task_layer_adj, task_offsets, canvas_width, canvas_height):
                    results_count += 1
                
                if bulk_apply:
                    if not is_default:
                        perform_merge(structured_dir, dest_name, selected_files, True, task_layer_adj, task_offsets, canvas_width, canvas_height)
                    for d in os.listdir(structured_dir):
                        sub = os.path.join(structured_dir, d)
                        if os.path.isdir(sub) and (not color or d != color):
                            perform_merge(sub, dest_name, selected_files, False, task_layer_adj, task_offsets, canvas_width, canvas_height)

            self.send_api_response(True, f"Đã hoàn thành {len(tasks)} lệnh ghép trong {results_count} thư mục.")
        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Batch Merge Error: {str(e)}")

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
                match = re.search(r"^(\d+)\.(png|webp)$", f) # Support webp
                if match: indices.append(int(match.group(1)))
            
            next_idx = max(indices) + 1 if indices else 1
            moved_count = 0

            for old_path in images_to_move:
                # Determine original extension
                _, ext = os.path.splitext(old_path)
                ext = ext.lstrip('.') # Remove leading dot

                new_fn = f"{next_idx}.{ext}"
                new_path = os.path.join(target_dir, new_fn)
                
                # Check if new_path exists (unlikely given logic)
                while os.path.exists(new_path):
                    next_idx += 1
                    new_fn = f"{next_idx}.{ext}"
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

    def handle_fix_color_code(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')
        color_folder = data.get('color')

        if not kit_folder or not part_folder or not color_folder or color_folder == "default":
            self.send_api_response(False, "Missing or invalid parameters")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            target_dir = safe_join(kit_path, part_folder, color_folder)

            if not os.path.exists(target_dir):
                self.send_api_response(False, "Folder not found")
                return

            # Find a representative image (usually 1.png)
            img_files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.webp'))]
            if not img_files:
                self.send_api_response(False, "No images found in folder to analyze.")
                return
            
            # Prefer 1.png if available, otherwise pick the first one
            rep_img = "1.png" if "1.png" in img_files else img_files[0]
            img_path = os.path.join(target_dir, rep_img)

            # Analyze color
            detected_hex = self.get_dominant_color(img_path)
            if not detected_hex:
                self.send_api_response(False, "Could not detect color from image (maybe it is too transparent).")
                return

            if detected_hex.upper() == color_folder.split('_')[0].upper():
                self.send_api_response(True, f"Mã màu hiện tại ({color_folder}) đã chính xác.", {"detected": detected_hex})
                return

            # Rename logic
            new_name = detected_hex.upper()
            
            # Check collisions
            base_part_path = os.path.join(kit_path, part_folder)
            temp_name = new_name
            counter = 2
            while os.path.exists(os.path.join(base_part_path, temp_name)):
                if temp_name.upper() == color_folder.upper(): # It's the same folder (case insensitive or already matched)
                    break
                temp_name = f"{new_name}_{counter}"
                counter += 1
            
            new_name = temp_name
            
            if new_name.upper() == color_folder.upper():
                self.send_api_response(True, f"Mã màu hiện tại ({color_folder}) đã chính xác (chỉ khác hoa/thường).", {"detected": detected_hex})
                return

            # Physical rename
            new_path = os.path.join(base_part_path, new_name)
            shutil.move(target_dir, new_path)

            self.send_api_response(True, f"Đã đổi tên folder từ {color_folder} thành {new_name}", {
                "old_name": color_folder,
                "new_name": new_name,
                "detected": detected_hex
            })

        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Fix color error: {str(e)}")

    def handle_fix_all_part_colors(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')

        if not kit_folder or not part_folder:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, part_folder)

            if not os.path.exists(part_path):
                self.send_api_response(False, "Part folder not found")
                return

            changes = []
            errors = []
            
            # Scan for color subfolders
            subfolders = [f for f in os.listdir(part_path) if os.path.isdir(os.path.join(part_path, f))]
            
            # Skip architectural folders
            skip_folders = ["items_merged", "cache_blobs"]
            
            # Sort manually for consistent processing
            subfolders.sort()

            for color_folder in subfolders:
                if color_folder in skip_folders or color_folder == "default":
                    continue
                
                # Check if it looks like a hex code (or hex_N)
                # But even if it doesn't, we want to fix it anyway.
                
                target_dir = os.path.join(part_path, color_folder)
                
                # Find image
                img_files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.webp'))]
                if not img_files:
                    continue # Empty or non-image folder
                
                rep_img = "1.png" if "1.png" in img_files else img_files[0]
                img_path = os.path.join(target_dir, rep_img)
                
                detected_hex = self.get_dominant_color(img_path)
                if not detected_hex:
                    errors.append(f"{color_folder}: Could not detect color")
                    continue
                
                if detected_hex.upper() == color_folder.split('_')[0].upper():
                    continue # Correct already
                
                new_name = detected_hex.upper()
                
                # Collision handling
                temp_name = new_name
                counter = 2
                while os.path.exists(os.path.join(part_path, temp_name)):
                    if temp_name.upper() == color_folder.upper():
                        break
                    temp_name = f"{new_name}_{counter}"
                    counter += 1
                
                new_name = temp_name
                
                if new_name.upper() == color_folder.upper():
                    continue

                # Rename
                new_path = os.path.join(part_path, new_name)
                try:
                    shutil.move(target_dir, new_path)
                    changes.append({"old": color_folder, "new": new_name})
                except Exception as e:
                    errors.append(f"{color_folder}: {str(e)}")

            self.send_api_response(True, f"Đã xử lý xong toàn bộ màu của {part_folder}.", {
                "changes": changes,
                "errors": errors,
                "processed_count": len(changes)
            })

        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Fix all colors error: {str(e)}")

    def handle_fix_colors_by_point(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')
        x = data.get('x')
        y = data.get('y')
        filename = data.get('filename', '1.png')

        if not kit_folder or not part_folder or x is None or y is None:
            self.send_api_response(False, "Missing parameters")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, part_folder)

            if not os.path.exists(part_path):
                self.send_api_response(False, "Part folder not found")
                return

            changes = []
            errors = []
            
            subfolders = [f for f in os.listdir(part_path) if os.path.isdir(os.path.join(part_path, f))]
            skip_folders = ["items_merged", "cache_blobs"]
            subfolders.sort()

            for color_folder in subfolders:
                if color_folder in skip_folders or color_folder == "default":
                    continue
                
                target_dir = os.path.join(part_path, color_folder)
                img_path = os.path.join(target_dir, filename)
                
                # Check for same name with different extension if primary not found
                if not os.path.exists(img_path):
                    base_fn, _ = os.path.splitext(filename)
                    for ext in ['.png', '.webp', '.jpg']:
                        alt_path = os.path.join(target_dir, f"{base_fn}{ext}")
                        if os.path.exists(alt_path):
                            img_path = alt_path
                            break
                
                if not os.path.exists(img_path):
                    errors.append(f"{color_folder}: File {filename} not found")
                    continue

                try:
                    with Image.open(img_path) as img:
                        img = img.convert("RGBA")
                        width, height = img.size
                        
                        # Ensure coordinates are within bounds
                        if x < 0 or x >= width or y < 0 or y >= height:
                            errors.append(f"{color_folder}: Coordinates ({x}, {y}) out of bounds for size {width}x{height}")
                            continue
                            
                        pixel = img.getpixel((int(x), int(y)))
                        if pixel[3] < 5: # Transparent
                            errors.append(f"{color_folder}: Pixel at ({x}, {y}) is transparent")
                            continue
                            
                        # Format as Hex
                        detected_hex = '{:02x}{:02x}{:02x}'.format(pixel[0], pixel[1], pixel[2]).upper()
                        
                        if detected_hex == color_folder.split('_')[0].upper():
                            continue 
                        
                        new_name = detected_hex
                        
                        # Collision handling
                        temp_name = new_name
                        counter = 2
                        while os.path.exists(os.path.join(part_path, temp_name)):
                            if temp_name.upper() == color_folder.upper():
                                break
                            temp_name = f"{new_name}_{counter}"
                            counter += 1
                        
                        new_name = temp_name
                        
                        if new_name.upper() == color_folder.upper():
                            continue

                        shutil.move(target_dir, os.path.join(part_path, new_name))
                        changes.append({"old": color_folder, "new": new_name})
                except Exception as e:
                    errors.append(f"{color_folder}: {str(e)}")

            self.send_api_response(True, f"Đã xử lý xong toàn bộ màu theo điểm ({x}, {y}).", {
                "changes": changes,
                "errors": errors,
                "processed_count": len(changes)
            })

        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Fix colors by point error: {str(e)}")

    def get_dominant_color(self, image_path):
        """Analyzes an image to find the most representative (fill) color by ignoring outlines/highlights."""
        try:
            with Image.open(image_path) as img:
                img = img.convert("RGBA")
                # Resize if the image is unusually large, but Neka parts are usually small
                pixels = np.array(img)
                pixels = pixels.reshape(-1, 4)
                
                # Filter out transparent pixels (alpha < 50)
                visible_pixels = pixels[pixels[:, 3] > 50]
                if len(visible_pixels) == 0:
                    return None
                
                # Get RGB components
                rgb = visible_pixels[:, :3].astype(np.float32)
                
                # Calculate brightness (Sum of RGB)
                brightness = np.sum(rgb, axis=1)
                
                # Sort indices by brightness
                sort_indices = np.argsort(brightness)
                
                # We want to focus on the 'middle' colors (the fill)
                # Ignore the darkest 20% (usually black/dark outlines)
                # Ignore the brightest 10% (usually white highlights or near-white)
                start_idx = int(len(rgb) * 0.20)
                end_idx = int(len(rgb) * 0.90)
                
                if end_idx > start_idx:
                    fill_pixels = rgb[sort_indices[start_idx:end_idx]]
                    # Use Median of the fill pixels to get the most representative color
                    main_color = np.median(fill_pixels, axis=0)
                else:
                    # Fallback if too few pixels
                    main_color = np.median(rgb, axis=0)
                    
                hex_color = '{:02X}{:02X}{:02X}'.format(int(main_color[0]), int(main_color[1]), int(main_color[2]))
                return hex_color
        except Exception as e:
            print(f"Color detection error: {e}")
            return None

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
                if f.lower().endswith(('.png', '.webp')) and not f.startswith('nav.') and not f.startswith('thumb_'): # Support webp
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
            print(f"Zip Kit Error: {e}")
            traceback.print_exc()
            try: self.send_api_response(False, f"Server Error creating zip: {str(e)}")
            except: pass

    def handle_download_kit(self, data):
            kit_id = data.get('id')
            custom_path = data.get('path') # Get custom path from frontend
            if not kit_id:
                self.send_api_response(False, "Missing 'id' parameter")
                return

            try:
                # Cleanup old progress
                temp_dir = tempfile.gettempdir()
                progress_file = os.path.join(temp_dir, f"progress_{kit_id}.json")
                if os.path.exists(progress_file):
                    os.remove(progress_file)

                # Determine download base directory
                output_base = custom_path if custom_path else DATA_DIR

                # Gọi script download_neka_kit.py với tham số --out
                cmd = ['python', 'download_neka_kit.py', str(kit_id)]
                if custom_path:
                    cmd.extend(['--out', custom_path])
                
                subprocess.run(cmd, check=True)

                # Đường dẫn thư mục sau khi tải
                kit_folder = f'neka_{kit_id}'
                kit_path = os.path.join(output_base, kit_folder)
                
                if not os.path.exists(kit_path):
                    self.send_api_response(False, f"Không tìm thấy dữ liệu cho kit {kit_id} tại {kit_path}")
                    return

                # Tạo file ZIP để tải về (Lưu zip vào temp hoặc ngay tại đó)
                zip_path = os.path.join(output_base, f"{kit_folder}.zip")
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

                # Cleanup progress
                if os.path.exists(progress_file):
                    try: os.remove(progress_file)
                    except: pass
                
                # Cleanup zip if needed
                # os.remove(zip_path)

            except subprocess.CalledProcessError as e:
                print(f"Download script failed with code {e.returncode}")
                self.send_api_response(False, f"Lỗi khi chạy script tải: {e}")
            except Exception as e:
                print(f"Download handler error: {e}")
                traceback.print_exc()
                self.send_api_response(False, f"Server error: {str(e)}")

    def handle_rename_color_folder(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')
        old_color = data.get('old_color')
        new_color = data.get('new_color')

        if not kit_folder or not part_folder or not old_color or not new_color:
            self.send_api_response(False, "Missing parameters (kit, part_folder, colors)")
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
                        move_to_trash(color_path, kit_folder=kit_folder, part_folder=part_folder)
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
        
        # Scan folders
        folders_to_scan = []
        target_folder = data.get('folder')
        
        if target_folder:
            if os.path.isdir(os.path.join(kit_path, target_folder)):
                folders_to_scan.append(target_folder)
            else:
                return self.send_api_response(False, f"Folder {target_folder} not found in kit")
        else:
            # Original logic: Scan all folders X-Y
            for entry in os.listdir(kit_path):
                if re.match(r"^\d+-\d+(?:-.*)?$", entry) and os.path.isdir(os.path.join(kit_path, entry)):
                    folders_to_scan.append(entry)
        
        for entry in folders_to_scan:
            entry_path = os.path.join(kit_path, entry)
            
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
                    # Check for N.png or N.webp
                    match = re.match(r"^(\d+)\.(png|webp)$", filename, re.IGNORECASE)
                    if match:
                        num = match.group(1)
                        # If we haven't found a source for this number yet, record it
                        # Prioritize root images? os.walk yields root first, so yes.
                        if num not in found_images:
                            found_images[num] = os.path.join(root, filename)

            # Now process the found images
            for num, source_path in found_images.items():
                thumb_name = f"thumb_{num}.png" # Thumbs are always PNG
                thumb_path = os.path.join(entry_path, thumb_name)
                
                results["total_images"] += 1
                
                # Create thumbnail
                try:
                    with Image.open(source_path) as img:
                        # Standardize to 1436x1902 to ensure consistent item sizes in thumbnails
                        # (Matches the main canvas stretching behavior)
                        std_w, std_h = 1436, 1902
                        if img.width != std_w or img.height != std_h:
                            # Use LANCZOS for high-quality down/up scaling
                            img = img.resize((std_w, std_h), Image.LANCZOS)
                        
                        img = img.resize((200, 200), Image.LANCZOS)
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
        
        # Scan folders to delete thumbs
        folders_to_scan = []
        target_folder = data.get('folder')
        
        if target_folder:
            if os.path.isdir(os.path.join(kit_path, target_folder)):
                folders_to_scan.append(target_folder)
            else:
                return self.send_api_response(False, f"Folder {target_folder} not found in kit")
        else:
            # Original logic: Scan all folders X-Y
            for entry in os.listdir(kit_path):
                if re.match(r"^\d+-\d+(?:-.*)?$", entry) and os.path.isdir(os.path.join(kit_path, entry)):
                    folders_to_scan.append(entry)
        
        for entry in folders_to_scan:
            entry_path = os.path.join(kit_path, entry)
            
            # Find all thumb_*.png files
            thumb_pattern = re.compile(r"^thumb_(\d+)\.(png|webp)$", re.IGNORECASE) # Support webp
            for filename in os.listdir(entry_path):
                if thumb_pattern.match(filename):
                    file_path = os.path.join(entry_path, filename)
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")
        
        return self.send_api_response(True, f"Đã xóa thành công {deleted_count} thumbnail.")

    def handle_crop_batch_thumbs(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder') # Part folder
        color = data.get('color')
        crop_x = int(data.get('x', 0))
        crop_y = int(data.get('y', 0))
        crop_w = int(data.get('width', 44))
        crop_h = int(data.get('height', 44))
        item_no = data.get('item_no') # Optional: only crop this item if provided

        if not kit_folder or not folder_name or not color:
            return self.send_api_response(False, "Missing parameters (kit, folder, color)")

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, folder_name)
            if color == 'default':
                color_path = part_path
            else:
                color_path = safe_join(part_path, color)

            if not os.path.exists(color_path):
                return self.send_api_response(False, f"Color folder not found: {color}")

            # Find images
            image_pattern = re.compile(r"^(\d+)\.(png|webp)$", re.IGNORECASE)
            processed_count = 0
            
            for filename in os.listdir(color_path):
                match = image_pattern.match(filename)
                if match:
                    num = match.group(1)
                    
                    # If item_no is provided, skip others
                    if item_no is not None and str(num) != str(item_no):
                        continue
                        
                    source_path = os.path.join(color_path, filename)
                    target_path = os.path.join(part_path, f"thumb_{num}.png") # Thumbs are always PNG

                    try:
                        with Image.open(source_path) as img:
                            # Crop: (left, top, right, bottom)
                            box = (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)
                            cropped_img = img.crop(box)
                            # Standardize to 200x200
                            cropped_img = cropped_img.resize((200, 200), Image.LANCZOS)
                            # Save as thumbnail in part folder
                            cropped_img.save(target_path)
                            processed_count += 1
                    except Exception as e:
                        print(f"Error processing {filename}: {e}")

            return self.send_api_response(True, f"Đã tạo thành công {processed_count} thumbnail vào folder bộ phận.")

        except Exception as e:
            return self.send_api_response(False, f"Lỗi phía server: {str(e)}")

    def handle_upload_file(self, data):
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
            if color and color != 'default' and not filename.startswith('nav.'): # nav.png/webp always in root
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

    def handle_batch_delete_reorder(self, data):
        kit_folder = data.get('kit')
        folder_name = data.get('folder')
        target_indices = data.get('indices', []) # List of integers to delete
        apply_all = data.get('apply_all', True)  # Default to True for backward compatibility
        current_color = data.get('color')        # Optional, used if apply_all is False

        if not kit_folder or not folder_name or not target_indices:
            self.send_api_response(False, "Missing parameters (kit, folder, indices)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, folder_name)

            if not os.path.exists(part_path):
                self.send_api_response(False, "Part folder not found")
                return

            # Convert to set for faster lookup
            to_delete = {int(i) for i in target_indices}
            
            # Identify directories to process
            dirs_to_process = []
            if apply_all:
                dirs_to_process.append(part_path)
                for entry in os.listdir(part_path):
                    sub = os.path.join(part_path, entry)
                    if os.path.isdir(sub):
                        dirs_to_process.append(sub)
            else:
                # Only process specific folder
                target_dir = part_path
                if current_color and current_color != 'default':
                    target_dir = safe_join(part_path, current_color)
                
                if os.path.exists(target_dir):
                    dirs_to_process.append(target_dir)
                else:
                    self.send_api_response(False, f"Target directory not found: {target_dir}")
                    return

            image_pattern = re.compile(r"^(\d+)\.(png|webp)$", re.IGNORECASE) # Support webp
            thumb_pattern = re.compile(r"^thumb_(\d+)\.(png|webp)$", re.IGNORECASE) # Support webp

            processed_dirs = 0
            
            for target_dir in dirs_to_process:
                is_root = (target_dir == part_path)
                
                # 1. Delete target files
                for entry in os.listdir(target_dir):
                    m_img = image_pattern.match(entry)
                    if m_img:
                        idx = int(m_img.group(1))
                        if idx in to_delete:
                            try: move_to_trash(os.path.join(target_dir, entry), kit_folder=kit_folder, part_folder=folder_name)
                            except: pass
                    
                    if is_root:
                        m_thumb = thumb_pattern.match(entry)
                        if m_thumb:
                            idx = int(m_thumb.group(1))
                            if idx in to_delete:
                                try: move_to_trash(os.path.join(target_dir, entry), kit_folder=kit_folder, part_folder=folder_name)
                                except: pass

                # 2. Reorder remaining files
                # Collect remaining number images
                remaining_files = [] # List of (index, extension)
                for entry in os.listdir(target_dir):
                    m = image_pattern.match(entry)
                    if m:
                        remaining_files.append((int(m.group(1)), m.group(2).lower()))
                
                remaining_files.sort(key=lambda x: x[0])
                
                # Rename them to 1.ext, 2.ext...
                for new_idx, (old_idx, ext) in enumerate(remaining_files, 1):
                    if new_idx == old_idx: continue # Already correct
                    
                    old_img_name = f"{old_idx}.{ext}"
                    new_img_name = f"{new_idx}.{ext}"
                    
                    try:
                        os.rename(os.path.join(target_dir, old_img_name), 
                                  os.path.join(target_dir, new_img_name))
                    except Exception as e:
                        print(f"Error reordering {old_img_name} to {new_img_name} in {target_dir}: {e}")
                    
                    # Also reorder thumbs if in root
                    if is_root:
                        # Check for thumb with any image extension
                        for t_ext in ["png", "webp"]:
                            old_thumb_name = f"thumb_{old_idx}.{t_ext}"
                            new_thumb_name = f"thumb_{new_idx}.{t_ext}"
                            if os.path.exists(os.path.join(target_dir, old_thumb_name)):
                                try:
                                    os.rename(os.path.join(target_dir, old_thumb_name), 
                                              os.path.join(target_dir, new_thumb_name))
                                except: pass
                
                processed_dirs += 1

            self.send_api_response(True, f"Đã xóa {len(to_delete)} ảnh và sắp xếp lại {processed_dirs} thư mục.")

        except Exception as e:
            self.send_api_response(False, f"Lỗi xử lý hàng loạt: {str(e)}")


    def handle_reorder_parts(self, data):
        kit_folder = data.get('kit')
        renames = data.get('renames') # List of {"old": "...", "new": "..."}

        if not kit_folder or not renames:
            self.send_api_response(False, "Missing parameters (kit or renames)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            if not os.path.exists(kit_path):
                self.send_api_response(False, "Kit not found")
                return

            # 1. Validation: check if all old paths exist
            for r in renames:
                old_path = os.path.join(kit_path, r['old'])
                if not os.path.exists(old_path):
                    self.send_api_response(False, f"Folder not found: {r['old']}")
                    return

            # 2. First pass: Rename to temporary names to avoid conflicts (e.g. swapping A and B)
            temp_renames = []
            for i, r in enumerate(renames):
                old_path = os.path.join(kit_path, r['old'])
                temp_name = f"{r['old']}.{i}.tmp"
                temp_path = os.path.join(kit_path, temp_name)
                
                # If temp path exists (unlikely), find a unique one
                counter = 0
                while os.path.exists(temp_path):
                    temp_name = f"{r['old']}.{i}.{counter}.tmp"
                    temp_path = os.path.join(kit_path, temp_name)
                    counter += 1
                
                shutil.move(old_path, temp_path)
                temp_renames.append({"temp": temp_name, "final": r['new']})

                # Also handle merged folder if exists
                merged_base = os.path.join(kit_path, "items_merged")
                old_merged = os.path.join(merged_base, r['old'])
                if os.path.exists(old_merged):
                    temp_merged = os.path.join(merged_base, f"{r['old']}.{i}.tmp")
                    shutil.move(old_merged, temp_merged)

            # 3. Second pass: Rename from temporary name to final name
            for r in temp_renames:
                temp_path = os.path.join(kit_path, r['temp'])
                final_path = os.path.join(kit_path, r['final'])
                
                # Security: ensure final path doesn't already exist unless it was one of the renamed folders
                # Because we used .tmp, it should be safe unless there's an unrelated folder with the same name.
                if os.path.exists(final_path):
                     # This shouldn't happen if the client sent a valid reordering plan, 
                     # but let's be safe.
                     self.send_api_response(False, f"Conflict: Final path {r['final']} already exists")
                     return

                shutil.move(temp_path, final_path)

                # Also handle merged folder
                merged_base = os.path.join(kit_path, "items_merged")
                temp_merged = os.path.join(merged_base, r['temp'])
                if os.path.exists(temp_merged):
                    final_merged = os.path.join(merged_base, r['final'])
                    shutil.move(temp_merged, final_merged)

            # 4. Update separated_layers.json
            sep_path = os.path.join(kit_path, "separated_layers.json")
            if os.path.exists(sep_path):
                try:
                    with open(sep_path, 'r', encoding='utf-8') as f:
                        sep_list = json.load(f)
                    
                    new_sep_list = []
                    for item in sep_list:
                        # Find if this item was renamed
                        found = False
                        for r in renames:
                            if r['old'] == item:
                                new_sep_list.append(r['new'])
                                found = True
                                break
                        if not found:
                            new_sep_list.append(item)
                    
                    with open(sep_path, 'w', encoding='utf-8') as f:
                        json.dump(new_sep_list, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    print(f"Warning: Failed to update separated_layers.json: {e}")

            self.send_api_response(True, "Reordered successfully")

        except Exception as e:
            self.send_api_response(False, f"Error during reordering: {str(e)}")

    def handle_reorder_images(self, data):
        kit_folder = data.get('kit')
        part_folder = data.get('part_folder')

        if not kit_folder or not part_folder:
            self.send_api_response(False, "Missing parameters (kit or part_folder)")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            part_path = safe_join(kit_path, part_folder)
            
            if not os.path.exists(part_path):
                self.send_api_response(False, f"Part folder not found: {part_folder}")
                return

            # Determine folders to process
            target_dirs = []
            
            # Find subdirectories (colors)
            subdirs = [d for d in os.listdir(part_path) if os.path.isdir(os.path.join(part_path, d))]
            # Filter subdirs (exclude items_merged if it somehow exists here, although unlikely)
            subdirs = [d for d in subdirs if d != "items_merged"]
            
            if subdirs:
                for sd in subdirs:
                    target_dirs.append(os.path.join(part_path, sd))
            else:
                # No color folders, process the part root itself
                target_dirs.append(part_path)

            image_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
            processed_count = 0
            
            for folder in target_dirs:
                # 1. Collect valid image files
                files = []
                for f in os.listdir(folder):
                    if not os.path.isfile(os.path.join(folder, f)):
                        continue
                    
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in image_extensions:
                        continue
                    
                    # Exclude thumbnails and nav
                    fname_lower = f.lower()
                    if fname_lower.startswith('thumb_') or fname_lower.startswith('thumbnail_'):
                        continue
                    if fname_lower in ['nav.png', 'nav.webp']:
                        continue
                    
                    files.append(f)
                
                if not files:
                    continue
                
                # 2. Natural Sort
                files.sort(key=natural_sort_key)
                
                # 3. Rename to TEMP to avoid collisions
                temp_map = []
                for i, old_name in enumerate(files):
                    ext = os.path.splitext(old_name)[1]
                    temp_name = f"reorder_tmp_{i}_{os.getpid()}{ext}"
                    try:
                        os.rename(os.path.join(folder, old_name), os.path.join(folder, temp_name))
                        temp_map.append((temp_name, ext))
                    except Exception as e:
                        print(f"Error renaming to temp: {e}")
                
                # 4. Rename to FINAL (1, 2, 3...)
                for i, (temp_name, ext) in enumerate(temp_map, 1):
                    new_name = f"{i}{ext}"
                    try:
                        os.rename(os.path.join(folder, temp_name), os.path.join(folder, new_name))
                    except Exception as e:
                        print(f"Error renaming to final: {e}")
                
                processed_count += 1

            self.send_api_response(True, f"Đã sắp xếp lại ảnh trong {processed_count} thư mục.")

        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Lỗi sắp xếp ảnh: {str(e)}")

    def handle_check_missing_thumbnails(self, data):
        """Check all kits including those in parent folders from folder.json."""
        try:
            missing_thumbnails = []
            total_folders = 0
            
            # Get specific kit if provided
            specific_kit = data.get('kit')
            
            # Load parent folders from folder.json
            parent_folders = []
            if os.path.exists('folder.json'):
                try:
                    with open('folder.json', 'r', encoding='utf-8') as f:
                        parent_folders = json.load(f)
                except:
                    parent_folders = []
            
            if not os.path.exists(DATA_DIR):
                self.send_api_response(False, f"DATA_DIR không tồn tại: {DATA_DIR}")
                return
            
            # List of all kit locations to check
            kit_locations = []
            
            # First, add parent folders from folder.json (they are subfolders of DATA_DIR)
            for parent in parent_folders:
                parent_path = os.path.join(DATA_DIR, parent)
                if os.path.exists(parent_path) and os.path.isdir(parent_path):
                    kit_locations.append((parent, parent_path))
            
            # Then add kits directly in DATA_DIR (those not in parent folders)
            kit_locations.append(('downloads', DATA_DIR))
            
            # Check all kit locations
            for location_name, location_path in kit_locations:
                if not os.path.exists(location_path):
                    continue
                
                try:
                    entries = os.listdir(location_path)
                except PermissionError:
                    continue
                
                for entry in sorted(entries):
                    kit_path = os.path.join(location_path, entry)
                    
                    # Skip if not a directory
                    if not os.path.isdir(kit_path) or entry.startswith('.'):
                        continue
                    
                    kit_name = entry
                    
                    # If location is a parent folder, use it; otherwise skip default parent entries
                    if location_name != 'downloads':
                        pass  # Check all kits inside parent folders
                    else:
                        # For downloads root, skip folders that are parent folder names
                        if kit_name in parent_folders + ['cache_blobs', 'thung_rac']:
                            continue
                    
                    # If specific kit is provided, only check that kit
                    if specific_kit and kit_name != specific_kit:
                        continue
                    
                    # Get list of subfolders (parts)
                    subfolders = []
                    try:
                        for item in os.listdir(kit_path):
                            item_path = os.path.join(kit_path, item)
                            if os.path.isdir(item_path) and not item.startswith('.'):
                                # Only get folders with format "number-number" (e.g., 1-9, 10-5)
                                if '-' in item:
                                    subfolders.append(item)
                    except PermissionError:
                        continue
                    
                    if not subfolders:
                        continue
                    
                    kit_missing = []
                    for subfolder in subfolders:
                        subfolder_path = os.path.join(kit_path, subfolder)
                        total_folders += 1
                        
                        # Check if thumb_*.png exists
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
                                'parent': location_name,
                                'path': subfolder_path.replace('\\', '/')
                            })
                    
                    if kit_missing:
                        print(f"⚠️  Found missing thumbnails in {location_name}/{kit_name}: {len(kit_missing)} folders", flush=True)
            
            # Return summary
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            
            response = {
                "success": True,
                "kit": specific_kit,
                "total_folders_checked": total_folders,
                "total_missing": len(missing_thumbnails),
                "percentage_missing": round(100 * len(missing_thumbnails) / total_folders, 1) if total_folders > 0 else 0,
                "missing_thumbnails": missing_thumbnails
            }
            self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))
            
        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Lỗi kiểm tra thumbnail: {str(e)}")


    def handle_check_invalid_filenames(self, data):
        """
        Quét tất cả folder bộ phận (X-Y) của một kit.
        Báo lỗi nếu file ảnh có tên không đúng định dạng:
          - Hợp lệ (root / color subfolder): n.png  hoặc  n.webp  (n là số nguyên dương)
          - Hợp lệ (root folder):           thumb_n.png  hoặc  thumb_n.webp
          - Các file không phải ảnh (json, txt, v.v.) được bỏ qua hoàn toàn.
          - nav.png cũng được bỏ qua (file điều hướng đặc biệt).
        """
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return

        try:
            kit_path = safe_join(DATA_DIR, kit_folder)
            if not os.path.exists(kit_path):
                self.send_api_response(False, "Kit not found")
                return

            IMAGE_EXTS = {'.png', '.webp', '.jpg', '.jpeg', '.gif'}
            # Pattern: chỉ số nguyên dương, ví dụ 1.png, 12.webp
            valid_image = re.compile(r'^\d+\.(png|webp|jpg|jpeg|gif)$', re.IGNORECASE)
            # Pattern thumb: thumb_n.png / thumb_n.webp
            valid_thumb = re.compile(r'^thumb_\d+\.(png|webp)$', re.IGNORECASE)
            # Các file đặc biệt được phép tồn tại ở bất kỳ đâu
            ALLOWED_SPECIAL = {'nav.png', 'nav.webp'}

            invalid_files = []  # list of dict

            part_pattern = re.compile(r'^\d+-\d+', )  # folder bộ phận: X-Y...

            for part_entry in sorted(os.listdir(kit_path)):
                part_path = os.path.join(kit_path, part_entry)
                if not os.path.isdir(part_path):
                    continue
                if not part_pattern.match(part_entry):
                    continue  # không phải folder bộ phận

                # Quét file trong root của folder bộ phận
                try:
                    root_items = os.scandir(part_path)
                except Exception:
                    continue

                color_dirs = []
                with root_items:
                    for item in root_items:
                        if item.is_dir():
                            color_dirs.append(item.name)
                            continue
                        if not item.is_file():
                            continue
                        fname = item.name
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in IMAGE_EXTS:
                            continue  # bỏ qua file không phải ảnh
                        if fname.lower() in ALLOWED_SPECIAL:
                            continue
                        # Hợp lệ nếu là n.ext HOẶC thumb_n.ext
                        if not valid_image.match(fname) and not valid_thumb.match(fname):
                            invalid_files.append({
                                'part': part_entry,
                                'color': None,       # root folder (không phải color sub)
                                'file': fname,
                                'location': f"{part_entry}/{fname}"
                            })

                # Quét file trong các color subfolder
                for color_name in sorted(color_dirs):
                    color_path = os.path.join(part_path, color_name)
                    try:
                        color_items = os.scandir(color_path)
                    except Exception:
                        continue
                    with color_items:
                        for cf in color_items:
                            if not cf.is_file():
                                continue
                            fname = cf.name
                            ext = os.path.splitext(fname)[1].lower()
                            if ext not in IMAGE_EXTS:
                                continue
                            if fname.lower() in ALLOWED_SPECIAL:
                                continue
                            # Trong color folder chỉ được phép n.ext (không có thumb)
                            if not valid_image.match(fname):
                                invalid_files.append({
                                    'part': part_entry,
                                    'color': color_name,
                                    'file': fname,
                                    'location': f"{part_entry}/{color_name}/{fname}"
                                })

            if invalid_files:
                print(f"⚠️  [check_invalid_filenames] Kit '{kit_folder}': {len(invalid_files)} file tên sai", flush=True)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            response = json.dumps({
                "success": True,
                "kit": kit_folder,
                "total_invalid": len(invalid_files),
                "invalid_files": invalid_files
            }, ensure_ascii=False)
            self.wfile.write(response.encode('utf-8'))

        except Exception as e:
            traceback.print_exc()
            self.send_api_response(False, f"Lỗi kiểm tra tên file: {str(e)}")


# ======================================================

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True

print(f"Server starting at http://localhost:{PORT}")
with ThreadedHTTPServer(("", PORT), KitHandler) as httpd:
    httpd.serve_forever()
