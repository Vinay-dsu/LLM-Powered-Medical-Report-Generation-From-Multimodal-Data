from docx import Document
from docx.shared import Pt
import os

doc = Document()

heading = doc.add_heading("Appendix A: Core Implementation Source Code", level=1)
doc.add_paragraph("This appendix provides an abridged view of the core neural network architecture for the Medical Report Generator (V5), specifically the multimodal CrossAttentionFusion layer and BioGPT-ViT integration.")

def add_code_file(doc, title, filepath):
    doc.add_heading(title, level=2)
    p = doc.add_paragraph()
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
        filtered_lines = []
        capture = False
        
        for line in lines:
            # We only want the MODEL ARCHITECTURE section
            if "# ======================== MODEL ARCHITECTURE ========================" in line:
                capture = True
                continue
            if "# ======================== INFERENCE ========================" in line:
                capture = False
                break
            
            if capture:
                filtered_lines.append(line)
        
        # Add a small note at the bottom
        filtered_lines.append("\n# ... Inference and Flask Server logic omitted for brevity ...\n")
        code_text = "".join(filtered_lines).strip()
    
    run = p.add_run(code_text)
    run.font.name = 'Courier New'
    run.font.size = Pt(8)

add_code_file(doc, "Multimodal Model Definition (app.py)", r"c:\GoatProject\app.py")

doc.save(r"c:\GoatProject\Appendix_A.docx")
print("Successfully generated 2-page Appendix_A.docx")
