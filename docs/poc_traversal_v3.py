import requests
import json

BASE_URL = "http://localhost:8000"

def test_hardened_endpoint():
    print("Testing Path Traversal on /api/zip_kit (POST)...")
    # This endpoint now uses validate_id(kit) and safe_join
    payload = {
        "kit": "../secret_file" 
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/zip_kit", json=payload)
        data = response.json()
        print(f"Server response: {data}")
        # Expecting 'success': False AND 'message' containing 'Security violation' or 'Invalid kit'
        if not data.get("success"):
            print("VULNERABILITY BLOCKED SUCCESSFULLY!")
        else:
            print("VULNERABILITY STILL PRESENT!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_hardened_endpoint()
