import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import WebSocket from 'ws';

const output = path.resolve('test-results/dashboard-binding');
await fs.mkdir(output, { recursive: true });
const profile = path.join(output, 'profile-dashboard-' + process.pid + '-' + Date.now());
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
  await call('Network.setBlockedURLs', { urls: ['https://*'] });
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  const phase = process.argv[2] || 'before';
  const pages = phase === 'paired' ? Object.fromEntries(['overview','seo','facebook_ads','facebook_content','tiktok','youtube'].flatMap(channel => [
    ['original-'+channel, '/__qa/original/'+channel], ['bound-'+channel, '/reports/rpt_'+'b'.repeat(32)+'?revision=2&section='+channel]
  ])) : phase === 'before' ? { overview: '/overview', seo: '/report/seo', facebook_ads: '/report/facebook-ads', facebook_content: '/report/social', tiktok: '/report/tiktok', youtube: '/report/youtube', published: '/reports/rpt_' + 'a'.repeat(32) + '?revision=2' } : { published: '/reports/rpt_' + 'a'.repeat(32) + '?revision=2' };
  const checks=[];
  for (const width of [1440, 768, 390]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    for (const [name, target] of Object.entries(pages)) {
      const requestStart=requests.length;
      await call('Page.navigate', {url: 'http://127.0.0.1:8083' + target});
      await until(`location.pathname===${JSON.stringify(target.split('?')[0])} && document.readyState === "complete"`);
      await evaluate('document.fonts.ready');
      await delay(350);
      if(name.startsWith('bound-')) {
        assert.ok(await evaluate('!!document.querySelector("#snapshot-data")'), 'dashboard rendered '+name);
        assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'), 'no overflow '+name+' '+width);
        assert.ok(!requests.slice(requestStart).some(r=>new URL(r.url).pathname.startsWith('/api/')), 'no mock API '+name);
        const rowButton = await evaluate('!!document.querySelector("[data-snapshot-detail]")');
        if(rowButton) {
          await click('[data-snapshot-detail]');
          assert.ok(await evaluate('document.querySelector("#snapshot-detail").open && document.querySelector("#snapshot-detail").innerText.includes("Revision 2")'));
          await click('#snapshot-detail [data-close-dialog]');
          const first=await evaluate('document.querySelector("[data-snapshot-search]").closest("[data-snapshot-table]").querySelectorAll("tbody tr:not([hidden])").length');
          assert.ok(first>0);
          await evaluate('document.querySelector("[data-snapshot-search]").value="no-fixture-matches-999";document.querySelector("[data-snapshot-search]").dispatchEvent(new Event("input"))');
          assert.equal(await evaluate('document.querySelector("[data-snapshot-search]").closest("[data-snapshot-table]").querySelectorAll("tbody tr:not([hidden])").length'),0);
          await evaluate('document.querySelector("[data-snapshot-search]").value="";document.querySelector("[data-snapshot-search]").dispatchEvent(new Event("input"))');
          assert.equal(await evaluate('document.querySelector("[data-snapshot-search]").closest("[data-snapshot-table]").querySelectorAll("tbody tr:not([hidden])").length'),first);
        }
        await evaluate('window.scrollTo({top:0,behavior:"instant"})');
      }
      checks.push({name,width,...await evaluate(`({font:getComputedStyle(document.body).fontFamily,background:getComputedStyle(document.body).backgroundColor,kpis:document.querySelectorAll('[data-snapshot-kpi],.seo-kpi-card,.fb-kpi,.fc-kpi-card,.vd-kpi').length})`)});
      await screenshot(phase + '-' + name + '-' + width + '.png');
      if(phase==='paired' && name.endsWith('seo')) {
        await evaluate('document.querySelector("#seo-keywords").scrollIntoView({block:"start",behavior:"instant"})'); await delay(500);
        await screenshot(phase+'-'+name+'-table-'+width+'.png');
      }
    }
  }
  assert.deepEqual(exceptions,[]);
  await fs.writeFile(path.join(output,phase+'-result.json'),JSON.stringify({phase,checks,exceptions:exceptions.length},null,2));
  console.log(JSON.stringify({phase, screenshots: Object.keys(pages).length * 3, exceptions: exceptions.length, output}));
  await call('Browser.close');
} finally {
  socket?.close(); chrome.kill(); clearInterval(keepalive);
}
