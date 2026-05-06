import os
import csv
import shutil

DATASET_DIR = os.path.join(os.path.dirname(__file__), 'tests_dataset')
IMG_DIR = os.path.join(DATASET_DIR, 'images')
CSV_PATH = os.path.join(DATASET_DIR, 'metadata.csv')
TARGET_DIR = os.path.join(os.path.dirname(__file__), 'benchmark_images')

def main():
    print(f"Creating highly-curated benchmark image directory at: {TARGET_DIR}")
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: Metadata not found at {CSV_PATH}")
        return
        
    copied = 0
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filename = row.get('filename')
            view = row.get('view')
            
            # Use only frontal chest x-rays PA/AP that actually exist on disk
            if view in ['PA', 'AP', 'AP Supine'] and filename:
                filepath = os.path.join(IMG_DIR, filename)
                valid_ext = filename.lower().endswith(('.png', '.jpg', '.jpeg'))
                
                if valid_ext and os.path.exists(filepath):
                    target_path = os.path.join(TARGET_DIR, f"{copied+1:02d}_{filename}")
                    
                    if not os.path.exists(target_path):
                        shutil.copy2(filepath, target_path)
                    copied += 1
                    
                    if copied >= 50:
                        break
                        
    print(f"Successfully collected {copied} benchmark images to '{TARGET_DIR}'")

if __name__ == '__main__':
    main()
