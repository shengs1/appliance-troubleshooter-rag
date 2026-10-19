import sys
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
print("Columns:", df.columns.tolist())

# find id column
id_col = [c for c in df.columns if 'id' in c.lower() or 'mã' in c.lower()][0]
q_col = [c for c in df.columns if 'câu hỏi' in c.lower() or 'cau_hoi' in c.lower() or 'question' in c.lower()][0]

qids = ['Q0002', 'Q0108', 'Q0158', 'Q0308', 'Q0165', 'Q0326', 'Q0536', 'Q0660', 'Q0537', 'Q0568', 'Q0813', 'Q0817']
for qid in qids:
    sub = df[df[id_col] == qid]
    if len(sub) > 0:
        row = sub.iloc[0]
        print(f"{qid}: [{row[q_col]}]")
