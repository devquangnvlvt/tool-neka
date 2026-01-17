python download_neka_kit.py 14326
// nạp data
python generate_kits_list.py

python app_server.py /// http://192.168.1.93:8000/character-creator.html

Các file NÊN GIỮ:
app_server.py

- Server chính
  character-creator.html
- Giao diện chính
  delete_neka_part.py
- Dùng bởi API
  download_neka_kit.py
- Download kit mới
  generate_kits_list.py
- Generate kits.json
  zip_neka_kit.py
- Dùng bởi API
  kits.json
- Danh sách kits
  requirements.txt
- Dependencies
  start.md
- Documentation
