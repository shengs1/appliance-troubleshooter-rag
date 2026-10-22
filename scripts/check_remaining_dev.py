import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
for qid in ['Q0164', 'Q0325', 'Q0541', 'Q0572', 'Q0543', 'Q0574', 'Q0552', 'Q0645']:
    row = df[df['ID'] == qid].iloc[0]
    print(f"{qid}: Brand={row['Hãng']}, Device={row['Loại_thiết_bị']}, Err={row['Mã_lỗi']}, Dup={row['Duplicate_Group']}, Q='{row['Câu_hỏi_đã_làm_sạch']}'")
