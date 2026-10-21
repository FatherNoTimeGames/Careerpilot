"""Synthetic compensation records use the verified public ATS schema, never real user data."""
import json
import hashlib
import math
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from careerpilot.compensation import analyze,annualize
from careerpilot.matching import relevant
from careerpilot.providers import load_sources
from careerpilot.store import connect
from careerpilot.discovery import discover,ingest
from careerpilot.web import snapshot
from careerpilot.job_evidence import requirements,GATES
from careerpilot.personalization import configuration,save_configuration,verify_job
from test_pipeline import fixture,SOURCE


def component(low=50000,high=65000,kind='Salary',currency='USD',interval='1 YEAR',summary='Base salary'):
    return {'compensationType':kind,'interval':interval,'currencyCode':currency,'minValue':low,'maxValue':high,'summary':summary}


def ashby(*tiers,description='Support Windows'):
    return fixture(description=description,compensation={'compensationTiers':list(tiers),
                     'summaryComponents':[component(1,999999)]})


def tier(*components,title=None,info=''):
    return {'title':title,'additionalInformation':info,'components':list(components)}


class Compensation(unittest.TestCase):
    def test_typed_base_salary_excludes_bonus_equity_and_summary_envelope(self):
        job=ashby(tier(component(),component(10000,30000,kind='Bonus'),component(1,5,kind='EquityPercentage')))
        result=analyze(job,'TX')
        self.assertEqual(result['annual']['min'],50000)
        self.assertEqual(result['annual']['max'],65000)
        self.assertEqual(result['annual']['published_period'],'year')
        self.assertEqual(len(result['published']),1)
        only_bonus=ashby(tier(component(kind='Bonus')))
        self.assertIsNone(analyze(only_bonus)['annual'])
        self.assertIsNone(analyze(ashby(tier(component(summary='OTE range'))))['annual'])

    def test_no_geographic_merging_and_explicit_texas_selection(self):
        job=ashby(tier(component(80000,95000),title='California'),tier(component(55000,65000),title='Texas'))
        self.assertIsNone(analyze(job)['annual'])
        self.assertEqual(analyze(job)['status'],'ambiguous')
        self.assertEqual(analyze(job,'TX')['annual']['min'],55000)
        self.assertEqual(analyze(job,'CA')['annual']['min'],80000)
        self.assertIsNone(analyze(job,'NY')['annual'])
        unknown=ashby(tier(component(80000,95000),title='Zone A'),tier(component(55000,65000),title='Zone B'))
        self.assertIsNone(analyze(unknown,'TX')['annual'])
        except_tx=ashby(tier(component(),title='All states except Texas'))
        self.assertIsNone(analyze(except_tx,'TX')['annual'])
        city_and_country=ashby(tier(component(80000,95000),title='SF & NYC'),tier(component(55000,65000),title='United States'))
        self.assertEqual(analyze(city_and_country,'TX')['annual']['min'],55000)
        self.assertIsNone(analyze(city_and_country,'NY')['annual'])
        own_city=ashby(tier(component(80000,95000),title='Austin, TX'),tier(component(55000,65000),title='United States'))
        self.assertIsNone(analyze(own_city,'TX')['annual'])

    def test_greenhouse_cents_require_explicit_period_and_base_context(self):
        raw={'min_cents':5050050,'max_cents':6500075,'currency_type':'USD',
             'title':'Texas annual base salary','blurb':'Published annual base salary; excludes bonuses and equity.'}
        result=analyze(fixture(description='IT support',pay_input_ranges=[raw]),'TX')
        self.assertEqual(result['annual']['min'],50500.5)
        self.assertEqual(result['annual']['max'],65000.75)
        ambiguous={**raw,'title':'Salary Range','blurb':'The base salary range for this role.'}
        self.assertIsNone(analyze(fixture(description='IT support',pay_input_ranges=[ambiguous]))['annual'])
        corroborated=analyze(fixture(description='Annual base salary $50,500.50 - $65,000.75.',pay_input_ranges=[ambiguous]))
        self.assertEqual(corroborated['annual']['min'],50500.5)

    def test_explicit_hourly_paid_schedule_and_unknown_schedule(self):
        job=ashby(tier(component(25,30,interval='1 HOUR')),description='35 paid hours per week and 48 paid weeks per year.')
        result=analyze(job)
        self.assertEqual(result['annual']['min'],42000)
        self.assertEqual(result['annual']['max'],50400)
        self.assertEqual(len(result['annual']['schedule_evidence']),2)
        missing=analyze(ashby(tier(component(25,30,interval='1 HOUR')),description='Full-time 40 hours per week.'))
        self.assertIsNone(missing['annual'])
        self.assertEqual(missing['published'][0]['min'],25)
        self.assertTrue(any('52-week' in w for w in missing['warnings']))
        annual_hours=analyze(ashby(tier(component(25,30,interval='1 HOUR')),description='1,680 paid hours per year.'))
        self.assertEqual(annual_hours['annual']['min'],42000)

    def test_monthly_weekly_and_conflicting_paid_calendar(self):
        monthly=analyze(ashby(tier(component(4500,5000,interval='1 MONTH')),description='12 paid months per year.'))
        self.assertEqual(monthly['annual']['min'],54000)
        weekly=analyze(fixture(description='Weekly base pay USD 1,100 - 1,200 per week. 48 paid weeks per year.'))
        self.assertEqual(weekly['annual']['min'],52800)
        self.assertIsNone(annualize(4500,5000,'month'))
        self.assertEqual(annualize(4500,5000,'month',paid_months=12)['max'],60000)
        for text in ['35-40 paid hours per week, 52 paid weeks per year.',
                     '35 paid hours per week, 40 paid hours per week, 52 paid weeks per year.',
                     '35 paid hours per week, 48 paid weeks per year, 2000 paid hours per year.']:
            self.assertIsNone(analyze(ashby(tier(component(25,30,interval='1 HOUR')),description=text))['annual'])

    def test_text_single_amount_shared_k_currencies_and_estimates(self):
        fixed=analyze(fixture(description='Annual base salary USD 55,000.'))
        self.assertEqual(fixed['annual']['min'],55000)
        self.assertEqual(fixed['annual']['max'],55000)
        shared=analyze(fixture(description='Annual base salary $55–70k.'))
        self.assertEqual(shared['annual']['min'],55000)
        self.assertEqual(shared['annual']['max'],70000)
        for text in ['Base salary $50,000 - $60,000.', 'Estimated annual base salary $55,000 - $70,000.',
                     'No annual salary $55,000 - $60,000.', 'Total annual compensation $55,000 - $70,000.',
                     'Annual base salary CAD $55,000 - $70,000.',
                     'Annual base salary USD $55,000 - CAD $70,000.', 'Annual base salary $55,000 - TBD.']:
            self.assertIsNone(analyze(fixture(description=text))['annual'],text)
        self.assertIsNone(analyze(fixture(location='Remote, Canada',description='Annual base salary $55,000 - $70,000.'))['annual'])
        rate=analyze(fixture(description='Hourly pay $25 - $30 per hour.'))
        self.assertIsNone(rate['annual'])
        self.assertEqual(rate['published'][0]['period'],'hour')
        explicit=analyze(fixture(description='Annual base salary $55,000 - $65,000 plus bonus.'))
        self.assertEqual(explicit['annual']['min'],55000)
        nested=analyze(fixture(description='Compensation includes annual base salary of $55,000 - $65,000.'))
        self.assertEqual(nested['annual']['min'],55000)

    def test_bad_numeric_values_and_multiple_inconsistent_bands_do_not_promote(self):
        for low,high in [(True,60000),('NaN',60000),(50000,'Infinity'),(-1,60000),(70000,50000)]:
            self.assertIsNone(annualize(low,high,'year'))
            self.assertIsNone(analyze(ashby(tier(component(low,high))))['annual'])
        mixed=ashby(tier(component(),component(30,40,interval='1 HOUR')))
        self.assertIsNone(analyze(mixed)['annual'])
        self.assertIsNone(analyze(fixture(description='Annual base salary $55,000-$65,000. Annual base salary $70,000-$90,000.'))['annual'])

    def test_reclassification_retains_records_and_cents_do_not_cross_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(tmp+'/db')
            try:
                config=configuration(db)
                save_configuration(db,{'expected_revision':config['revision'],'work_state':'TX'})
                raw={'min_cents':4000000,'max_cents':4999960,'currency_type':'USD','title':'Texas annual base salary','blurb':'Annual base salary'}
                ingest(db,SOURCE,[fixture(description='Windows support',pay_input_ranges=[raw])])
                job=snapshot(db)['jobs'][0]
                self.assertEqual(job['category'],'secondary')
                self.assertEqual(job['salary']['max'],49999.6)
                self.assertIn('salary_details',job)
                db.execute("UPDATE settings SET value='45000' WHERE key='salary_target'")
                db.commit()
                self.assertEqual(snapshot(db)['jobs'][0]['category'],'primary')
                self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
            finally:db.close()


class Coverage(unittest.TestCase):
    def test_added_role_families_do_not_turn_software_jobs_into_support(self):
        for title in ['IT Engineer','IT Systems Engineer','Endpoint Engineer','Technical Trainer','IT Implementation Specialist']:
            self.assertTrue(relevant({'title':title}),title)
        for title in ['Software Engineer','IT Recruiter','Account Executive']:
            self.assertFalse(relevant({'title':title}),title)
        self.assertEqual(requirements(fixture(title='IT Engineer Intern'))['full_time']['status'],'fail')

    def test_source_configuration_is_validated_and_bounded(self):
        load_sources('sources.json')  # The deployed configuration must validate without fixing its size forever.
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sources.json'
            for value in [{},[],[{}],[{'provider':'ashby','board':'../bad','employer':'Test'}],
                          [{**SOURCE,'board':'board'+str(i)} for i in range(21)]]:
                path.write_text(json.dumps(value))
                with self.assertRaises((ValueError,KeyError)):load_sources(path)

    def test_salary_parser_changes_do_not_fake_source_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(tmp+'/db')
            try:
                job=fixture()
                ingest(db,SOURCE,[job])
                before=db.execute('SELECT fingerprint,updated_at FROM jobs').fetchone()
                with patch('careerpilot.discovery.salary',return_value=None):
                    counts=ingest(db,SOURCE,[job])
                after=db.execute('SELECT fingerprint,updated_at,data FROM jobs').fetchone()
                self.assertEqual(counts['updated'],0)
                self.assertEqual(after['fingerprint'],before['fingerprint'])
                self.assertEqual(after['updated_at'],before['updated_at'])
                self.assertIsNone(json.loads(after['data'])['salary'])
                # Legacy fingerprints included the derived salary/assessment; migrate without
                # expiring an unchanged, explicitly reviewed posting.
                legacy=hashlib.sha256(after['data'].encode()).hexdigest()
                db.execute('UPDATE jobs SET fingerprint=?',(legacy,));db.commit()
                verify_job(db,{'job_id':1,'expected_fingerprint':legacy,'expected_updated_at':None,'acknowledge':True,
                               'criteria':{key:{'status':'pass','evidence':'Synthetic owner confirmation'} for key in GATES}})
                self.assertEqual(ingest(db,SOURCE,[job])['updated'],0)
                self.assertFalse(snapshot(db)['jobs'][0]['match']['stale_verification'])
                self.assertEqual(ingest(db,SOURCE,[fixture(description='Actual employer change')])['updated'],1)
            finally:db.close()

    def test_lease_takeover_does_not_commit_stale_results_or_delete_new_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(tmp+'/db')
            try:
                ingest(db,SOURCE,[fixture()])
                takeover=time.time()+9000
                def fetch(_):
                    db.execute('UPDATE lease SET until=? WHERE id=1',(takeover,));db.commit()
                    return [fixture(description='Stale response must not overwrite stored job')]
                result=discover(db,[SOURCE],fetcher=fetch)
                self.assertEqual(result['status'],'interrupted')
                self.assertEqual(db.execute('SELECT until FROM lease').fetchone()[0],takeover)
                self.assertNotIn('Stale response',db.execute('SELECT description FROM jobs').fetchone()[0])
                self.assertEqual(db.execute('SELECT status FROM runs ORDER BY id DESC LIMIT 1').fetchone()[0],'interrupted')
            finally:db.close()
