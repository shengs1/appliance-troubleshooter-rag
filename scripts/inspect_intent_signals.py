import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

pairs = [
    ('Q0002', 'Q0108'),
    ('Q0158', 'Q0308'),
    ('Q0159', 'Q0310'),
    ('Q0160', 'Q0311'),
    ('Q0161', 'Q0312'),
    ('Q0165', 'Q0326'),
    ('Q0167', 'Q0328'),
    ('Q0196', 'Q0333'),
    ('Q0214', 'Q0350'),
    ('Q0215', 'Q0351'),
    ('Q0234', 'Q0318'),
]

for exp, pred in pairs:
    re = df_by_id[exp]
    rp = df_by_id[pred]
    print(f"=== {exp} (Expected) vs {pred} (Predicted Top-1) ===")
    print(f"  EXP : Q_Type='{re.get('Loại_câu_hỏi')}' | Ans_Type='{re.get('Loại_câu_trả_lời')}' | Cause='{re.get('Nguyên_nhân')}' | Fix='{re.get('Cách_khắc_phục')}'")
    print(f"        Q_Clean = '{re.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"        Answer  = '{str(re.get('Trả_lời'))[:80]}'")
    print(f"  PRED: Q_Type='{rp.get('Loại_câu_hỏi')}' | Ans_Type='{rp.get('Loại_câu_trả_lời')}' | Cause='{rp.get('Nguyên_nhân')}' | Fix='{rp.get('Cách_khắc_phục')}'")
    print(f"        Q_Clean = '{rp.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"        Answer  = '{str(rp.get('Trả_lời'))[:80]}'")
    print()
