import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time

print("Testing load_default_sample_dirty()...")
t0 = time.time()
from src.ingestion.generate_sample_dirty_input import load_default_sample_dirty
data = load_default_sample_dirty()
t_load = time.time() - t0
print(f"load_default_sample_dirty took: {t_load:.3f}s | num invoices: {len(data.get('einvoices', []))}")

print("\nTesting generate_dynamic_dirty_payload(count=3)...")
t1 = time.time()
from src.ingestion.generate_sample_dirty_input import generate_dynamic_dirty_payload
dyn_data = generate_dynamic_dirty_payload(count=3)
t_dyn = time.time() - t1
print(f"generate_dynamic_dirty_payload(count=3) took: {t_dyn:.3f}s")

print("\nTesting Template_Converters load_default_sample_dirty()...")
t2 = time.time()
from Template_Converters.dirty_generator import load_default_sample_dirty as tc_load
tc_data = tc_load()
t_tc = time.time() - t2
print(f"Template_Converters load_default_sample_dirty took: {t_tc:.3f}s")

print("\nTesting convert_and_validate_in_memory()...")
t3 = time.time()
from src.ingestion.converter import convert_and_validate_in_memory
res = convert_and_validate_in_memory(data)
t_proc = time.time() - t3
print(f"convert_and_validate_in_memory took: {t_proc:.3f}s | status: {res.get('status')}")

print("\nTesting Template_Converters PayloadBuilder...")
t4 = time.time()
from Template_Converters.payload_builder import PayloadBuilder
for inv in tc_data.get("einvoices", []):
    PayloadBuilder.auto_correct_and_build(inv)
t_tc_proc = time.time() - t4
print(f"Template_Converters PayloadBuilder took: {t_tc_proc:.3f}s")
