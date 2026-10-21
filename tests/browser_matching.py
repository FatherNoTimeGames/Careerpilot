"""Optional real Chromium check using synthetic jobs and a temporary verified profile."""
import json
import os
import secrets
import tempfile
import threading
from playwright.sync_api import sync_playwright
from careerpilot.store import connect
from careerpilot import studio, personalization
from careerpilot.discovery import ingest
from careerpilot.web import server

with tempfile.TemporaryDirectory() as tmp:
    os.environ['CAREERPILOT_PASSWORD']=secrets.token_urlsafe(32)
    path=tmp+'/jobs.sqlite3'
    db=connect(path)
    facts=[{'id':'skills','section':'skills','text':'Supported Windows and Microsoft 365.','status':'confirmed','evidence':'Synthetic test owner attestation','document_id':None,'start_date':'','end_date':''},
           {'id':'employment','section':'employment','text':'Hospital IT technician supporting clinical employees.','status':'confirmed','evidence':'Synthetic test owner attestation','document_id':None,'start_date':'','end_date':''}]
    revision=studio.save_profile(db,{'expected_revision':0,'facts':facts})['revision']
    studio.verify_profile(db,{'expected_revision':revision,'acknowledge':True})
    personalization.save_configuration(db,{'expected_revision':1,'work_state':'TX'})
    description=('Windows and Microsoft 365 internal IT support for employees at a hospital. Full-time. Health insurance. No travel required. No certifications required. Hiring in Texas. 8 AM to 4 PM Central. No on-call. Career growth. Annual base salary $55,000 - $65,000.')
    job={'external_id':'1','url':'https://example.invalid/jobs/1','employer':'Synthetic employer','title':'IT Support Specialist','location':'Remote, United States','employment_type':'FullTime','is_remote':True,'description':description}
    ingest(db,{'provider':'greenhouse','board':'synthetic','employer':'Synthetic employer'},[job])
    app=server(path,port=0)
    thread=threading.Thread(target=app.serve_forever);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CAREERPILOT_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':393,'height':851},http_credentials={'username':'careerpilot','password':os.environ['CAREERPILOT_PASSWORD']})
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(app.server_port)+'/#primary')
            page.get_by_text('100 / 100 match points',exact=True).wait_for()
            page.get_by_text('Why this match · requirements & evidence',exact=True).click()
            page.get_by_role('heading',name='Score breakdown',exact=True).wait_for()
            form=page.locator('.job-verification')
            form.locator('[data-gate=state] textarea').fill('Synthetic employer posting confirms Texas eligibility')
            form.locator('[name=acknowledge]').check()
            form.get_by_role('button',name='Save requirement review').click()
            page.get_by_text('100 / 100 match points',exact=True).wait_for()
            page.get_by_role('button',name='Interested',exact=True).click()
            page.get_by_text('+1.7 feedback ranking points',exact=False).wait_for()
            page.locator('nav a[href="#settings"]').click()
            page.locator('#matching-settings select[name=work_state]').select_option('CA')
            page.get_by_role('button',name='Save matching priorities',exact=True).click()
            page.locator('nav a[href="#primary"]').click()
            page.get_by_text('100 / 100 match points',exact=True).wait_for()
            page.get_by_text('Why this match · requirements & evidence',exact=True).click()
            page.get_by_text('The posting, work state or profile changed since your last requirement review. That review is no longer applied.',exact=True).wait_for()
            page.locator('nav a[href="#settings"]').click()
            page.locator('#matching-settings input[name=learning_enabled]').uncheck()
            page.get_by_role('button',name='Save matching priorities',exact=True).click()
            page.once('dialog',lambda dialog:dialog.accept())
            page.get_by_role('button',name='Reset learned preferences',exact=True).click()
            page.get_by_text('0 current feedback records since the last reset.',exact=False).wait_for()
            page.locator('#matching-settings select[name=work_state]').select_option('TX')
            page.get_by_role('button',name='Save matching priorities',exact=True).click()
            page.screenshot(path='/tmp/careerpilot-matching-mobile.png',full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Mobile horizontal overflow'
            page.reload();page.locator('#matching-settings').wait_for()
            assert page.locator('#matching-settings select[name=work_state]').input_value()=='TX'
            assert not errors,errors
            browser.close()
        assert db.execute('SELECT review_status FROM jobs').fetchone()[0]=='interested'
        assert personalization.configuration(db)['work_state']=='TX'
        print('Matching mobile browser passed: score breakdown, owner review, feedback ranking, stale state verification, priority controls, learning disable/reset and reload persistence. No JS errors or horizontal overflow.')
    finally:
        app.shutdown();thread.join();app.server_close();db.close()
