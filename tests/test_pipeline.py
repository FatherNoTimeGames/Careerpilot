"""Fixtures below are synthetic, isolated in temporary DBs; never production results."""
import base64
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from careerpilot.store import connect, settings
from careerpilot.providers import retrieve, canonical_url, fetch_json
from careerpilot.matching import salary, category, annualize, assess
from careerpilot.discovery import discover, ingest, worker
from careerpilot.web import server, snapshot

SOURCE = {"provider": "greenhouse", "board": "fixture", "employer": "Test employer"}


def fixture(ident="1", **changes):
    return {"external_id": ident, "url": "https://example.org/jobs/"+ident,
            "employer": "Test employer", "title": "IT Support Specialist",
            "location": "Remote, United States", "employment_type": "FullTime", "is_remote": True,
            "description": "Full-time internal support. Annual base salary $45,000 - $60,000. Health insurance.", **changes}


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name+"/db.sqlite3"
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_repeat_update_remove_reopen_preserves_feedback(self):
        self.assertEqual(ingest(self.db, SOURCE, [fixture()])["new"], 1)
        self.db.execute("UPDATE jobs SET review_status='interested'")
        self.db.commit()
        self.assertEqual(ingest(self.db, SOURCE, [fixture()])["new"], 0)
        self.assertEqual(ingest(self.db, SOURCE, [fixture(description="Updated", url="https://example.org/changed")])["updated"], 1)
        self.assertEqual(snapshot(self.db)["jobs"][0]["canonical_url"], "https://example.org/changed")
        ingest(self.db, SOURCE, [])
        self.assertTrue(snapshot(self.db)["jobs"][0]["active"])
        ingest(self.db, SOURCE, [])
        self.assertFalse(snapshot(self.db)["jobs"][0]["active"])
        ingest(self.db, SOURCE, [fixture()])
        job = snapshot(self.db)["jobs"][0]
        self.assertTrue(job["active"])
        self.assertEqual(job["review_status"], "interested")
        self.assertEqual(len(snapshot(self.db)["jobs"]), 1)

    def test_cross_source_canonical_dedup_and_source_independent_removal(self):
        other = {**SOURCE, "board": "other"}
        ingest(self.db, SOURCE, [fixture()])
        ingest(self.db, other, [fixture()])
        ingest(self.db, SOURCE, [])
        ingest(self.db, SOURCE, [])
        self.assertEqual(len(snapshot(self.db)["jobs"]), 1)
        self.assertTrue(snapshot(self.db)["jobs"][0]["active"])
        self.assertEqual(canonical_url('https://example.org/job?utm_source=x&gh_jid=12'), 'https://example.org/job?gh_jid=12')
        with self.assertRaises(ValueError):
            canonical_url('javascript:alert(1)')

    def test_failure_does_not_remove_and_backoff_survives_restart(self):
        ingest(self.db, SOURCE, [fixture()])
        def fail(_):
            raise urllib.error.HTTPError('https://example.org', 429, 'rate limited', {'Retry-After': '172800'}, None)
        result = discover(self.db, [SOURCE], fetcher=fail)
        self.assertEqual(result['status'], 'failed')
        self.assertGreater(self.db.execute('SELECT next_attempt FROM sources').fetchone()[0], time.time()+172700)
        self.assertTrue(snapshot(self.db)['jobs'][0]['active'])
        self.assertEqual(self.db.execute('SELECT missing_count FROM listings').fetchone()[0], 0)
        other = connect(self.path)
        try:
            result = discover(other, [SOURCE], fetcher=lambda _: self.fail('Must respect backoff'))
            self.assertEqual(result['status'], 'deferred')
        finally:
            other.close()

    def test_lock_prevents_overlapping_runs(self):
        self.db.execute('INSERT INTO lease VALUES (1,?)', (time.time()+60,))
        self.db.commit()
        self.assertEqual(discover(self.db, [SOURCE])['status'], 'already_running')

    def test_salary_categories_and_settings_preserve_jobs(self):
        pay = salary(fixture())
        self.assertEqual(pay['min'], 45000)
        self.assertEqual(salary(fixture(description='Remote role. Base salary $50,000 - $60,000 plus bonus.'))['min'], 50000)
        self.assertEqual(category(pay, 50000), 'primary')
        self.assertEqual(category(pay, 70000), 'secondary')
        self.assertEqual(category(None, 50000), 'unknown')
        self.assertIsNone(salary(fixture(description='Total compensation $80,000 - $100,000 with bonus.')))
        self.assertIsNone(salary(fixture(description='Base salary $45 - $60 per hour')))
        self.assertIsNone(salary(fixture(description='Base salary CAD $45,000 - $60,000')))
        self.assertIsNone(annualize(25, 30, 'hour'))
        self.assertIsNone(annualize(1000, 1200, 'week'))
        self.assertEqual(annualize(1000, 1200, 'week', paid_weeks=48)['min'], 48000)
        self.assertEqual(annualize(25, 30, 'hour', 35, 48)['min'], 42000)
        ingest(self.db, SOURCE, [fixture()])
        self.db.execute('UPDATE settings SET value=? WHERE key=?', ('70000', 'salary_target'))
        self.db.commit()
        self.assertEqual(snapshot(self.db)['jobs'][0]['category'], 'secondary')

    def test_hybrid_overrides_misleading_remote_boolean(self):
        result = assess(fixture(workplace_type='Hybrid'))
        self.assertEqual(result['remote'], 'rejected')
        self.assertEqual(result['eligibility'], 'excluded')
        self.assertEqual(assess(fixture(description='No travel required.'))['rejected_reasons'], [])
        self.assertEqual(assess(fixture(employment_type='Contract'))['eligibility'], 'excluded')
        self.assertNotIn('Full-time employment', assess(fixture(employment_type='FullTime', description=''))['verification_needed'])

    def test_retry_after_http_date_respected(self):
        from email.utils import formatdate
        error = urllib.error.HTTPError('https://example.org', 429, 'Rate limited',
                                      {'Retry-After': formatdate(time.time()+3600, usegmt=True)}, None)
        with patch('urllib.request.urlopen', side_effect=error) as request, patch('time.sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                fetch_json('https://example.org')
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_provider_contract_and_malformed_snapshot(self):
        raw = {'id': 12, 'title': 'IT Support Analyst', 'location': {'name': 'Remote US'},
               'content': '<p>Windows &amp; Microsoft 365</p>', 'absolute_url': 'https://example.org/12'}
        jobs = retrieve(SOURCE, fetch=lambda _: {'jobs': [raw]})
        self.assertEqual(jobs[0]['description'], 'Windows & Microsoft 365')
        ashby = retrieve({**SOURCE, 'provider': 'ashby'}, fetch=lambda _: {'jobs': [
            {'id': 'a', 'title': 'Endpoint Support Specialist', 'location': 'USA',
             'jobUrl': 'https://example.org/a', 'descriptionPlain': 'Support Windows',
             'workplaceType': 'Remote', 'isRemote': True, 'employmentType': 'FullTime'}]})
        self.assertEqual(ashby[0]['workplace_type'], 'Remote')
        for payload in [{}, {'jobs': [raw, {}]}, {'jobs': [raw, raw]}]:
            with self.assertRaises(ValueError):
                retrieve(SOURCE, fetch=lambda _, p=payload: p)

    def test_unattended_worker_runs_without_browser_and_restarts(self):
        # Accelerated fixture interval only in this isolated test database.
        self.db.execute("UPDATE settings SET value='0.00001' WHERE key='interval_hours'")
        self.db.commit()
        stop = threading.Event()
        actual_discover = discover
        calls = []
        def discovery(db, sources):
            calls.append(1)
            return actual_discover(db, sources, fetcher=lambda _: [fixture()])
        with patch('careerpilot.discovery.discover', side_effect=discovery):
            thread = threading.Thread(target=worker, args=(self.path, [SOURCE], stop, .02))
            thread.start()
            deadline = time.time()+3
            while len(calls) < 2 and time.time() < deadline:
                time.sleep(.02)
            stop.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
        self.assertGreaterEqual(self.db.execute('SELECT count(*) FROM runs WHERE status="completed"').fetchone()[0], 2)


class HTTP(unittest.TestCase):
    def test_auth_csrf_persistence_and_submission_guard(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CAREERPILOT_PASSWORD': 'test-only-long-password'}):
            dbpath = tmp+'/db'
            db = connect(dbpath)
            ingest(db, SOURCE, [fixture()])
            db.close()
            app = server(dbpath, port=0)
            thread = threading.Thread(target=app.serve_forever)
            thread.start()
            base = 'http://127.0.0.1:'+str(app.server_port)
            auth = 'Basic '+base64.b64encode(b'careerpilot:test-only-long-password').decode()
            def request(path, body=None, extra=None):
                headers = {'Authorization': auth, **(extra or {})}
                if body is not None:
                    headers.update({'Content-Type': 'application/json', 'X-CareerPilot': '1'})
                req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
                # Loopback only; this does not alter external network proxy settings.
                return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base+'/api/state')
                self.assertEqual(error.exception.code, 401)
                self.assertIn(b'CareerPilot', request('/').read())
                request('/api/review', {'id': 1, 'status': 'interested'}).close()
                with self.assertRaises(urllib.error.HTTPError):
                    request('/api/review', {'id': 1, 'status': 'submitted'})
                with self.assertRaises(urllib.error.HTTPError):
                    request('/api/settings', {'enabled': False}, {'Origin': 'https://evil.example'})
                request('/api/settings', {'salary_target': 70000, 'enabled': False}).close()
                result = json.load(request('/api/state'))
                self.assertEqual(result['jobs'][0]['review_status'], 'interested')
                self.assertEqual(result['settings']['salary_target'], 70000)
                self.assertFalse(result['settings']['enabled'])
                self.assertFalse(result['worker']['active'])
                self.assertEqual(result['jobs'][0]['category'], 'secondary')
            finally:
                app.shutdown()
                thread.join()
                app.server_close()


if __name__ == '__main__':
    unittest.main()
