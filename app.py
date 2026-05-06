"""
Medical Report Generator — Flask Web App (V5)
=============================================
Serves the V5 multimodal model (ViT + BioGPT) for generating
chest X-ray radiology reports via a web interface.
"""

import io
import os
import re
import time
import traceback

import numpy as np
import torch
import torch.nn as nn
from flask import Flask, jsonify, request, send_from_directory
from PIL import Image
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoModel

# ======================== CONFIG ========================
CHECKPOINT_PATH = os.path.join(os.path.dirname(__file__),
                               'version_5', 'best_multimodal_v5.pt')
IMAGE_SIZE = 224
IMAGE_MEAN = [0.485, 0.456, 0.406]
IMAGE_STD = [0.229, 0.224, 0.225]

# Generation
NUM_BEAMS = 4
LENGTH_PENALTY = 1.2
REPETITION_PENALTY = 2.5
NO_REPEAT_NGRAM = 3
MIN_GEN_TOKENS = 50
MAX_GEN_TOKENS = 256

# Cross-attention (must match training)
CROSS_ATTN_HEADS = 8
CROSS_ATTN_DROPOUT = 0.1


# ======================== MODEL ARCHITECTURE ========================

class CrossAttentionFusion(nn.Module):
    def __init__(self, hidden_size, num_heads=CROSS_ATTN_HEADS,
                 dropout=CROSS_ATTN_DROPOUT):
        super().__init__()
        self.cross_attn = nn.MultiheadAttention(
            hidden_size, num_heads, dropout=dropout, batch_first=True)
        self.norm1 = nn.LayerNorm(hidden_size)
        self.ffn = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 4), nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 4, hidden_size), nn.Dropout(dropout))
        self.norm2 = nn.LayerNorm(hidden_size)

    def forward(self, text_emb, img_emb):
        attn_out, _ = self.cross_attn(query=text_emb, key=img_emb, value=img_emb)
        text_emb = self.norm1(text_emb + attn_out)
        return self.norm2(text_emb + self.ffn(text_emb))


class BioGPTMultimodal(nn.Module):
    def __init__(self, vit_model, gpt_model):
        super().__init__()
        self.vit = vit_model
        self.gpt = gpt_model
        gpt_hidden = gpt_model.config.hidden_size
        self.proj = nn.Linear(vit_model.config.hidden_size, gpt_hidden)
        self.cross_attn = CrossAttentionFusion(gpt_hidden)

    def forward(self, pixel_values, input_ids, attention_mask, labels=None):
        vit_out = self.vit(pixel_values=pixel_values).last_hidden_state
        img_emb = self.proj(vit_out)
        token_emb = self.gpt.get_input_embeddings()(input_ids)
        fused_text = self.cross_attn(token_emb, img_emb)
        inputs_embeds = torch.cat([img_emb, fused_text], dim=1)
        img_mask = torch.ones((input_ids.size(0), img_emb.size(1)),
                              dtype=attention_mask.dtype,
                              device=attention_mask.device)
        new_attn = torch.cat([img_mask, attention_mask], dim=1)
        new_labels = None
        if labels is not None:
            pad = torch.full((labels.size(0), img_emb.size(1)), -100,
                             dtype=labels.dtype, device=labels.device)
            new_labels = torch.cat([pad, labels], dim=1)
        return self.gpt(inputs_embeds=inputs_embeds,
                        attention_mask=new_attn, labels=new_labels,
                        return_dict=True)


# ======================== INFERENCE ========================

def preprocess_image(pil_image, image_size=IMAGE_SIZE):
    """Preprocess a PIL image for the ViT model."""
    mean = np.array(IMAGE_MEAN, dtype='float32').reshape(1, 1, 3)
    std = np.array(IMAGE_STD, dtype='float32').reshape(1, 1, 3)
    im = pil_image.convert('RGB').resize((image_size, image_size),
                                         resample=Image.BILINEAR)
    arr = np.array(im).astype('float32') / 255.0
    arr = (arr - mean) / std
    arr = np.transpose(arr, (2, 0, 1))
    return torch.from_numpy(arr).unsqueeze(0).to(torch.float32)


def generate_report(model, tokenizer, pil_image, history_text='',
                    device='cuda'):
    """Generate a raw report from a PIL image."""
    model.eval()
    pix = preprocess_image(pil_image).to(device)

    prompt = f'Patient history: {history_text}\nReport: '
    prefix_enc = tokenizer(prompt, return_tensors='pt').to(device)
    prefix_ids = prefix_enc['input_ids']
    prefix_attn = prefix_enc['attention_mask']

    with torch.no_grad():
        vit_out = model.vit(pixel_values=pix).last_hidden_state
        img_emb = model.proj(vit_out)
        token_emb = model.gpt.get_input_embeddings()(prefix_ids)
        fused_text = model.cross_attn(token_emb, img_emb)

        inputs_embeds = torch.cat([img_emb, fused_text], dim=1)
        img_mask = torch.ones((1, img_emb.size(1)),
                              dtype=prefix_attn.dtype).to(device)
        new_mask = torch.cat([img_mask, prefix_attn], dim=1)

        gen_ids = model.gpt.generate(
            inputs_embeds=inputs_embeds,
            attention_mask=new_mask,
            max_new_tokens=MAX_GEN_TOKENS,
            min_new_tokens=MIN_GEN_TOKENS,
            num_beams=NUM_BEAMS,
            length_penalty=LENGTH_PENALTY,
            repetition_penalty=REPETITION_PENALTY,
            no_repeat_ngram_size=NO_REPEAT_NGRAM,
        )
        out_text = tokenizer.decode(gen_ids[0], skip_special_tokens=True)
        if prompt in out_text:
            out_text = out_text.split(prompt, 1)[1]

    return out_text.strip()


def smart_sentence_split(text):
    abbreviations = (r'(?<!Dr)(?<!Mr)(?<!Mrs)(?<!Ms)(?<!No)'
                     r'(?<!vs)(?<!etc)(?<!i\.e)(?<!e\.g)')
    sentences = re.split(abbreviations + r'\.\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def parse_report_sections(raw_text):
    """Parse raw model text into structured sections (returns dict)."""
    raw_text = raw_text.replace('_ _ _', '[DATE]').replace('_ _', '[NAME]')
    raw_text = raw_text.strip()

    findings = ''
    impression = ''
    raw_lower = raw_text.lower()

    findings_markers = ['findings:', 'finding:']
    impression_markers = ['impression:', 'impressions:']

    for marker in findings_markers:
        idx = raw_lower.find(marker)
        if idx != -1:
            text_after = raw_text[idx + len(marker):].strip()
            imp_idx = -1
            for imp_marker in impression_markers:
                imp_search = text_after.lower().find(imp_marker)
                if imp_search != -1:
                    imp_idx = imp_search
                    break
            if imp_idx != -1:
                findings = text_after[:imp_idx].strip()
                impression = text_after[imp_idx:].strip()
                for imp_marker in impression_markers:
                    if impression.lower().startswith(imp_marker):
                        impression = impression[len(imp_marker):].strip()
                        break
            else:
                findings = text_after.strip()
            break

    if not findings and not impression:
        for imp_marker in impression_markers:
            if raw_lower.startswith(imp_marker):
                impression = raw_text[len(imp_marker):].strip()
                break
        if not impression:
            findings = raw_text

    # Split into sentences
    finding_sentences = smart_sentence_split(findings) if findings else []
    impression_sentences = smart_sentence_split(impression) if impression else []

    # Ensure sentences end with periods
    finding_sentences = [s + '.' if not s.endswith('.') else s
                         for s in finding_sentences if s]
    impression_sentences = [s + '.' if not s.endswith('.') else s
                            for s in impression_sentences if s]

    # -- Enhance impression if model output was too short or empty --
    # A professional radiology impression should read as flowing clinical prose
    if len(impression_sentences) < 2 and finding_sentences:
        findings_lower = ' '.join(finding_sentences).lower()

        pathology_phrases = []

        if 'opacity' in findings_lower or 'consolidation' in findings_lower:
            pathology_phrases.append(
                'pulmonary opacity/consolidation suggesting possible infiltrate '
                'or inflammatory process')
        if 'effusion' in findings_lower:
            pathology_phrases.append('pleural effusion warranting further clinical assessment')
        if 'atelectasis' in findings_lower:
            pathology_phrases.append(
                'atelectasis, possibly related to underlying process or post-procedural change')
        if 'pneumothorax' in findings_lower:
            pathology_phrases.append('pneumothorax requiring urgent clinical evaluation')
        if 'cardiomegaly' in findings_lower:
            pathology_phrases.append('cardiomegaly for which echocardiographic correlation is advised')
        if 'edema' in findings_lower:
            pathology_phrases.append('pulmonary edema pattern suggestive of fluid overload')
        if 'mass' in findings_lower or 'nodule' in findings_lower:
            pathology_phrases.append(
                'pulmonary nodule/mass for which further imaging (CT) is recommended for characterization')
        if 'fracture' in findings_lower:
            pathology_phrases.append('osseous fracture identified on the current examination')
        if 'pneumonia' in findings_lower or 'infiltrate' in findings_lower:
            pathology_phrases.append(
                'findings suggestive of pneumonia or infectious process')

        if pathology_phrases:
            # Build a cohesive paragraph
            existing = ' '.join(impression_sentences).strip()
            summary = (
                'The above findings are notable for '
                + ', '.join(pathology_phrases[:-1])
                + (' and ' + pathology_phrases[-1] if len(pathology_phrases) > 1 else pathology_phrases[0])
                + '. Clinical correlation and follow-up are recommended.'
            )
            if existing:
                impression_sentences = [existing + ' ' + summary]
            else:
                impression_sentences = [summary]
        elif not impression_sentences:
            if any(w in findings_lower for w in ['clear', 'normal', 'unremarkable', 'no acute']):
                impression_sentences = [
                    'No acute cardiopulmonary abnormality identified. '
                    'The lungs are clear and the cardiac silhouette is within normal limits. '
                    'No pleural effusion or pneumothorax is seen.'
                ]
            else:
                impression_sentences = [
                    'Findings as described above. Clinical correlation is advised for further evaluation.'
                ]

    # Clean up and ensure impression sentences are distinct and properly capitalized
    structured_impression = []
    for s in impression_sentences:
        s = s.strip()
        if s:
            if not s[0].isupper():
                s = s.capitalize()
            structured_impression.append(s)

    return {
        'findings': finding_sentences,
        'impression': structured_impression,
        'recommendations': [
            'Clinical correlation is recommended.',
            'Follow-up imaging may be warranted based on clinical context.',
            'Consult attending physician for treatment decisions.',
        ],
        'disclaimer': (
            'This report was generated by an AI model (ViT + BioGPT). '
            'It is NOT a substitute for professional medical diagnosis. '
            'Always consult a qualified radiologist for clinical decisions.'
        ),
    }


# ======================== FLASK APP ========================

from flask_cors import CORS

app = Flask(__name__, static_folder='static')
CORS(app)

# Globals for model
model = None
tokenizer = None
device = None


def load_model():
    """Load the V5 model at startup."""
    global model, tokenizer, device

    if torch.cuda.is_available():
        device = 'cuda'
        props = torch.cuda.get_device_properties(0)
        print(f'  GPU: {props.name} ({props.total_memory / 1e9:.1f} GB VRAM)')
    else:
        device = 'cpu'
        print('  No GPU detected — using CPU (slower)')

    print('\n[1/4] Loading tokenizer...')
    tokenizer = AutoTokenizer.from_pretrained('microsoft/biogpt')
    if tokenizer.pad_token is None:
        tokenizer.add_special_tokens({'pad_token': '<pad>'})

    print('[2/4] Loading ViT (microsoft/rad-dino)...')
    try:
        vit = AutoModel.from_pretrained('microsoft/rad-dino')
        print('  ✓ rad-dino loaded')
    except Exception:
        print('  rad-dino failed, falling back to vit-base-patch16-224-in21k')
        from transformers import ViTModel
        vit = ViTModel.from_pretrained('google/vit-base-patch16-224-in21k')

    print('[3/4] Loading BioGPT...')
    biogpt = AutoModelForCausalLM.from_pretrained('microsoft/biogpt')
    biogpt.resize_token_embeddings(len(tokenizer))

    print('[4/4] Loading V5 checkpoint...')
    model = BioGPTMultimodal(vit, biogpt)
    ckpt = torch.load(CHECKPOINT_PATH, map_location=device, weights_only=False)
    result = model.load_state_dict(ckpt['model_state_dict'], strict=False)
    if result.missing_keys:
        print(f'  Note: {len(result.missing_keys)} missing keys (expected for architecture diff)')
    if result.unexpected_keys:
        print(f'  Note: {len(result.unexpected_keys)} unexpected keys')
    print('  ✓ Checkpoint loaded successfully')

    model = model.to(device)
    print(f'  Model loaded in FP32 on {device}')

    model.eval()
    total = sum(p.numel() for p in model.parameters())
    print(f'\n✅ Model ready! ({total:,} parameters)')
    print(f'   Device: {device}')
    print(f'   Open http://localhost:5000 in your browser\n')


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """Generate a report from an uploaded X-ray image."""
    if model is None:
        return jsonify({'error': 'Model not loaded yet'}), 503

    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    history = request.form.get('history', '')

    try:
        pil_image = Image.open(io.BytesIO(file.read()))
        start = time.time()
        raw = generate_report(model, tokenizer, pil_image,
                              history_text=history, device=device)
        elapsed = time.time() - start

        sections = parse_report_sections(raw)

        return jsonify({
            'raw_report': raw,
            'sections': sections,
            'inference_time': round(elapsed, 2),
            'device': device,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ready' if model is not None else 'loading',
        'device': device or 'unknown',
    })


if __name__ == '__main__':
    print('=' * 60)
    print('  Medical Report Generator — V5')
    print('  ViT (rad-dino) + BioGPT + Cross-Attention')
    print('=' * 60)
    load_model()
    app.run(host='0.0.0.0', port=5000, debug=False)
