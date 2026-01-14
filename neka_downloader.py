import os
import json
import time
import argparse
import requests
import sys

# Try to import selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None

def download_file(url, folder, filename):
    if not os.path.exists(folder):
        os.makedirs(folder)
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        return
    
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
    except Exception as e:
        print(f"Error downloading {url}: {e}")

def decode_b62(s):
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
    
    # Placeholder for cycle
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
                # Check for negative
                is_neg = False
                if res.startswith('-'):
                    is_neg = True
                    res = res[1:]
                num = decode_b62(res)
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
        cache[val] = res # Set ref
        for x in parts[1:]:
            res.append(decompress(decode_b62(x), vocab, cache))
    elif raw.startswith("o|"):
        # Format: o|KEYS_IDX|VAL1|VAL2...
        parts = raw.split("|")
        keys_idx = decode_b62(parts[1])
        keys = decompress(keys_idx, vocab, cache)
        
        values = []
        for x in parts[2:]:
            values.append(decompress(decode_b62(x), vocab, cache))
            
        res = {}
        cache[val] = res
        
        if isinstance(keys, list) and len(keys) == len(values):
            for k, v in zip(keys, values):
                # Ensure keys are strings
                if not isinstance(k, str):
                    k = str(k)
                res[k] = v
        else:
            # Fallback for weird cases
            # print(f"Warning: Object mismatch at {val}")
            res = {"__raw_error__": raw}
    else:
        res = raw
        
    cache[val] = res
    return res

def get_clean_data_via_browser(url, output_file):
    if not webdriver:
        print("Error: Selenium is not installed.")
        return None

    print(f"Launching browser to fetch data from {url}...")
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    # chrome_options.add_argument("--headless") # Optional: run headless if confident
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(url)
        print("Waiting for page / data...")
        time.sleep(5) 
        
        # We only need __NEXT_DATA__
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
                        root_idx = decode_b62(root_str)
                        final_data = decompress(root_idx, vocab, cache)
                        
                        if final_data:
                            # Normalize structure if needed
                            # The root object usually contains the 'data' field which has 'parts'
                            
                            # Sometimes the root IS the processed kit, sometimes it wrapps it
                            # Let's save it
                            with open(output_file, 'w', encoding='utf-8') as f:
                                json.dump(final_data, f, ensure_ascii=False)
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

def process_kit_data(json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            kit = json.load(f)
            
        kit_name = kit.get('name', 'unknown_kit').replace(' ', '_').replace('/', '-')
        kit_id = str(kit.get('id', 'unknown_id'))
        print(f"Processing Kit: {kit_name} (ID: {kit_id})")
        
        base_dir = os.path.join("downloads", f"{kit_name}_{kit_id}")
        items_dir = os.path.join(base_dir, "items")
        colors_dir = os.path.join(base_dir, "colors")
        
        for d in [base_dir, items_dir, colors_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
                
        # Save metadata
        with open(os.path.join(base_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(kit, f, ensure_ascii=False, indent=4)
            
        data = kit.get('data', {})
        if not data:
            print("No 'data' field found in kit.")
            return

        parts = data.get('parts', [])
        tonings = data.get('tonings', [])
        
        total_assets = 0
        
        # Process Parts
        for part in parts:
            part_name = part.get('name', 'unnamed').replace(' ', '_').replace('/', '-')
            part_id = part.get('id', 'unknown_part_id') # Added part_id for logging
            items = part.get('items', [])
            print(f"  - Part: {part_name} (ID: {part_id}), Items: {len(items)}")
            
            # items is a list of LISTS of layers
            for item_idx, item_layers in enumerate(items):
                if not isinstance(item_layers, list):
                    # Fallback if structure is different
                    item_layers = [item_layers]
                
                # Determine Item ID (try to find 'id' in any layer, else use first blob)
                item_id = None
                for layer in item_layers:
                    if isinstance(layer, dict):
                        if 'id' in layer:
                            item_id = layer['id']
                            break
                
                if not item_id and len(item_layers) > 0 and isinstance(item_layers[0], dict):
                    item_id = item_layers[0].get('blob')
                    
                if not item_id:
                    item_id = f"item_{item_idx}"

                # Download layers
                for layer_idx, layer in enumerate(item_layers):
                    if not isinstance(layer, dict):
                        continue
                        
                    asset_hash = layer.get('blob')
                    if asset_hash:
                        # Construct URL
                        # Valid format found: https://img2.neka.cc/{hash} (no .png extension)
                        asset_url = f"https://img2.neka.cc/{asset_hash}"
                        
                        # Target path: downloads/kit_id/items/part_name/item_id_layer.png
                        # User requested: downloads/{kit_name}_{kit_id}/items
                        # Let's group by part to avoid clashes
                        
                        # Sanitize names
                        safe_part_name = "".join([c for c in part_name if c.isalnum() or c in (' ', '-', '_')]).strip()
                        safe_item_id = "".join([c for c in str(item_id) if c.isalnum() or c in (' ', '-', '_')]).strip()
                        
                        # We might want to save distinct layers if an item has multiple
                        # item_id.png (if single) item_id_0.png (if multi)
                        filename = f"{safe_item_id}.png"
                        if len(item_layers) > 1:
                            filename = f"{safe_item_id}_{layer_idx}.png"
                            
                        # Structure: items/part_name/filename
                        # User asked for: downloads/{kit_name}_{kit_id}/items
                        item_dir = os.path.join(base_dir, "items", safe_part_name)
                        if not os.path.exists(item_dir):
                            os.makedirs(item_dir)
                            
                        download_file(asset_url, item_dir, filename)
                        total_assets += 1
                         
        # Process Tonings/Colors
        print(f"Found {len(tonings)} tonings")
        for idx, ton in enumerate(tonings):
            t_name = ton.get('name', f'color_{idx}').replace(' ', '_').replace('/', '-')
            asset_id = ton.get('cover') 
            # Note: Tonings structure varies. Check if 'resources' exists?
            # Assuming 'cover' is the asset for now or usage id.
            if asset_id and len(asset_id) > 10:
                 url = f"https://img2.neka.cc/{asset_id}!/format/png/compress/true/max/100"
                 fname = f"{t_name}_{asset_id}.png"
                 download_file(url, colors_dir, fname)
                 total_assets += 1
                 
        print(f"Download complete! Saved {total_assets} files to {base_dir}")
        
    except Exception as e:
        print(f"Error processing data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python neka_downloader.py <URL>")
        print("Will attempt to use local dump if available.")

    url = sys.argv[1] if len(sys.argv) > 1 else None
    
    # If URL is provided, we default to fetching fresh data.
    # If NO URL, we look for local dump.
    
    json_file = None
    local_dump = "neka_raw_dump.json"

    if not url:
        if os.path.exists(local_dump):
            print(f"No URL provided. Found local dump {local_dump}, attempting to process it...")
            try:
                with open(local_dump, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                props = data.get('next_data', {}).get('props', {}).get('pageProps', {})
                kit_raw = props.get('kitOnSale')
                
                if isinstance(kit_raw, list) and len(kit_raw) >= 2:
                    vocab = kit_raw[0]
                    root_str = kit_raw[1]
                    print(f"Decompressing kit with root: {root_str}")
                    cache = {}
                    root_idx = decode_b62(root_str)
                    final_data = decompress(root_idx, vocab, cache)
                    
                    output_file = "kit_data.json"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(final_data, f, ensure_ascii=False)
                    print(f"Successfully extracted data to {output_file}")
                    json_file = output_file
            except Exception as e:
                print(f"Failed to process local dump: {e}")
                import traceback
                traceback.print_exc()
        else:
             print("No URL provided and no valid local dump found.")
             print("Usage: python neka_downloader.py <URL>")
             
    else:
        # URL provided, fetch fresh
        print(f"URL provided: {url}. Fetching data...")
        json_file = get_clean_data_via_browser(url, "kit_data.json")

    if json_file:
        process_kit_data(json_file)
