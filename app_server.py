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
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))

        if self.path == '/api/delete_part':
            self.handle_delete_part(data)
        elif self.path == '/api/zip_kit':
            self.handle_zip_kit(data)
        elif self.path == '/api/get_kit_structure':
            self.handle_get_kit_structure(data)
        else:
            self.send_error(404, "Unknown API endpoint")

    def handle_get_kit_structure(self, data):
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return

        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            structured_dir = os.path.join(base_path, "downloads", kit_folder, "items_structured")
            
            if not os.path.exists(structured_dir):
                self.send_api_response(False, f"Directory not found: {structured_dir}")
                return

            parts = []
            for entry in os.listdir(structured_dir):
                entry_path = os.path.join(structured_dir, entry)
                if not os.path.isdir(entry_path):
                    continue

                match = re.match(r"^(\d+)-(\d+)$", entry)
                if not match:
                    continue

                x = int(match.group(1))
                y = int(match.group(2))

                # Scan for items (thumb_*.png)
                items = []
                # Find all thumb_N.png and get the max N or list them
                # Actually, we can just look for thumb_*.png
                thumb_pattern = re.compile(r"^thumb_(\d+)\.png$")
                item_indices = []
                for f in os.listdir(entry_path):
                    m = thumb_pattern.match(f)
                    if m:
                        item_indices.append(int(m.group(1)))
                
                num_items = max(item_indices) if item_indices else 0
                
                # Scan for colors (subdirectories)
                colors = []
                for sub in os.listdir(entry_path):
                    sub_path = os.path.join(entry_path, sub)
                    if os.path.isdir(sub_path):
                        # It's a color folder
                        colors.append(sub)
                
                # Check for "default" or if it has images in root
                # Actually, our reorganized logic puts images in root if "default"
                # but let's just use the subfolders as colors.
                
                parts.append({
                    "x": x,
                    "y": y,
                    "folder": entry,
                    "items_count": num_items,
                    "colors": colors
                })

            # Sort by Y for navigation
            parts.sort(key=lambda p: p['y'])

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({"success": True, "parts": parts})
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

    def handle_zip_kit(self, data):
        kit_folder = data.get('kit')
        if not kit_folder:
            self.send_api_response(False, "Missing kit parameter")
            return

        try:
            from zip_neka_kit import zip_kit
            zip_path = zip_kit(kit_folder)
            
            # Send the ZIP file as download
            if os.path.exists(zip_path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(zip_path)}"')
                self.send_header('Content-Length', str(os.path.getsize(zip_path)))
                self.end_headers()
                
                with open(zip_path, 'rb') as f:
                    self.wfile.write(f.read())
                
                # Optionally delete the zip file after sending
                # os.remove(zip_path)
            else:
                self.send_api_response(False, "Failed to create ZIP file")
        except Exception as e:
            self.send_api_response(False, f"Server Error: {str(e)}")


    def send_api_response(self, success, message):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({"success": success, "message": message})
        self.wfile.write(response.encode('utf-8'))

print(f"Server starting at http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), KitHandler) as httpd:
    httpd.serve_forever()
