#!/usr/bin/env python3
"""
Extract MTG tournament data from screenshots and convert to CSV files.
Processes screenshots one by one and extracts: Rank, Name, Points, W-L-D stats.
"""

import csv
import re
from pathlib import Path
from PIL import Image
import pytesseract

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "data" / "screenshots"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "tournament_data"
OUTPUT_DIR.mkdir(exist_ok=True)


def extract_text_from_image(image_path):
    try:
        img = Image.open(image_path)
        return pytesseract.image_to_string(img)
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return ""


def clean_name(name):
    if not name:
        return ""
    name = name.replace(')', '').replace('(', '').replace('{', '').replace('}', '')
    name = name.replace('\\', '').replace('|', '').replace('§', '').replace('$', '')
    name = name.replace('[', '').replace(']', '')
    name = re.sub(r'\.*$', '', name)
    name = re.sub(r'\.{2,}', '', name)
    name = re.sub(r'\s*if\s*$', '', name)
    name = re.sub(r'\s*i\s*$', '', name)
    # Strip stray trailing digits/single-letter tokens (leaked Points/artifacts)
    name = re.sub(r'\s+\d+$', '', name)
    name = re.sub(r'\s+[^\sA-Za-złśćżźóąęńŁŚĆŻŹÓĄĘŃ]+$', '', name)
    name = ' '.join(name.split())
    return name.strip()


def parse_tournament_data(text):
    lines = text.split('\n')
    results = parse_horizontal_format(lines)
    if results:
        return results
    return parse_vertical_format(lines)


def parse_horizontal_format(lines):
    results = []
    for line in lines:
        line = line.strip()
        if not line or line.lower() in ['rank name points w-l-d omw%', 'match standings']:
            continue
        if 'rank' in line.lower() and 'name' in line.lower():
            continue
        wld_match = re.search(r'(\d+-\d+-\d+)', line)
        if not wld_match:
            continue
        wld = wld_match.group(1)
        before_wld = line[:wld_match.start()].strip()
        parts = before_wld.split()
        if len(parts) < 2:
            continue
        try:
            rank = int(parts[0])
        except ValueError:
            continue
        name_and_points = ' '.join(parts[1:])
        points_match = re.search(r'(\d+)\s*$', name_and_points)
        if points_match:
            points = points_match.group(1)
            name = name_and_points[:points_match.start()].strip()
        else:
            name = name_and_points
            points = "0"
        name = clean_name(name)
        if name:
            results.append({'Rank': str(rank), 'Name': name, 'Points': points, 'W-L-D': wld})
    return results


def parse_vertical_format(lines):
    results = []
    rank_name_end = -1
    points_start = -1
    wld_start = -1
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if 'points' in line_lower and 'rank' not in line_lower and 'name' not in line_lower:
            points_start = i
        elif line_lower == 'w-l-d':
            wld_start = i
        elif line_lower.startswith('rank') and 'name' in line_lower:
            rank_name_end = i
    if points_start < 0 or wld_start < 0:
        return results
    rank_name_data = []
    for i in range(rank_name_end + 1, points_start):
        line = lines[i].strip()
        if line:
            line = re.sub(r'^\d+\.\s*', '', line)
            match = re.match(r'^(\d+)\s+(.+)$', line)
            if match:
                rank, name = match.groups()
                name = clean_name(name)
                if name:
                    rank_name_data.append({'rank': rank, 'name': name})
    points_data = []
    for i in range(points_start + 1, wld_start):
        line = lines[i].strip()
        if line and re.match(r'^\d+$', line):
            points_data.append(line)
    wld_data = []
    for i in range(wld_start + 1, len(lines)):
        line = lines[i].strip()
        if line and re.match(r'^\d+-\d+-\d+', line):
            wld_match = re.search(r'(\d+-\d+-\d+)', line)
            if wld_match:
                wld_data.append(wld_match.group(1))

    # Points OCR is often garbled/misaligned (e.g. "Ve", missing lines).
    # W-L-D is far more reliable, so we only require Rank/Name and W-L-D to
    # line up; Points is recomputed later as 3*W + D if it's missing/wrong.
    num_results = min(len(rank_name_data), len(wld_data))
    for i in range(num_results):
        points = points_data[i] if i < len(points_data) else "0"
        results.append({
            'Rank': rank_name_data[i]['rank'],
            'Name': rank_name_data[i]['name'],
            'Points': points,
            'W-L-D': wld_data[i]
        })
    return results


def process_screenshot(image_path):
    print(f"Processing: {image_path.name}")
    text = extract_text_from_image(image_path)
    results = parse_tournament_data(text)
    return results, text


def save_to_csv(results, output_path):
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Rank', 'Name', 'Points', 'W-L-D'])
        writer.writeheader()
        writer.writerows(results)
    print(f"  Saved {len(results)} records to {output_path.name}")


def main():
    image_files = sorted(list(SCREENSHOTS_DIR.glob("*.png")) + list(SCREENSHOTS_DIR.glob("*.jpg")))
    if not image_files:
        print("No image files found!")
        return
    print(f"Found {len(image_files)} screenshots to process\n")
    for idx, image_path in enumerate(image_files, 1):
        print(f"[{idx}/{len(image_files)}] {image_path.name}")
        results, raw_text = process_screenshot(image_path)
        output_path = OUTPUT_DIR / (image_path.stem + ".csv")
        save_to_csv(results, output_path)
        print()


if __name__ == "__main__":
    main()
