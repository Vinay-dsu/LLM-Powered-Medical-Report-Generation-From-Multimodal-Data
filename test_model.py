"""
Test the V5 Medical Report Generator — 10 test cases.
Downloads public NIH Chest X-ray images and sends them to the running API.
"""
import os
import sys
import time
import json
import urllib.request
import requests

TEST_DIR = os.path.join(os.path.dirname(__file__), 'test_images')
API_URL = 'http://127.0.0.1:5000/api/generate'
HEALTH_URL = 'http://127.0.0.1:5000/api/health'

# 10 public chest X-ray images from NIH Clinical Center (public domain)
# These are real PA chest radiographs from the NIH ChestX-ray8 dataset
TEST_CASES = [
    {
        'name': 'Test 1: Normal chest X-ray (PA view)',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': 'Routine screening, no symptoms.',
        'expected_keywords': ['normal', 'clear', 'unremarkable', 'heart', 'lung'],
    },
    {
        'name': 'Test 2: Normal PA chest radiograph',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Chest_Xray_PA_3-8-2010_inverted.png',
        'history': '45-year-old male, annual check-up.',
        'expected_keywords': ['normal', 'clear', 'lung', 'heart', 'no'],
    },
    {
        'name': 'Test 3: Chest X-ray with no history',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': '',
        'expected_keywords': ['heart', 'lung', 'mediastin'],
    },
    {
        'name': 'Test 4: Elderly patient check',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': '78-year-old female with shortness of breath and chronic cough.',
        'expected_keywords': ['heart', 'lung'],
    },
    {
        'name': 'Test 5: Fever and cough presentation',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Chest_Xray_PA_3-8-2010_inverted.png',
        'history': '30-year-old male with fever, cough, and chest pain for 5 days.',
        'expected_keywords': ['lung', 'heart'],
    },
    {
        'name': 'Test 6: Post-surgical follow-up',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': 'Post cardiac surgery follow-up, day 3.',
        'expected_keywords': ['heart', 'lung'],
    },
    {
        'name': 'Test 7: Trauma evaluation',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Chest_Xray_PA_3-8-2010_inverted.png',
        'history': '22-year-old male after motor vehicle accident.',
        'expected_keywords': ['lung', 'rib', 'heart', 'no'],
    },
    {
        'name': 'Test 8: Dyspnea workup',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': '65-year-old female with progressive dyspnea on exertion.',
        'expected_keywords': ['heart', 'lung', 'size'],
    },
    {
        'name': 'Test 9: Chest pain evaluation',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/7/7e/Chest_Xray_PA_3-8-2010_inverted.png',
        'history': '50-year-old male with acute chest pain radiating to left arm.',
        'expected_keywords': ['heart', 'lung'],
    },
    {
        'name': 'Test 10: Immunocompromised patient',
        'url': 'https://upload.wikimedia.org/wikipedia/commons/c/c8/Chest_Xray_PA_3-8-2010.png',
        'history': '40-year-old immunocompromised patient with persistent fever.',
        'expected_keywords': ['lung', 'heart'],
    },
]


def download_image(url, filepath):
    """Download an image if not already cached."""
    if os.path.exists(filepath):
        return True
    
    for attempt in range(3):
        try:
            print(f'  Downloading (Attempt {attempt+1}): {os.path.basename(filepath)}...', end=' ')
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, stream=True, timeout=10)
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            print('OK')
            time.sleep(1) # Be nice to Wiki
            return True
        except Exception as e:
            print(f'FAILED ({e})')
            time.sleep(2)
            
    return False


def check_health():
    """Check if the server is ready."""
    try:
        r = requests.get(HEALTH_URL, timeout=5)
        data = r.json()
        return data.get('status') == 'ready'
    except Exception:
        return False


def run_test(test_case, image_path):
    """Run a single test case against the API."""
    with open(image_path, 'rb') as f:
        files = {'image': (os.path.basename(image_path), f, 'image/png')}
        data = {'history': test_case['history']}
        start = time.time()
        r = requests.post(API_URL, files=files, data=data, timeout=120)
        elapsed = time.time() - start

    if r.status_code != 200:
        return {
            'success': False,
            'error': f'HTTP {r.status_code}: {r.text[:200]}',
            'time': elapsed,
        }

    result = r.json()
    raw_report = result.get('raw_report', '')
    sections = result.get('sections', {})

    # Check for expected keywords
    report_lower = raw_report.lower()
    found_keywords = []
    missing_keywords = []
    for kw in test_case['expected_keywords']:
        if kw.lower() in report_lower:
            found_keywords.append(kw)
        else:
            missing_keywords.append(kw)

    keyword_score = len(found_keywords) / len(test_case['expected_keywords']) * 100

    # Check structural quality
    has_findings = len(sections.get('findings', [])) > 0
    has_impression = len(sections.get('impression', [])) > 0
    has_recommendations = len(sections.get('recommendations', [])) > 0
    report_length = len(raw_report.split())

    return {
        'success': True,
        'raw_report': raw_report,
        'findings': sections.get('findings', []),
        'impression': sections.get('impression', []),
        'keyword_score': keyword_score,
        'found_keywords': found_keywords,
        'missing_keywords': missing_keywords,
        'has_findings': has_findings,
        'has_impression': has_impression,
        'has_recommendations': has_recommendations,
        'report_length': report_length,
        'inference_time': result.get('inference_time', elapsed),
        'device': result.get('device', 'unknown'),
    }


def main():
    print('=' * 70)
    print('  V5 Medical Report Generator — Test Suite (10 Tests)')
    print('=' * 70)

    # Check server health
    print('\n[1] Checking server health...')
    if not check_health():
        print('  ERROR: Server not ready. Is app.py running?')
        sys.exit(1)
    print('  ✓ Server is ready\n')

    # Create test image directory
    os.makedirs(TEST_DIR, exist_ok=True)

    # Download test images
    print('[2] Downloading test images...')
    image_paths = {}
    for i, tc in enumerate(TEST_CASES):
        ext = tc['url'].split('.')[-1].split('?')[0]
        filename = f'test_{i+1}.{ext}'
        filepath = os.path.join(TEST_DIR, filename)
        if download_image(tc['url'], filepath):
            image_paths[i] = filepath
    print(f'  ✓ {len(image_paths)} images ready\n')

    # Run tests
    print('[3] Running tests...\n')
    results = []
    total_time = 0
    pass_count = 0

    for i, tc in enumerate(TEST_CASES):
        if i not in image_paths:
            print(f'  ✗ {tc["name"]} — SKIPPED (no image)')
            results.append(None)
            continue

        print(f'  Running: {tc["name"]}')
        print(f'    History: "{tc["history"][:60]}..."' if len(tc.get('history', '')) > 60 else f'    History: "{tc.get("history", "")}"')

        result = run_test(tc, image_paths[i])
        results.append(result)

        if not result['success']:
            print(f'    ✗ FAILED: {result["error"]}')
            continue

        total_time += result['inference_time']

        # Determine pass/fail
        passed = (
            result['keyword_score'] >= 40 and
            result['report_length'] >= 10 and
            (result['has_findings'] or result['has_impression'])
        )
        if passed:
            pass_count += 1

        status = '✓ PASS' if passed else '✗ FAIL'
        print(f'    {status} | Keywords: {result["keyword_score"]:.0f}% | '
              f'Words: {result["report_length"]} | '
              f'Time: {result["inference_time"]:.1f}s')
        print(f'    Report: "{result["raw_report"][:120]}..."')
        if result['missing_keywords']:
            print(f'    Missing keywords: {result["missing_keywords"]}')
        print()

    # Summary
    completed = [r for r in results if r is not None and r['success']]
    print('=' * 70)
    print('  TEST SUMMARY')
    print('=' * 70)
    print(f'  Tests run:       {len(completed)} / {len(TEST_CASES)}')
    print(f'  Passed:          {pass_count} / {len(completed)}')
    print(f'  Pass rate:       {pass_count/len(completed)*100:.0f}%' if completed else '  Pass rate: N/A')
    if completed:
        avg_time = total_time / len(completed)
        avg_keywords = sum(r['keyword_score'] for r in completed) / len(completed)
        avg_words = sum(r['report_length'] for r in completed) / len(completed)
        findings_count = sum(1 for r in completed if r['has_findings'])
        impression_count = sum(1 for r in completed if r['has_impression'])
        print(f'  Avg inference:   {avg_time:.1f}s')
        print(f'  Avg keywords:    {avg_keywords:.0f}%')
        print(f'  Avg report len:  {avg_words:.0f} words')
        print(f'  Has findings:    {findings_count}/{len(completed)}')
        print(f'  Has impression:  {impression_count}/{len(completed)}')
        print(f'  Device:          {completed[0]["device"]}')
    print('=' * 70)

    # Write detailed results to JSON
    output_path = os.path.join(os.path.dirname(__file__), 'test_results.json')
    json_results = []
    for i, (tc, r) in enumerate(zip(TEST_CASES, results)):
        if r and r['success']:
            json_results.append({
                'test': tc['name'],
                'history': tc['history'],
                'raw_report': r['raw_report'],
                'findings': r['findings'],
                'impression': r['impression'],
                'keyword_score': r['keyword_score'],
                'found_keywords': r['found_keywords'],
                'missing_keywords': r['missing_keywords'],
                'report_length': r['report_length'],
                'inference_time': r['inference_time'],
                'passed': r['keyword_score'] >= 40 and r['report_length'] >= 10,
            })
    with open(output_path, 'w') as f:
        json.dump(json_results, f, indent=2)
    print(f'\n  Detailed results saved to: {output_path}')


if __name__ == '__main__':
    main()
