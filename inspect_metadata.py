import json
import os

path = r"d:\web\laragon\www\tool-neka\downloads\neka_14057\metadata.json"

if not os.path.exists(path):
    print("File not found")
    exit()

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("Top keys:", data.keys())
if 'data' in data:
    print("Data keys:", data['data'].keys())
    
    if 'tonings' in data['data']:
        print("Found 'tonings'!")
        tonings = data['data']['tonings']
        print(f"Total tonings: {len(tonings)}")
        if len(tonings) > 0:
            print("First toning sample:", json.dumps(tonings[0], ensure_ascii=False, indent=2))
            
            # Search for a specific toning ID mentioned earlier
            target_id = "rDPpc3FeRfw3HHHDtjDnyatuhDSxPWG5"
            for t in tonings:
                if t['id'] == target_id:
                    with open("inspect_result.txt", "a", encoding="utf-8") as out:
                        out.write(f"\nFound target toning {target_id}:\n")
                        out.write(json.dumps(t, ensure_ascii=False, indent=2))
                    break

with open("inspect_result.txt", "a", encoding="utf-8") as out:
    out.write(f"\nData keys: {list(data['data'].keys())}\n")
    if 'colorGroups' in data['data']:
        out.write("Found 'colorGroups'!\n")
        out.write(f"First colorGroup sample: {json.dumps(data['data']['colorGroups'][0], ensure_ascii=False, indent=2)}\n")
