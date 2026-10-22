import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
for qid in ['Q0535', 'Q0566', 'Q0597', 'Q0628', 'Q0659', 'Q0690']:
    row = df[df['ID'] == qid].iloc[0]
    print(f"{qid}: Brand={row['Hãng']}, Device={row['Loại_thiết_bị']}, Issue={row['Issue_ID']}, Dup={row['Duplicate_Group']}, Q='{row['Câu_hỏi_đã_làm_sạch']}'")
