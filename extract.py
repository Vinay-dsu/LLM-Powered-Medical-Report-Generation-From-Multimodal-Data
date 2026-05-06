import sys
import docx
import fitz
import os

with open("extract_output.txt", "w", encoding="utf-8") as out:
    def read_docx(file_path):
        out.write(f"--- CONTENT OF {os.path.basename(file_path)} ---\n")
        doc = docx.Document(file_path)
        for p in doc.paragraphs:
            if p.text.strip():
                out.write(p.text + "\n")
        out.write("\n")

    def read_pdf(file_path):
        out.write(f"--- CONTENT OF {os.path.basename(file_path)} ---\n")
        doc = fitz.open(file_path)
        for p in doc:
            out.write(p.get_text() + "\n")
        out.write("\n")

    docx_files = [
        r"Docx\Document format Details.docx",
        r"Docx\Index-Contents.docx",
        r"Docx\Project Report Content.docx"
    ]

    pdf_file = r"Docx\Draft.pdf"

    for df in docx_files:
        if os.path.exists(df):
            read_docx(df)
        else:
            out.write(f"File not found: {df}\n")

    if os.path.exists(pdf_file):
        read_pdf(pdf_file)
    else:
        out.write(f"File not found: {pdf_file}\n")
