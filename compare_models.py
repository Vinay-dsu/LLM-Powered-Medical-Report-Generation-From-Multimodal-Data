"""Extract and compare metrics from executed v4 and v5 notebooks."""
import json
import re

def extract_outputs(nb_path):
    """Extract all text outputs from a notebook."""
    with open(nb_path, 'r', encoding='utf8') as f:
        nb = json.load(f)
    
    all_text = []
    for cell in nb['cells']:
        for out in cell.get('outputs', []):
            if out.get('output_type') == 'stream':
                all_text.extend(out.get('text', []))
            elif out.get('output_type') in ('execute_result', 'display_data'):
                data = out.get('data', {})
                all_text.extend(data.get('text/plain', []))
    return ''.join(all_text)

def find_metrics(text):
    """Find BLEU, ROUGE, METEOR scores."""
    metrics = {}
    patterns = [
        (r'BLEU-1\s*:\s*([\d.]+)', 'BLEU-1'),
        (r'BLEU-2\s*:\s*([\d.]+)', 'BLEU-2'),
        (r'BLEU-3\s*:\s*([\d.]+)', 'BLEU-3'),
        (r'BLEU-4\s*:\s*([\d.]+)', 'BLEU-4'),
        (r'ROUGE1\s*:\s*([\d.]+)', 'ROUGE-1'),
        (r'ROUGE2\s*:\s*([\d.]+)', 'ROUGE-2'),
        (r'ROUGEL\s*:\s*([\d.]+)', 'ROUGE-L'),
        (r'METEOR\s*:\s*([\d.]+)', 'METEOR'),
    ]
    for pattern, name in patterns:
        match = re.search(pattern, text)
        if match:
            metrics[name] = float(match.group(1))
    return metrics

def find_training_info(text):
    """Extract training loss progression and other info."""
    info = {}
    
    # Find all epoch results
    epoch_pattern = r'Epoch\s+(\d+)\s*\|\s*Train:\s*([\d.]+)\s*\|\s*Val:\s*([\d.]+)'
    epochs = re.findall(epoch_pattern, text)
    if epochs:
        info['epochs'] = [(int(e), float(t), float(v)) for e, t, v in epochs]
    
    # Best val loss
    best_val = re.search(r'Best val loss:\s*([\d.]+)', text)
    if best_val:
        info['best_val_loss'] = float(best_val.group(1))
    
    # Early stopping
    early = re.search(r'Early stopping triggered at epoch (\d+)', text)
    if early:
        info['early_stop_epoch'] = int(early.group(1))
    
    # Total params
    total = re.search(r'Total parameters:\s*([\d,]+)', text)
    if total:
        info['total_params'] = total.group(1)
    
    trainable = re.search(r'Trainable parameters:\s*([\d,]+)', text)
    if trainable:
        info['trainable_params'] = trainable.group(1)
    
    # Cross-attention params
    cross = re.search(r'Cross-attention.*?:\s*([\d,]+)', text)
    if cross:
        info['cross_attn_params'] = cross.group(1)
    
    # ViT model used
    vit_match = re.search(r'Final ViT:\s*(.+)', text)
    if vit_match:
        info['vit_model'] = vit_match.group(1).strip()
    
    # Vision encoder
    vit_match2 = re.search(r'Vision encoder:\s*(.+)', text)
    if vit_match2:
        info['vit_model'] = vit_match2.group(1).strip()
    
    # Dataset size
    train_match = re.search(r'Train:\s*(\d+)\s*\|\s*Validation:\s*(\d+)', text)
    if train_match:
        info['train_size'] = int(train_match.group(1))
        info['val_size'] = int(train_match.group(2))

    return info

def find_sample_reports(text):
    """Extract generated sample reports."""
    reports = []
    pattern = r'SAMPLE\s+(\d+).*?REFERENCE REPORT:\s*\n\s*(.*?)\n.*?GENERATED REPORT:\s*\n(.*?)(?=SAMPLE|\Z)'
    matches = re.findall(pattern, text, re.DOTALL)
    for num, ref, gen in matches[:3]:  # first 3
        reports.append({
            'num': num,
            'reference': ref.strip()[:200],
            'generated': gen.strip()[:200],
        })
    return reports

# Process both notebooks
print("=" * 70)
print("EXTRACTING V4 RESULTS")
print("=" * 70)
v4_text = extract_outputs('version_4/version_4.ipynb')
v4_metrics = find_metrics(v4_text)
v4_info = find_training_info(v4_text)
print(f"Training info: {json.dumps(v4_info, indent=2, default=str)}")
print(f"Metrics: {json.dumps(v4_metrics, indent=2)}")

print("\n" + "=" * 70)
print("EXTRACTING V5 RESULTS")
print("=" * 70)
v5_text = extract_outputs('version_5/version_5.ipynb')
v5_metrics = find_metrics(v5_text)
v5_info = find_training_info(v5_text)
print(f"Training info: {json.dumps(v5_info, indent=2, default=str)}")
print(f"Metrics: {json.dumps(v5_metrics, indent=2)}")

print("\n" + "=" * 70)
print("COMPARISON")
print("=" * 70)
if v4_metrics and v5_metrics:
    print(f"{'Metric':<12} {'V4':>8} {'V5':>8} {'Winner':>8}")
    print("-" * 40)
    for m in v4_metrics:
        v4_val = v4_metrics.get(m, 0)
        v5_val = v5_metrics.get(m, 0)
        winner = 'V4' if v4_val > v5_val else 'V5' if v5_val > v4_val else 'Tie'
        print(f"{m:<12} {v4_val:>8.4f} {v5_val:>8.4f} {winner:>8}")

# Save raw text for debugging
with open('v4_output.txt', 'w', encoding='utf8') as f:
    f.write(v4_text)
with open('v5_output.txt', 'w', encoding='utf8') as f:
    f.write(v5_text)
print("\nRaw outputs saved to v4_output.txt and v5_output.txt")
