"""
Local Inference Script — Medical Report Generator (v4)
=====================================================
Generates structured radiology reports from chest X-ray images.
Designed for GPUs with 4GB+ VRAM (uses FP16 for low memory usage).

Requirements:
    pip install torch torchvision transformers timm Pillow

Usage:
    python run_local.py --image path/to/xray.jpg
    python run_local.py --image path/to/xray.jpg --checkpoint path/to/best_multimodal_v4.pt
    python run_local.py --image path/to/xray.jpg --cpu   (force CPU if no GPU)
"""

import argparse
import os
import re
import sys

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    ViTModel,
)

# ======================== CONFIG ========================
IMAGE_SIZE = 224
IMAGE_MEAN = [0.485, 0.456, 0.406]
IMAGE_STD = [0.229, 0.224, 0.225]

# Generation parameters
NUM_BEAMS = 4
LENGTH_PENALTY = 1.2
REPETITION_PENALTY = 2.5
NO_REPEAT_NGRAM = 3
MIN_GEN_TOKENS = 50
MAX_GEN_TOKENS = 256

# Cross-attention config (must match training)
CROSS_ATTN_HEADS = 8
CROSS_ATTN_DROPOUT = 0.1


# ======================== MODEL ARCHITECTURE ========================
# (same as training notebook — must match exactly)

class CrossAttentionFusion(nn.Module):
    def __init__(self, hidden_size, num_heads=CROSS_ATTN_HEADS,
                 dropout=CROSS_ATTN_DROPOUT):
        super().__init__()
        self.cross_attn = nn.MultiheadAttention(
            hidden_size, num_heads, dropout=dropout, batch_first=True
        )
        self.norm1 = nn.LayerNorm(hidden_size)
        self.ffn = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 4, hidden_size),
            nn.Dropout(dropout),
        )
        self.norm2 = nn.LayerNorm(hidden_size)

    def forward(self, text_emb, img_emb):
        attn_out, _ = self.cross_attn(
            query=text_emb, key=img_emb, value=img_emb
        )
        text_emb = self.norm1(text_emb + attn_out)
        ffn_out = self.ffn(text_emb)
        text_emb = self.norm2(text_emb + ffn_out)
        return text_emb


class BioGPTMultimodal(nn.Module):
    def __init__(self, vit_model, gpt_model):
        super().__init__()
        self.vit = vit_model
        self.gpt = gpt_model
        gpt_hidden = gpt_model.config.hidden_size
        self.proj = nn.Linear(vit_model.config.hidden_size, gpt_hidden)
        self.cross_attn = CrossAttentionFusion(
            gpt_hidden, num_heads=CROSS_ATTN_HEADS, dropout=CROSS_ATTN_DROPOUT
        )

    def forward(self, pixel_values, input_ids, attention_mask, labels=None):
        vit_out = self.vit(pixel_values=pixel_values).last_hidden_state
        img_emb = self.proj(vit_out)
        token_emb = self.gpt.get_input_embeddings()(input_ids)
        fused_text = self.cross_attn(token_emb, img_emb)
        inputs_embeds = torch.cat([img_emb, fused_text], dim=1)
        img_mask = torch.ones(
            (input_ids.size(0), img_emb.size(1)),
            dtype=attention_mask.dtype, device=attention_mask.device,
        )
        new_attn = torch.cat([img_mask, attention_mask], dim=1)
        if labels is not None:
            pad = torch.full(
                (labels.size(0), img_emb.size(1)), -100,
                dtype=labels.dtype, device=labels.device,
            )
            new_labels = torch.cat([pad, labels], dim=1)
        else:
            new_labels = None
        return self.gpt(
            inputs_embeds=inputs_embeds,
            attention_mask=new_attn,
            labels=new_labels,
            return_dict=True,
        )


# ======================== UTILITIES ========================

def preprocess_image(image_path, image_size=IMAGE_SIZE):
    """Load and normalize an image for ViT."""
    mean = np.array(IMAGE_MEAN, dtype='float32').reshape(1, 1, 3)
    std = np.array(IMAGE_STD, dtype='float32').reshape(1, 1, 3)
    im = Image.open(image_path).convert('RGB').resize(
        (image_size, image_size), resample=Image.BILINEAR
    )
    arr = np.array(im).astype('float32') / 255.0
    arr = (arr - mean) / std
    arr = np.transpose(arr, (2, 0, 1))
    return torch.from_numpy(arr).unsqueeze(0).to(torch.float32)


def smart_sentence_split(text):
    abbreviations = r'(?<!Dr)(?<!Mr)(?<!Mrs)(?<!Ms)(?<!No)(?<!vs)(?<!etc)(?<!i\.e)(?<!e\.g)'
    sentences = re.split(abbreviations + r'\.\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def generate_report(model, tokenizer, image_path, history_text='', device='cuda'):
    """Generate a raw report from an X-ray image."""
    model.eval()
    pix = preprocess_image(image_path).to(device)

    # Use FP16 if on GPU
    use_fp16 = device != 'cpu'

    prompt = f'Patient history: {history_text}\nReport: '
    prefix_enc = tokenizer(prompt, return_tensors='pt').to(device)
    prefix_ids = prefix_enc['input_ids']
    prefix_attn = prefix_enc['attention_mask']

    with torch.no_grad():
        with torch.cuda.amp.autocast(enabled=use_fp16):
            vit_out = model.vit(pixel_values=pix).last_hidden_state
            img_emb = model.proj(vit_out)
            token_emb = model.gpt.get_input_embeddings()(prefix_ids)
            fused_text = model.cross_attn(token_emb, img_emb)

            inputs_embeds = torch.cat([img_emb, fused_text], dim=1)
            img_mask = torch.ones((1, img_emb.size(1)),
                                  dtype=prefix_attn.dtype).to(device)
            new_mask = torch.cat([img_mask, prefix_attn], dim=1)

        # Generate outside autocast for stability
        gen_ids = model.gpt.generate(
            inputs_embeds=inputs_embeds.float(),
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


def format_structured_report(raw_text, patient_info=None):
    """Format raw model output into a structured radiology report."""
    raw_text = raw_text.replace('_ _ _', '[DATE]').replace('_ _', '[NAME]').strip()

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

    sep = '=' * 60
    dash = '-' * 60
    lines = [sep, '           CHEST X-RAY RADIOLOGY REPORT', sep]

    if patient_info:
        lines += ['', 'PATIENT INFORMATION:', f'  {patient_info}']

    if findings:
        lines += ['', dash, 'FINDINGS:', dash]
        for i, s in enumerate(smart_sentence_split(findings), 1):
            s = s.strip()
            if s and not s.endswith('.'):
                s += '.'
            if s:
                lines.append(f'  {i}. {s}')

    if impression:
        lines += ['', dash, 'IMPRESSION:', dash]
        for s in smart_sentence_split(impression):
            s = s.strip()
            if s and not s.endswith('.'):
                s += '.'
            if s:
                lines.append(f'  * {s}')

    lines += [
        '', dash, 'RECOMMENDATIONS:', dash,
        '  * Clinical correlation is recommended.',
        '  * Follow-up imaging may be warranted based on clinical context.',
        '  * Consult attending physician for treatment decisions.',
        '', dash, 'DISCLAIMER:', dash,
        '  This report was generated by an AI model (ViT + BioGPT).',
        '  It is NOT a substitute for professional medical diagnosis.',
        '  Always consult a qualified radiologist for clinical decisions.',
        '', sep,
    ]

    return '\n'.join(lines)


# ======================== MAIN ========================

def main():
    parser = argparse.ArgumentParser(
        description='Generate radiology reports from chest X-ray images (local inference)'
    )
    parser.add_argument('--image', type=str, required=True,
                        help='Path to the chest X-ray image (.jpg, .png)')
    parser.add_argument('--checkpoint', type=str, default='best_multimodal_v4.pt',
                        help='Path to the model checkpoint (.pt file)')
    parser.add_argument('--history', type=str, default='',
                        help='Patient history text (optional)')
    parser.add_argument('--cpu', action='store_true',
                        help='Force CPU inference (slower but works without GPU)')
    args = parser.parse_args()

    # Validate inputs
    if not os.path.isfile(args.image):
        print(f'Error: Image not found: {args.image}')
        sys.exit(1)
    if not os.path.isfile(args.checkpoint):
        print(f'Error: Checkpoint not found: {args.checkpoint}')
        print('Make sure you downloaded best_multimodal_v4.pt from Kaggle.')
        sys.exit(1)

    # Device selection
    if args.cpu or not torch.cuda.is_available():
        device = 'cpu'
        if not args.cpu:
            print('No GPU detected, using CPU (this will be slower).')
    else:
        device = 'cuda'
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_mem / 1e9
        print(f'GPU: {props.name} ({vram_gb:.1f} GB VRAM)')

    print(f'Device: {device}')

    # Step 1: Download base models from HuggingFace (first run only, cached after)
    print('\n[1/4] Loading tokenizer (microsoft/biogpt)...')
    tokenizer = AutoTokenizer.from_pretrained('microsoft/biogpt')
    if tokenizer.pad_token is None:
        tokenizer.add_special_tokens({'pad_token': '<pad>'})

    print('[2/4] Loading ViT base model (google/vit-base-patch16-224-in21k)...')
    vit = ViTModel.from_pretrained('google/vit-base-patch16-224-in21k')

    print('[3/4] Loading BioGPT base model (microsoft/biogpt)...')
    biogpt = AutoModelForCausalLM.from_pretrained('microsoft/biogpt')
    biogpt.resize_token_embeddings(len(tokenizer))

    # Build model and load trained weights
    print('[4/4] Loading trained checkpoint...')
    model = BioGPTMultimodal(vit, biogpt)

    checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint['model_state_dict'])

    # Move to device (FP16 on GPU for lower VRAM usage)
    if device == 'cuda':
        model = model.half().to(device)  # FP16 = ~850MB VRAM
        print('Model loaded in FP16 (low VRAM mode)')
    else:
        model = model.to(device)
        print('Model loaded in FP32 (CPU mode)')

    model.eval()

    total_params = sum(p.numel() for p in model.parameters())
    print(f'Total parameters: {total_params:,}')

    # Generate report
    print(f'\nGenerating report for: {args.image}')
    if args.history:
        print(f'Patient history: {args.history}')
    print('-' * 60)

    raw = generate_report(model, tokenizer, args.image,
                          history_text=args.history, device=device)

    structured = format_structured_report(
        raw, patient_info=args.history if args.history else None
    )
    print(structured)

    # Also print raw output
    print('\n--- Raw model output ---')
    print(raw)


if __name__ == '__main__':
    main()
