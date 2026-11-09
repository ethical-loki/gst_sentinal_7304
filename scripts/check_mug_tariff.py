import pandas as pd
df = pd.read_parquet('data/tariff_master.parquet')
m = df[df['description'].str.contains('mug', case=False, na=False)]
print('Mug rows in tariff:', len(m))
for idx, r in m.head(5).iterrows():
    print(r['hsn_code'], ':', r['description'][:100])

