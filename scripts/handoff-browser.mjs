import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import WebSocket from 'ws';

const output = path.resolve('test-results/dashboard-binding');
await fs.mkdir(output, { recursive: true });
const profile = path.join(output, 'profile-handoff-' + process.pid + '-' + Date.now());
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--in-process-gpu', '--remote-debugging-port=0', '--disable-background-networking',
  '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--user-data-dir=' + profile, 'about:blank'
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
chrome.stderr.on('data', data => console.error(data.toString().trim()));
chrome.on('exit', (code, signal) => console.error('Chrome exit', code, signal));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const keepalive = setInterval(() => {}, 1000);
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = Number((await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; }
    catch { await delay(100); }
  }
  assert.ok(port, 'Chrome must start');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }));
  let sequence = 0;
  const pending = new Map(), requests = [], exceptions = [];
  socket.addEventListener('close', event => { for (const { reject } of pending.values()) reject(new Error('CDP closed: ' + event.code)); });
  socket.addEventListener('error', event => console.error('CDP socket error', event.message));
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
    } else if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request);
    else if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  });
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(() => reject(new Error('CDP timeout: ' + method)), 15000);
    pending.set(id, { resolve: result => { clearTimeout(timeout); resolve(result); }, reject: error => { clearTimeout(timeout); reject(error); } });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const until = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await delay(100);
    }
    throw new Error('Timeout: ' + expression + '\n' + await evaluate('document.body.innerText'));
  };
  const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const screenshot = async name => {
    const result = await call('Page.captureScreenshot', { format: 'png' });
    await fs.writeFile(path.join(output, name), Buffer.from(result.data, 'base64'));
  };
  await call('Page.enable');
  await call('Runtime.enable');
  await call('Network.enable');
  await fs.mkdir(path.join(output,'downloads'), {recursive:true});
  await call('Browser.setDownloadBehavior', {behavior:'allow', downloadPath:path.join(output,'downloads')});
  await call('Network.setBlockedURLs', { urls: ['https://*'] });
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  const runtimeLoginOnly = process.argv.includes('--runtime-login');
  const admin = runtimeLoginOnly ? 'http://localhost:8090' : 'http://localhost:8093';
  const viewer = runtimeLoginOnly ? 'http://localhost:8080' : 'http://localhost:8084';
  // The report entry must render the existing Admin login, including its styles
  // and controls, at the same size as the normal Admin root. No runtime sign-in.
  for (const width of [1440, 390]) {
    await call('Emulation.setDeviceMetricsOverride', {width, height:1000, deviceScaleFactor:1, mobile:false});
    await call('Page.navigate', {url:admin+'/'});
    await until('!!document.querySelector(".login-screen .login-card #auth-form")');
    const loginSignature = `(() => {const card=document.querySelector('.login-card');const css=getComputedStyle(card);const rect=card.getBoundingClientRect();return {html:card.outerHTML,width:rect.width,height:rect.height,radius:css.borderRadius,background:css.backgroundColor,padding:css.padding};})()`;
    const originalLogin = await evaluate(loginSignature);
    assert.notEqual(originalLogin.radius, '0px', 'original Admin login stylesheet loaded');
    await screenshot((runtimeLoginOnly?'runtime':'fixture')+'-original-admin-login-'+width+'.png');
    for (const entry of ['/', '/login', '/reports']) {
      await call('Page.navigate', {url:viewer+entry});
      await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('.login-screen .login-card #auth-form')`);
      assert.equal(await evaluate('location.pathname'), '/viewer/reports');
      assert.deepEqual(await evaluate(loginSignature), originalLogin, 'report entry reuses original Admin login');
    }
    await screenshot((runtimeLoginOnly?'runtime':'fixture')+'-restored-admin-login-'+width+'.png');
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'login fits viewport '+width);
  }
  await call('Emulation.setDeviceMetricsOverride', {width:1440, height:1000, deviceScaleFactor:1, mobile:false});
  if (runtimeLoginOnly) {
    assert.deepEqual(exceptions, []);
    assert.ok(!requests.some(r => r.method === 'POST'), 'runtime login smoke must not submit credentials or data');
    const result = {result:'PASS', original_admin_login:true, new_entries_use_original_login:true, desktop_mobile:true, no_credentials_submitted:true, js_exceptions:0};
    await fs.writeFile(path.join(output,'restored-login-runtime-result.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } else {
  const state = JSON.parse(await fs.readFile(path.join(output,'e2e-state.json'),'utf8'));
  for (const entry of ['/', '/login', '/reports']) {
    await call('Page.navigate',{url:viewer+entry});
    await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('#auth-form')`);
    assert.equal(await evaluate('location.pathname'), '/viewer/reports');
  }
  await screenshot('admin-only-login-at-admin.png');
  await evaluate('document.querySelector("[name=email]").value="review-admin@example.test"; document.querySelector("[name=password]").value="Review-Password-12345"; document.querySelector("#auth-form").requestSubmit()');
  await until('document.querySelector("#existing-report")?.options.length > 1');
  await evaluate(`document.querySelector('#existing-report').value=${JSON.stringify(state.report_id+':1')};document.querySelector('#existing-report').dispatchEvent(new Event('change'))`);
  await until('!document.querySelector("#selected-report-open").hidden');
  await screenshot('e2e-admin-selected.png');
  const before = requests.length;
  await click('#selected-report-open');
  await until('!!document.querySelector("#snapshot-data")');
  const destination = await evaluate('location.href');
  assert.equal(destination, viewer+'/reports/'+state.report_id+'?revision=1');
  assert.ok(!requests.slice(before).some(r => new URL(r.url).pathname === '/login' || new URL(r.url).pathname === '/reports'));
  assert.equal(await evaluate(`document.querySelector('[data-snapshot-kpi="gsc.clicks"]').textContent.trim()`), '60');
  await until('document.querySelectorAll("[data-bundle-chart] svg path").length > 0');
  for (const width of [1440,768,390]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
    await evaluate('window.scrollTo(0,0);document.fonts.ready'); await delay(150);
    await screenshot('e2e-report-'+width+'.png');
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'no horizontal page overflow '+width);
    if (width < 1024) {await click('#sidebar-toggle'); await click('[data-path="thu-hang-tu-khoa"]');}
    else await click('[data-path="thu-hang-tu-khoa"]');
    assert.ok((await evaluate('location.href')).includes('revision=1'));
    await delay(650);
    await screenshot('e2e-details-'+width+'.png');
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  const filterBefore=requests.length;
  await evaluate('document.querySelector("[data-snapshot-search]").value="not-in-fixture";document.querySelector("[data-snapshot-search]").dispatchEvent(new Event("input"))');
  await click('#data-source'); await screenshot('e2e-source-popup.png'); await click('#source-dialog [data-close-dialog]');
  await click('#export-report'); await click('#export-csv'); await delay(200);
  assert.ok(!requests.slice(filterBefore).some(r=>r.url.includes('/api/')), 'filter/export must not call mock API');
  // The same renderer must change geometry when its saved series changes.
  const changed=await evaluate(`(() => { const e=document.querySelector('[data-bundle-chart]'); const c={title:'fixture',kind:'line',source:'fixture',unit:'count',labels:['2026-09-01','2026-09-02','2026-09-03'],values:[1,null,3]};dashboardCharts.renderBundleChart(e,c);const a=e.querySelector('path').getAttribute('d');dashboardCharts.renderBundleChart(e,{...c,values:[3,1,2]});return a!==e.querySelector('path').getAttribute('d');})()`);assert.ok(changed);
  // A missing Viewer cookie resumes through the live Admin session, without a password.
  await call('Network.deleteCookies', {name:'kdh_viewer_session',url:viewer});
  await evaluate('document.documentElement.dataset.navigationProbe="old"');
  await call('Page.navigate',{url:viewer+'/reports/'+state.report_id+'?revision=1'});
  await until('document.documentElement.dataset.navigationProbe !== "old" && document.readyState === "complete" && !!document.querySelector("#snapshot-data")');
  assert.equal(await evaluate('location.href'),viewer+'/reports/'+state.report_id+'?revision=1');
  // End the viewing session only; Admin remains valid and owns report selection.
  await evaluate(`document.querySelector('form[action="/logout"]').requestSubmit()`);
  await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('#existing-report')`);
  await call('Page.navigate',{url:viewer+'/auth/handoff/start?mode=preview&target_id='+state.candidate_id});
  await until('!!document.querySelector(".snapshot-preview")');await screenshot('e2e-preview.png');
  assert.ok(await evaluate('document.body.innerText.includes("chưa xuất bản")'));
  // Revoke the originating Admin session through normal CSRF-protected logout.
  await call('Page.navigate',{url:admin+'/'});await until('!!document.querySelector("#content")');
  await evaluate(`(async()=>{const me=await (await fetch('/api/auth/me')).json();const r=await fetch('/api/auth/logout',{method:'POST',headers:{'X-KDH-Request':'1','X-CSRF-Token':me.csrf}});if(!r.ok)throw Error('logout failed');})()`);
  await call('Page.navigate',{url:viewer+'/internal-preview/'+state.candidate_id});
  await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('#auth-form')`);await screenshot('e2e-revoked-session.png');
  await call('Page.navigate',{url:viewer+'/reports/'+state.report_id+'?revision=1'});
  await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('#auth-form')`);await screenshot('e2e-expired-admin-login.png');
  await evaluate('document.querySelector("[name=email]").value="review-admin@example.test"; document.querySelector("[name=password]").value="Review-Password-12345"; document.querySelector("#auth-form").requestSubmit()');
  await until('!!document.querySelector("#snapshot-data")');
  assert.equal(await evaluate('location.href'),viewer+'/reports/'+state.report_id+'?revision=1');
  // Changing the Admin account must not silently replace a live viewing session.
  await call('Page.navigate',{url:admin+'/'});await until('!!document.querySelector("#content")');
  await evaluate(`(async()=>{window.qaSecondaryEmail='second-admin-'+Date.now()+'@example.test';const me=await(await fetch('/api/auth/me')).json();const created=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json','X-KDH-Request':'1','X-CSRF-Token':me.csrf},body:JSON.stringify({email:window.qaSecondaryEmail,name:'Second Admin',password:'Second-Admin-12345',role:'admin',allowed:[]})});if(!created.ok)throw Error('fixture user failed');})()`);
  // Simulate another valid Admin identity without revoking the original parent.
  await call('Network.deleteCookies', {name:'kdh_session',url:admin});
  await evaluate(`(async()=>{const logged=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-KDH-Request':'1'},body:JSON.stringify({email:window.qaSecondaryEmail,password:'Second-Admin-12345'})});if(!logged.ok)throw Error('fixture account change failed');})()`);
  await call('Page.navigate',{url:viewer+'/auth/handoff/start?mode=published&target_id='+state.report_id+'&revision=1'});
  await until('document.querySelector("#handoff-reset")?.hidden === false');
  await screenshot('admin-only-identity-conflict.png');
  await evaluate('document.querySelector("#handoff-reset").requestSubmit()');
  await until(`location.origin === ${JSON.stringify(admin)} && !!document.querySelector('#existing-report')`);
  await call('Page.navigate',{url:viewer+'/auth/handoff/start?mode=published&target_id='+state.report_id+'&revision=1'});
  await until('!!document.querySelector("#snapshot-data")');
  await call('Page.navigate',{url:viewer+'/reports/'+state.report_id+'?revision=1&section=youtube'});
  await until('document.body.innerText.includes("Section")');
  await screenshot('e2e-forbidden-section.png');
  for(const path of ['/overview','/report/seo','/api/v1/video-reports/youtube']) {
    const status=await evaluate(`fetch(${JSON.stringify(path)}).then(r=>r.status)`); assert.equal(status,404,'production blocks '+path);
  }
  assert.deepEqual(exceptions,[]);
  assert.ok(requests.filter(r=>r.method==='POST' && r.url.includes('/api/auth/login')).every(r=>new URL(r.url).origin===admin));
  assert.ok(!requests.some(r=>r.method==='POST' && r.url===viewer+'/login'));
  const summary={result:'PASS',report_id:state.report_id,revision:1,original_admin_login:true,desktop_tablet_mobile:true,no_second_login:true,new_has_no_login:true,entry_redirects_to_admin:true,viewer_expiry_resumes:true,revocation:true,expired_login_resumes:true,identity_conflict_recovery:true,preview:true,chart_geometry_changes:true,filter_export_no_mock:true,forbidden_section:true,production_mock_routes_blocked:true,js_exceptions:0};
  await fs.writeFile(path.join(output,'admin-only-result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
  }
  await call('Browser.close');
} finally { socket?.close(); chrome.kill(); clearInterval(keepalive); }
