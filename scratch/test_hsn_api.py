import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import search_hsn, preload_hsn_cache

async def run_tests():
    print("Preloading HSN cache...")
    await preload_hsn_cache()
    print("Testing search_hsn function with Final_hsn_sac_copy.xlsx...")
    for q in ['0101', 'cotton', 'horses', 'soya', 'steel']:
        data = await search_hsn(query=q)
        matches = data.get('matches', [])
        print(f"Query '{q}': {len(matches)} matches")
        if matches:
            m0 = matches[0]
            print(f"  First: [{m0['hsn_code']}] IGST: {m0['igst_rate']}%, CGST: {m0['cgst_rate']}%, SGST: {m0['sgst_rate']}% | {m0['description'][:45]}")
            assert "igst_rate" in m0 and "cgst_rate" in m0 and "sgst_rate" in m0
            # Verify mathematical relationship: IGST = CGST + SGST (half and half)
            assert abs(m0['igst_rate'] - (m0['cgst_rate'] + m0['sgst_rate'])) < 0.01

    print("\nFASTAPI search_hsn DIRECT FUNCTION VERIFICATION PASSED!")

if __name__ == '__main__':
    asyncio.run(run_tests())
