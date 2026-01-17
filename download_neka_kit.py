import os
import json
import time
import sys
import requests
import shutil
from PIL import Image
import numpy as np

# Try to import selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============= GRADIENT MAPPING FUNCTIONS =============

def decode_b62(s):
    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    base_map = {c: i for i, c in enumerate(ALPHABET)}
    val = 0
    s_clean = s.split('.')[1] if '.' in s else s
    for c in s_clean:
        if c in base_map:
            val = val * 62 + base_map[c]
    denom = 62 ** len(s_clean)
    return val / denom

def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))

def create_gradient_lut(gradients):
    parsed = []
    for g in gradients:
        off = g['offset']
        if isinstance(off, str):
            if off.startswith('0.'):
                off = decode_b62(off)
            else:
                try: off = float(off)
                except: off = 0.0
        else:
            off = float(off)
        parsed.append((off, hex_to_rgb(g['color'])))
    
    parsed.sort(key=lambda x: x[0])
    
    # If all offsets are the same (e.g., all 0), distribute them evenly from 0.0 to 1.0
    if len(parsed) > 1 and all(p[0] == parsed[0][0] for p in parsed):
        num = len(parsed)
        for i in range(num):
            parsed[i] = (i / (num - 1), parsed[i][1])

    if not parsed: return [(0,0,0)] * 256

    lut = []
    for i in range(256):
        pos = i / 255.0
        start = parsed[0]
        end = parsed[-1]
        
        for j in range(len(parsed) - 1):
            if parsed[j][0] <= pos <= parsed[j+1][0]:
                start = parsed[j]
                end = parsed[j+1]
                break
        
        t_range = end[0] - start[0]
        if t_range == 0:
            ratio = 0
        else:
            ratio = (pos - start[0]) / t_range
            
        c1 = start[1]
        c2 = end[1]
        
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        
        # Clamp values to 0-255 range
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        lut.append((r, g, b))
        
    return lut

def apply_gradient(image_path, lut, output_path):
    try:
        img = Image.open(image_path).convert("RGBA")
        r, g, b, a = img.split()
        gray = img.convert("L")
        gray_data = np.array(gray)
        lut_arr = np.array(lut, dtype=np.uint8)
        rgb_data = lut_arr[gray_data]
        res_img = Image.fromarray(rgb_data, mode="RGB")
        res_img.putalpha(a)
        res_img.save(output_path)
    except Exception as e:
        print(f"Error coloring {image_path}: {e}")
        shutil.copy2(image_path, output_path)

# ============= DECOMPRESSION FUNCTIONS =============

def decode_b62_full(s):
    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    base_map = {c: i for i, c in enumerate(ALPHABET)}
    val = 0
    for c in s:
        if c in base_map:
            val = val * 62 + base_map[c]
    return val

def decompress(val, vocab, cache):
    if val in cache:
        return cache[val]
    
    cache[val] = None 
    
    if val >= len(vocab):
        return None
        
    raw = vocab[val]
    
    if not isinstance(raw, str):
        cache[val] = raw
        return raw
        
    res = raw
    if raw.startswith("n|"):
        try:
             res = raw[2:]
             if '.' not in res:
                is_neg = False
                if res.startswith('-'):
                    is_neg = True
                    res = res[1:]
                num = decode_b62_full(res)
                res = -num if is_neg else num
             else:
                res = float(res)
        except:
             pass
    elif raw.startswith("s|"):
        res = raw[2:]
    elif raw.startswith("a|"):
        parts = raw.split("|")
        res = []
        cache[val] = res
        for x in parts[1:]:
            res.append(decompress(decode_b62_full(x), vocab, cache))
    elif raw.startswith("o|"):
        parts = raw.split("|")
        keys_idx = decode_b62_full(parts[1])
        keys = decompress(keys_idx, vocab, cache)
        
        values = []
        for x in parts[2:]:
            values.append(decompress(decode_b62_full(x), vocab, cache))
            
        res = {}
        cache[val] = res
        
        if isinstance(keys, list) and len(keys) == len(values):
            for k, v in zip(keys, values):
                if not isinstance(k, str):
                    k = str(k)
                res[k] = v
        else:
            res = {"__raw_error__": raw}
    else:
        res = raw
        
    cache[val] = res
    return res

# ============= DOWNLOAD METADATA =============

def get_clean_data_via_browser(url, output_file):
    if not webdriver:
        print("Error: Selenium is not installed.")
        return None

    print(f"Launching browser to fetch data from {url}...")
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(url)
        print("Waiting for page / data...")
        time.sleep(5) 
        
        script = "return window.__NEXT_DATA__;"
        next_data = driver.execute_script(script)
        
        driver.quit()
        
        if next_data:
            print("Obtained __NEXT_DATA__, attempting decompression...")
            try:
                props = next_data.get('props', {}).get('pageProps', {})
                kit_raw = props.get('kitOnSale')
                
                if isinstance(kit_raw, list) and len(kit_raw) >= 2:
                    vocab = kit_raw[0]
                    root_str = kit_raw[1]
                    
                    if isinstance(root_str, str):
                        print(f"Decompressing kit with root: {root_str}")
                        cache = {}
                        root_idx = decode_b62_full(root_str)
                        final_data = decompress(root_idx, vocab, cache)
                        
                        if final_data:
                            with open(output_file, 'w', encoding='utf-8') as f:
                                json.dump(final_data, f, ensure_ascii=False, indent=2)
                            print(f"Successfully extracted and decompressed data to {output_file}")
                            return output_file
            except Exception as e:
                print(f"Decompression failed: {e}")
                import traceback
                traceback.print_exc()

        return None
        
    except Exception as e:
        print(f"Browser error: {e}")
        try: driver.quit()
        except: pass
        return None

# ============= HELPER FUNCTIONS FOR THREADING =============

def download_with_retry(url, dest_path, timeout=30, retries=3):
    for i in range(retries):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                with open(dest_path, 'wb') as f:
                    f.write(resp.content)
                return True
            else:
                print(f"  [Retry {i+1}/{retries}] Failed {url}: {resp.status_code}")
        except Exception as e:
            print(f"  [Retry {i+1}/{retries}] Error downloading {url}: {e}")
        time.sleep(2)
    return False

def process_blob_task(task):
    blob = task['blob']
    current_lut = task['lut']
    filepath = task['filepath']
    cache_dir = task['cache_dir']
    
    if os.path.exists(filepath):
        return False

    url = f"https://img2.neka.cc/{blob}"
    cache_path = os.path.join(cache_dir, f"{blob}.png")
    
    # Check cache first
    if not os.path.exists(cache_path):
        success = download_with_retry(url, cache_path)
        if not success:
            return False
            
    try:
        if current_lut:
            apply_gradient(cache_path, current_lut, filepath)
        else:
            shutil.copy2(cache_path, filepath)
        return True
    except Exception as e:
        print(f"  Error processing blob {blob}: {e}")
        return False

# ============= REORGANIZE KIT =============

def get_color_code_from_filter(filter_data):
    if not isinstance(filter_data, dict):
        return "default"
    gradients = filter_data.get('gradients', [])
    if not gradients: return "default"
    
    # Try to find a meaningful color from the gradient
    main_color = gradients[0].get('color', '000000')
    if len(gradients) > 1 and main_color.lower() in ['#ffffff', '#000000']:
        main_color = gradients[-1].get('color', '000000')
        
    return main_color.replace('#', '').upper()

def reorganize_kit(metadata_path):
    print(f"DEBUG: reorganize_kit called with {metadata_path}")
    base_dir = os.path.dirname(metadata_path)
    
    with open(metadata_path, 'r', encoding='utf-8') as f:
        kit = json.load(f)
        
    data = kit.get('data', {})
    parts = data.get('parts', [])
    tonings = data.get('tonings', [])
    layer_heights = data.get('layerHeights', [])
    lh_map = {lh.get('id'): idx for idx, lh in enumerate(layer_heights)}
    
    toning_map = {}
    for t in tonings:
        # Safety check: kit 14368 has strings in tonings array
        if not isinstance(t, dict):
            continue
            
        t_id = t.get('id')
        filters = t.get('filters', [])
        
        processed_colors = []
        seen_codes = {}
        
        for filter_idx, f_data in enumerate(filters):
            if not isinstance(f_data, dict):
                continue
            base_code = get_color_code_from_filter(f_data)
            
            if base_code in seen_codes:
                seen_codes[base_code] += 1
                folder_code = f"{base_code}_{seen_codes[base_code]}"
            else:
                seen_codes[base_code] = 1
                folder_code = base_code
            
            processed_colors.append({
                "code": folder_code,
                "gradients": f_data.get('gradients', [])
            })
            
        toning_map[t_id] = processed_colors
        
    print(f"Loaded {len(toning_map)} tonings.")
    
    # Pre-map addon tonings if any part/item defines its own
    # Some kits have tonings defined elsewhere or special overrides
    # For now we rely on toning_map populated from data['tonings']
    
    total_files = 0
    
    for part_idx, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        part_name = part.get('name', 'unnamed').replace(' ', '_').replace('/', '-')
        part_zindex = part.get('zIndex', 0)
        nav_position = part_idx + 1  # Y: navigation position (1-indexed)
        
        # X: Use layerHeight index if available, else zIndex
        lh_id = part.get('layerHeight', 'default')
        x_value = lh_map.get(lh_id, part_zindex)
        
        # Format: X-Y only
        folder_name = f"{x_value}-{nav_position}"
        
        part_toning_id = part.get('toning')
        toning_ids = set()
        if part_toning_id:
            toning_ids.add(part_toning_id)
        
        # Also check addonLayers for more tonings
        addon_layers = part.get('addonLayers', [])
        if isinstance(addon_layers, list):
            for al in addon_layers:
                if isinstance(al, dict):
                    al_toning = al.get('toning')
                    if al_toning:
                        toning_ids.add(al_toning)

        items = part.get('items', [])
        num_items = len(items)

        # Collect all unique colors from all tonings
        all_colors_dict = {} # code -> color_data
        for t_id in toning_ids:
            colors_for_tid = toning_map.get(t_id, [])
            for c in colors_for_tid:
                code = c["code"]
                if code not in all_colors_dict:
                    all_colors_dict[code] = c
        
        colors = list(all_colors_dict.values())
        if not colors:
            colors = [{"code": "default", "gradients": []}]
        
        is_flattened = (num_items == 1 and len(colors) > 1)
        
        print(f"> Processing Part: {folder_name} | Items: {num_items} | Colors: {len(colors)} | Flattened: {is_flattened}")
        
        # Download navigation icon (cover image) first
        part_cover = part.get('cover')
        if part_cover:
        
        # Determine colors for this part
            base_part_dir = os.path.join(base_dir, "items_structured", folder_name)
            if not os.path.exists(base_part_dir):
                os.makedirs(base_part_dir)
            
            nav_path = os.path.join(base_part_dir, "nav.png")
            if not os.path.exists(nav_path):
                try:
                    cache_dir = os.path.join(os.path.dirname(base_dir), "cache_blobs")
                    if not os.path.exists(cache_dir): 
                        os.makedirs(cache_dir)
                    
                    cache_path = os.path.join(cache_dir, f"{part_cover}.png")
                    if not os.path.exists(cache_path):
                        print(f"  Downloading nav icon {part_cover}...")
                        url = f"https://img2.neka.cc/{part_cover}"
                        resp = requests.get(url, timeout=10)
                        if resp.status_code == 200:
                            with open(cache_path, 'wb') as f:
                                f.write(resp.content)
                    
                    shutil.copy2(cache_path, nav_path)
                    print(f"  ✓ Saved nav icon")
                except Exception as e:
                    print(f"  Error downloading nav icon: {e}")
        
        # Download item thumbnails
        base_part_dir = os.path.join(base_dir, "items_structured", folder_name)
        if not os.path.exists(base_part_dir):
            os.makedirs(base_part_dir)
        
        for item_idx, item_layers in enumerate(items):
            if not isinstance(item_layers, list):
                item_layers = [item_layers]
            
            # Get thumbnail from first layer
            if len(item_layers) > 0:
                first_layer = item_layers[0]
                if isinstance(first_layer, dict):
                    thumbnail_blob = first_layer.get('thumbnail') or first_layer.get('blob')
                    
                    if thumbnail_blob:
                        thumb_path = os.path.join(base_part_dir, f"thumb_{item_idx + 1}.png")
                        
                        if not os.path.exists(thumb_path):
                            try:
                                cache_dir = os.path.join(os.path.dirname(base_dir), "cache_blobs")
                                if not os.path.exists(cache_dir):
                                    os.makedirs(cache_dir)
                                
                                cache_path = os.path.join(cache_dir, f"{thumbnail_blob}.png")
                                if not os.path.exists(cache_path):
                                    url = f"https://img2.neka.cc/{thumbnail_blob}"
                                    resp = requests.get(url, timeout=10)
                                    if resp.status_code == 200:
                                        with open(cache_path, 'wb') as f:
                                            f.write(resp.content)
                                
                                shutil.copy2(cache_path, thumb_path)
                            except Exception as e:
                                print(f"  Error downloading thumbnail {item_idx + 1}: {e}")
        
        print(f"  ✓ Saved {num_items} thumbnails")
        
        file_counter = 1
        for color_data in colors:
            color_code = color_data["code"]
            gradients = color_data["gradients"]
            
            lut = None
            if gradients:
                lut = create_gradient_lut(gradients)
            
            # Target Dir logic
            if is_flattened or color_code == "default":
                target_dir = os.path.join(base_dir, "items_structured", folder_name)
            else:
                target_dir = os.path.join(base_dir, "items_structured", folder_name, color_code)
                
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # Sequential naming: 1.png, 2.png...
            # If not flattened, each color has its own folder, so reset.
            # If flattened, they all go in the same folder, so DON'T reset.
            if not is_flattened:
                file_counter = 1
            
            for item_idx, item_layers in enumerate(items):
                if not isinstance(item_layers, list): item_layers = [item_layers]
                
                # Combine main layers with addonTextures and addonLayers (if simple)
                all_blobs_to_process = []
                for layer in item_layers:
                    if not isinstance(layer, dict):
                        continue
                    # 1. Main blob
                    if layer.get('blob'):
                        all_blobs_to_process.append({
                            "blob": layer.get('blob'),
                            "toning_id": part_toning_id # Default toning
                        })
                    
                    # 2. Addon textures in this layer
                    addon_textures = layer.get('addonTextures', [])
                    for at in addon_textures:
                        if isinstance(at, dict) and at.get('blob'):
                             # Addon textures usually follow the part's toning or have their own
                             at_toning = at.get('layer') or part_toning_id
                             all_blobs_to_process.append({
                                 "blob": at.get('blob'),
                                 "toning_id": at_toning
                             })

                for task in all_blobs_to_process:
                    blob = task["blob"]
                    current_lut = lut
                    
                    # Sequential naming: 1.png, 2.png, 3.png...
                    filename = f"{file_counter}.png"
                    filepath = os.path.join(target_dir, filename)
                    
                    if os.path.exists(filepath):
                        # Even if file exists, we MUST increment the counter to avoid skipping subsequent colors/items
                        file_counter += 1
                        continue
                        
                    url = f"https://img2.neka.cc/{blob}"
                    try:
                        cache_dir = os.path.join(os.path.dirname(base_dir), "cache_blobs")
                        if not os.path.exists(cache_dir): os.makedirs(cache_dir)
                        
                        cache_path = os.path.join(cache_dir, f"{blob}.png")
                        if not os.path.exists(cache_path):
                            print(f"Downloading blob {blob}...")
                            resp = requests.get(url, timeout=10)
                            if resp.status_code == 200:
                                with open(cache_path, 'wb') as f_cache:
                                    f_cache.write(resp.content)
                            else:
                                print(f"Failed to download {url}: {resp.status_code}")
                                continue
                        
                        if current_lut:
                            apply_gradient(cache_path, current_lut, filepath)
                        else:
                            shutil.copy2(cache_path, filepath)
                            
                        total_files += 1
                        file_counter += 1
                        
                    except Exception as e:
                        print(f"  Error handling blob {blob}: {e}")

    print(f"Done! Created {total_files} colored files in 'items_structured'.")

# ============= MAIN =============

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_neka_kit.py <URL or ID>")
        print("Example: python download_neka_kit.py https://www.neka.cc/composer/12705")
        print("Example: python download_neka_kit.py 12705")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    # Check if argument is URL or just ID
    if arg.startswith("http"):
        url = arg
    else:
        url = f"https://www.neka.cc/composer/{arg}"
    
    print(f"Processing: {url}")
    
    # Step 1: Download metadata
    temp_json = "temp_kit_data.json"
    metadata_file = get_clean_data_via_browser(url, temp_json)
    
    if not metadata_file:
        print("Failed to download metadata.")
        sys.exit(1)
    
    # Step 2: Read metadata to get kit name and ID
    with open(metadata_file, 'r', encoding='utf-8') as f:
        kit = json.load(f)
    
    kit_name = kit.get('name', 'unknown_kit').replace(' ', '_').replace('/', '-')
    kit_id = str(kit.get('id', 'unknown_id'))
    
    # Step 3: Create final directory structure
    # Use ID-only naming to avoid Chinese characters in folder names
    base_dir = os.path.join("downloads", f"neka_{kit_id}")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    
    final_metadata_path = os.path.join(base_dir, "metadata.json")
    shutil.move(temp_json, final_metadata_path)
    
    print(f"\nKit: {kit_name} (ID: {kit_id})")
    print(f"Metadata saved to: {final_metadata_path}")
    
    # Step 4: Reorganize and download images
    print("\nStarting image download and organization...")
    reorganize_kit(final_metadata_path)
    
    print(f"\n✓ Complete! Check: {base_dir}/items_structured/")
