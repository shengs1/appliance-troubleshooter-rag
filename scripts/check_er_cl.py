import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
for qid in ['Q0005', 'Q0007', 'Q0008', 'Q0110']:
    row = df[df['ID'] == qid].iloc[0]
    print(f"{qid}: Brand={row['Hãng']}, Device={row['Loại_thiết_bị']}, Err='{row['Mã_lỗi']}', Q='{row['Câu_hỏi_đã_làm_sạch'][:50]}'")
