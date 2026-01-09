import fitz  # pip install PyMuPDF

def pdf_to_paragraphs(pdf_path):
    """
    将 PDF 拆分成段落
    返回列表，每个元素是一个段落字典：{page_num, paragraph_index, content}
    """
    doc = fitz.open(pdf_path)
    paragraphs = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")  # 获取文本
        # 按双换行拆分段落
        raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for idx, para in enumerate(raw_paragraphs):
            paragraphs.append({
                "page_num": page_num,
                "paragraph_index": idx,
                "content": para
            })

    return paragraphs

# ========================
# 示例
# ========================
pdf_path = "paper1.pdf"
paragraphs = pdf_to_paragraphs(pdf_path)

for p in paragraphs:
    print(f"Page {p['page_num']}, Paragraph {p['paragraph_index']}")
    print(p["content"])
    print("---")