# utils/curriculum_loader.py

import re

def read_curriculum(filepath='5_class_ukr.txt'):
    with open(filepath, encoding='utf-8') as f:
        return f.read()


def parse_curriculum_manually(text):
    def roman_to_int(roman):
        values = {'I': 1, 'V': 5, 'X': 10, 'L': 50}
        total = 0
        prev = 0
        for ch in reversed(roman):
            val = values.get(ch, 0)
            if val < prev:
                total -= val
            else:
                total += val
            prev = val
        return total

    structure = {
        'number': 5,
        'name': 'Математика 5 клас',
        'sections': []
    }

    current_section = None
    current_paragraph = None
    item_number = 0

    lines = text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('Розділ'):
            match = re.match(r'Розділ\s+([IVX]+)\.\s*(.+)', line)
            if match:
                roman, name = match.groups()
                current_section = {
                    'number': roman_to_int(roman),
                    'name': name,
                    'paragraphs': []
                }
                structure['sections'].append(current_section)
            continue

        if line.startswith('§'):
            match = re.match(r'§\s*(\d+)\.\s*(.+)', line)
            if match:
                num, name = match.groups()
                current_paragraph = {
                    'number': int(num),
                    'name': name,
                    'items': []
                }
                current_section['paragraphs'].append(current_paragraph)
                item_number = 0
            continue

        if re.match(r'^\d+\.', line):
            match = re.match(r'^(\d+)\.\s*(.+)', line)
            if match:
                item_number = int(match.group(1))
                content = match.group(2)
                current_paragraph['items'].append({
                    'number': item_number,
                    'name': content,
                    'type': 'основний'
                })
            continue

        if line.startswith('•'):
            item_number += 1
            current_paragraph['items'].append({
                'number': item_number,
                'name': line[1:].strip(),
                'type': 'розважання'
            })
            continue

        if re.match(r'^(Завдання|Головне|Вправи|Відповіді|Предметний покажчик)', line):
            item_number += 1
            current_paragraph['items'].append({
                'number': item_number,
                'name': line,
                'type': 'розширення'
            })
            continue

        item_number += 1
        current_paragraph['items'].append({
            'number': item_number,
            'name': line,
            'type': 'розширення'
        })

    return structure
