"""
NLG Evaluation Metrics for Medical Report Generator (V5)
=========================================================
Computes BLEU (1-4), ROUGE-L, METEOR, and keyword accuracy
on 50 images from the IEEE-8023 COVID Chest X-Ray Dataset.

Reference reports are constructed from dataset ground truth labels
and standard radiology templates.
"""

import os
import csv
import json
import time
import re
import requests
from io import BytesIO
from PIL import Image

# NLG Metrics
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer

# Download required NLTK data
nltk.download('wordnet', quiet=True)
nltk.download('omw-1.4', quiet=True)
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

API_URL = 'http://127.0.0.1:5000/api/generate'
DATASET_DIR = os.path.join(os.path.dirname(__file__), 'tests_dataset')
IMG_DIR = os.path.join(DATASET_DIR, 'images')
CSV_PATH = os.path.join(DATASET_DIR, 'metadata.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'evaluation_metrics.json')

# Reference report templates by pathology
REFERENCE_TEMPLATES = {
    'COVID-19': (
        "Findings: PA view of the chest demonstrates bilateral ground-glass opacities "
        "predominantly in the peripheral and lower lung zones. No significant pleural "
        "effusion is identified. The cardiac silhouette is within normal limits. "
        "Impression: Bilateral ground-glass opacities consistent with viral pneumonia, "
        "highly suggestive of COVID-19 infection given clinical context. "
        "No acute cardiopulmonary decompensation."
    ),
    'Pneumonia': (
        "Findings: Chest radiograph demonstrates focal consolidation in the lung fields "
        "with possible air bronchograms. The cardiac silhouette is within normal limits. "
        "No pleural effusion or pneumothorax identified. "
        "Impression: Findings consistent with pneumonia. Clinical correlation and "
        "follow-up chest radiograph recommended."
    ),
    'ARDS': (
        "Findings: Diffuse bilateral pulmonary opacities are present consistent with "
        "acute respiratory distress syndrome. The cardiac silhouette appears normal. "
        "Endotracheal tube and central venous catheter noted in appropriate position. "
        "Impression: Diffuse bilateral opacities consistent with ARDS. "
        "Clinical correlation recommended."
    ),
    'Streptococcus': (
        "Findings: Chest radiograph shows focal consolidation in the lung fields "
        "suggestive of bacterial pneumonia. The cardiac silhouette is normal. "
        "No pleural effusion or pneumothorax. "
        "Impression: Consolidation consistent with bacterial pneumonia, "
        "possibly streptococcal in origin. Antibiotic therapy and follow-up recommended."
    ),
    'SARS': (
        "Findings: Bilateral ground-glass opacities are noted predominantly in the "
        "peripheral lung zones. No pleural effusion identified. The cardiac silhouette "
        "is within normal limits. "
        "Impression: Bilateral ground-glass opacities suggestive of viral pneumonia, "
        "consistent with SARS coronavirus infection. Clinical correlation recommended."
    ),
    'Normal': (
        "Findings: PA and lateral views of the chest provided. The lungs are clear "
        "without focal consolidation. No pleural effusion or pneumothorax is seen. "
        "The cardiac and mediastinal silhouettes are unremarkable. "
        "Impression: No acute cardiopulmonary abnormality identified."
    ),
}


def get_reference(finding_label):
    """Get reference report template based on ground truth label."""
    finding_lower = finding_label.lower()
    if 'covid' in finding_lower:
        return REFERENCE_TEMPLATES['COVID-19']
    elif 'ards' in finding_lower:
        return REFERENCE_TEMPLATES['ARDS']
    elif 'streptococcus' in finding_lower:
        return REFERENCE_TEMPLATES['Streptococcus']
    elif 'sars' in finding_lower and 'covid' not in finding_lower:
        return REFERENCE_TEMPLATES['SARS']
    elif any(w in finding_lower for w in ['pneumonia', 'bacterial', 'viral']):
        return REFERENCE_TEMPLATES['Pneumonia']
    elif 'normal' in finding_lower or 'no finding' in finding_lower:
        return REFERENCE_TEMPLATES['Normal']
    else:
        return REFERENCE_TEMPLATES['Pneumonia']  # fallback


def clean_report(text):
    """Clean and normalize a report for NLG evaluation."""
    text = re.sub(r'[^\x00-\x7F]+', '', text)  # strip non-ASCII
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def query_api(pil_image, history):
    """Query the local API."""
    img_byte_arr = BytesIO()
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    pil_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    files = {'image': ('test.png', img_byte_arr, 'image/png')}
    data = {'history': history}
    r = requests.post(API_URL, files=files, data=data, timeout=120)
    if r.status_code == 200:
        return r.json()
    return None


def compute_metrics(reference, hypothesis):
    """Compute all NLG metrics for a single pair."""
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()

    smoothie = SmoothingFunction().method1

    # BLEU scores (1-4)
    bleu1 = sentence_bleu([ref_tokens], hyp_tokens,
                          weights=(1, 0, 0, 0), smoothing_function=smoothie)
    bleu2 = sentence_bleu([ref_tokens], hyp_tokens,
                          weights=(0.5, 0.5, 0, 0), smoothing_function=smoothie)
    bleu3 = sentence_bleu([ref_tokens], hyp_tokens,
                          weights=(0.33, 0.33, 0.33, 0), smoothing_function=smoothie)
    bleu4 = sentence_bleu([ref_tokens], hyp_tokens,
                          weights=(0.25, 0.25, 0.25, 0.25), smoothing_function=smoothie)

    # METEOR
    try:
        meteor = meteor_score([ref_tokens], hyp_tokens)
    except Exception:
        meteor = 0.0

    # ROUGE-L
    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
    rouge_result = scorer.score(reference, hypothesis)
    rouge_l_f = rouge_result['rougeL'].fmeasure
    rouge_l_p = rouge_result['rougeL'].precision
    rouge_l_r = rouge_result['rougeL'].recall

    # Clinical keyword accuracy
    clinical_keywords = [
        'findings', 'impression', 'chest', 'lung', 'cardiac',
        'consolidation', 'effusion', 'pneumothorax', 'opacity',
        'normal', 'clear', 'silhouette', 'mediastinal'
    ]
    found = sum(1 for kw in clinical_keywords if kw in hypothesis)
    keyword_coverage = found / len(clinical_keywords)

    return {
        'bleu1': bleu1,
        'bleu2': bleu2,
        'bleu3': bleu3,
        'bleu4': bleu4,
        'meteor': meteor,
        'rouge_l_f': rouge_l_f,
        'rouge_l_p': rouge_l_p,
        'rouge_l_r': rouge_l_r,
        'keyword_coverage': keyword_coverage,
    }


def main():
    print("=" * 70)
    print("  NLG Evaluation: BLEU / ROUGE-L / METEOR / CIDEr")
    print("  Dataset: IEEE-8023 COVID Chest X-Ray (50 images)")
    print("=" * 70)

    # Read metadata
    test_cases = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row.get('filename')
            finding = row.get('finding')
            view = row.get('view')
            age = row.get('age')
            sex = row.get('sex')
            history = row.get('clinical_notes', '')

            if view in ['PA', 'AP', 'AP Supine'] and filename:
                filepath = os.path.join(IMG_DIR, filename)
                valid_ext = filename.lower().endswith(('.png', '.jpg', '.jpeg'))
                if valid_ext and os.path.exists(filepath):
                    hist_str = f"{age}yo {sex}. " if age and sex else ""
                    hist_str += history[:100] + ("..." if len(history) > 100 else "")
                    test_cases.append({
                        'filepath': filepath,
                        'finding': finding,
                        'history': hist_str.strip()
                    })
                    if len(test_cases) >= 50:
                        break

    print(f"\n  Found {len(test_cases)} test images.\n")

    # Aggregate metrics
    all_metrics = {
        'bleu1': [], 'bleu2': [], 'bleu3': [], 'bleu4': [],
        'meteor': [], 'rouge_l_f': [], 'rouge_l_p': [], 'rouge_l_r': [],
        'keyword_coverage': [],
    }
    per_category = {}
    individual_results = []
    inference_times = []

    start = time.time()

    for i, tc in enumerate(test_cases):
        try:
            pil_image = Image.open(tc['filepath'])
        except Exception:
            print(f"  [{i+1:02d}] SKIP - cannot open image")
            continue

        t0 = time.time()
        res = query_api(pil_image, tc['history'])
        t1 = time.time()

        if not res:
            print(f"  [{i+1:02d}] SKIP - API error")
            continue

        inference_times.append(t1 - t0)

        raw = clean_report(res.get('raw_report', ''))
        ref = clean_report(get_reference(tc['finding']))

        metrics = compute_metrics(ref, raw)

        # Aggregate
        for k, v in metrics.items():
            all_metrics[k].append(v)

        # Per-category
        cat = tc['finding'].split(',')[0].strip()
        if cat not in per_category:
            per_category[cat] = {k: [] for k in all_metrics}
        for k, v in metrics.items():
            per_category[cat][k].append(v)

        individual_results.append({
            'image': os.path.basename(tc['filepath']),
            'finding': tc['finding'],
            **{k: round(v, 4) for k, v in metrics.items()},
            'inference_time': round(t1 - t0, 2),
        })

        status = "OK" if metrics['bleu1'] > 0.2 else "LOW"
        print(f"  [{i+1:02d}/{len(test_cases)}] {status} | "
              f"B1:{metrics['bleu1']:.3f} B4:{metrics['bleu4']:.3f} "
              f"R-L:{metrics['rouge_l_f']:.3f} M:{metrics['meteor']:.3f} "
              f"| {tc['finding'][:25]}")

    elapsed = time.time() - start

    # Compute averages
    def avg(lst):
        return sum(lst) / len(lst) if lst else 0.0

    summary = {
        'total_images': len(individual_results),
        'total_time': round(elapsed, 1),
        'avg_inference_time': round(avg(inference_times), 2),
        'overall_metrics': {
            'BLEU-1': round(avg(all_metrics['bleu1']), 4),
            'BLEU-2': round(avg(all_metrics['bleu2']), 4),
            'BLEU-3': round(avg(all_metrics['bleu3']), 4),
            'BLEU-4': round(avg(all_metrics['bleu4']), 4),
            'METEOR': round(avg(all_metrics['meteor']), 4),
            'ROUGE-L (F1)': round(avg(all_metrics['rouge_l_f']), 4),
            'ROUGE-L (Precision)': round(avg(all_metrics['rouge_l_p']), 4),
            'ROUGE-L (Recall)': round(avg(all_metrics['rouge_l_r']), 4),
            'Clinical Keyword Coverage': round(avg(all_metrics['keyword_coverage']), 4),
        },
        'per_category_metrics': {},
        'individual_results': individual_results,
    }

    for cat, cat_metrics in per_category.items():
        summary['per_category_metrics'][cat] = {
            'count': len(cat_metrics['bleu1']),
            'BLEU-1': round(avg(cat_metrics['bleu1']), 4),
            'BLEU-4': round(avg(cat_metrics['bleu4']), 4),
            'METEOR': round(avg(cat_metrics['meteor']), 4),
            'ROUGE-L (F1)': round(avg(cat_metrics['rouge_l_f']), 4),
        }

    # Save results
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("  OVERALL NLG METRICS")
    print("=" * 70)
    om = summary['overall_metrics']
    print(f"  BLEU-1     : {om['BLEU-1']:.4f}")
    print(f"  BLEU-2     : {om['BLEU-2']:.4f}")
    print(f"  BLEU-3     : {om['BLEU-3']:.4f}")
    print(f"  BLEU-4     : {om['BLEU-4']:.4f}")
    print(f"  METEOR     : {om['METEOR']:.4f}")
    print(f"  ROUGE-L F1 : {om['ROUGE-L (F1)']:.4f}")
    print(f"  ROUGE-L P  : {om['ROUGE-L (Precision)']:.4f}")
    print(f"  ROUGE-L R  : {om['ROUGE-L (Recall)']:.4f}")
    print(f"  Keyword Cov: {om['Clinical Keyword Coverage']:.4f}")
    print(f"\n  Avg Inference: {summary['avg_inference_time']}s")
    print(f"  Total Time: {summary['total_time']}s")
    print("=" * 70)

    print(f"\n  Results saved to: {OUTPUT_PATH}")

    # Per-category breakdown
    print("\n  PER-CATEGORY BREAKDOWN:")
    print(f"  {'Category':<20} {'N':>3} {'BLEU-1':>8} {'BLEU-4':>8} {'METEOR':>8} {'ROUGE-L':>8}")
    print("  " + "-" * 60)
    for cat, cm in sorted(summary['per_category_metrics'].items()):
        print(f"  {cat[:20]:<20} {cm['count']:>3} {cm['BLEU-1']:>8.4f} "
              f"{cm['BLEU-4']:>8.4f} {cm['METEOR']:>8.4f} {cm['ROUGE-L (F1)']:>8.4f}")


if __name__ == '__main__':
    main()
