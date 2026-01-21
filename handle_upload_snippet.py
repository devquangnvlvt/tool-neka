
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
            
            # Determine correct path
            # For nav.png, we usually want it in the parent X-Y folder, even if we are in a subcolor view
            # But the user might want a specific nav for a subcolor? Neka usually shares one nav per part.
            # Let's trust the "Parent" vs "Current" logic from frontend OR just default to parent if filename is nav.png
            
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
            # Remove header if present (e.g. "data:image/png;base64,")
            if ',' in file_content:
                file_content = file_content.split(',')[1]
            
            file_bytes = base64.b64decode(file_content)
            
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            self.send_api_response(True, f"Uploaded {filename}")

        except Exception as e:
            self.send_api_response(False, f"Upload error: {str(e)}")
