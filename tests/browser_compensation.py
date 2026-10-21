"""Optional mobile UI regression; all pay/job fixtures stay in a temporary database."""
import os
import secrets
import tempfile
import threading
from playwright.sync_api import sync_playwright
from careerpilot.store import connect
from careerpilot.web import server
from careerpilot.discovery import ingest
from careerpilot.personalization import save_configuration


def job(ident,title,low,high,period,description):
    return {'external_id':ident,'title':title,'url':'https://example.invalid/jobs/'+ident,'employer':'Synthetic test employer',
            'location':'Remote, United States','is_remote':True,'workplace_type':'Remote','employment_type':'FullTime',
            'description':description,'compensation':{'compensationTiers':[{'title':'Texas','components':[
                {'compensationType':'Salary','minValue':low,'maxValue':high,'currencyCode':'USD','interval':period,'summary':'Base pay'}]}]}}


with tempfile.TemporaryDirectory() as tmp:
    os.environ['CAREERPILOT_PASSWORD']=secrets.token_urlsafe(32)
    path=tmp+'/jobs.sqlite3';db=connect(path)
    save_configuration(db,{'expected_revision':1,'work_state':'TX'})
    ingest(db,{'provider':'ashby','board':'synthetic','employer':'Synthetic test employer'},[
        job('1','IT Support Specialist — Paid Schedule',25,30,'1 HOUR','35 paid hours per week and 48 paid weeks per year.'),
        job('2','IT Support Specialist — Schedule Unknown',30,35,'1 HOUR','Full-time, 40 hours per week. Paid weeks are not stated.'),
        job('3','IT Support Specialist — Cents',40000,49999.60,'1 YEAR','Support Windows workstations.')])
    app=server(path,port=0);thread=threading.Thread(target=app.serve_forever);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CAREERPILOT_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':393,'height':851},http_credentials={'username':'careerpilot','password':os.environ['CAREERPILOT_PASSWORD']})
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            base='http://127.0.0.1:'+str(app.server_port)
            page.goto(base+'/#primary')
            page.get_by_text('$42,000–$50,400',exact=True).wait_for()
            page.get_by_text('Range starts below your target.',exact=True).wait_for()
            page.get_by_text('Pay evidence & annualization',exact=True).click()
            page.locator('.compensation-details').get_by_text('35 paid hours per week · 48 paid weeks per year',exact=False).wait_for()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path='/tmp/careerpilot-pay-mobile.png',full_page=True)
            page.locator('nav a[href="#unknown"]').click()
            page.get_by_text('Annual salary not verified',exact=True).wait_for()
            page.get_by_text('Pay evidence · verification needed',exact=True).click()
            page.get_by_text('$30–$35 / hour',exact=True).wait_for()
            assert '$62,400' not in page.locator('main').inner_text()
            page.locator('nav a[href="#secondary"]').click()
            page.get_by_text('$40,000–$49,999.60',exact=True).wait_for()
            page.locator('nav a[href="#settings"]').click()
            page.locator('#settings-form input[name=salary_target]').fill('45000')
            page.locator('#settings-form button').click()
            page.locator('nav a[href="#primary"]').click()
            page.get_by_text('$40,000–$49,999.60',exact=True).wait_for()
            page.reload();page.get_by_text('$40,000–$49,999.60',exact=True).wait_for()
            assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==3
            assert not errors,errors
            print('Compensation mobile browser passed: explicit hourly annualization, crossing-target warning, unknown paid-calendar rate display, cent precision, threshold reclassification and reload persistence. No JS errors or horizontal overflow.')
            browser.close()
    finally:
        app.shutdown();thread.join();app.server_close();db.close()
