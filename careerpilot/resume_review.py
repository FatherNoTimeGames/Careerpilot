"""Deterministic checks; never claim semantic truth or AI proofreading."""
import re
from datetime import date

SECTIONS = {'contact': 'Contact', 'summary': 'Professional Summary', 'employment': 'Professional Experience',
            'education': 'Education', 'skills': 'Technical Skills', 'personal': 'Personal Technical Experience',
            'accomplishments': 'Accomplishments', 'certifications': 'Certifications'}
ALIASES = {'contact': 'contact', 'summary': 'summary', 'professional summary': 'summary',
           'experience': 'employment', 'employment': 'employment', 'employment history': 'employment',
           'work experience': 'employment', 'professional experience': 'employment',
           'education': 'education', 'skills': 'skills', 'technical skills': 'skills',
           'personal technical experience': 'personal', 'personal projects': 'personal',
           'accomplishments': 'accomplishments', 'achievements': 'accomplishments', 'certifications': 'certifications'}


MONTHS = {name: i for i, name in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
DATE = r'(?:[A-Za-z]{3,9}\s+\d{4}|(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?)'


def source_dates(text):
    match = re.search(r'(' + DATE + r')\s*(?:–|—|-|\bto\b)\s*(' + DATE + r'|present|current)', text, re.I)
    if not match:
        return '', ''
    def convert(value):
        value = value.lower().strip()
        if value in {'present', 'current'}:
            return 'present'
        if re.fullmatch(r'(?:19|20)\d{2}(?:-\d{2})?', value):
            return value
        parts = value.split()
        if len(parts) == 2 and parts[0][:3] in MONTHS:
            return parts[1] + '-' + str(MONTHS[parts[0][:3]]).zfill(2)
        return ''
    return convert(match[1]), convert(match[2])


def organize(text):
    facts, section, lines = [], 'contact', []
    def flush():
        if lines:
            start, end = source_dates('\n'.join(lines))
            facts.append({'section': section, 'text': '\n'.join(lines).strip(), 'status': 'pending',
                          'evidence': 'Imported text; confirm against original document', 'start_date': start, 'end_date': end})
            lines.clear()
    for raw in text.splitlines():
        line = raw.strip()
        key = line.rstrip(':').lower()
        if key in ALIASES:
            flush()
            section = ALIASES[key]
        elif not line:
            flush()
        else:
            lines.append(line)
            if len('\n'.join(lines)) > 4000:
                flush()
    flush()
    # Date ranges are copied from source evidence, never confirmed automatically.
    return facts[:100]


def profile_warnings(facts):
    warnings, blockers = [], []
    sections = {f['section'] for f in facts}
    for section in ['contact', 'employment', 'education', 'skills']:
        if section not in sections:
            warnings.append(f'Missing {SECTIONS[section]} information')
    seen = set()
    for i, fact in enumerate(facts, 1):
        if fact['status'] != 'confirmed':
            warnings.append(f'Entry {i}: {fact["status"]}; excluded from resume versions until confirmed')
        key = re.sub(r'\s+', ' ', fact['text']).lower()
        if key in seen:
            warnings.append(f'Entry {i}: duplicate content')
        seen.add(key)
        start, end = fact.get('start_date', ''), fact.get('end_date', '')
        text_start, text_end = source_dates(fact['text'])
        if (start and text_start and start != text_start) or (end and text_end and end != text_end):
            blockers.append(f'Entry {i}: date fields contradict the date range in the text')
        if start and end and end != 'present' and start > end:
            blockers.append(f'Entry {i}: end date precedes start date')
        if start and start > date.today().isoformat()[:7]:
            blockers.append(f'Entry {i}: start date is in the future; verify this is actual experience')
        years = [int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', fact['text'])]
        if len(years) == 2 and years[0] > years[1]:
            blockers.append(f'Entry {i}: reversed years in source text; correct or separate these statements')
        if fact['section'] in {'employment', 'education'} and not start:
            warnings.append(f'Entry {i}: dates are unstructured or missing; enter verified date fields')
        if re.search(r'\b(?:present|current|currently)\b', fact['text'], re.I) or end == 'present':
            warnings.append(f'Entry {i}: confirm ongoing/current information is still up to date')
        if fact['section'] == 'contact' and not re.search(r'\b\S+@\S+\.\S+\b', fact['text']):
            warnings.append(f'Entry {i}: verify name and contact information; email not detected')
    return {'warnings': list(dict.fromkeys(warnings)), 'blockers': list(dict.fromkeys(blockers))}


def revision_review(blocks):
    warnings, blockers = [], []
    for i, block in enumerate(blocks, 1):
        original, revised = block['original'], block['revised']
        if not revised.strip():
            blockers.append(f'Entry {i}: revised content is empty')
        old_numbers = set(re.findall(r'\b\d+(?:[.,]\d+)*(?:%|\+)?', original))
        new_numbers = set(re.findall(r'\b\d+(?:[.,]\d+)*(?:%|\+)?', revised))
        if new_numbers - old_numbers:
            blockers.append(f'Entry {i}: new numerical claims; verify them in the career profile first')
        credentials = r'\b(?:certified|certification|CCNA|CISSP|CompTIA|MCSE|MBA|PhD)\b'
        if set(x.lower() for x in re.findall(credentials, revised, re.I)) - set(x.lower() for x in re.findall(credentials, original, re.I)):
            blockers.append(f'Entry {i}: new credential language; verify in the career profile first')
        if original != revised and not block.get('explanation', '').strip():
            blockers.append(f'Entry {i}: explain the wording change')
        if re.search(r'\b(?:results-driven|dynamic professional|leverage|synergy|passionate professional|proven track record)\b', revised, re.I):
            warnings.append(f'Entry {i}: consider plainer language instead of generic resume phrasing')
        if re.search(r'\b(\w+)\s+\1\b', revised, re.I):
            warnings.append(f'Entry {i}: repeated word')
        if '  ' in revised or re.search(r'\s+[,.!?]', revised):
            warnings.append(f'Entry {i}: spacing or punctuation needs review')
        if len(revised.split()) > 150:
            warnings.append(f'Entry {i}: long entry; consider concise bullets')
    starts = [b['revised'].split()[0].lower() for b in blocks if b['revised'].split()]
    if len(starts) >= 3 and len(set(starts)) <= len(starts)//2:
        warnings.append('Several entries begin with the same word; review repetitive phrasing')
    return {'warnings': warnings, 'blockers': blockers,
            'method': 'Deterministic number, credential, repetition and formatting checks. Human proofreading and truth verification remain required.'}
