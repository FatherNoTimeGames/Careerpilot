'use strict';
// Private Studio state is fetched only on the two authenticated Studio screens.
const ResumeStudio = (() => {
  let root, screen, jobs = [], data, draftProfile = null, expectedProfile = null;
  let selectedVersion = null, loadingToken = 0, dirty = false;
  const versionEdits = new Map();
  const updateDirty = () => { dirty = draftProfile !== null || versionEdits.size > 0; };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const warnings = review => `${(review?.blockers || []).map(x => `<p class="warning">${escape(x)}</p>`).join('')}${(review?.warnings || []).length ? `<details><summary>${review.warnings.length} items to review</summary><ul>${review.warnings.map(x => `<li>${escape(x)}</li>`).join('')}</ul></details>` : ''}`;
  const notify = message => { const el=document.querySelector('#notice'); el.textContent=message; el.classList.add('visible'); setTimeout(()=>el.classList.remove('visible'),6000); };
  async function request(action, body) {
    const response = await fetch('/api/studio' + (action ? '/' + action : ''), body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type':'application/json','X-CareerPilot':'1'}, body:JSON.stringify(body)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Studio operation failed');
    return result;
  }
  async function refresh() { data = await request(''); render(); }
  function options(values, current) { return Object.entries(values).map(([value,label])=>`<option value="${escape(value)}" ${value===current?'selected':''}>${escape(label)}</option>`).join(''); }
  function profileForm() {
    const facts = draftProfile ?? data.profile.facts;
    return `<p class="eyebrow">YOUR VERIFIED FOUNDATION</p><h1>Career profile</h1><p class="muted">Confirm facts before using them in a résumé. Personal experience stays separate from professional qualifications.</p><p><a href="#studio">Import a résumé or manage versions →</a></p>
      <div class="panel"><span class="tag">Revision ${data.profile.revision} · ${data.profile.verified?'Verified':'Needs review'}</span>${draftProfile?'<p class="warning">You have unsaved profile edits. Save before verifying or creating a résumé.</p>':''}${warnings(data.profile.review)}
      <form id="profile-form">${facts.map((f,i)=>`<fieldset class="fact" data-fact="${i}"><legend>Entry ${i+1}</legend><div class="two-col"><label>Section<select name="section">${options(data.sections,f.section)}</select></label><label>Verification<select name="status">${options({pending:'Awaiting verification',inferred:'Inferred — not confirmed',confirmed:'Confirmed by me'},f.status)}</select></label></div><label>Facts — use your own truthful wording<textarea name="text" rows="4" maxlength="5000" required>${escape(f.text)}</textarea></label><div class="two-col"><label>Start date<input name="start_date" placeholder="YYYY or YYYY-MM" value="${escape(f.start_date)}"></label><label>End date<input name="end_date" placeholder="YYYY, YYYY-MM or present" value="${escape(f.end_date)}"></label></div><label>Evidence or personal attestation<textarea name="evidence" maxlength="1000" rows="2" placeholder="What supports this information?">${escape(f.evidence)}</textarea></label>${f.document_id?`<p class="muted">Source: original document #${f.document_id}</p>`:''}<p class="muted">Selecting Confirmed by me attests that you checked this entry. Editing its content resets verification.</p><button type="button" class="secondary" data-action="remove-fact" data-index="${i}">Remove entry</button></fieldset>`).join('') || '<p>No career facts yet. Import a résumé or add your first entry.</p>'}<div class="actions"><button type="button" class="secondary" data-action="add-fact">Add information</button><button type="submit">Save profile</button></div></form></div>
      <form id="verify-profile" class="panel"><h2>Verify this profile revision</h2><p>Only confirmed entries are eligible for résumé versions. Pending or inferred entries stay excluded.</p><label class="check"><input type="checkbox" name="acknowledge" required>I have reviewed the confirmed facts, dates and warnings for this saved revision.</label><button ${draftProfile || !facts.length?'disabled':''}>Verify saved profile</button></form>`;
  }
  function versionCard(v) {
    const pending = versionEdits.get(v.id);
    if (pending) v = {...v, blocks: v.blocks.map(b => ({...b, ...pending.blocks.find(edit=>edit.fact_id===b.fact_id)}))};
    const approved=v.status==='approved', target=jobs.find(j=>j.id===v.job_id);
    return `<details class="panel version" data-version="${v.id}" ${selectedVersion===v.id?'open':''}><summary><strong>${escape(v.label)}</strong> · v${v.id} · ${approved?'Approved':'Draft'}${data.master_version_id===v.id?' · MASTER':''}</summary>${pending?'<p class="warning">Unsaved wording changes are retained while you navigate this tab. Save them before closing it.</p>':''}<p class="muted">Profile revision ${v.profile_revision}${target?' · Target: '+escape(target.title)+' at '+escape(target.employer):''}${v.source_document_id?' · Original document #'+v.source_document_id:''}</p>
      ${v.profile_outdated?'<p class="warning">The career profile has changed since this version was created. Review outdated information; drafts must be recreated from the verified current profile before approval.</p>':''}<p class="muted">${escape(data.ai.mode)}. Changed wording requires a reason and your truth review. Checks cannot establish semantic accuracy.</p>
      <form class="version-form" data-version="${v.id}">${v.blocks.map(b=>`<fieldset class="revision-block" data-fact-id="${escape(b.fact_id)}"><legend>${escape(data.sections[b.section])}</legend><div class="comparison"><div><h3>Verified original</h3><pre>${escape(b.original)}</pre></div><label>Revised wording<textarea name="revised" rows="6" maxlength="6000" ${approved?'readonly':''}>${escape(b.revised)}</textarea></label></div><label>Why this changed<textarea name="explanation" rows="2" maxlength="1000" ${approved?'readonly':''}>${escape(b.explanation)}</textarea></label></fieldset>`).join('')}${approved?'':'<button type="submit">Save wording & run checks</button>'}</form>
      ${warnings(v.review)}<p class="muted">${escape(v.review.method)}</p>
      ${v.preview?`<h3>Rendered PDF · ${v.preview.rendered_pages} page(s)</h3><p class="muted">Text completeness, DOCX round-trip and rendered margins checked. Inspect every page for readability and layout before approval.</p><div class="pdf-pages">${Array.from({length:v.preview.rendered_pages},(_,i)=>`<a href="/api/studio/versions/${v.id}/pages/${i+1}" target="_blank" rel="noopener"><img src="/api/studio/versions/${v.id}/pages/${i+1}" alt="Résumé version ${v.id}, page ${i+1}" loading="lazy"></a>`).join('')}</div>`:''}
      ${approved?`<div class="actions"><a class="button" href="/api/studio/versions/${v.id}/pdf">Download PDF</a><a class="button secondary" href="/api/studio/versions/${v.id}/docx">Download editable DOCX</a><button class="secondary" data-action="set-master" data-id="${v.id}" ${data.master_version_id===v.id?'disabled':''}>${data.master_version_id===v.id?'Current master':'Make master résumé'}</button></div><form class="select-version" data-version="${v.id}"><label>Use this approved version for a job<select name="job_id" required><option value="">Choose a job</option>${jobs.map(j=>`<option value="${j.id}">${escape(j.title)} · ${escape(j.employer)}</option>`).join('')}</select></label><button>Select for job</button><p class="muted">This selection does not authorize preparing or submitting an application.</p></form>`:`<div class="actions"><button class="secondary" data-action="preview" data-id="${v.id}">Check & render PDF preview</button></div><form class="approve-version" data-version="${v.id}"><label class="check"><input type="checkbox" name="truth_reviewed" required>I proofread every entry and confirm the revisions preserve verified facts without added claims.</label><label class="check"><input type="checkbox" name="layout_reviewed" required>I inspected every rendered PDF page for completeness, readability and layout.</label><button ${v.preview?'':'disabled'}>Approve this version</button><p class="muted">Approval preserves this version. It does not replace the master or authorize an application.</p></form>`}</details>`;
  }
  function studioView() {
    const confirmed=data.profile.facts.filter(f=>f.status==='confirmed');
    return `<p class="eyebrow">TRUTHFUL DOCUMENTS, READY TO REUSE</p><h1>Résumé Studio</h1><p class="muted">Import once. Verify your career facts. Review and reuse approved versions.</p><div class="warning">AI rewriting is unavailable: no approved AI provider is configured. Use the manual comparison editor below; processing stays on this server.</div>
      <form id="import-resume" class="panel"><h2>Import an original résumé</h2><label>PDF or DOCX · maximum 5 MB, 20 pages<input type="file" name="resume" accept=".pdf,.docx" required></label><button>Import & extract</button><p class="muted">The original is preserved unchanged. Imported information is never confirmed automatically. Image-only PDFs need manual entry; OCR is not available.</p></form>
      <details class="panel"><summary>Original documents (${data.documents.length})</summary>${data.documents.map(d=>`<div class="source"><strong>${escape(d.filename)}</strong><p><a href="/api/studio/documents/${d.id}/original">Download original</a></p>${d.warnings.map(w=>`<p class="warning">${escape(w)}</p>`).join('')}<details><summary>Extracted source text</summary><pre>${escape(d.extracted_text||'No readable text extracted.')}</pre></details><button class="secondary" data-action="import-facts" data-id="${d.id}" ${d.extracted_text?'':'disabled'}>Review extracted entries in profile</button></div>`).join('')||'<p>No originals uploaded.</p>'}</details>
      <form id="create-version" class="panel"><h2>Create a résumé version</h2><p>Career profile: ${data.profile.verified?'verified':'not yet verified'} · <a href="#profile">Edit and verify profile →</a></p><label>Version name<input name="label" maxlength="120" required placeholder="Master résumé — reviewed"></label><label>Optional target job<select name="job_id"><option value="">General résumé</option>${jobs.map(j=>`<option value="${j.id}">${escape(j.title)} · ${escape(j.employer)}</option>`).join('')}</select></label><label>Original document reference<select name="source_document_id"><option value="">None / multiple sources</option>${data.documents.map(d=>`<option value="${d.id}">${escape(d.filename)}</option>`).join('')}</select></label><details><summary>Choose confirmed facts to emphasize (${confirmed.length})</summary>${confirmed.map(f=>`<label class="check"><input type="checkbox" name="fact_ids" value="${escape(f.id)}" checked>${escape(data.sections[f.section])}: ${escape(f.text.slice(0,180))}</label>`).join('')||'<p>No confirmed entries.</p>'}</details><button ${data.profile.verified&&confirmed.length?'':'disabled'}>Create review draft</button><p class="muted">Drafts use a snapshot of confirmed facts. Tailoring changes emphasis, not qualifications. This is not full application preparation.</p></form>
      <h2>Résumé versions</h2>${data.versions.map(versionCard).join('')||'<div class="panel"><p>No versions yet. Start with an import or add facts in Career profile.</p></div>'}
      <div class="panel"><h2>Selected versions by job</h2>${data.job_resumes.map(s=>{const j=jobs.find(j=>j.id===s.job_id),v=data.versions.find(v=>v.id===s.version_id);return `<p>${escape(j?j.title+' · '+j.employer:'Job #'+s.job_id)} — ${escape(v?.label)} (v${s.version_id})</p>`}).join('')||'<p class="muted">No job selections yet.</p>'}</div>`;
  }
  function render() {
    if(!root || !['studio','profile'].includes(location.hash.slice(1)))return;
    root.innerHTML=screen==='profile'?profileForm():studioView();
  }
  function captureProfile() {
    const source=draftProfile ?? data.profile.facts;
    const facts=[...root.querySelectorAll('[data-fact]')].map(el=>{
      const item={...source[Number(el.dataset.fact)]};
      ['section','status','text','start_date','end_date','evidence'].forEach(k=>item[k]=el.querySelector(`[name="${k}"]`).value);
      return item;
    });
    expectedProfile ??= data.profile.revision;
    draftProfile=facts;
    dirty=true;
  }
  async function saveWording(id) {
    const v=data.versions.find(v=>v.id===id),form=root.querySelector(`.version-form[data-version="${id}"]`);
    if(!form||v.status==='approved')return;
    const blocks=[...form.querySelectorAll('.revision-block')].map(el=>({fact_id:el.dataset.factId,revised:el.querySelector('[name="revised"]').value,explanation:el.querySelector('[name="explanation"]').value}));
    const changed=blocks.some((b,i)=>b.revised!==v.blocks[i].revised||b.explanation!==v.blocks[i].explanation);
    if(!changed) { versionEdits.delete(id); updateDirty(); }
    if(changed) { await request('version/edit',{version_id:id,expected_edit_revision:versionEdits.get(id)?.revision??v.edit_revision,blocks}); versionEdits.delete(id); updateDirty(); await refresh(); }
  }
  async function onClick(e) {
    const button=e.target.closest('[data-action]');if(!button)return;
    e.preventDefault(); const action=button.dataset.action,id=Number(button.dataset.id);button.disabled=true;
    try {
      if(action==='add-fact') {
        captureProfile();draftProfile.push({id:crypto.randomUUID(),section:'employment',status:'pending',text:'',evidence:'',start_date:'',end_date:'',document_id:null});render();
      } else if(action==='remove-fact') {captureProfile();draftProfile.splice(Number(button.dataset.index),1);render();}
      else if(action==='import-facts') {
        const result=await request('document/facts',{document_id:id});
        expectedProfile??=data.profile.revision;
        draftProfile=[...(draftProfile??data.profile.facts),...result.suggested_facts];dirty=true;location.hash='profile';
      } else if(action==='preview') {
        selectedVersion=id;await saveWording(id);const v=data.versions.find(v=>v.id===id);
        await request('version/preview',{version_id:id,expected_edit_revision:v.edit_revision});await refresh();notify('Preview checked. Inspect every page before approval.');
      } else if(action==='set-master') {
        if(!window.confirm('Replace the master résumé with this approved version? The previous version will remain saved.'))return;
        await request('master',{version_id:id,expected_master_version_id:data.master_version_id,approve_replacement:true});await refresh();notify('Master résumé updated.');
      }
    } catch(error) {notify(error.message);} finally {button.disabled=false;}
  }
  async function onSubmit(e) {
    const form=e.target;if(!form.closest('#main'))return;e.preventDefault();
    const body=new FormData(form),button=form.querySelector('button[type="submit"],button:not([type])');if(button)button.disabled=true;
    try {
      if(form.id==='import-resume') {
        const file=body.get('resume');if(!file?.size||file.size>5*1024*1024)throw new Error('Select a PDF or DOCX no larger than 5 MB.');
        const buffer=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<buffer.length;i+=8192)binary+=String.fromCharCode(...buffer.subarray(i,i+8192));
        const result=await request('import',{filename:file.name,data:btoa(binary)});await refresh();notify('Original saved. Open Original documents to review extracted entries.');
      } else if(form.id==='profile-form') {
        captureProfile();await request('profile/save',{expected_revision:expectedProfile,facts:draftProfile});draftProfile=null;expectedProfile=null;updateDirty();await refresh();notify('Profile saved. Review warnings, then verify this revision.');
      } else if(form.id==='verify-profile') {
        if(draftProfile)throw new Error('Save your profile edits first.');
        await request('profile/verify',{expected_revision:data.profile.revision,acknowledge:body.has('acknowledge')});await refresh();notify('Profile verified. Confirmed facts can now be reused.');
      } else if(form.id==='create-version') {
        const result=await request('version/create',{profile_revision:data.profile.revision,label:body.get('label'),job_id:body.get('job_id')?Number(body.get('job_id')):null,source_document_id:body.get('source_document_id')?Number(body.get('source_document_id')):null,fact_ids:body.getAll('fact_ids')});selectedVersion=result.version_id;await refresh();notify('Draft created from confirmed facts.');
      } else if(form.classList.contains('version-form')) {
        selectedVersion=Number(form.dataset.version);await saveWording(selectedVersion);await refresh();notify('Wording saved and checked.');
      } else if(form.classList.contains('approve-version')) {
        const id=Number(form.dataset.version);await saveWording(id);const v=data.versions.find(v=>v.id===id);
        await request('version/approve',{version_id:id,expected_edit_revision:v.edit_revision,truth_reviewed:body.has('truth_reviewed'),layout_reviewed:body.has('layout_reviewed')});updateDirty();await refresh();notify('Version approved. Master résumé unchanged.');
      } else if(form.classList.contains('select-version')) {
        await request('select',{version_id:Number(form.dataset.version),job_id:Number(body.get('job_id'))});await refresh();notify('Résumé version selected; no application action authorized.');
      }
    } catch(error) {notify(error.message);} finally {if(button)button.disabled=false;}
  }
  async function mount(element, section, jobList) {
    root=element;screen=section;jobs=jobList;const token=++loadingToken;
    if(!root.dataset.studioEvents) {
      root.addEventListener('click',onClick);
      root.addEventListener('submit',e=>{if(['studio','profile'].includes(location.hash.slice(1)))onSubmit(e);});
      root.addEventListener('input',e=>{
        const fact=e.target.closest('[data-fact]');
        if(fact){if(['text','start_date','end_date','section'].includes(e.target.name))fact.querySelector('[name="status"]').value='pending';captureProfile();const verify=root.querySelector('#verify-profile button');if(verify)verify.disabled=true;}
        const versionForm=e.target.closest('.version-form');
        if(versionForm) {
          const id=Number(versionForm.dataset.version),v=data.versions.find(v=>v.id===id);
          const blocks=[...versionForm.querySelectorAll('.revision-block')].map(el=>({fact_id:el.dataset.factId,revised:el.querySelector('[name="revised"]').value,explanation:el.querySelector('[name="explanation"]').value}));
          versionEdits.set(id,{revision:versionEdits.get(id)?.revision??v.edit_revision,blocks});updateDirty();
        }
      });
      root.dataset.studioEvents='1';
    }
    try {const loaded=await request('');if(token!==loadingToken)return;data=loaded;render();}
    catch(error){if(token===loadingToken&&['studio','profile'].includes(location.hash.slice(1)))root.innerHTML=`<h1>Private Résumé Studio</h1><p class="warning">${escape(error.message)}</p><p class="muted">A private server password is required before storing candidate documents. Enter it securely in your host configuration; never put it in chat or Git.</p>`;}
  }
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
  return {mount};
})();
