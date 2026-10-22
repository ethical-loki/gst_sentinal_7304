import sys
import io
import os
sys.path.insert(0, os.path.abspath("."))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


import json
from backend.converter_service import load_default_sample_dirty, process_converter_pipeline
from Template_Converters.validator import GSTValidator

dirty = load_default_sample_dirty()
print("Dirty payload keys:", list(dirty.keys()))

raw_val = GSTValidator.validate_payload_document(dirty)
raw_errs = raw_val.get("results", [{}])[0].get("errors", [])
print(f"Raw validator errors count: {len(raw_errs)}")
for err in raw_errs:
    print(" - Raw error:", err.get("error_code"), err.get("field"), err.get("message"))

pipe = process_converter_pipeline(dirty, sync_to_disk=False)
pipe_errs = pipe["validation_report"].get("results", [{}])[0].get("errors", [])
print(f"Pipeline errors count: {len(pipe_errs)}")
for err in pipe_errs:
    print(" - Pipe error:", err.get("error_code"), err.get("field"), err.get("message"))

transformations = pipe["validation_report"].get("results", [{}])[0].get("corrections_applied", [])
print(f"Corrections count: {len(transformations)}")
for c in transformations[:5]:
    print(" - Correction:", c.get("category"), c.get("field"), c.get("original"), "->", c.get("corrected"))
