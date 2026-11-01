with open('Template_Converters/payload_builder.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_target = """            if sentinel_audit and sentinel_audit.get("should_rectify"):
                cf_hsn = str(sentinel_audit.get("rectified_hsn", "")).strip()
                is_same_heading = bool(orig_hsn and cf_hsn and len(orig_hsn) >= 4 and len(cf_hsn) >= 4 and orig_hsn[:4] == cf_hsn[:4])
                if cf_hsn and cf_hsn != orig_hsn and not is_same_heading:"""

new_target = """            if sentinel_audit and sentinel_audit.get("should_rectify"):
                cf_hsn = str(sentinel_audit.get("rectified_hsn", "") or "").strip()
                is_same_heading = bool(orig_hsn and cf_hsn and len(orig_hsn) >= 4 and len(cf_hsn) >= 4 and orig_hsn[:4] == cf_hsn[:4])
                if cf_hsn and cf_hsn.lower() not in ("none", "nan") and cf_hsn.isdigit() and cf_hsn != orig_hsn and not is_same_heading:"""

text = text.replace(old_target.replace('\n', '\r\n'), new_target.replace('\n', '\r\n'))
text = text.replace(old_target, new_target)

with open('Template_Converters/payload_builder.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated Template_Converters/payload_builder.py')

