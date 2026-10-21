"""Documented, local matching points. Scores are evidence summaries, not probabilities."""
import copy
import json
import re
from datetime import datetime, timezone
from collections import Counter
from .job_evidence import GATES, SKILLS, STATES, affirmative_skill_ids, hit, preferences, requirements
from .matching import salary, category
from .store import now, event
from .studio import current_profile, Conflict

DEFAULT_CONFIG = {'revision':1, 'work_state':'', 'learning_enabled':True, 'learning_epoch':0,
                  'weights':{'technical':35,'transferable':10,'salary':20,'schedule':10,'internal':10,'on_call':10,'growth':5}}
DIMENSIONS = {'technical':'Verified technical overlap','transferable':'Healthcare/teaching transfer',
              'salary':'Base salary','schedule':'Working hours','internal':'Internal employee support',
              'on_call':'On-call expectations','growth':'Career development'}


def configuration(db):
    row=db.execute("SELECT value FROM settings WHERE key='matching'").fetchone()
    return json.loads(row[0]) if row else copy.deepcopy(DEFAULT_CONFIG)


def save_configuration(db, body):
    with db:
        db.execute('BEGIN IMMEDIATE')
        old=configuration(db)
        if body.get('expected_revision') != old['revision']:
            raise Conflict('Matching priorities changed; reload before saving')
        if set(body)-{'expected_revision','weights','work_state','learning_enabled','reset_learning'}:
            raise ValueError('Unknown matching setting')
        new=copy.deepcopy(old)
        if 'weights' in body:
            values=body['weights']
            if not isinstance(values,dict) or set(values)!=set(DIMENSIONS) or any(type(v) is not int or not 0<=v<=100 for v in values.values()) or not sum(values.values()):
                raise ValueError('Provide all seven weights (0–100); at least one must be positive')
            new['weights']=values
        if 'work_state' in body:
            value=body['work_state']
            if not isinstance(value,str) or value not in {'',*STATES}:
                raise ValueError('Choose a supported US work state')
            new['work_state']=value
        if 'learning_enabled' in body:
            if type(body['learning_enabled']) is not bool:
                raise ValueError('Learning preference must be boolean')
            new['learning_enabled']=body['learning_enabled']
        if body.get('reset_learning') is True:
            new['learning_epoch']+=1
        new['revision']+=1
        db.execute("INSERT INTO settings VALUES ('matching',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(new),))
        event(db,'matching_settings_changed',details='Priorities updated; job/profile/resume records retained')
    return {'ok':True}


def candidate_evidence(profile):
    facts=[f for f in profile['facts'] if f['status']=='confirmed' and f['section'] in {'employment','skills','accomplishments','certifications'}] if profile['verified'] else []
    skills, references=set(),{}
    for fact in facts:
        for key in affirmative_skill_ids(fact['text']):
            skills.add(key)
            references.setdefault(key,[]).append(fact['id'])
    employment=' '.join(f['text'] for f in facts if f['section']=='employment')
    return {'skills':skills,'references':references,
            'healthcare':bool(hit(r'\b(?:hospital|clinical|medical clinic|healthcare)\b',employment)),
            'teaching':bool(hit(r'\b(?:teach(?:ing|er)?|mathematics instruction)\b',employment))}


def traits(job, features, pay_category):
    result=[]
    for key,positive,negative in [('internal','internal_support','customer_support'),('on_call','no_on_call','on_call'),('schedule','daytime','off_hours')]:
        value=features[key]['value']
        if value==1:result.append(positive)
        elif value==0:result.append(negative)
    if features['growth']['value']==1:result.append('career_growth')
    if features['healthcare']:result.append('healthcare')
    if pay_category in {'primary','secondary'}:result.append('salary_'+pay_category)
    return result


def feedback_model(db, config):
    signals={}
    rows=db.execute('SELECT action,reason,traits FROM matching_feedback WHERE epoch=?',(config['learning_epoch'],)).fetchall()
    for row in rows:
        if row['action']=='skipped' and row['reason']=='unspecified':
            continue  # Skipping a job is not an unexplained vote against its pay or schedule.
        selected=json.loads(row['traits'])
        groups={'schedule':{'daytime','off_hours'},'on_call':{'no_on_call','on_call'},
                'customer':{'internal_support','customer_support'},'salary':{'salary_primary','salary_secondary'},
                'growth':{'career_growth'},'healthcare':{'healthcare'}}
        if row['reason'] in groups:selected=[t for t in selected if t in groups[row['reason']]]
        elif row['reason'] not in {'general','unspecified'}:selected=[]
        for tag in selected:
            entry=signals.setdefault(tag,{'positive':0,'negative':0})
            entry['positive' if row['action']=='interested' else 'negative']+=1
    return {'signals':signals,'feedback_count':len(rows),'enabled':config['learning_enabled']}


def evaluate(job, profile, candidate, config, target, manual=None, model=None):
    pay=salary(job)
    section=category(pay,target)
    gates=requirements(job,config['work_state'])
    review_data=json.loads(manual['data']) if manual else {}
    stale=bool(manual and (manual['fingerprint']!=job.get('fingerprint') or review_data.get('work_state')!=config['work_state'] or review_data.get('profile_revision')!=profile['revision'] or 'criteria' not in review_data))
    if manual and not stale:
        for key,value in review_data['criteria'].items():
            gates[key]={**value,'method':'owner verification','reviewed_at':manual['updated_at']}
    failed=[GATES[key]+': '+v['evidence'] for key,v in gates.items() if v['status']=='fail']
    unknown=[GATES[key]+': '+v['evidence'] for key,v in gates.items() if v['status']=='unknown']
    features=preferences(job)
    # A vocabulary mention is a potential requirement, not proof every term is mandatory.
    required=affirmative_skill_ids(job['description'])
    matched=required & candidate['skills']
    missing=required-candidate['skills']
    dimension={}
    dimension['technical']={'value':len(matched)/len(required) if required else None,
                            'evidence':f'{len(matched)} of {len(required)} recognized technical topics supported by confirmed professional facts' if required else 'No recognized technical topics; review qualifications manually'}
    transfer=[]
    if features['healthcare']:transfer.append(('Healthcare experience',candidate['healthcare']))
    if features['training']:transfer.append(('Teaching experience',candidate['teaching']))
    dimension['transferable']={'value':sum(v for _,v in transfer)/len(transfer) if transfer else None,
                               'evidence':'; '.join(name+(' supported' if value else ' not established') for name,value in transfer) or 'No recognized healthcare/training connection in posting'}
    dimension['salary']={'value':1 if pay and pay['min']>=target else .5 if pay and pay['max']>=target else 0 if pay else None,
                         'evidence':pay['evidence'] if pay else 'Published annual USD base compensation not verified'}
    dimension.update({key:features[key] for key in ['schedule','internal','on_call','growth']})
    total=sum(config['weights'].values())
    score=round(100*sum(config['weights'][k]*(v['value'] or 0) for k,v in dimension.items())/total,1) if profile['verified'] else None
    coverage=round(100*sum(config['weights'][k] for k,v in dimension.items() if v['value'] is not None)/total) if profile['verified'] else 0
    strengths=[SKILLS[key][0]+' — confirmed professional evidence' for key in sorted(matched)] if profile['verified'] else []
    strengths.extend(name+' transfers to posting context' for name,value in transfer if value)
    gaps=[{'key':key,'label':SKILLS[key][0],'reason':'Mentioned in posting; not established in confirmed professional facts. Verify whether required.'} for key in sorted(missing)] if profile['verified'] else []
    experience=hit(r'\b\d+(?:\s*[-–]\s*\d+|\+)?\s+years?\b',job['description'])
    if experience:unknown.append('Role-specific experience needs review (not an automatic rejection): '+experience)
    education=hit(r'\b(?:bachelor|master|doctoral|computer science degree|IT degree)\b',job['description'])
    if education:unknown.append('Education level and field need review; no equivalent degree is assumed: '+education)
    if re.search(r'\b(?:senior|sr\.?|lead|principal|manager|director)\b',job['title'],re.I):
        unknown.append('Review seniority and technical scope against confirmed employment; title alone is not an automatic rejection')
    bonus=0
    learned=[]
    tags=traits(job,features,section)
    if model and config['learning_enabled'] and score is not None and not failed:
        values=[]
        for tag in tags:
            signal=model['signals'].get(tag)
            if signal:
                value=5*(signal['positive']-signal['negative'])/max(3,sum(signal.values()))
                values.append(value)
                learned.append({'trait':tag,**signal})
        bonus=round(max(-5,min(5,sum(values)/len(values))),1) if values else 0
    eligibility='excluded' if failed else 'needs_verification' if any(v['status']=='unknown' for v in gates.values()) else 'requirements_verified'
    return {'method':'CareerPilot deterministic matching v1','score':score,'evidence_coverage':coverage,
            'profile_revision':profile['revision'] if profile['verified'] else None,
            'profile_required':not profile['verified'],'eligibility':eligibility,
            'gates':gates,'strengths':strengths,'gaps':gaps,'verification_needed':unknown,
            'rejected_reasons':failed,'stale_verification':stale,
            'skill_evidence':{key:candidate['references'][key] for key in sorted(matched)},
            'dimensions':{k:{**v,'label':DIMENSIONS[k],'weight':config['weights'][k],
                             'points':round(100*config['weights'][k]*(v['value'] or 0)/total,2) if score is not None else None} for k,v in dimension.items()},
            'feedback_adjustment':bonus,'feedback_evidence':learned,
            'confidence':'low' if coverage<50 or eligibility!='requirements_verified' else 'medium' if coverage<80 else 'higher evidence coverage',
            'salary':pay,'category':section,'traits':tags,
            'limitation':'Keyword evidence and owner checks; not a hiring probability or a complete semantic qualification review.'}


def context(db):
    profile=current_profile(db)
    config=configuration(db)
    return profile,candidate_evidence(profile),config,feedback_model(db,config)


def record_feedback(db, job_id, action, reason='unspecified'):
    if action not in {'interested','skipped','discovered'} or reason not in {'unspecified','general','schedule','on_call','customer','salary','growth','healthcare','qualification'}:
        raise ValueError('Unsupported matching feedback')
    row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row:raise ValueError('Job not found')
    if action=='discovered':
        db.execute('DELETE FROM matching_feedback WHERE job_id=?',(job_id,))
        return
    profile,candidate,config,model=context(db)
    value=evaluate({**json.loads(row['data']),'fingerprint':row['fingerprint']},profile,candidate,config,
                   json.loads(db.execute("SELECT value FROM settings WHERE key='salary_target'").fetchone()[0]))
    db.execute('''INSERT INTO matching_feedback VALUES (?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
               action=excluded.action,reason=excluded.reason,traits=excluded.traits,epoch=excluded.epoch,updated_at=excluded.updated_at''',
               (job_id,action,reason,json.dumps(value['traits']),config['learning_epoch'],now()))


def verify_job(db, body):
    ident=body.get('job_id')
    if type(ident) is not int:raise ValueError('Numeric job ID required')
    if body.get('acknowledge') is not True:raise ValueError('Explicit owner review acknowledgment required')
    claims=body.get('criteria')
    if not isinstance(claims,dict) or set(claims)!=set(GATES):raise ValueError('Provide every requirement check')
    cleaned={}
    for key,value in claims.items():
        if not isinstance(value,dict) or value.get('status') not in {'pass','fail','unknown'}:
            raise ValueError('Invalid requirement status')
        evidence=value.get('evidence','')
        if not isinstance(evidence,str) or not 1<=len(evidence.strip())<=700:
            raise ValueError('Each requirement needs a source quote or verification note (1–700 characters)')
        cleaned[key]={'status':value['status'],'evidence':evidence.strip()}
    with db:
        db.execute('BEGIN IMMEDIATE')
        job=db.execute('SELECT fingerprint FROM jobs WHERE id=?',(ident,)).fetchone()
        if not job:raise ValueError('Job not found')
        if body.get('expected_fingerprint')!=job[0]:raise Conflict('Posting changed; review the current posting again')
        old=db.execute('SELECT updated_at FROM job_verifications WHERE job_id=?',(ident,)).fetchone()
        if body.get('expected_updated_at')!=(old[0] if old else None):raise Conflict('Requirement review changed; reload before saving')
        stamp=datetime.now(timezone.utc).isoformat(timespec='microseconds')
        payload={'criteria':cleaned,'work_state':configuration(db)['work_state'],'profile_revision':current_profile(db)['revision']}
        db.execute('INSERT INTO job_verifications VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET fingerprint=excluded.fingerprint,data=excluded.data,updated_at=excluded.updated_at',
                   (ident,job[0],json.dumps(payload),stamp))
        event(db,'job_requirements_reviewed',ident,'Owner verification saved; no application action authorized')
    return {'ok':True}


def gap_summary(jobs, profile_verified):
    if not profile_verified:return []
    counts=Counter()
    ids={}
    for job in jobs:
        match=job['match']
        if not job['active'] or job['review_status']=='skipped' or match['eligibility']=='excluded' or match['category']!='primary':continue
        for gap in match['gaps']:
            counts[gap['key']]+=1
            ids.setdefault(gap['key'],[]).append(job['id'])
    links={'powershell':('PowerShell documentation and local scripting practice','https://learn.microsoft.com/powershell/'),
           'sql':('SQLite documentation and local query practice','https://www.sqlite.org/docs.html'),
           'intune':('Microsoft Intune concepts documentation','https://learn.microsoft.com/mem/intune/'),
           'azure':('Azure concepts documentation; no paid lab required','https://learn.microsoft.com/azure/'),
           'linux':('Linux command-line documentation and existing local practice','https://www.gnu.org/software/bash/manual/')}
    return [{'skill':key,'label':SKILLS[key][0],'job_count':count,'job_ids':ids[key],
             'suggestion':links.get(key,('Review the employer requirement and ask whether on-the-job training is available',None))[0],
             'url':links.get(key,(None,None))[1]} for key,count in counts.most_common(5)]
