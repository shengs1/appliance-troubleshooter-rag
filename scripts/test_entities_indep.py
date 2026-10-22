import sys
from rag_chatbot.retrieval import extract_question_entities

sys.stdout.reconfigure(encoding='utf-8')

queries = [
    'điều hoà pana báo f16 là bị làm sao thợ ơi',
    'bếp từ pana nhấp nháy chữ U11 lúc đang nấu',
    'máy giặt lg kêu tít tít rồi hiện IE không vào nước',
    'điều hòa samsung tự nhiên hiện mã lỗi CF',
    'máy giặt samsung báo lỗi DC cửa đóng rồi mà vẫn kêu'
]
for q in queries:
    print(f"'{q}'\n  --> {extract_question_entities(q)}")
