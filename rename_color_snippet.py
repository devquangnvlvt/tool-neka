
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
