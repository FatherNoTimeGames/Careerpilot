"""Employer-published base pay only. No estimated hours, bonuses, FX or merged geography bands."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .providers import plaintext
from .job_evidence import STATES

PERIODS = {'1 YEAR':'year','1 MONTH':'month','1 WEEK':'week','1 HOUR':'hour',
           'per-year':'year','per-month':'month','per-week':'week','per-hour':'hour',
           'year':'year','month':'month','week':'week','hour':'hour'}


def number(value):
    if isinstance(value,bool) or value is None:
        return None
    try:
        result=Decimal(str(value))
        return result if result.is_finite() and 0<=result<=Decimal('100000000') else None
    except (InvalidOperation,ValueError):
        return None


def annualize(low,high,period,hours_per_week=None,paid_weeks=None,paid_months=None,paid_hours_per_year=None):
    low,high=number(low),number(high)
    if low is None or high is None or high<low:return None
    hours,weeks,months,annual_hours=map(number,(hours_per_week,paid_weeks,paid_months,paid_hours_per_year))
    factor=None
    if period=='year':factor=Decimal(1)
    elif period=='month' and months and months<=12:factor=months
    elif period=='week' and weeks and weeks<=53:factor=weeks
    elif period=='hour':
        if annual_hours and annual_hours<=24*366:factor=annual_hours
        elif hours and weeks and hours<=168 and weeks<=53:factor=hours*weeks
    if factor is None:return None
    return {'min':float((low*factor).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),
            'max':float((high*factor).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),'currency':'USD'}


def schedule(text):
    specs={
      'hours_per_week':r'\b(\d+(?:\.\d+)?)\s+paid hours?\s*(?:per|/|a)\s*week\b',
      'paid_weeks':r'\b(\d+(?:\.\d+)?)\s+paid weeks?\s*(?:per|/|a)\s*year\b',
      'paid_months':r'\b(\d+(?:\.\d+)?)\s+paid months?\s*(?:per|/|a)\s*year\b',
      'paid_hours_per_year':r'\b(\d[\d,]*(?:\.\d+)?)\s+paid hours?\s*(?:per|/|a)\s*year\b'}
    values,evidence={},[]
    ambiguous=bool(re.search(r'\d\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s+paid (?:hours|weeks|months)\b',text,re.I))
    for key,pattern in specs.items():
        found=list(re.finditer(pattern,text,re.I))
        unique={Decimal(m[1].replace(',','')) for m in found}
        if len(unique)>1:ambiguous=True
        values[key]=float(next(iter(unique))) if len(unique)==1 else None
        evidence.extend(m[0] for m in found)
    if values['paid_hours_per_year'] and values['hours_per_week'] and values['paid_weeks'] and Decimal(str(values['paid_hours_per_year']))!=Decimal(str(values['hours_per_week']))*Decimal(str(values['paid_weeks'])):
        ambiguous=True
    if ambiguous:values={k:None for k in specs}
    return values,evidence,ambiguous


def record(low,high,currency,period,evidence,scope='',source='posting',base_confirmed=True):
    low,high=number(low),number(high)
    if low is None or high is None or high<low:return None
    return {'min':float(low),'max':float(high),'currency':currency or 'Unknown',
            'period':period,'evidence':evidence[:1800],'scope':scope[:1800],
            'source':source,'base_confirmed':base_confirmed}


def structured(job):
    rows=[]
    ashby=job.get('compensation')
    if isinstance(ashby,dict):
        tiers=ashby.get('compensationTiers')
        collections=tiers if isinstance(tiers,list) and tiers else [{'components':ashby.get('summaryComponents',[]),'title':''}]
        for tier in collections:
            if not isinstance(tier,dict):continue
            scope=' '.join(str(tier.get(k) or '') for k in ['title','additionalInformation'])
            for component in tier.get('components') or []:
                if not isinstance(component,dict) or component.get('compensationType')!='Salary':continue
                period=PERIODS.get(component.get('interval'),'unknown')
                summary=str(component.get('summary') or '')
                # A mislabeled OTE/total-cash field is not a verified base-pay component.
                base=not bool(re.search(r'\b(?:OTE|on[- ]target earnings|total compensation|total cash)\b',summary,re.I))
                row=record(component.get('minValue'),component.get('maxValue'),component.get('currencyCode'),period,
                           'Ashby Salary component: '+summary+'; interval '+str(component.get('interval')),
                           scope,'ashby',base)
                if row:rows.append(row)
    greenhouse=job.get('pay_input_ranges')
    if isinstance(greenhouse,list):
        for band in greenhouse:
            if not isinstance(band,dict):continue
            lo,hi=number(band.get('min_cents')),number(band.get('max_cents'))
            if lo is None or hi is None:continue
            title=str(band.get('title') or '')
            blurb=plaintext(band.get('blurb'))
            period=explicit_period(title+' '+blurb)
            # Greenhouse ranges lack a mandatory interval field. Never assume a year from amount size.
            row=record(lo/100,hi/100,band.get('currency_type'),period,'Greenhouse: '+title+'; '+blurb,
                       title,'greenhouse',bool(re.search(r'\bbase (?:salary|pay|wage)|\b(?:annual|hourly|weekly|monthly) (?:salary|wage)\b',title+' '+blurb,re.I)))
            if row:rows.append(row)
    return rows


def explicit_period(text):
    patterns={'hour':r'\bhourly\b|\bper hour\b|/\s*(?:hour|hr)\b',
              'week':r'\bweekly\b|\bper week\b|/\s*(?:week|wk)\b',
              'month':r'\bmonthly\b|\bper month\b|/\s*(?:month|mo)\b',
              'year':r'\b(?:annual|annually|yearly)\b|\bper (?:year|annum)\b|/\s*(?:year|yr)\b'}
    found=[key for key,pattern in patterns.items() if re.search(pattern,text,re.I)]
    return found[0] if len(found)==1 else 'unknown'


def text_ranges(job):
    text=job.get('description','')
    label=r'(?:(?:annual|annually|yearly|hourly|weekly|monthly)\s+)?(?:base\s+)?(?:salary|wage)(?:\s+(?:range|rate))?|(?:(?:annual|yearly|hourly|weekly|monthly)\s+)?base\s+(?:pay|compensation)(?:\s+(?:range|rate))?|(?:hourly|weekly|monthly)\s+pay(?:\s+(?:range|rate))?|pay\s+(?:range|rate)'
    pattern=re.compile(r'(?P<label>(?:'+label+r'))\s*[^.!?;$€£]{0,80}?(?P<currency>USD\s*\$?|US\$|CAD\s*\$?|C\$|AUD\s*\$?|A\$|GBP\s*£?|EUR\s*€?|\$|€|£)\s*'
                       r'(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?P<lk>[kK]?)(?:\s*(?:-|–|—|to)\s*'
                       r'(?:USD\s*\$?|US\$|\$)?\s*(?P<high>\d[\d,]*(?:\.\d+)?)\s*(?P<hk>[kK]?))?',re.I)
    rows=[]
    for match in pattern.finditer(text):
        after=text[match.end():match.end()+55]
        if not match['high'] and re.match(r'\s*(?:[-–—]|to\b)',after,re.I):
            continue  # An unsupported upper endpoint must not become a fictional fixed salary.
        # Keep period context in the current pay phrase, not a later salary band or paid-hours statement.
        suffix=re.split(r'(?<=[.!?;])\s+|\b(?:plus|and|with|for|based|depending)\b',after,maxsplit=1,flags=re.I)[0]
        context=match[0]+suffix
        prefix=text[max(0,match.start()-30):match.start()]
        currency_token=match['currency'].upper().strip()
        currency='USD' if currency_token.startswith(('USD','US$')) else 'CAD' if currency_token.startswith(('CAD','C$')) else 'AUD' if currency_token.startswith(('AUD','A$')) else 'GBP' if currency_token.startswith(('GBP','£')) else 'EUR' if currency_token.startswith(('EUR','€')) else None
        if currency is None:
            # A bare dollar symbol is ambiguous outside an explicitly US source location/country.
            declared=re.search(r'\b(USD|CAD|AUD|SGD|NZD)\b',prefix+' '+context,re.I)
            currency=declared[1].upper() if declared else 'USD' if re.search(r'\b(?:united states|USA|US)\b',job.get('location',''),re.I) or str(job.get('country','')).upper() in {'US','USA','UNITED STATES'} else 'Unknown'
        period=explicit_period(context)
        low=Decimal(match['low'].replace(',',''))*(1000 if match['lk'] else 1)
        high=Decimal((match['high'] or match['low']).replace(',',''))*(1000 if (match['hk'] if match['high'] else match['lk']) else 1)
        # In $55–70k the shared suffix applies to both endpoints.
        if match['high'] and match['hk'] and not match['lk'] and low<1000:low*=1000
        bad=re.search(r'\b(?:total|OTE|on[- ]target|bonus|commission|equity|no|without|estimated|estimate)\s*(?:annual |base )?$',prefix,re.I) or re.search(r'\b(?:OTE|on[- ]target earnings|total compensation|total cash|estimated|estimate)\b',context,re.I)
        base=not bool(bad) and bool(re.search(r'\b(?:base|salary|wage)\b|\b(?:hourly|weekly|monthly)\s+pay\b',match['label'],re.I))
        row=record(low,high,currency,period,context,source='posting text',base_confirmed=base)
        if row:rows.append(row)
    return rows


def state_mentions(scope):
    found=set()
    for code,name in STATES.items():
        if re.search(r'\b'+re.escape(name)+r'\b',scope,re.I) or re.search(r'\b'+code+r'\b',scope):found.add(code)
    return found


CITY_STATES={'SF':'CA','San Francisco':'CA','NYC':'NY','New York City':'NY','Austin':'TX','Dallas':'TX',
             'Houston':'TX','San Antonio':'TX','Seattle':'WA','Boston':'MA','Chicago':'IL','Denver':'CO'}


def scope_cities(scope):
    return {state for city,state in CITY_STATES.items() if re.search(r'\b'+re.escape(city)+r'\b',scope,re.I)}


def simple_geographic_scope(scope):
    # Only a pure place-list is exhaustive; a tier label or example is not.
    text=scope
    for name in sorted([*STATES.values(),*STATES.keys(),*CITY_STATES.keys()],key=len,reverse=True):
        text=re.sub(r'\b'+re.escape(name)+r'\b','',text,flags=re.I)
    return not bool(re.sub(r'\band\b|[\s,;&/()\-]','',text,flags=re.I))


def applicable(rows,work_state):
    if not work_state:return rows
    def excluded(row):
        return work_state in state_mentions(row['scope']) and bool(re.search(r'\b(?:except|excluding|not eligible|not applicable|does not apply)\b',row['scope'],re.I))
    rows=[r for r in rows if not excluded(r)]
    # A work state alone cannot distinguish a city-specific band within that state.
    city_unclear=any(work_state in scope_cities(r['scope']) for r in rows)
    explicit=[r for r in rows if work_state in state_mentions(r['scope']) and not scope_cities(r['scope'])]
    if explicit and not city_unclear:return explicit
    def elsewhere(row):
        places=state_mentions(row['scope'])|scope_cities(row['scope'])
        return bool(places) and work_state not in places and simple_geographic_scope(row['scope'])
    national=[r for r in rows if r['scope'].strip().lower() in {'united states','us','usa','all us states','all 50 us states'}]
    if national and all(r in national or elsewhere(r) for r in rows):return national
    if rows and all(elsewhere(r) for r in rows):return []
    # Do not assume an unspecified tier means every other US state.
    return rows


def analyze(job,work_state=''):
    rows=structured(job)
    textual=text_ranges(job)
    if not rows:rows=textual
    else:
        # Explicit matching text may supply an interval absent from a structured band.
        for row in rows:
            if row['period']=='unknown':
                corroboration=[t for t in textual if t['base_confirmed'] and t['currency']==row['currency'] and t['min']==row['min'] and t['max']==row['max'] and t['period']!='unknown']
                periods={t['period'] for t in corroboration}
                if len(periods)==1:
                    row['period']=next(iter(periods))
                    row['evidence']+='; matching period evidence: '+corroboration[0]['evidence']
    warnings=[]
    if not rows:return {'annual':None,'published':[],'warnings':['No reliable published base-pay range found'],'status':'unknown'}
    schedule_values,schedule_evidence,ambiguous_schedule=schedule(job.get('description',''))
    if ambiguous_schedule:warnings.append('Paid schedule has ranges or conflicting values; no annual hours assumed')
    candidates=applicable([r for r in rows if r['base_confirmed'] and r['currency']=='USD'],work_state)
    normalized=[]
    for row in candidates:
        annual=annualize(row['min'],row['max'],row['period'],**schedule_values)
        if annual:
            normalized.append((row,annual))
    if any(not r['base_confirmed'] for r in rows):warnings.append('Non-base or total-pay figures were not used for salary ranking')
    if any(r['currency']!='USD' for r in rows):warnings.append('Non-USD or ambiguous currency is not converted into a confirmed USD salary')
    if any(r['period']=='unknown' for r in candidates):warnings.append('Pay period is not explicit; no annual period is assumed')
    if any(r['period'] in {'hour','week','month'} and annualize(r['min'],r['max'],r['period'],**schedule_values) is None for r in candidates):
        warnings.append('Annualization needs explicit expected paid hours/weeks/months; no 40-hour or 52-week default is used')
    if not candidates:warnings.append('No applicable confirmed USD base band for the selected work state')
    distinct={(a['min'],a['max']) for _,a in normalized}
    if len(distinct)>1:
        warnings.append('Multiple differing salary bands remain; no geographic ranges are merged')
        return {'annual':None,'published':rows,'warnings':warnings,'status':'ambiguous'}
    # An unresolved base band cannot be ignored in favor of another range or a summary.
    if len(normalized)!=len(candidates):
        return {'annual':None,'published':rows,'warnings':warnings,'status':'unknown'}
    if normalized:
        row,annual=normalized[0]
        annual.update({'evidence':row['evidence'],'basis':'Employer-published USD base pay; '+('explicit annual period' if row['period']=='year' else 'normalized using explicitly published paid schedule'),
                       'published_min':row['min'],'published_max':row['max'],'published_period':row['period'],
                       'scope':row['scope'],'schedule_evidence':schedule_evidence if row['period']!='year' else []})
        if not work_state or work_state not in state_mentions(row['scope']):warnings.append('Confirm geographic applicability of the published band')
        return {'annual':annual,'published':rows,'warnings':warnings,'status':'verified'}
    return {'annual':None,'published':rows,'warnings':warnings,'status':'unknown'}


def salary(job,work_state=''):
    return analyze(job,work_state)['annual']
