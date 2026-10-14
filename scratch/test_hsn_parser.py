import openpyxl, re, time
import pandas as pd
from pathlib import Path

def parse_final_hsn_file(file_path):
    raw_df = pd.read_excel(file_path)
    records = []
    current_desc = ''
    current_rate = None

    for idx, row in raw_df.iterrows():
        c0 = '' if pd.isna(row.iloc[0]) else str(row.iloc[0]).strip()
        c1 = '' if pd.isna(row.iloc[1]) else str(row.iloc[1]).strip()
        c2 = row.iloc[2]
        
        if 'heading/Tariff item' in c0 or 'Chapter/Head' in c0:
            continue
        if pd.notna(c2):
            current_rate = c2
        if c1:
            current_desc = c1
        elif c1 == '' and c0 == '':
            continue
            
        if c0:
            parsed_igst, parsed_cgst, parsed_sgst = 18.0, 9.0, 9.0
            if current_rate is not None:
                r_str = str(current_rate).strip()
                if r_str.lower() in ['nil', 'none', 'null', '0']:
                    parsed_igst, parsed_cgst, parsed_sgst = 0.0, 0.0, 0.0
                else:
                    try:
                        val = float(r_str)
                        if val <= 1.0:
                            parsed_cgst = round(val * 100, 3)
                            parsed_sgst = parsed_cgst
                            parsed_igst = round(val * 200, 3)
                        else:
                            parsed_igst = round(val, 2)
                            parsed_cgst = round(val / 2.0, 2)
                            parsed_sgst = parsed_cgst
                    except ValueError:
                        pct_m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*%', r_str)
                        if pct_m:
                            p_val = float(pct_m.group(1))
                            parsed_igst = p_val
                            parsed_cgst = round(p_val / 2.0, 2)
                            parsed_sgst = parsed_cgst

            # Find all digit groups
            digits_list = re.findall(r'\b\d+\b', c0)
            if digits_list:
                main_code = digits_list[0]
                if len(main_code) in [1, 3]:
                    main_code = main_code.zfill(len(main_code) + 1)
            else:
                main_code = re.sub(r'[^0-9]', '', c0) or c0

            # Range handling
            range_m = re.match(r'^(\d{2,4})\s+to\s+(\d{2,4})', c0)
            if range_m:
                s_val = int(range_m.group(1))
                e_val = int(range_m.group(2))
                pad = len(range_m.group(1))
                all_codes = [str(n).zfill(pad) for n in range(s_val, e_val + 1)]
            else:
                all_codes = [d.zfill(len(d) + (1 if len(d) in [1, 3] else 0)) for d in digits_list]

            search_hsn_str = f"{c0} {main_code} {' '.join(all_codes)}".lower()

            records.append({
                'HSN_CD': main_code,
                'raw_code': c0,
                'all_codes': all_codes,
                'HSN_Description': current_desc,
                'Rate': current_rate,
                'gst_rate': parsed_igst,
                'igst_rate': parsed_igst,
                'cgst_rate': parsed_cgst,
                'sgst_rate': parsed_sgst,
                '_search_hsn': search_hsn_str,
                '_search_desc': current_desc.lower()
            })

    return pd.DataFrame(records)

if __name__ == '__main__':
    t0 = time.time()
    df = parse_final_hsn_file('data/Final_hsn_sac_copy.xlsx')
    print(f"Parsed {len(df)} rows in {time.time()-t0:.2f}s")

    for q in ['0101', 'cotton yarn', 'steel', '8504', 'live horses', 'soya']:
        sub = df[df['_search_hsn'].str.contains(q, regex=False) | df['_search_desc'].str.contains(q, regex=False)]
        print(f"Query '{q}': {len(sub)} matches")
        if len(sub) > 0:
            r0 = sub.iloc[0]
            print(f"   -> [{r0['HSN_CD']}] IGST: {r0['igst_rate']}%, CGST: {r0['cgst_rate']}%, SGST: {r0['sgst_rate']}% | {r0['HSN_Description'][:45]}")
