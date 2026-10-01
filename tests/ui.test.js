import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import { JSDOM, VirtualConsole } from 'jsdom';

const html = await fs.readFile(new URL('../templates/index.html', import.meta.url), 'utf8');
const source = {};
for (const file of ['api.js', 'ui.js', 'views.js', 'app.js']) source[file] = await fs.readFile(new URL('../static/' + file, import.meta.url), 'utf8');
const types = [{ id: 'seo', label: 'Website Traffic & SEO', can_generate: true }, { id: 'ga4', label: 'Google Analytics 4', can_generate: true }, { id: 'gmb', label: 'Google Business Profile', can_generate: true }];
const admin = { id: 'admin', name: 'Admin kiểm thử', email: 'admin@example.test', role: 'admin', allowed: types.map(t => t.id), active: 1 };
const overview = { reports: [], report_count: 0, jobs: [], running: 0, failed: 0, sources: {}, google_connected: false, types, last_export: null, dashboard_url: 'http://localhost:8088', organization: { name: 'KinderHealth', author: '' } };

async function harness({ signedIn = true, role = 'admin', dataset = null, demo = false, requestMode = false } = {}) {
  const errors = [], requests = [], gates = new Map(); const virtualConsole = new VirtualConsole(); virtualConsole.on('jsdomError', e => errors.push(e));
  const dom = new JSDOM(html, { url: 'http://localhost/#overview', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole });
  const w = dom.window;
  w.structuredClone = structuredClone;
  w.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  w.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  let user = { ...admin, role }; let params = null;
  const processed = new Set();
  const makeDataset = () => dataset || {
    id: 'dataset-1', params: { ...params, search_type: 'web' }, created_at: '2026-09-29T07:00:00+00:00', exportable: true,
    sources: { ga4: { source: 'ga4', label: 'Google Analytics 4', status: 'ready', latest_available_date: params.end, fetched_at: '2026-09-29T07:00:00+00:00', warnings: [], asset: '484358741', timezone: 'Asia/Ho_Chi_Minh', totals: { activeUsers: 15, sessions: 22, screenPageViews: 31, engagementRate: .5 }, daily: [{ date: params.start, activeUsers: 5, sessions: 10, screenPageViews: 10, engagementRate: .5 }, { date: params.end, activeUsers: 10, sessions: 12, screenPageViews: 21, engagementRate: .5 }], channels: [], pages: [] } }
  };
  w.fetch = async (path, options = {}) => {
    const body = options.body && typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    requests.push({ path, method: options.method, body }); let result; let status = 200;
    if (!signedIn && !['/api/auth/me', '/api/auth/login'].includes(path)) { status = 401; result = { error: 'Phiên hết hạn' }; }
    else if (path === '/api/auth/me') result = { user: signedIn ? user : null, csrf: 'csrf-test', setup_required: false };
    else if (path === '/api/auth/login') { signedIn = true; result = { user, csrf: 'csrf-test' }; }
    else if (path === '/api/auth/logout') { signedIn = false; result = {}; }
    else if (path === '/api/overview') result = demo ? { ...overview, demo_enabled: true, demo_datasets: { seo: 'dataset-1' }, demo_sources: dataset.sources } : { ...overview, job_mode: requestMode ? 'request' : 'worker' };
    else if (path === '/api/uploads') result = [];
    else if (path === '/api/analyses') { params = body; result = { job_id: 'job-1', created: true }; }
    else if (path === '/api/jobs/job-1' || path === '/api/jobs/job-1/process') { if (path.endsWith('/process')) processed.add('job-1'); result = { id: 'job-1', kind: 'analysis', status: requestMode && !processed.has('job-1') ? 'queued' : 'succeeded', dataset_id: 'dataset-1', params, steps: [] }; }
    else if (path === '/api/datasets/dataset-1') result = makeDataset();
    else if (path === '/api/datasets/dataset-1/export') result = { job_id: 'export-1', created: true };
    else if (path === '/api/jobs/export-1' || path === '/api/jobs/export-1/process') { if (path.endsWith('/process')) processed.add('export-1'); result = { id: 'export-1', kind: 'export', status: requestMode && !processed.has('export-1') ? 'queued' : 'succeeded', dataset_id: 'dataset-1', params, steps: [] }; }
    else if (path === '/api/google') result = { configured: false, connected: false, sources: {}, assets: { ga4: '484358741', gsc: 'https://kinderhealth.vn/', keywords: 'Ranking' } };
    else if (path === '/api/jobs' || path === '/api/events' || path === '/api/reports' || path === '/api/schedules') result = [];
    else if (path === '/api/users') result = [user];
    else if (path === '/api/settings') result = { organization: { name: 'KinderHealth', author: '' }, timezone: 'Asia/Ho_Chi_Minh', versions: 'Giữ toàn bộ phiên bản', oauth_configured: false };
    else { status = 404; result = { error: 'Unknown test API ' + path }; }
    if (gates.has(path)) await gates.get(path);
    return { ok: status < 400, status, json: async () => structuredClone(result) };
  };
  const context = dom.getInternalVMContext(); const modules = new Map();
  for (const [name, code] of Object.entries(source)) modules.set(name, new vm.SourceTextModule(code, { context, identifier: name }));
  await modules.get('app.js').link(spec => modules.get(spec.replace('./', '')));
  await modules.get('app.js').evaluate();
  const until = async predicate => { const end = Date.now() + 3000; while (Date.now() < end) { if (predicate()) return; await new Promise(r => setTimeout(r, 10)); } throw new Error('UI timeout: ' + w.document.body.textContent.slice(-1500)); };
  await until(() => signedIn ? !!w.document.querySelector('h1') : !!w.document.querySelector('#auth-form'));
  return { dom, w, document: w.document, requests, errors, until, hold: path => { let release; gates.set(path, new Promise(r => release = r)); return () => { gates.delete(path); release(); }; }, expireAs: role => { signedIn = false; user = { ...admin, id: 'next-user', role, allowed: ['gmb'] }; }, close: () => w.close() };
}

test('Demo opens a labeled snapshot and switching to real data requires a fresh analysis', async () => {
  const dataset = { id: 'dataset-1', params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false, exclude_products: false, demo: true }, created_at: '2026-09-29T00:00:00Z', exportable: true, sources: { ga4: { source: 'ga4', label: 'Google Analytics 4', status: 'ready', demo: true, totals: { activeUsers: 200, sessions: 320, screenPageViews: 700, engagementRate: .6 }, daily: [], warnings: [], latest_available_date: '2026-09-28' } } };
  const h = await harness({ demo: true, dataset }); try {
    assert.match(h.document.body.textContent, /DEMO · SỐ LIỆU MÔ PHỎNG/);
    assert.match(h.document.body.textContent, /Chưa kết nối Google/);
    h.w.location.hash = 'analysis';
    await h.until(() => h.document.querySelector('#analysis-form'));
    assert.equal(h.document.querySelector('[name="demo"]').checked, true);
    assert.match(h.document.querySelector('#analysis-results').textContent, /DEMO · Số liệu mô phỏng/);
    assert.equal(h.document.querySelector('#export-button').disabled, false);
    h.document.querySelector('[name="demo"]').click();
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.requests.some(r => r.path === '/api/analyses'));
    assert.equal(h.requests.find(r => r.path === '/api/analyses').body.demo, false);
    await h.until(() => h.requests.filter(r => r.path === '/api/datasets/dataset-1').length === 2 && !h.document.querySelector('#job-progress .progress-card'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Login uses application credentials, keeps Google separate, and exposes navigation', async () => {
  const h = await harness({ signedIn: false }); try {
    assert.match(h.document.body.textContent, /Tài khoản ứng dụng và kết nối dữ liệu Google/);
    h.document.querySelector('#auth-email').value = 'admin@example.test'; h.document.querySelector('#auth-password').value = 'test-only-password';
    h.document.querySelector('#auth-form').requestSubmit();
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan vận hành');
    assert.equal(h.requests.filter(r => r.path === '/api/auth/login').length, 1);
    assert.match(h.document.body.textContent, /Chưa kết nối Google/);
    assert.equal(h.document.querySelectorAll('.nav-link').length, 9);
    assert.equal(h.w.localStorage.length, 0);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Filter edits preserve the applied result, disable export, and export uses the same dataset', async () => {
  const h = await harness(); try {
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    h.document.querySelector('#filter-start').value = '2026-09-01'; h.document.querySelector('#filter-end').value = '2026-09-28';
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.document.querySelector('#export-button')?.disabled === false);
    assert.match(h.document.querySelector('#applied-period').textContent, /01\/09\/2026.*28\/09\/2026/);
    const input = h.document.querySelector('#filter-end'); input.value = '2026-09-27'; input.dispatchEvent(new h.w.Event('input', { bubbles: true }));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    assert.equal(h.document.querySelector('#dirty-note').classList.contains('show'), true);
    assert.match(h.document.querySelector('#applied-period').textContent, /28\/09\/2026/);
    input.value = '2026-09-28'; input.dispatchEvent(new h.w.Event('input', { bubbles: true }));
    assert.equal(h.document.querySelector('#export-button').disabled, false);
    h.document.querySelector('#export-button').click();
    await h.until(() => h.document.querySelector('#modal').open);
    assert.match(h.document.querySelector('#modal').textContent, /Không gọi lấy một tập dữ liệu mới/);
    h.document.querySelector('[data-action=export-confirm]').click();
    await h.until(() => h.document.querySelector('a[href="/api/jobs/export-1/download"]'));
    assert.equal(h.requests.filter(r => r.path === '/api/analyses').length, 1);
    assert.deepEqual(h.requests.find(r => r.path === '/api/datasets/dataset-1/export').body, {});
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Vercel processes queued analysis and export through authenticated POST requests', async () => {
  const h = await harness({ requestMode: true }); try {
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    h.document.querySelector('#filter-start').value = '2026-09-01';
    h.document.querySelector('#filter-end').value = '2026-09-28';
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.document.querySelector('#export-button')?.disabled === false);
    h.document.querySelector('#export-button').click();
    await h.until(() => h.document.querySelector('[data-action=export-confirm]'));
    h.document.querySelector('[data-action=export-confirm]').click();
    await h.until(() => h.document.querySelector('a[href="/api/jobs/export-1/download"]'));
    const process = h.requests.filter(r => r.path.endsWith('/process'));
    assert.deepEqual(process.map(r => r.path), ['/api/jobs/job-1/process', '/api/jobs/export-1/process']);
    assert.ok(process.every(r => r.method === 'POST'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Failed source remains an error, does not render fake KPI and cannot export', async () => {
  const dataset = { id: 'dataset-1', params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false, exclude_products: false }, created_at: '2026-09-29T00:00:00Z', exportable: false, sources: { gsc: { source: 'gsc', label: 'Search Console', status: 'permission_denied', error: 'Thiếu quyền <img src=x onerror=alert(1)>', fetched_at: '2026-09-29T00:00:00Z', latest_available_date: null, warnings: [] } } };
  const h = await harness({ dataset }); try {
    h.w.location.hash = 'analysis?dataset=dataset-1'; await h.until(() => h.document.querySelector('#analysis-results'));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    assert.match(h.document.querySelector('#analysis-results').textContent, /Thiếu quyền <img/);
    assert.equal(h.document.querySelector('#analysis-results img'), null);
    assert.equal(h.document.querySelector('#analysis-results .kpi'), null);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('All operator pages render; unconfigured OAuth is explicit and viewer has no admin navigation', async () => {
  const h = await harness(); try {
    for (const page of ['reports', 'connections', 'activity', 'uploads', 'schedules', 'users', 'settings']) {
      h.w.location.hash = page; await h.until(() => h.document.querySelector(`[href="#${page}"]`)?.classList.contains('active') && h.document.querySelector('#content h1'));
      assert.doesNotMatch(h.document.querySelector('#content').textContent, /Không thể hiển thị màn hình/);
      if (page === 'connections') { assert.match(h.document.querySelector('.nav-link[href="#connections"]').textContent, /Kết nối nền tảng/); assert.equal(h.document.querySelectorAll('.nav-sub-link').length, 3); assert.equal(h.document.querySelectorAll('.platform-card-link').length, 3); for (const platform of ['google', 'facebook', 'tiktok']) assert.ok(h.document.querySelector(`.nav-sub-link[href="#connections/${platform}"]`)); }
    }
    h.w.location.hash = 'connections/google'; await h.until(() => h.document.querySelector('.nav-sub-link[href="#connections/google"].active'));
    assert.equal(h.document.querySelector('[data-action=connect-google]').disabled, true); assert.match(h.document.querySelector('#content').textContent, /Chưa cấu hình Google OAuth/);
    h.w.location.hash = 'connections/facebook'; await h.until(() => h.document.querySelector('.nav-sub-link[href="#connections/facebook"].active'));
    assert.match(h.document.querySelector('#content').textContent, /Meta API chưa được tích hợp ở backend/); assert.equal(h.document.querySelector('#content button[disabled]').textContent, 'Kết nối Facebook'); assert.ok(h.document.querySelector('a[href="https://developers.facebook.com/docs/marketing-apis/"]'));
    h.w.location.hash = 'connections/tiktok'; await h.until(() => h.document.querySelector('.nav-sub-link[href="#connections/tiktok"].active'));
    assert.match(h.document.querySelector('#content').textContent, /TikTok API chưa được tích hợp ở backend/); assert.equal(h.document.querySelector('#content button[disabled]').textContent, 'Kết nối TikTok'); assert.ok(h.document.querySelector('a[href="https://business-api.tiktok.com/portal/docs"]'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
  const viewer = await harness({ role: 'viewer' }); try {
    assert.equal(viewer.document.querySelector('.nav-link[href="#connections"]'), null);
    assert.equal(viewer.document.querySelector('.nav-link[href="#users"]'), null);
    viewer.w.location.hash = 'users'; await viewer.until(() => viewer.document.body.textContent.includes('Màn hình này chỉ dành cho quản trị viên.'));
    assert.equal(viewer.requests.some(r => r.path === '/api/users'), false);
  } finally { viewer.close(); }
});

test('Session expiry clears the previous user dataset before a different account logs in', async () => {
  const h = await harness(); try {
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    h.document.querySelector('#filter-start').value = '2026-09-01'; h.document.querySelector('#filter-end').value = '2026-09-28';
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.document.querySelector('#export-button')?.disabled === false);
    h.expireAs('viewer'); h.w.location.hash = 'overview';
    await h.until(() => h.document.querySelector('#auth-form'));
    assert.equal(h.document.querySelector('#analysis-results'), null);
    h.document.querySelector('#auth-email').value = 'next@example.test'; h.document.querySelector('#auth-password').value = 'test-only-password';
    h.document.querySelector('#auth-form').requestSubmit();
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan vận hành');
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    assert.equal(h.document.querySelector('#analysis-results .kpi'), null);
    assert.match(h.document.querySelector('#applied-period').textContent, /Chưa có bộ lọc được áp dụng/);
  } finally { h.close(); }
});

test('A response still in flight cannot restore the previous account data after expiry', async () => {
  const h = await harness(); let release; try {
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    h.document.querySelector('#filter-start').value = '2026-09-01'; h.document.querySelector('#filter-end').value = '2026-09-28';
    release = h.hold('/api/datasets/dataset-1'); h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.requests.some(r => r.path === '/api/datasets/dataset-1'));
    h.expireAs('viewer'); h.w.location.hash = 'overview'; await h.until(() => h.document.querySelector('#auth-form'));
    h.document.querySelector('#auth-email').value = 'next@example.test'; h.document.querySelector('#auth-password').value = 'test-only-password'; h.document.querySelector('#auth-form').requestSubmit();
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan vận hành');
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    release(); release = null; await new Promise(r => setTimeout(r, 50));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    assert.equal(h.document.querySelector('#analysis-results .kpi'), null);
    assert.match(h.document.querySelector('#applied-period').textContent, /Chưa có bộ lọc được áp dụng/);
  } finally { release?.(); h.close(); }
});
