import requests
import json

BASE_URL = "http://localhost:8000"

def test_path_traversal():
    print("Testing Path Traversal with .agent folder...")
    # Attempt to reach d:\web\laragon\www\tool-neka\.agent
    # Kit path is os.path.join(base_path, "downloads", kit_folder)
    # So downloads/../../.agent should be d:\web\laragon\www\tool-neka\.agent
    payload = {
        "kit": "../../.agent" 
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/get_kit_structure", json=payload)
        data = response.json()
        print(f"Server response: {data}")
        if data.get("success"):
            print("VULNERABILITY CONFIRMED!")
        else:
            print(f"Failed to list: {data.get('message')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_path_traversal()
