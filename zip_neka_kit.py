import os
import zipfile
import sys
import time
from config import DATA_DIR


def zip_kit(kit_folder):
    """
    Zips the structured items and metadata of a kit.
    """
    target_path = os.path.join(DATA_DIR, kit_folder)

    # Smart resolution: if "neka_{id}" exists, use it
    if not os.path.exists(target_path):
        # Try checking if input was just ID but folder is neka_{ID}
        if not kit_folder.startswith("neka_"):
            alt_folder = f"neka_{kit_folder}"
            alt_path = os.path.join(DATA_DIR, alt_folder)
            if os.path.exists(alt_path):
                print(f"Found folder {alt_folder} instead of {kit_folder}")
                target_path = alt_path
                # We still name the zip as the requested ID or the actual folder name?
                # Let's keep the zip name as requested to match what server sends
                # But actually server sends header filename based on kit_folder from request.
                pass

    if not os.path.exists(target_path):
        print(f"Error: Folder {target_path} not found.")
        # Raise exception so app_server catches it
        raise FileNotFoundError(f"Folder not found: {kit_folder}")

    output_zip = os.path.join(DATA_DIR, f"{kit_folder}.zip")
    print(f"Zipping {target_path} to {output_zip}...")
    
    start_time = time.time()
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(target_path):
            for file in files:
                # Don't include the output zip file itself
                if file == output_zip:
                    continue
                    
                file_path = os.path.join(root, file)
                # Create relative path for zip 
                arcname = os.path.relpath(file_path, target_path)
                zipf.write(file_path, arcname)



    end_time = time.time()
    size_mb = os.path.getsize(output_zip) / (1024 * 1024)
    print(f"Successfully created {output_zip}")
    print(f"Size: {size_mb:.2f} MB")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print(f"Location: {os.path.abspath(output_zip)}")
    
    return os.path.abspath(output_zip)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python zip_neka_kit.py <kit_folder_name>")
        print("Example: python zip_neka_kit.py MLP捏个小马_11628")
    else:
        kit_folder = sys.argv[1]
        zip_kit(kit_folder)
