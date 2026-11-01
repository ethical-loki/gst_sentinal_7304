with open("backend/main.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """        contents = await file.read()
        is_excel = file.filename.endswith((".xlsx", ".xls"))
        import io"""

replacement = """        contents = await file.read()
        fname = (file.filename or "").lower()
        is_excel = fname.endswith((".xlsx", ".xls"))
        import io"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open("backend/main.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("Updated upload_spreadsheet_hsn_intelligence in main.py")
else:
    print("Target not found")

