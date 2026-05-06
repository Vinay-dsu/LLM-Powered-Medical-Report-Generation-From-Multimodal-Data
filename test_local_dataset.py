import os
import csv
import time
import requests
import json
from io import BytesIO
from PIL import Image

API_URL = 'http://127.0.0.1:5000/api/generate'
DATASET_DIR = os.path.join(os.path.dirname(__file__), 'tests_dataset')
IMG_DIR = os.path.join(DATASET_DIR, 'images')
CSV_PATH = os.path.join(DATASET_DIR, 'metadata.csv')

def query_api(pil_image, history):
    """Query the local API running the V5 model."""
    img_byte_arr = BytesIO()
    # Convert image to RGB (some might be RGBA or L)
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    pil_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    files = {'image': ('test.png', img_byte_arr, 'image/png')}
    data = {'history': history}
    r = requests.post(API_URL, files=files, data=data, timeout=60)
    if r.status_code == 200:
        return r.json()
    return None

def main():
    print("=" * 70)
    print("  V5 Model Evaluation: 50 Samples (IEEE-8023 Chest X-Ray Dataset)")
    print("=" * 70)
    
    # Read metadata
    print("\n[1] Parsing dataset metadata and selecting 50 X-Rays...")
    test_cases = []
    
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: Metadata not found at {CSV_PATH}")
        return
        
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row.get('filename')
            finding = row.get('finding')
            view = row.get('view')
            age = row.get('age')
            sex = row.get('sex')
            history = row.get('clinical_notes', '')
            
            # Use only frontal chest x-rays PA/AP that actually exist on disk
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
                        
    print(f"  ✓ Selected {len(test_cases)} valid images for testing.\n")
    
    # Run evaluation
    results = []
    correct_count = 0
    total = len(test_cases)
    
    print("[2] Running benchmark...")
    start_time = time.time()
    
    for i, tc in enumerate(test_cases):
        try:
            pil_image = Image.open(tc['filepath'])
        except Exception as e:
            print(f"  [{i+1:02d}/{total}] ⚠ Failed to open image, skipping...")
            total -= 1
            continue
            
        res = query_api(pil_image, tc['history'])
        if not res:
            print(f"  [{i+1:02d}/{total}] ⚠ API request failed, skipping...")
            total -= 1
            continue
            
        raw_report = res.get('raw_report', '').lower()
        true_finding = tc['finding']
        
        # Evaluate model generation against the true label
        # This dataset is primarily abnormal (COVID-19, Pneumonia, ARDS, etc.) or Normal
        is_abnormal_truth = true_finding.lower() != 'normal'
        
        abnormal_keywords = ['pneumonia', 'opacity', 'consolidation', 'effusion', 'atelectasis', 'infiltrate', 'abnormal', 'disease', 'edema', 'covid']
        is_abnormal_pred = any(k in raw_report for k in abnormal_keywords)
        
        normal_keywords = ['clear', 'normal', 'unremarkable']
        is_normal_pred = any(k in raw_report for k in normal_keywords)
        
        is_correct = False
        if is_abnormal_truth and is_abnormal_pred and not (is_normal_pred and not is_abnormal_pred):
            is_correct = True
        elif not is_abnormal_truth and is_normal_pred and not is_abnormal_pred:
            is_correct = True
            
        if is_correct:
            correct_count += 1
            
        truth_str = 'ABNORMAL' if is_abnormal_truth else 'NORMAL  '
        pred_str = 'ABNORMAL' if is_abnormal_pred else ('NORMAL  ' if is_normal_pred else 'UNCERTAIN')
        
        status = "✓" if is_correct else "✗"
        print(f"  [{i+1:02d}/{total}] {status} True: {truth_str} ({true_finding.split(',')[0][:10]:<10}) | Pred: {pred_str} | Rep: {raw_report[:40].strip()}...")
        
        results.append({
            'finding': true_finding,
            'report': raw_report,
            'is_correct': is_correct
        })
        
    end_time = time.time()
    accuracy = (correct_count / total) * 100 if total > 0 else 0
    
    print("\n" + "=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"  Total time   : {end_time - start_time:.1f}s")
    print(f"  Avg time/img : {(end_time - start_time) / total:.2f}s")
    print(f"  Total tested : {total}")
    print(f"  Accuracy     : {accuracy:.1f}% ({correct_count}/{total} correct)")
    print("=" * 70)

if __name__ == '__main__':
    main()
