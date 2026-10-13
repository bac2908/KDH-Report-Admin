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
  const state = JSON.parse(await fs.readFile(path.join(output,'e2e-state.json'),'utf8'));
  const admin = 'http://localhost:8093', viewer = 'http://localhost:8084';
  await call('Page.navigate',{url:admin+'/'});
  await until('!!document.querySelector("#auth-form")');
  await evaluate('document.querySelector("#auth-email").value="review-admin@example.test"; document.querySelector("#auth-password").value="Review-Password-12345"; document.querySelector("#auth-form").requestSubmit()');
  await until('!!document.querySelector("#content")');
  await call('Page.navigate',{url:admin+'/marketing'});
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
  // Log out New only; Admin parent remains valid for an internal preview.
  await evaluate(`document.querySelector('form[action="/logout"]').requestSubmit()`);
  await until('location.pathname==="/login"');
  await call('Page.navigate',{url:viewer+'/auth/handoff/start?mode=preview&target_id='+state.candidate_id});
  await until('!!document.querySelector(".snapshot-preview")');await screenshot('e2e-preview.png');
  assert.ok(await evaluate('document.body.innerText.includes("chưa xuất bản")'));
  // Revoke the originating Admin session through normal CSRF-protected logout.
  await call('Page.navigate',{url:admin+'/'});await until('!!document.querySelector("#content")');
  await evaluate(`(async()=>{const me=await (await fetch('/api/auth/me')).json();const r=await fetch('/api/auth/logout',{method:'POST',headers:{'X-KDH-Request':'1','X-CSRF-Token':me.csrf}});if(!r.ok)throw Error('logout failed');})()`);
  await call('Page.navigate',{url:viewer+'/internal-preview/'+state.candidate_id});
  await until('location.pathname==="/login"');await screenshot('e2e-revoked-session.png');
  await call('Page.navigate',{url:viewer+'/auth/handoff/start?mode=published&target_id='+state.report_id+'&revision=1'});
  await until('!!document.querySelector("#handoff-login")');await screenshot('e2e-expired-admin-login.png');
  await evaluate('document.querySelector("[name=email]").value="review-admin@example.test"; document.querySelector("[name=password]").value="Review-Password-12345"; document.querySelector("#handoff-login").requestSubmit()');
  await until('!!document.querySelector("#snapshot-data")');
  assert.equal(await evaluate('location.href'),viewer+'/reports/'+state.report_id+'?revision=1');
  await call('Page.navigate',{url:viewer+'/reports/'+state.report_id+'?revision=1&section=youtube'});
  await until('document.body.innerText.includes("Section")');
  await screenshot('e2e-forbidden-section.png');
  for(const path of ['/overview','/report/seo','/api/v1/video-reports/youtube']) {
    const status=await evaluate(`fetch(${JSON.stringify(path)}).then(r=>r.status)`); assert.equal(status,404,'production blocks '+path);
  }
  assert.deepEqual(exceptions,[]);
  const summary={result:'PASS',report_id:state.report_id,revision:1,desktop_tablet_mobile:true,no_second_login:true,revocation:true,expired_login_resumes:true,preview:true,chart_geometry_changes:true,filter_export_no_mock:true,forbidden_section:true,production_mock_routes_blocked:true,js_exceptions:0};
  await fs.writeFile(path.join(output,'e2e-result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
  await call('Browser.close');
} finally { socket?.close(); chrome.kill(); clearInterval(keepalive); }
