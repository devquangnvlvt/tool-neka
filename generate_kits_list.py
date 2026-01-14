import os
import json

base_dir = "downloads"
kits = []

if os.path.exists(base_dir):
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path) and "_" in entry:
            metadata_path = os.path.join(full_path, "metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        kits.append({
                            "id": data.get("id"),
                            "name": data.get("name"),
                            "folder": entry
                        })
                except:
                    pass

with open("kits.json", "w", encoding="utf-8") as f:
    json.dump(kits, f, ensure_ascii=False, indent=2)

print(f"Found {len(kits)} kits.")
