"""Conservative posting evidence. Unknown/conflicting claims never satisfy a hard filter."""
import re

GATES = {'remote': 'Fully remote', 'us': 'US hiring', 'state': 'Work-state eligibility',
         'full_time': 'Full-time employment', 'benefits': 'Benefits', 'travel': 'No required travel',
         'certifications': 'No additional certification before applying', 'role_focus':'Suitable IT/support responsibilities'}

SKILLS = {
    'ad_support': ('Active Directory support', r'\bactive directory\b|\bAD (?:accounts?|users?)\b'),
    'm365': ('Microsoft 365 support', r'\b(?:microsoft|office)\s*365\b|\bM365\b'),
    'windows': ('Windows support', r'\bwindows\b'),
    'imaging': ('Computer imaging/deployment', r'\b(?:imaging|image deployment|computer deployment)\b'),
    'hardware': ('Hardware troubleshooting', r'\b(?:hardware|laptops?|workstations?)\b'),
    'printers': ('Printer support', r'\bprinters?\b'),
    'networking': ('Basic networking', r'\b(?:networking|TCP/IP|DNS|DHCP|cabling)\b'),
    'application_support': ('Application support', r'\bapplication (?:support|troubleshooting)\b'),
    'intune': ('Microsoft Intune', r'\bintune\b'),
    'sccm': ('SCCM/MECM', r'\b(?:SCCM|MECM)\b'),
    'powershell': ('PowerShell', r'\bpowershell\b'),
    'linux': ('Linux administration', r'\blinux\b'),
    'azure': ('Azure', r'\bazure\b'),
    'aws': ('AWS', r'\bAWS\b|amazon web services'),
    'sql': ('SQL', r'\bSQL\b'),
    'workday': ('Workday', r'\bworkday\b'),
    'salesforce': ('Salesforce', r'\bsalesforce\b'),
    'ad_admin': ('Advanced Active Directory administration', r'\b(?:domain controllers?|forest trusts?|group policy design)\b'),
    'network_engineering': ('Network engineering', r'\b(?:BGP|OSPF|network engineering|router configuration)\b'),
    'meditech_admin': ('Meditech administration', r'\bmeditech administrat\w*\b'),
}
STATES = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado',
          'CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho',
          'IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana',
          'ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi',
          'MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey',
          'NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma',
          'OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota',
          'TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington',
          'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia'}


def hit(pattern, text):
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    return text[max(0, match.start()-45):min(len(text), match.end()+100)].strip()


def claim(status, evidence, method='posting'):
    return {'status': status, 'evidence': evidence, 'method': method}


def choice(positive, negative, missing):
    if positive and negative:
        return claim('unknown', 'Conflicting posting statements: '+positive+' | '+negative)
    if negative:
        return claim('fail', negative)
    if positive:
        return claim('pass', positive)
    return claim('unknown', missing)


def affirmative_skill_ids(text):
    found = set()
    for key, (_, pattern) in SKILLS.items():
        for match in re.finditer(pattern, text, re.I):
            before = text[max(0,match.start()-65):match.start()].lower()
            after = text[match.end():match.end()+65].lower()
            # Never turn disclaimers or explicit absence into candidate skill evidence.
            if re.search(r'(?:no|without|lack(?:s|ing)?|not assume|not experienced in|not proficient in|no experience (?:with|in))[^.;\n]*$', before):
                continue
            if re.match(r'\s*(?:experience\s+)?(?:not held|not possessed|not a skill|not verified)', after):
                continue
            found.add(key)
    return found


def schedule_evidence(text):
    bad = hit(r'\b(?:night shift|third shift|3rd shift|rotating shifts|overnight shift|required weekends)\b', text)
    if bad:
        return {'value': 0, 'evidence': bad}
    pattern = (r'\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\s*(?:-|–|—|to)\s*'
               r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\s*(central|CST|CDT|eastern|EST|EDT|mountain|MST|MDT|pacific|PST|PDT)\b')
    match = re.search(pattern, text, re.I)
    if not match:
        return {'value': None, 'evidence': 'Exact working hours and timezone need verification'}
    def minutes(hour, minute, period):
        hour, minute = int(hour), int(minute or 0)
        if not 1 <= hour <= 12 or not 0 <= minute < 60:
            return None
        return (hour % 12 + (12 if period.lower().startswith('p') else 0))*60 + minute
    start, end = minutes(*match.group(1,2,3)), minutes(*match.group(4,5,6))
    if start is None or end is None:
        return {'value': None, 'evidence': 'Invalid or ambiguous working hours'}
    zone = match[7].lower()
    # US regional times share seasonal shifts; Arizona/non-US offsets remain manual.
    shift = -60 if zone in {'eastern','est','edt'} else 60 if zone in {'mountain','mst','mdt'} else 120 if zone in {'pacific','pst','pdt'} else 0
    fits = 7*60 <= start+shift < end+shift <= 17*60
    return {'value': int(fits), 'evidence': match[0]+' (regional timezone conversion; verify daylight-saving details)'}


def preferences(job):
    text = job['title']+' '+job['description']
    internal = hit(r'\binternal (?:IT|support|employees?|end[- ]users?)\b|support(?:ing)? (?:our |internal )?(?:employees|colleagues|staff)\b',text)
    external = hit(r'\b(?:customer[- ]facing|call cent(?:er|re)|support(?:ing)? (?:our )?(?:customers|clients)|enterprise customers|sales targets)\b',text)
    internal_value = .5 if internal and external else 1 if internal else 0 if external else None
    no_call = hit(r'\bno (?:regular |required )?on[- ]call\b|\bon[- ]call (?:is )?not required\b',text)
    call_text = re.sub(r'\bno (?:regular |required )?on[- ]call\b|\bon[- ]call (?:is )?not required\b','',text,flags=re.I)
    call = hit(r'\b(?:on[- ]call (?:rotation|duties|responsibilities|coverage)|participate in.{0,25}on[- ]call|required on[- ]call)\b',call_text)
    growth = hit(r'\b(?:career (?:growth|development|advancement)|mentorship|training (?:provided|program)|professional development)\b',text)
    return {'internal': {'value':internal_value,'evidence':internal or external or 'Internal versus customer support not established'},
            'on_call': {'value':None if no_call and call else 1 if no_call else 0 if call else None,'evidence':no_call or call or 'On-call expectations not established'},
            'schedule':schedule_evidence(text),
            'growth':{'value':1 if growth else None,'evidence':growth or 'Advancement or training opportunities not established'},
            'healthcare':bool(hit(r'\b(?:hospital|clinical|medical clinic|healthtech|healthcare company)\b',text)),
            'training':bool(hit(r'\b(?:teaching|training employees|train(?:ing)? (?:our )?(?:staff|users)|instructional|technical training)\b',text))}


def requirements(job, work_state=''):
    text, loc = job['description'], job['location']
    workplace = str(job.get('workplace_type') or '').lower()
    remote_pos = (f'Workplace type: {workplace}' if workplace=='remote' else None) or (f'Source location: {loc}' if re.search(r'\bremote\b',loc,re.I) else None) or ('Source isRemote=true' if job.get('is_remote') is True else None) or hit(r'\b(?:fully remote|100% remote|work from home)\b',text)
    remote_neg = (f'Workplace type: {workplace}' if workplace in {'hybrid','onsite','on-site'} else None) or (f'Source location: {loc}' if (re.search(r'\b(?:hybrid|on[- ]site|not remote)\b',loc,re.I) or (re.search(r'\boffice\b',loc,re.I) and not re.search(r'\bremote\b',loc,re.I))) else None) or ('Source isRemote=false' if job.get('is_remote') is False else None) or hit(r'\b(?:required to (?:work|be) (?:in|from) (?:the |our )?office|must work (?:in|from) (?:the |our )?office|in[- ]office.{0,15}(?:three|3|four|4|five|5) days)\b',text)
    # Explicit office obligations override a generic remote boolean.
    remote = claim('fail',remote_neg) if remote_neg else choice(remote_pos,None,'Fully remote status not established')
    country = str(job.get('country') or '').lower()
    us_pos = f'Source location: {loc}' if re.search(r'\b(?:united states|USA|U\.S\.|US)\b',loc,re.I) or country in {'us','usa','united states'} else None
    foreign = ((f'Source country: {country}' if country and country not in {'us','usa','united states'} else None) or hit(r'\b(?:canada|united kingdom|ireland|india|south korea|australia|germany|france)\b',loc)) if not us_pos else None
    us = choice(us_pos,foreign,'US hiring eligibility not established')
    # State eligibility is deliberately owner-verified: nationwide claims may have exceptions.
    state = claim('unknown', 'Verify hiring eligibility in '+(STATES.get(work_state,work_state) if work_state else 'your work state; no state saved'))
    if work_state:
        name = STATES[work_state]
        excluded = hit(r'\b(?:cannot hire|do not hire|unable to hire|not hiring in|not eligible|ineligible|except|excluding|not available in)\b[^.;]{0,100}\b'+re.escape(name)+r'\b',text)
        if excluded:
            state = claim('fail',excluded)
        else:
            listed = hit(r'\b(?:must (?:reside|be based|be located) in|hiring in|eligible (?:work )?states?:)\s*[^.;]{0,65}\b'+re.escape(name)+r'\b',text)
            nationwide = hit(r'\b(?:hire|hiring|employ|employment|remote work)\b[^.;]{0,60}\ball 50 (?:US |U\.S\. |United States )?states\b',text)
            if listed or nationwide:
                state = claim('pass',listed or nationwide)
    employment = str(job.get('employment_type') or '').lower()
    full_pos = f'Source employment type: {employment}' if employment in {'fulltime','full-time','full_time'} else hit(r'\bfull[- ]time\b',text)
    nonfull = hit(r'\b(?:part[- ]time|contract(?:or)?|internship|intern|temporary)\b',employment+' '+job['title']) or hit(r'\b(?:this role|this position|employment type|job type)\b[^.;]{0,30}\b(?:contract|part[- ]time|temporary|not (?:a )?full[- ]time)\b',text)
    full = claim('fail',nonfull) if nonfull else choice(full_pos,None,'Full-time status not established')
    benefit_text=re.sub(r'\b(?:no|without) (?:health|medical) insurance\b','',text,flags=re.I)
    benefits = choice(hit(r'\b(?:health insurance|medical insurance|medical,? dental(?:,? and vision)?|healthcare benefits)\b',benefit_text),
                      hit(r'\b(?:no benefits|without benefits|not eligible for benefits)\b',text),'Employment benefits not established')
    no_travel = hit(r'\b(?:no (?:regular |required )?travel(?: is required)?|travel (?:is )?not required|0% travel)\b',text)
    travel_text = re.sub(r'\b(?:no (?:regular |required )?travel(?: is required)?|travel (?:is )?not required|0% travel)\b','',text,flags=re.I)
    travel_req = hit(r'\b(?:travel (?:is )?required|must (?:be able to )?travel|travel up to [1-9]\d*%|[1-9]\d*% (?:required )?travel)\b',travel_text)
    travel = choice(no_travel,travel_req,'Travel and routine commuting need verification')
    no_cert = hit(r'\b(?:no (?:IT |technical )?certifications? (?:is |are )?(?:required|needed)|certifications? (?:is |are )?not required)\b',text)
    cert = hit(r'\b(?:certifications?|certified|CompTIA|CCNA|CISSP|ITIL|A\+)\b',text)
    cert_text=re.sub(r'\b(?:no (?:IT |technical )?certifications? (?:is |are )?(?:required|needed)|certifications? (?:is |are )?not required)\b','',text,flags=re.I)
    cert_req=hit(r'\b(?:CompTIA|CCNA|CISSP|ITIL|certifications?)\b[^.;]{0,65}\b(?:required|mandatory|must hold)\b|\bmust (?:hold|have|possess)\b[^.;]{0,65}\b(?:CompTIA|CCNA|CISSP|ITIL|certification)\b',cert_text)
    certifications = choice(no_cert,cert_req if no_cert else None,'Verify whether certifications must be held before applying'+(': '+cert if cert else ''))
    # Internal employee support is suitable; explicit call-center/sales roles are excluded.
    # Other customer-facing technical work needs owner judgment rather than a guessed fit.
    bad_focus=hit(r'\b(?:call cent(?:er|re)|sales representative|customer service representative)\b',job['title'])
    internal=preferences(job)['internal']
    role_focus=claim('fail',bad_focus) if bad_focus else claim('pass',internal['evidence']) if internal['value']==1 else claim('unknown','Verify that direct customer service or sales does not dominate the responsibilities: '+internal['evidence'])
    return dict(remote=remote,us=us,state=state,full_time=full,benefits=benefits,travel=travel,certifications=certifications,role_focus=role_focus)
