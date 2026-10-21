"""Private profile/version workflows. No application preparation or submission authority."""
import base64
import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from .store import now, event
from .resume_revision import revision_provider
from .resume_review import SECTIONS, organize, profile_warnings, revision_review, source_dates


class Conflict(ValueError):
    pass


def process(request):
    try:
        child = subprocess.run([sys.executable, '-m', 'careerpilot.resume_documents'],
                               input=json.dumps(request), capture_output=True, text=True, timeout=35,
                               cwd=Path(__file__).resolve().parent.parent)
        result = json.loads(child.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        raise ValueError('Document processing exceeded limits or failed; original retained if uploaded') from None
    if not result.get('ok'):
        raise ValueError(result.get('error', 'Document could not be processed'))
    return result['result']


def current_profile(db):
    row = db.execute('SELECT * FROM career_profiles ORDER BY id DESC LIMIT 1').fetchone()
    return {'revision': row['id'], 'verified': bool(row['verified']), 'facts': json.loads(row['facts']),
            'created_at': row['created_at']} if row else {'revision': 0, 'verified': False, 'facts': []}


def state(db):
    profile = current_profile(db)
    versions = []
    for row in db.execute('SELECT * FROM resume_versions ORDER BY id DESC'):
        version = dict(row)
        version['blocks'] = json.loads(version['blocks'])
        version['review'] = json.loads(version['review'])
        version['profile_outdated'] = version['profile_revision'] != profile['revision']
        exports = db.execute('SELECT checks,edit_revision FROM resume_exports WHERE version_id=?', (row['id'],)).fetchone()
        version['preview'] = json.loads(exports['checks']) if exports and exports['edit_revision'] == row['edit_revision'] else None
        versions.append(version)
    master = db.execute('SELECT version_id FROM resume_master WHERE id=1').fetchone()
    return {'profile': {**profile, 'review': profile_warnings(profile['facts'])},
            'documents': [dict(row) | {'warnings': json.loads(row['warnings'])}
                          for row in db.execute('SELECT id,filename,kind,sha256,extracted_text,warnings,created_at FROM resume_documents ORDER BY id DESC')],
            'versions': versions, 'master_version_id': master[0] if master else None,
            'job_resumes': [dict(row) for row in db.execute('SELECT * FROM job_resumes')],
            'sections': SECTIONS,
            'ai': revision_provider.capability()}


def import_document(db, body):
    filename = body.get('filename')
    if not isinstance(filename, str) or not filename or len(filename) > 200:
        raise ValueError('A filename is required (maximum 200 characters)')
    filename = filename.replace('\\', '/').rsplit('/', 1)[-1]
    kind = filename.rsplit('.', 1)[-1].lower()
    if kind not in {'pdf', 'docx'}:
        raise ValueError('Only PDF and DOCX uploads are supported')
    try:
        raw = base64.b64decode(body['data'], validate=True)
    except (KeyError, ValueError, TypeError):
        raise ValueError('Invalid upload encoding') from None
    if not 0 < len(raw) <= 5 * 1024 * 1024:
        raise ValueError('Upload must be between 1 byte and 5 MB')
    # Commit the original before processing. An unreadable document must remain recoverable.
    with db:
        ident = db.execute('''INSERT INTO resume_documents(filename,kind,sha256,original,extracted_text,warnings,created_at)
                           VALUES (?,?,?,?,?,?,?)''', (filename, kind, hashlib.sha256(raw).hexdigest(), raw, '', '[]', now())).lastrowid
        event(db, 'resume_imported', details=f'Document {ident}; content withheld from log')
    try:
        result = process({'action': 'extract', 'kind': kind, 'data': body['data']})
    except ValueError as exc:
        result = {'text': '', 'warnings': [str(exc)]}
    facts = organize(result['text'])
    if len(facts) >= 100:
        result['warnings'].append('Extraction reached the 100-entry limit. Review the full original for information not organized into entries.')
    if facts:
        result['warnings'].append('Extracted grouping and dates need manual verification; nothing is confirmed automatically.')
    with db:
        db.execute('UPDATE resume_documents SET extracted_text=?,warnings=? WHERE id=?',
                   (result['text'], json.dumps(result['warnings']), ident))
    # Import never silently replaces the career profile.
    return {'document_id': ident, 'suggested_facts': [{**f, 'id': str(uuid.uuid4()), 'document_id': ident} for f in facts],
            'warnings': result['warnings']}


def document_facts(db, body):
    ident = body.get('document_id')
    if type(ident) is not int:
        raise ValueError('Numeric document ID required')
    row = db.execute('SELECT extracted_text FROM resume_documents WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Document not found')
    return {'suggested_facts': [{**f, 'id': str(uuid.uuid4()), 'document_id': ident} for f in organize(row[0])]}


def clean_facts(db, values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('Profile must contain at most 100 entries')
    result, seen = [], set()
    for raw in values:
        if not isinstance(raw, dict) or raw.get('section') not in SECTIONS or raw.get('status') not in {'pending', 'inferred', 'confirmed'}:
            raise ValueError('Invalid section or fact verification status')
        ident = raw.get('id') or str(uuid.uuid4())
        if not isinstance(ident, str) or len(ident) > 80 or ident in seen:
            raise ValueError('Invalid or duplicate fact ID')
        seen.add(ident)
        text, evidence = raw.get('text', ''), raw.get('evidence', '')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 5000:
            raise ValueError('Each entry needs 1–5,000 characters')
        if not isinstance(evidence, str) or len(evidence) > 1000:
            raise ValueError('Evidence must be text, at most 1,000 characters')
        if raw['status'] == 'confirmed' and not evidence.strip():
            raise ValueError('Confirmed entries require an evidence or personal-attestation note')
        dates = {}
        for field in ['start_date', 'end_date']:
            value = raw.get(field, '')
            if not isinstance(value, str) or (value and not re.fullmatch(r'(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?|present' if field == 'end_date' else r'(?:19|20)\d{2}(?:-(?:0[1-9]|1[0-2]))?', value)):
                raise ValueError('Dates must be YYYY or YYYY-MM; end date may be present')
            dates[field] = value
        doc = raw.get('document_id')
        if doc is not None and (type(doc) is not int or not db.execute('SELECT 1 FROM resume_documents WHERE id=?', (doc,)).fetchone()):
            raise ValueError('Unknown source document')
        result.append({'id': ident, 'section': raw['section'], 'text': text.strip(), 'status': raw['status'],
                       'evidence': evidence.strip(), 'document_id': doc, **dates})
    return result


def save_profile(db, body):
    facts = clean_facts(db, body.get('facts'))
    with db:
        db.execute('BEGIN IMMEDIATE')
        if body.get('expected_revision') != current_profile(db)['revision']:
            raise Conflict('Profile changed in another window; reload before saving')
        revision = db.execute('INSERT INTO career_profiles(facts,created_at) VALUES (?,?)', (json.dumps(facts), now())).lastrowid
        event(db, 'profile_saved', details=f'Revision {revision}; content withheld from log')
    return {'revision': revision, 'review': profile_warnings(facts)}


def verify_profile(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        profile = current_profile(db)
        if body.get('expected_revision') != profile['revision']:
            raise Conflict('Profile changed; reload and review again')
        if body.get('acknowledge') is not True or not any(f['status'] == 'confirmed' for f in profile['facts']):
            raise ValueError('Confirm at least one fact and explicitly acknowledge profile review')
        review = profile_warnings(profile['facts'])
        if review['blockers']:
            raise ValueError('; '.join(review['blockers']))
        db.execute('UPDATE career_profiles SET verified=1 WHERE id=?', (profile['revision'],))
        event(db, 'profile_verified', details=f'Revision {profile["revision"]}')
    return {'ok': True}


def get_version(db, ident):
    if type(ident) is not int:
        raise ValueError('Numeric version ID required')
    row = db.execute('SELECT * FROM resume_versions WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Resume version not found')
    return row


def create_version(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        profile = current_profile(db)
        if not profile['verified'] or body.get('profile_revision') != profile['revision']:
            raise ValueError('Save and verify the current career profile first')
        facts = [f for f in profile['facts'] if f['status'] == 'confirmed']
        selected = body.get('fact_ids')
        if selected is not None:
            if not isinstance(selected, list) or not selected or any(not isinstance(i, str) for i in selected) or len(set(selected)) != len(selected) or set(selected) - {f['id'] for f in facts}:
                raise ValueError('Select confirmed facts only')
            by_id = {f['id']: f for f in facts}
            facts = [by_id[i] for i in selected]
        else:
            order = list(SECTIONS)
            facts.sort(key=lambda f: order.index(f['section']))
        blocks = []
        for fact in facts:
            text = fact['text']
            if fact.get('start_date') and not source_dates(text)[0]:
                text += '\n' + fact['start_date'] + (' – ' + fact['end_date'].title() if fact.get('end_date') else '')
            blocks.append({'fact_id': fact['id'], 'section': fact['section'], 'original': text,
                           'revised': text, 'explanation': ''})
        label = body.get('label', '')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 120:
            raise ValueError('Version name must be 1–120 characters')
        job = body.get('job_id')
        if job is not None and (type(job) is not int or not db.execute('SELECT 1 FROM jobs WHERE id=?', (job,)).fetchone()):
            raise ValueError('Unknown target job')
        source = body.get('source_document_id')
        if source is not None and source not in {f['document_id'] for f in facts}:
            raise ValueError('Source document must support a selected fact')
        version = db.execute('''INSERT INTO resume_versions(label,profile_revision,job_id,source_document_id,blocks,review,created_at)
                     VALUES (?,?,?,?,?,?,?)''', (label.strip(), profile['revision'], job, source,
                     json.dumps(blocks), json.dumps(revision_review(blocks)), now())).lastrowid
        event(db, 'resume_draft_created', job, f'Version {version}; no application authorization')
    return {'version_id': version}


def edit_version(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        version = get_version(db, body.get('version_id'))
        if version['status'] != 'draft':
            raise ValueError('Approved versions are immutable; create a new version')
        if body.get('expected_edit_revision') != version['edit_revision']:
            raise Conflict('Draft changed; reload before editing')
        originals = json.loads(version['blocks'])
        edits = body.get('blocks')
        if not isinstance(edits, list) or len(edits) != len(originals):
            raise ValueError('Provide a revision for each selected fact')
        for block, edited in zip(originals, edits):
            if not isinstance(edited, dict) or edited.get('fact_id') != block['fact_id']:
                raise ValueError('Facts cannot be replaced in a draft; edit the career profile instead')
            for key, limit in [('revised', 6000), ('explanation', 1000)]:
                value = edited.get(key, '')
                if not isinstance(value, str) or len(value) > limit:
                    raise ValueError('Invalid revision text or explanation')
                block[key] = value.strip()
        review = revision_review(originals)
        db.execute('UPDATE resume_versions SET blocks=?,review=?,edit_revision=edit_revision+1 WHERE id=?',
                   (json.dumps(originals), json.dumps(review), version['id']))
        db.execute('DELETE FROM resume_exports WHERE version_id=?', (version['id'],))
        db.execute('DELETE FROM resume_pages WHERE version_id=?', (version['id'],))
        event(db, 'resume_draft_edited', details=f'Version {version["id"]}')
    return {'review': review}


def preview_version(db, body):
    version = get_version(db, body.get('version_id'))
    if version['edit_revision'] != body.get('expected_edit_revision'):
        raise Conflict('Draft changed; reload before previewing')
    blocks = json.loads(version['blocks'])
    review = revision_review(blocks)
    if review['blockers']:
        raise ValueError('; '.join(review['blockers']))
    result = process({'action': 'export', 'blocks': [{'heading': SECTIONS[b['section']], 'text': b['revised']} for b in blocks]})
    with db:
        db.execute('BEGIN IMMEDIATE')
        current = get_version(db, version['id'])
        if current['edit_revision'] != version['edit_revision'] or current['status'] != 'draft':
            raise Conflict('Version changed during export; reload')
        db.execute('INSERT OR REPLACE INTO resume_exports VALUES (?,?,?,?,?)',
                   (version['id'], version['edit_revision'], base64.b64decode(result['pdf']),
                    base64.b64decode(result['docx']), json.dumps(result['checks'])))
        db.execute('DELETE FROM resume_pages WHERE version_id=?', (version['id'],))
        for i, page in enumerate(result['pages'], 1):
            db.execute('INSERT INTO resume_pages VALUES (?,?,?)', (version['id'], i, base64.b64decode(page)))
    return {'checks': result['checks']}


def approve_version(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        version = get_version(db, body.get('version_id'))
        if version['status'] != 'draft' or version['edit_revision'] != body.get('expected_edit_revision'):
            raise Conflict('Draft changed or already approved; reload')
        profile = current_profile(db)
        if not profile['verified'] or profile['revision'] != version['profile_revision']:
            raise ValueError('Career profile changed; verify it and create a new draft before approving')
        if body.get('truth_reviewed') is not True or body.get('layout_reviewed') is not True:
            raise ValueError('Explicit truth/proofreading and rendered-layout approval required')
        export = db.execute('SELECT * FROM resume_exports WHERE version_id=?', (version['id'],)).fetchone()
        if not export or export['edit_revision'] != version['edit_revision']:
            raise ValueError('Generate and inspect the current PDF preview first')
        if revision_review(json.loads(version['blocks']))['blockers']:
            raise ValueError('Resolve blocked revisions before approval')
        db.execute("UPDATE resume_versions SET status='approved',approved_at=? WHERE id=?", (now(), version['id']))
        event(db, 'resume_approved', version['job_id'], f'Version {version["id"]}; master unchanged; no submission authorization')
    return {'ok': True}


def set_master(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        version = get_version(db, body.get('version_id'))
        old = db.execute('SELECT version_id FROM resume_master WHERE id=1').fetchone()
        if body.get('expected_master_version_id') != (old[0] if old else None):
            raise Conflict('Master changed; reload before replacing it')
        if version['status'] != 'approved' or body.get('approve_replacement') is not True:
            raise ValueError('Explicit approval of an approved version as master is required')
        db.execute('INSERT INTO resume_master VALUES (1,?) ON CONFLICT(id) DO UPDATE SET version_id=excluded.version_id', (version['id'],))
        event(db, 'master_resume_replaced', details=f'Version {version["id"]}')
    return {'ok': True}


def select_for_job(db, body):
    with db:
        version = get_version(db, body.get('version_id'))
        job = body.get('job_id')
        if version['status'] != 'approved' or type(job) is not int or not db.execute('SELECT 1 FROM jobs WHERE id=?', (job,)).fetchone():
            raise ValueError('Select an approved version and an existing job')
        db.execute('INSERT INTO job_resumes VALUES (?,?,?) ON CONFLICT(job_id) DO UPDATE SET version_id=excluded.version_id,selected_at=excluded.selected_at',
                   (job, version['id'], now()))
        event(db, 'resume_selected_for_job', job, f'Version {version["id"]}; not preparation or submission authorization')
    return {'ok': True}


ACTIONS = {'import': import_document, 'document/facts': document_facts, 'profile/save': save_profile, 'profile/verify': verify_profile,
           'version/create': create_version, 'version/edit': edit_version, 'version/preview': preview_version,
           'version/approve': approve_version, 'master': set_master, 'select': select_for_job}
