import os
import time
import requests
import json
from datasets import load_dataset
from io import BytesIO

API_URL = 'http://127.0.0.1:5000/api/generate'

def query_api(pil_image):
    """Query the local API running the V5 model."""
    img_byte_arr = BytesIO()
    pil_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    files = {'image': ('test.png', img_byte_arr, 'image/png')}
    data = {'history': ''}
    r = requests.post(API_URL, files=files, data=data, timeout=60)
    if r.status_code == 200:
        return r.json()
    return None

def main():
    print("=" * 60)
    print("  V5 Model Evaluation: 50 Samples from HuggingFace Datasets")
    print("=" * 60)
    
    # Using a common public dataset: Falah/chest_xray (0=Normal, 1=Pneumonia)
    print("\n[1] Loading 'Falah/chest_xray' dataset in streaming mode...")
    dataset = load_dataset("Falah/chest_xray", split="test", streaming=True)
    
    results = []
    correct_count = 0
    total = 0
    
    print("\n[2] Running evaluation on 50 samples...")
    start_time = time.time()
    
    for i, data in enumerate(dataset):
        if total >= 50:
            break
            
        try:
            pil_image = data["image"].convert("RGB")
            label = data["label"]  # 0 or 1
        except Exception as e:
            continue
        
        res = query_api(pil_image)
        if not res:
            print(f"[{total+1}/50] ⚠ API request failed, skipping...")
            continue
            
        raw_report = res.get('raw_report', '').lower()
        
        # Evaluate model generation against the true label
        is_pneumonia_truth = (label == 1)
        
        # Keywords indicating abnormal structures/pneumonia
        abnormal_keywords = ['pneumonia', 'opacity', 'consolidation', 'effusion', 'atelectasis', 'infiltrate', 'abnormal', 'disease']
        is_abnormal_pred = any(k in raw_report for k in abnormal_keywords)
        
        # Keywords indicating normal healthy chest
        normal_keywords = ['clear', 'normal', 'unremarkable']
        is_normal_pred = any(k in raw_report for k in normal_keywords)
        
        # Determine strict correctness:
        # If Ground Truth is Pneumonia -> Must mention abnormal keywords, and NOT strictly say 'heart and lungs are normal'
        # If Ground Truth is Normal -> Must mention normal keywords, and NOT mention abnormal keywords
        is_correct = False
        if is_pneumonia_truth and is_abnormal_pred and not (is_normal_pred and not is_abnormal_pred):
            is_correct = True
        elif not is_pneumonia_truth and is_normal_pred and not is_abnormal_pred:
            is_correct = True
            
        if is_correct:
            correct_count += 1
            
        total += 1
        truth_str = 'PNEUMONIA' if is_pneumonia_truth else 'NORMAL   '
        pred_str = 'ABNORMAL' if is_abnormal_pred else ('NORMAL  ' if is_normal_pred else 'UNCERTAIN')
        
        status = "✓" if is_correct else "✗"
        print(f"  [{total:02d}/50] {status} True: {truth_str} | Pred: {pred_str} | Report: {raw_report[:45].strip()}...")
        
        results.append({
            'label': label,
            'report': raw_report,
            'is_correct': is_correct
        })
        
    end_time = time.time()
    accuracy = (correct_count / total) * 100 if total > 0 else 0
    
    print("\n" + "=" * 60)
    print("  BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"  Total time   : {end_time - start_time:.1f}s")
    print(f"  Avg time/img : {(end_time - start_time) / total:.2f}s")
    print(f"  Total tested : {total}")
    print(f"  Accuracy     : {accuracy:.1f}% ({correct_count}/{total} correct)")
    print("=" * 60)

if __name__ == '__main__':
    main()
