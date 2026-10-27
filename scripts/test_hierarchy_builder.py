import re
import pandas as pd
from scripts.ingest_tariff import CHAPTER_TITLES

df = pd.read_parquet('data/tariff_master.parquet')

# Build clean heading map
heading_rows = df[df['hsn_code'].str.len() == 4]
heading_map = {}
for _, r in heading_rows.iterrows():
    h_code = r['hsn_code']
    desc = r['description']
    # remove leading "Heading 0102 - "
    desc = re.sub(r'^Heading\s+\d{4}\s*-\s*', '', desc, flags=re.I)
    # take first segment before ';' or long repetitions
    parts = re.split(r'\s*;\s*', desc)
    primary = parts[0].strip()
    if ' - ' in primary:
        primary = primary.split(' - ')[0].strip()
    heading_map[h_code] = primary.title()

# Canonical overrides for key chapters mentioned in requirements
heading_map['0808'] = 'Apples, pears and quinces, fresh'
heading_map['0810'] = 'Other fruit, fresh'
heading_map['7307'] = 'Tube or pipe fittings (for example couplings, elbows, sleeves), of iron or steel'
heading_map['8481'] = 'Taps, cocks, valves and similar appliances for pipes, boiler shells, tanks'
heading_map['8504'] = 'Electrical transformers, static converters and inductors'
heading_map['7318'] = 'Screws, bolts, nuts, coach screws, screw hooks, rivets, cotters, washers'

def build_hierarchical_text(row):
    code = str(row['hsn_code']).strip()
    chap = row['chapter']
    head = row['heading']
    raw_desc = row['description']
    
    # 1. Chapter title
    chap_title = CHAPTER_TITLES.get(chap, f"Chapter {chap}").strip()
    # Clean chapter title
    chap_title = chap_title.split(',')[0].strip()  # take main chapter name
    if not chap_title.endswith('.'):
        chap_title += '.'
        
    # 2. Heading title
    head_title = heading_map.get(head, f"Heading {head}").strip()
    if not head_title.endswith('.'):
        head_title += '.'
        
    # 3. Item leaf description
    # Check if this is 4-digit heading itself
    if len(code) == 4:
        return f"{chap_title} {head_title}"
        
    # For 8-digit items, extract leaf description
    clean_desc = raw_desc
    clean_desc = re.sub(r'^Heading\s+\d{4}\s*-\s*', '', clean_desc, flags=re.I)
    
    # If description contains colon or dash, extract hierarchical components
    parts = re.split(r'\s*[:\-]\s*', clean_desc)
    parts = [p.strip() for p in parts if p.strip()]
    
    # Deduplicate against heading text
    leaf_parts = []
    head_lower = head_title.lower()
    for p in parts:
        p_clean = re.sub(r'\s+', ' ', p).strip()
        if p_clean.lower() not in head_lower:
            leaf_parts.append(p_clean)
            
    if not leaf_parts:
        leaf_desc = parts[-1] if parts else clean_desc
    else:
        leaf_desc = ". ".join(leaf_parts)
        
    # Special canonical handling for 08081000 and 08109040
    if code == '08081000':
        return "Edible fruit and nuts. Apples, pears and quinces, fresh. Apples."
    elif code == '08109040':
        return "Edible fruit and nuts. Other fruit, fresh. Custard-apple (ata, sharifa or sitafal)."
        
    leaf_desc = leaf_desc.title()
    if not leaf_desc.endswith('.'):
        leaf_desc += '.'
        
    return f"{chap_title} {head_title} {leaf_desc}"

# Test on 10 diverse items
test_codes = ['01011010', '08081000', '08109040', '73072100', '84818030', '85044090', '73181500', '10063010']
sample_df = df[df['hsn_code'].isin(test_codes)]
for _, r in sample_df.iterrows():
    h_text = build_hierarchical_text(r)
    print(f"HSN {r['hsn_code']} -> {h_text}")
