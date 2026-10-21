"""Matching fixtures are synthetic and isolated from real candidate/profile data."""
import copy
import json
import tempfile
import unittest
from careerpilot.store import connect
from careerpilot import studio, personalization as match
from careerpilot.job_evidence import affirmative_skill_ids, requirements, schedule_evidence, GATES
from careerpilot.discovery import ingest
from careerpilot.web import snapshot
from test_pipeline import SOURCE, fixture
from test_studio import fact


def good_job(**changes):
    return fixture(**{'description':('Internal IT support for employees in a hospital. Windows and Microsoft 365. '
                 'Full-time. Health insurance. No travel required. No certifications required. '
                 'Hiring in Texas. 8 AM to 4 PM Central. No on-call. Career growth and mentorship. '
                 'Annual base salary $55,000 - $65,000.'), **changes})


class Matching(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=connect(self.tmp.name+'/jobs.sqlite3')
        config=match.configuration(self.db)
        match.save_configuration(self.db,{'expected_revision':config['revision'],'work_state':'TX'})

    def tearDown(self):
        self.db.close();self.tmp.cleanup()

    def profile(self,facts=None,verify=True):
        revision=studio.save_profile(self.db,{'expected_revision':studio.current_profile(self.db)['revision'],
                     'facts':facts or [fact(),fact('Hospital IT technician supporting clinical employees.',id='employment',section='employment')]})['revision']
        if verify:studio.verify_profile(self.db,{'expected_revision':revision,'acknowledge':True})
        return revision

    def evaluate(self,job=None,manual=None):
        profile,candidate,config,model=match.context(self.db)
        return match.evaluate(job or good_job(),profile,candidate,config,50000,manual,model)

    def test_documented_score_coverage_and_required_filters(self):
        self.profile()
        result=self.evaluate()
        self.assertEqual(result['score'],100)
        self.assertEqual(result['evidence_coverage'],100)
        self.assertEqual(result['eligibility'],'requirements_verified')
        self.assertEqual(result['feedback_adjustment'],0)
        self.assertEqual(len(result['skill_evidence']),2)
        bad=self.evaluate(good_job(workplace_type='Hybrid',is_remote=True))
        self.assertEqual(bad['eligibility'],'excluded')
        self.assertEqual(bad['gates']['remote']['status'],'fail')
        self.assertGreater(bad['score'],90) # A high score must never outweigh exclusion.
        customer=self.evaluate(good_job(title='IT Support Specialist - Call Center'))
        self.assertEqual(customer['gates']['role_focus']['status'],'fail')
        self.assertEqual(customer['eligibility'],'excluded')

    def test_pending_inferred_personal_and_negative_claims_cannot_add_qualifications(self):
        self.profile([fact('Windows support',status='pending')],verify=False)
        self.assertIsNone(self.evaluate()['score'])
        self.profile([fact('Windows support'),fact('PowerShell',id='personal',section='personal'),
                      fact('Azure administration',id='inferred',status='inferred'),
                      fact('No experience with SQL or Linux.',id='negative')])
        result=self.evaluate(good_job(description='Windows PowerShell Azure SQL Linux'))
        self.assertEqual(set(result['skill_evidence']),{'windows'})
        self.assertEqual({g['key'] for g in result['gaps']},{'powershell','azure','sql','linux'})
        self.assertNotIn('ad_admin',affirmative_skill_ids('Active Directory account support. Do not assume advanced domain controllers or forest trusts.'))

    def test_unknown_evidence_receives_no_free_points(self):
        self.profile()
        result=self.evaluate(good_job(description='Windows support'))
        self.assertEqual(result['score'],35)
        self.assertEqual(result['evidence_coverage'],35)
        self.assertEqual(result['eligibility'],'needs_verification')
        self.assertEqual(result['dimensions']['salary']['value'],None)
        self.assertNotEqual(result['confidence'],'higher evidence coverage')

    def test_texas_restrictions_and_conflicting_state_evidence(self):
        self.assertEqual(requirements(good_job(),'TX')['state']['status'],'pass')
        self.assertEqual(requirements(good_job(description='We cannot hire residents of Texas.'),'TX')['state']['status'],'fail')
        self.assertEqual(requirements(good_job(description='We cannot hire in Texas.'),'TX')['state']['status'],'fail')
        self.assertEqual(requirements(good_job(description='Eligible work states: California, except Texas.'),'TX')['state']['status'],'fail')
        self.assertEqual(requirements(good_job(description='We serve patients in all 50 US states.'),'TX')['state']['status'],'unknown')
        self.assertEqual(requirements(good_job(description='We hire in all 50 US states.'),'TX')['state']['status'],'pass')
        self.assertEqual(requirements(good_job(),'CA')['state']['status'],'unknown')

    def test_schedule_negation_and_no_automatic_experience_rejection(self):
        self.profile()
        self.assertEqual(schedule_evidence('9 AM to 5 PM Eastern')['value'],1)
        self.assertEqual(schedule_evidence('9 AM to 5 PM Pacific')['value'],0)
        self.assertIsNone(schedule_evidence('9 to 5 business hours')['value'])
        result=self.evaluate(good_job(description='Full-time support. 3+ years experience. No travel required. No on-call.'))
        self.assertEqual(result['gates']['travel']['status'],'pass')
        self.assertEqual(result['dimensions']['on_call']['value'],1)
        self.assertNotEqual(result['eligibility'],'excluded')
        self.assertTrue(any('3+ years' in x for x in result['verification_needed']))
        required=self.evaluate(good_job(description='Must travel up to 20%.'))
        self.assertEqual(required['gates']['travel']['status'],'fail')

    def test_salary_bands_changes_and_professional_skill_gaps(self):
        self.profile()
        crossing=self.evaluate(good_job(description='Windows. Annual base salary $45,000 - $60,000.'))
        self.assertEqual(crossing['category'],'primary')
        self.assertEqual(crossing['dimensions']['salary']['value'],.5)
        below=self.evaluate(good_job(description='Windows. Annual base salary $40,000 - $45,000.'))
        self.assertEqual(below['category'],'secondary')
        self.assertEqual(below['dimensions']['salary']['value'],0)
        result=self.evaluate(good_job(description='Windows and PowerShell experience. 10 years of relevant experience preferred.'))
        self.assertEqual(result['gaps'][0]['key'],'powershell')
        self.assertNotEqual(result['eligibility'],'excluded')

    def test_owner_verification_stales_on_posting_state_and_profile_changes(self):
        self.profile()
        ingest(self.db,SOURCE,[good_job(description='Windows support')])
        row=self.db.execute('SELECT fingerprint FROM jobs WHERE id=1').fetchone()
        body={'job_id':1,'expected_fingerprint':row[0],'expected_updated_at':None,'acknowledge':True,
              'criteria':{key:{'status':'pass','evidence':'Synthetic employer confirmation for this criterion'} for key in GATES}}
        match.verify_job(self.db,body)
        view=snapshot(self.db)['jobs'][0]
        self.assertEqual(view['match']['eligibility'],'requirements_verified')
        with self.assertRaises(studio.Conflict):match.verify_job(self.db,body)
        config=match.configuration(self.db)
        match.save_configuration(self.db,{'expected_revision':config['revision'],'work_state':'CA'})
        self.assertTrue(snapshot(self.db)['jobs'][0]['match']['stale_verification'])
        config=match.configuration(self.db)
        match.save_configuration(self.db,{'expected_revision':config['revision'],'work_state':'TX'})
        self.profile([fact('Windows support only')])
        self.assertTrue(snapshot(self.db)['jobs'][0]['match']['stale_verification'])
        ingest(self.db,SOURCE,[good_job(description='Windows support, updated role')])
        self.assertTrue(snapshot(self.db)['jobs'][0]['match']['stale_verification'])
        self.assertNotEqual(snapshot(self.db)['jobs'][0]['match']['eligibility'],'requirements_verified')

    def test_feedback_is_bounded_deduplicated_resettable_and_cannot_change_qualifications(self):
        self.profile()
        ingest(self.db,SOURCE,[good_job()])
        original=self.evaluate()
        with self.db:
            for _ in range(5):match.record_feedback(self.db,1,'interested','general')
        model=match.context(self.db)[3]
        self.assertEqual(model['feedback_count'],1)
        result=self.evaluate()
        self.assertGreater(result['feedback_adjustment'],0)
        self.assertLessEqual(result['feedback_adjustment'],5)
        self.assertEqual(result['score'],original['score'])
        self.assertEqual(result['skill_evidence'],original['skill_evidence'])
        self.assertEqual(result['category'],original['category'])
        bad=self.evaluate(good_job(workplace_type='Hybrid'))
        self.assertEqual(bad['feedback_adjustment'],0)
        self.assertEqual(bad['eligibility'],'excluded')
        config=match.configuration(self.db)
        match.save_configuration(self.db,{'expected_revision':config['revision'],'learning_enabled':False})
        self.assertEqual(self.evaluate()['feedback_adjustment'],0)
        config=match.configuration(self.db)
        match.save_configuration(self.db,{'expected_revision':config['revision'],'reset_learning':True,'learning_enabled':True})
        self.assertEqual(self.evaluate()['feedback_adjustment'],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM matching_feedback').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_unspecified_skip_does_not_train_but_reasoned_skip_does(self):
        self.profile();ingest(self.db,SOURCE,[good_job()])
        with self.db:match.record_feedback(self.db,1,'skipped')
        self.assertEqual(self.evaluate()['feedback_adjustment'],0)
        with self.db:match.record_feedback(self.db,1,'skipped','schedule')
        self.assertLess(self.evaluate()['feedback_adjustment'],0)
        with self.db:match.record_feedback(self.db,1,'discovered')
        self.assertEqual(self.evaluate()['feedback_adjustment'],0)

    def test_relative_weights_validation_and_private_snapshot(self):
        self.profile()
        config=match.configuration(self.db)
        weights={k:0 for k in config['weights']};weights['technical']=100
        match.save_configuration(self.db,{'expected_revision':config['revision'],'weights':weights})
        result=self.evaluate(good_job(description='Windows and PowerShell support'))
        self.assertEqual(result['score'],50)
        config=match.configuration(self.db)
        with self.assertRaises(ValueError):
            match.save_configuration(self.db,{'expected_revision':config['revision'],'weights':{k:0 for k in weights}})
        ingest(self.db,SOURCE,[good_job()])
        public=snapshot(self.db,private=False)
        self.assertFalse(public['matching']['available'])
        self.assertNotIn('matching',public['settings'])
        self.assertNotIn('match',public['jobs'][0])
        self.assertIsNone(public['matching']['config'])

    def test_gap_rollup_only_active_desirable_nonexcluded_jobs(self):
        self.profile()
        ingest(self.db,SOURCE,[good_job(description='Windows PowerShell. Annual base salary $55,000 - $65,000.')])
        jobs=snapshot(self.db)['jobs']
        gaps=match.gap_summary(jobs,True)
        self.assertEqual(gaps[0]['skill'],'powershell')
        self.assertIn('documentation',gaps[0]['suggestion'])
        self.assertEqual(match.gap_summary(jobs,False),[])
        jobs[0]['active']=False
        self.assertEqual(match.gap_summary(jobs,True),[])
