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
                match = re.match(r"^(\d+)-(\d+)$", entry)
                if not match: continue
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
                parts.append({
                    "x": x, "y": y, "folder": entry,
                    "items_count": num_items, "colors": colors,
                    "is_separated": entry in separated_folders
                })
            parts.sort(key=lambda p: p['y'])
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "success": True, "parts": parts,
                "has_separated_layers": len(separated_folders) > 0,
                "separated_folders": separated_folders
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
                # 1. Identify part index from folder name (X-Y -> Y is part_index + 1)
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
