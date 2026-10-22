import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_excel('data/raw/dataset.xlsx', sheet_name='DATA_CLEAN_TECH')
df_by_id = {str(row['ID']).strip(): row for _, row in df.iterrows()}

pairs = [
    ('Q0158', 'Q0308', 'Panasonic Điều hòa F16', 'DUP79719DB9'),
    ('Q0159', 'Q0310', 'Panasonic Điều hòa F93', 'DUP44278C6B'),
    ('Q0160', 'Q0311', 'Panasonic Điều hòa F95', 'DUP9E57CFC6'),
    ('Q0161', 'Q0312', 'Panasonic Điều hòa F97', 'DUPC3E76538'),
    ('Q0165', 'Q0326', 'Panasonic Điều hòa H97', 'DUPF2D57116'),
    ('Q0167', 'Q0328', 'Panasonic Điều hòa H99', 'DUP660C4236'),
    ('Q0196', 'Q0333', 'Panasonic Máy giặt H09', 'DUP11C6536F'),
    ('Q0214', 'Q0350', 'Panasonic Bếp từ U04', 'DUPD0D40AC0'),
    ('Q0215', 'Q0351', 'Panasonic Bếp từ U11*', 'DUP8C02EB6E'),
    ('Q0234', 'Q0318', 'Panasonic Điều hòa H27', 'DUPF11FAC19'),
]

print("="*90)
print("GIAI ĐOẠN 4 — PHÂN LOẠI KHOA HỌC 10 CẶP BẢN GHI SONG SINH")
print("="*90)

for idx, (exp, pred, desc, dg) in enumerate(pairs, 1):
    re = df_by_id[exp]
    rp = df_by_id[pred]
    ans_exp = str(re.get('Trả_lời')).strip()
    ans_pred = str(rp.get('Trả_lời')).strip()

    print(f"Cặp #{idx}: {exp} vs {pred} ({desc} | Duplicate_Group: {dg})")
    print(f"  - Câu hỏi Exp : '{re.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"  - Câu hỏi Pred: '{rp.get('Câu_hỏi_đã_làm_sạch')}'")
    print(f"  - Nội dung {exp} (Expected): '{ans_exp}'")
    print(f"  - Nội dung {pred} (Predicted): '{ans_pred}'")
    print(f"  -> Phân loại mối quan hệ tri thức: BỔ SUNG NHAU (CAUSE vs REPAIR)")
    print("-" * 90)
