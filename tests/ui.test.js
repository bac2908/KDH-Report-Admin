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

async function harness({ signedIn = true, role = 'admin', dataset = null, demo = false, requestMode = false, setupRequired = false, googleConfigured = false, googleConnected = false, googleSources = {}, metaStatus = { configured: false, connected: false, has_connection: false, status: 'disconnected' }, metaReadError = null, metaConnectError = null, metaRevoked = true, jobs = [], uploads = [], reports = [], datasetRecords = {}, datasetErrors = {}, reportBundleResult = { report_id: 'rpt_test_bundle', revision: 1, status: 'draft' }, reportBundleError = null, reportBundleDetail = null, reportBundleReadError = null, reportBundleUpdateResult = { report_id: 'rpt_test_bundle', revision: 1, status: 'draft' }, reportBundleUpdateError = null } = {}) {
  const errors = [], requests = [], gates = new Map(); const virtualConsole = new VirtualConsole(); virtualConsole.on('jsdomError', e => errors.push(e));
  const dom = new JSDOM(html, { url: 'http://localhost/#overview', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole });
  const w = dom.window;
  w.structuredClone = structuredClone;
  w.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  w.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  let user = { ...admin, role }; let params = null; let providerConnected = googleConnected;
  const processed = new Set(); let createdBundlePayload = null; let currentBundlePayload = null;
  let capturedSections = {};
  const captureSections = sections => Object.fromEntries(sections.map((section, position) => {
    const record = datasetRecords[section.dataset_id] || dataset;
    const data = record ? structuredClone(record) : null;
    if (data) delete data.exportable;
    return [section.key, { dataset_id: section.dataset_id, position, report_type: record?.params?.report_type,
      valid: record?.exportable, data }];
  }));
  const makeDataset = () => dataset || {
    id: 'dataset-1', params: { ...params, search_type: 'web' }, created_at: '2026-09-29T07:00:00+00:00', exportable: true,
    sources: { ga4: { source: 'ga4', label: 'Google Analytics 4', status: 'ready', latest_available_date: params.end, fetched_at: '2026-09-29T07:00:00+00:00', warnings: [], asset: '484358741', timezone: 'Asia/Ho_Chi_Minh', totals: { activeUsers: 15, sessions: 22, screenPageViews: 31, engagementRate: .5 }, daily: [{ date: params.start, activeUsers: 5, sessions: 10, screenPageViews: 10, engagementRate: .5 }, { date: params.end, activeUsers: 10, sessions: 12, screenPageViews: 21, engagementRate: .5 }], channels: [], pages: [] } }
  };
  w.fetch = async (path, options = {}) => {
    const body = options.body && typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    requests.push({ path, method: options.method, body }); let result; let status = 200;
    if (!signedIn && !['/api/auth/me', '/api/auth/login', '/api/auth/setup'].includes(path)) { status = 401; result = { error: 'Phiên hết hạn' }; }
    else if (path === '/api/auth/me') result = { user: signedIn ? user : null, csrf: 'csrf-test', setup_required: setupRequired };
    else if (path === '/api/auth/login') { signedIn = true; result = { user, csrf: 'csrf-test' }; }
    else if (path === '/api/auth/setup') { setupRequired = false; result = {}; }
    else if (path === '/api/auth/logout') { signedIn = false; result = {}; }
    else if (path === '/api/overview') result = demo ? { ...overview, sources: googleSources, demo_enabled: true, demo_datasets: { seo: 'dataset-1' }, demo_sources: dataset.sources } : { ...overview, sources: googleSources, job_mode: requestMode ? 'request' : 'worker' };
    else if (path === '/api/uploads' && options.method === 'POST') result = {};
    else if (path === '/api/uploads') result = uploads;
    else if (path === '/api/analyses') { params = body; result = { job_id: 'job-1', created: true }; }
    else if (path === '/api/jobs/job-1' || path === '/api/jobs/job-1/process') { if (path.endsWith('/process')) processed.add('job-1'); result = { id: 'job-1', kind: 'analysis', status: requestMode && !processed.has('job-1') ? 'queued' : 'succeeded', dataset_id: 'dataset-1', params, steps: [] }; }
    else if (path === '/api/datasets/dataset-1') result = makeDataset();
    else if (path.startsWith('/api/datasets/') && options.method !== 'POST') {
      const datasetId = decodeURIComponent(path.slice('/api/datasets/'.length));
      if (datasetErrors[datasetId]) { status = datasetErrors[datasetId].status; result = { error: datasetErrors[datasetId].message }; }
      else if (datasetRecords[datasetId]) result = datasetRecords[datasetId];
      else { status = 404; result = { error: 'Dataset not found' }; }
    }
    else if (path === '/api/datasets/dataset-1/save') result = { report_id: 'report-1' };
    else if (path === '/api/datasets/dataset-1/export') result = { job_id: 'export-1', created: true };
    else if (path.startsWith('/api/datasets/') && path.endsWith('/export') && options.method === 'POST') result = { job_id: 'detail-export-1', created: true };
    else if (path === '/api/jobs/detail-export-1') result = { id: 'detail-export-1', kind: 'export', status: 'succeeded', params: {}, steps: [] };
    else if (path === '/api/jobs/export-1' || path === '/api/jobs/export-1/process') { if (path.endsWith('/process')) processed.add('export-1'); result = { id: 'export-1', kind: 'export', status: requestMode && !processed.has('export-1') ? 'queued' : 'succeeded', dataset_id: 'dataset-1', params, steps: [] }; }
    else if (path === '/api/google/check') result = { created: true, job_id: 'check-1' };
    else if (path === '/api/jobs/check-1') result = { id: 'check-1', kind: 'connection', status: 'succeeded', params: { start: '2026-09-01', end: '2026-09-07' }, created_at: '2026-09-08T00:00:00Z', finished_at: '2026-09-08T00:01:00Z', steps: [] };
    else if (path === '/api/google/connect') result = { url: 'https://accounts.google.com/test-auth' };
    else if (path === '/api/meta/connect') {
      if (metaConnectError) { status = metaConnectError.status; result = { error: metaConnectError.message }; }
      else result = { url: '#meta-test-authorization' };
    }
    else if (path === '/api/meta' && options.method === 'DELETE') {
      metaStatus = { configured: true, connected: false, has_connection: false, status: 'disconnected' };
      result = { revoked_at_provider: metaRevoked, message: metaRevoked ? 'Đã ngắt kết nối Meta.' : 'Đã xóa kết nối tại ứng dụng. Meta chưa xác nhận thu hồi.' };
    }
    else if (path === '/api/meta') {
      if (metaReadError) { status = metaReadError.status; result = { error: metaReadError.message }; }
      else result = metaStatus;
    }
    else if (path === '/api/google' && options.method === 'DELETE') { providerConnected = false; result = { message: 'Đã ngắt kết nối Google.' }; }
    else if (path === '/api/google') result = { configured: googleConfigured, connected: providerConnected, email: providerConnected ? 'connected@example.test' : null, connected_at: providerConnected ? '2026-09-01T00:00:00Z' : null, checked_at: null, sources: googleSources, assets: { ga4: 'property-config', gsc: 'property-url', keywords: 'sheet-config' } };
    else if (path === '/api/jobs') result = jobs;
    else if (path === '/api/reports') result = reports;
    else if (path === '/api/report-bundles' && options.method === 'POST') {
      if (reportBundleError) { status = reportBundleError.status; result = { error: reportBundleError.message }; }
      else { createdBundlePayload = body; currentBundlePayload = body; capturedSections = captureSections(body.sections); result = reportBundleResult; }
    }
    else if (path.startsWith('/api/report-bundles/') && options.method === 'GET') {
      const payload = currentBundlePayload || createdBundlePayload;
      result = reportBundleDetail || {
        report: { id: reportBundleResult.report_id, revision: reportBundleResult.revision, status: reportBundleResult.status, name: payload?.name },
        client: { id: 'client_kinderhealth', name: 'KinderHealth' },
        period: { start: payload?.start_date, end: payload?.end_date },
        comparison: payload?.compare_start_date ? { start: payload.compare_start_date, end: payload.compare_end_date } : null,
        freshness: { generated_at: '2026-10-01T07:00:00Z' },
        quality: { status: 'unknown', warnings: [] },
        navigation: { default_section: payload?.default_section || 'overview', sections: payload?.sections?.map(section => section.key) || ['overview'] },
        sections: capturedSections
      };
      if (reportBundleReadError?.status) { status = reportBundleReadError.status; result = { error: reportBundleReadError.message }; }
    }
    else if (path.startsWith('/api/report-bundles/') && options.method === 'PATCH') {
      if (reportBundleUpdateError) { status = reportBundleUpdateError.status; result = { error: reportBundleUpdateError.message }; }
      else { currentBundlePayload = body; capturedSections = captureSections(body.sections); result = reportBundleUpdateResult; }
    }
    else if (path === '/api/events' || path === '/api/schedules') result = [];
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
    assert.equal(h.document.querySelectorAll('.overview-stat').length, 4);
    assert.equal(h.document.querySelectorAll('.overview-dashboard-card').length, 2);
    assert.equal(h.document.querySelector('.overview-demo-banner')?.querySelector('.demo-metrics'), null);
    assert.match(h.document.querySelector('.overview-page').textContent, /Chưa có dữ liệu xu hướng/);
    for (const route of ['#analysis', '#activity', '#reports', '#connections', '#uploads']) {
      assert.ok(h.document.querySelector(`.overview-page a[href="${route}"]`), `missing overview action ${route}`);
    }
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
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan');
    assert.equal(h.requests.filter(r => r.path === '/api/auth/login').length, 1);
    assert.match(h.document.body.textContent, /Chưa kết nối Google/);
    assert.ok(h.document.querySelector('.overview-page'));
    for (const route of ['#analysis', '#connections', '#activity', '#uploads', '#reports']) {
      assert.ok(h.document.querySelector(`.overview-page a[href="${route}"]`), `missing overview link ${route}`);
    }
    assert.equal(h.document.querySelectorAll('.nav-link').length, 13);
    assert.equal(h.w.localStorage.length, 0);
    h.document.querySelector('[data-action="check-google"]').click();
    await h.until(() => h.requests.some(r => r.path === '/api/google/check'));
    await h.until(() => h.document.querySelector('#toasts').textContent.includes('Các nguồn đã được kiểm tra.'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('First-admin setup, password visibility, recovery modal, and logout remain available', async () => {
  const h = await harness({ signedIn: false, setupRequired: true }); try {
    const setupForm = h.document.querySelector('#auth-form');
    assert.equal(setupForm.dataset.setup, 'true');
    assert.ok(setupForm.querySelector('#auth-name[name="name"]'));
    assert.ok(setupForm.querySelector('#auth-email[name="email"]'));
    assert.equal(setupForm.querySelector('#auth-password[name="password"]').minLength, 12);
    assert.equal(setupForm.querySelector('[data-action="forgot"]'), null);

    const password = setupForm.querySelector('#auth-password');
    const togglePassword = setupForm.querySelector('[data-action="toggle-password"]');
    togglePassword.click();
    assert.equal(password.type, 'text');
    await h.until(() => !togglePassword.disabled);
    togglePassword.click();
    await h.until(() => !togglePassword.disabled);
    assert.equal(password.type, 'password');

    setupForm.querySelector('#auth-name').value = 'Admin kiểm thử';
    setupForm.querySelector('#auth-email').value = 'admin@example.test';
    password.value = 'test-only-password';
    setupForm.requestSubmit();
    await h.until(() => h.document.querySelector('#auth-form')?.dataset.setup === 'false');
    assert.deepEqual(h.requests.find(r => r.path === '/api/auth/setup').body, {
      name: 'Admin kiểm thử', email: 'admin@example.test', password: 'test-only-password'
    });

    h.document.querySelector('[data-action="forgot"]').click();
    await h.until(() => h.document.querySelector('#modal').open);
    assert.match(h.document.querySelector('#modal').textContent, /Khôi phục mật khẩu/);
    h.document.querySelector('[data-action="close-modal"]').click();
    assert.equal(h.document.querySelector('#modal').open, false);

    h.document.querySelector('#auth-email').value = 'admin@example.test';
    h.document.querySelector('#auth-password').value = 'test-only-password';
    h.document.querySelector('#auth-form').requestSubmit();
    await h.until(() => h.document.querySelector('.overview-page'));
    h.document.querySelector('[data-action="logout"]').click();
    await h.until(() => h.document.querySelector('#auth-form'));
    assert.equal(h.requests.filter(r => r.path === '/api/auth/logout').length, 1);
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

test('Schedules describe worker operation without a fixed daily cloud window', async () => {
  for (const requestMode of [false, true]) {
    const h = await harness({ requestMode }); try {
      h.w.location.hash = 'schedules';
      await h.until(() => h.document.querySelector('[data-action=new-schedule]'));
      const text = h.document.body.textContent;
      assert.doesNotMatch(text, /07:00–08:00/);
      assert.match(text, requestMode ? /tần suất gọi/ : /Nếu máy chủ tắt/);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  }
});

test('Request mode processes queued analysis and export through authenticated POST requests', async () => {
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

test('Analysis quality workspace preserves controls and summarizes only real Dataset source metadata', async () => {
  const dataset = {
    id: 'dataset-1',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false, exclude_products: true, demo: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: false,
    sources: {
      ga4: { source: 'ga4', status: 'ready', latest_available_date: '2026-09-27', fetched_at: '2026-09-29T06:00:00Z', last_success_at: '2026-09-28T06:00:00Z', warnings: [], daily: [], totals: { sessions: 22 } },
      gsc: { source: 'gsc', status: 'permission_denied', latest_available_date: null, fetched_at: '2026-09-29T06:01:00Z', error: 'Thiếu quyền Search Console', warnings: ['API chưa được bật.'], daily: [], queries: [] }
    }
  };
  const h = await harness({ dataset }); try {
    h.w.location.hash = 'analysis?dataset=dataset-1';
    await h.until(() => h.document.querySelector('#analysis-results .analysis-quality-card'));
    assert.equal(h.document.querySelector('.analysis-page h1').textContent, 'Phân tích & kiểm tra');
    for (const id of ['analysis-form', 'comparison-period', 'dirty-note', 'applied-period', 'export-button', 'job-progress', 'analysis-results', 'save-report-button']) {
      if (id === 'save-report-button') assert.equal(h.document.querySelector(`#${id}`), null);
      else assert.ok(h.document.querySelector(`#${id}`), `missing #${id}`);
    }
    for (const name of ['report_type', 'start', 'end', 'compare', 'exclude_products']) {
      assert.ok(h.document.querySelector(`#analysis-form [name="${name}"]`), `missing ${name}`);
    }
    assert.match(h.document.querySelector('.analysis-quality-metrics').textContent, /1 \/ 2/);
    assert.match(h.document.querySelector('.analysis-quality-metrics').textContent, /Nguồn cần chú ý\s*1/);
    assert.match(h.document.querySelector('.analysis-quality-metrics').textContent, /01\/09\/2026\s*–\s*28\/09\/2026/);
    assert.match(h.document.querySelector('.analysis-quality-metrics').textContent, /dataset-1/);
    assert.equal(h.document.querySelectorAll('.analysis-source-card').length, 2);
    assert.match(h.document.querySelector('.analysis-source-status-grid').textContent, /27\/09\/2026/);
    assert.match(h.document.querySelector('#analysis-results').textContent, /Thiếu quyền Search Console/);
    assert.match(h.document.querySelector('#analysis-results').textContent, /API chưa được bật/);
    assert.match(h.document.querySelector('#analysis-results').textContent, /Chưa có dữ liệu xu hướng/);
    assert.doesNotMatch(h.document.querySelector('#analysis-results').textContent, /98%/);
    h.document.querySelector('[data-action="analysis-tab"][data-tab="gsc"]').click();
    assert.equal(h.document.querySelector('#analysis-results .source-section').querySelector('h2').textContent, 'Search Console');
    assert.equal(h.document.querySelectorAll('#analysis-results .source-section').length, 1);
    const gscMetadata = h.document.querySelector('#analysis-results .source-section .section-title small');
    assert.match(gscMetadata.textContent, /Lấy lúc/);
    assert.doesNotMatch(gscMetadata.textContent, /Chưa có|Dữ liệu đến/);

    const reportType = h.document.querySelector('[name="report_type"]');
    reportType.value = 'gmb';
    reportType.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    assert.ok(h.document.querySelector('#filter-upload_id'));
    assert.ok(h.document.querySelector('[name="upload_id"]'));
    const compare = h.document.querySelector('[name="compare"]');
    compare.checked = true;
    compare.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    assert.ok(h.document.querySelector('#filter-previous_upload_id'));
    assert.ok(h.document.querySelector('[name="previous_upload_id"]'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Analysis save action still saves the current valid Dataset snapshot', async () => {
  const dataset = {
    id: 'dataset-1',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false, exclude_products: false, demo: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: { ga4: { source: 'ga4', status: 'ready', latest_available_date: '2026-09-28', fetched_at: '2026-09-29T06:00:00Z', warnings: [], daily: [], totals: { sessions: 22 } } }
  };
  const h = await harness({ dataset }); try {
    h.w.location.hash = 'analysis?dataset=dataset-1';
    await h.until(() => h.document.querySelector('#save-report-button'));
    h.document.querySelector('#save-report-button').click();
    await h.until(() => h.w.location.hash === '#reports');
    assert.deepEqual(h.requests.find(r => r.path === '/api/datasets/dataset-1/save'), {
      path: '/api/datasets/dataset-1/save', method: 'POST', body: {}
    });
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Analysis presets, comparison, GSC exclusion, and progress continue using the existing analysis flow', async () => {
  const h = await harness(); try {
    h.w.location.hash = 'analysis';
    await h.until(() => h.document.querySelector('#analysis-form'));
    h.document.querySelector('[data-action="preset"][data-value="last7"]').click();
    assert.ok(h.document.querySelector('[name="start"]').value);
    assert.ok(h.document.querySelector('[name="end"]').value);

    h.document.querySelector('[name="start"]').value = '2026-09-01';
    h.document.querySelector('[name="end"]').value = '2026-09-28';
    const compare = h.document.querySelector('[name="compare"]');
    compare.checked = true;
    compare.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    const exclude = h.document.querySelector('[name="exclude_products"]');
    exclude.checked = true;
    exclude.dispatchEvent(new h.w.Event('change', { bubbles: true }));

    const releaseJob = h.hold('/api/jobs/job-1');
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.document.querySelector('#job-progress .progress-card'));
    const request = h.requests.find(r => r.path === '/api/analyses');
    assert.equal(request.body.compare, true);
    assert.equal(request.body.exclude_products, true);
    assert.equal(request.body.start, '2026-09-01');
    assert.equal(request.body.end, '2026-09-28');
    assert.match(h.document.querySelector('#comparison-period').textContent, /Kỳ so sánh dự kiến/);
    releaseJob();
    await h.until(() => h.document.querySelector('#export-button')?.disabled === false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('GMB analysis retains upload selection and submits through the existing analysis endpoint', async () => {
  const uploads = [{ id: 'gmb-upload-1', name: 'gmb-september.csv', start_date: '2026-09-01', end_date: '2026-09-28', locations: 1, demo: false }];
  const h = await harness({ uploads }); try {
    h.w.location.hash = 'analysis';
    await h.until(() => h.document.querySelector('#analysis-form'));
    const reportType = h.document.querySelector('[name="report_type"]');
    reportType.value = 'gmb';
    reportType.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    assert.ok(h.document.querySelector('[name="upload_id"]'));
    assert.equal(h.document.querySelector('[name="previous_upload_id"]'), null);
    h.document.querySelector('[name="start"]').value = '2026-09-01';
    h.document.querySelector('[name="end"]').value = '2026-09-28';
    const upload = h.document.querySelector('[name="upload_id"]');
    upload.value = 'gmb-upload-1';
    upload.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    h.document.querySelector('#analysis-form').requestSubmit();
    await h.until(() => h.requests.some(r => r.path === '/api/analyses'));
    assert.deepEqual(h.requests.find(r => r.path === '/api/analyses').body, {
      report_type: 'gmb',
      start: '2026-09-01',
      end: '2026-09-28',
      compare: false,
      demo: false,
      exclude_products: false,
      upload_id: 'gmb-upload-1',
      previous_upload_id: ''
    });
    await h.until(() => h.document.querySelector('#export-button')?.disabled === false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Primary navigation is complete and provider routes remain reachable without permanent subnavigation', async () => {
  const h = await harness(); try {
    const expectedRoutes = ['overview', 'clients', 'connections', 'assets', 'sync', 'analysis', 'datasets', 'report-builder', 'reports', 'activity', 'schedules', 'users', 'settings'];
    assert.deepEqual(Array.from(h.document.querySelectorAll('#sidebar .nav-link'), link => link.getAttribute('href').slice(1)), expectedRoutes);
    assert.equal(h.document.querySelectorAll('#sidebar .nav-sub-link').length, 0);
    for (const page of ['reports', 'connections', 'activity', 'schedules', 'users', 'settings']) {
      h.w.location.hash = page; await h.until(() => h.document.querySelector(`[href="#${page}"]`)?.classList.contains('active') && h.document.querySelector('#content h1'));
      assert.doesNotMatch(h.document.querySelector('#content').textContent, /Không thể hiển thị màn hình/);
      if (page === 'connections') { assert.match(h.document.querySelector('.nav-link[href="#connections"]').textContent, /Kết nối nền tảng/); assert.equal(h.document.querySelectorAll('.connection-source').length, 7); assert.match(h.document.querySelector('#content').textContent, /Meta[\s\S]*Chưa tích hợp/); assert.match(h.document.querySelector('#content').textContent, /YouTube[\s\S]*Chưa tích hợp/); assert.ok(h.document.querySelector('#content a[href="#connections/facebook"]')); assert.ok(h.document.querySelector('#content a[href="#connections/tiktok"]')); }
    }
    h.w.location.hash = 'connections/google'; await h.until(() => h.document.querySelector('.breadcrumb strong')?.textContent.includes('Google') && h.document.querySelector('[data-action="connect-google"]'));
    assert.ok(h.document.querySelector('.nav-link[href="#connections"].active'));
    assert.equal(h.document.querySelector('[data-action=connect-google]').disabled, true); assert.match(h.document.querySelector('#content').textContent, /Chưa cấu hình Google OAuth/);
    h.w.location.hash = 'connections/facebook'; await h.until(() => h.document.querySelector('#content h1')?.textContent.includes('Facebook'));
    assert.match(h.document.querySelector('#content').textContent, /Chưa cấu hình Meta OAuth/); assert.equal(h.document.querySelector('#content button[disabled]').textContent, 'Kết nối Meta');
    h.w.location.hash = 'connections/tiktok'; await h.until(() => h.document.querySelector('#content h1')?.textContent.includes('TikTok'));
    assert.match(h.document.querySelector('#content').textContent, /TikTok API chưa được tích hợp ở backend/); assert.equal(h.document.querySelector('#content button[disabled]').textContent, 'Kết nối TikTok'); assert.ok(h.document.querySelector('a[href="https://business-api.tiktok.com/portal/docs"]'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
  const viewer = await harness({ role: 'viewer' }); try {
    assert.equal(viewer.document.querySelector('.nav-link[href="#connections"]'), null);
    assert.equal(viewer.document.querySelector('.nav-link[href="#assets"]'), null);
    assert.equal(viewer.document.querySelector('.nav-link[href="#users"]'), null);
    assert.equal(viewer.document.querySelector('.nav-link[href="#report-builder"]'), null);
    viewer.w.location.hash = 'users'; await viewer.until(() => viewer.document.body.textContent.includes('Màn hình này chỉ dành cho quản trị viên.'));
    assert.equal(viewer.requests.some(r => r.path === '/api/users'), false);
  } finally { viewer.close(); }
});

test('Dataset and Report Builder routes show safe empty states without API calls', async () => {
  const h = await harness(); try {
    const before = h.requests.map(request => request.path);
    h.w.location.hash = 'datasets';
    await h.until(() => h.document.querySelector('.nav-link[href="#datasets"].active') && h.document.querySelector('#content h1'));
    assert.match(h.document.querySelector('#content').textContent, /Chưa có Dataset/);
    assert.match(h.document.querySelector('#content').textContent, /Dataset sẽ xuất hiện sau khi hoàn tất một lần phân tích dữ liệu/);
    assert.equal(h.document.querySelector('.datasets-page a[href="#analysis"]')?.textContent.includes('Tạo Dataset từ phân tích'), true);
    assert.deepEqual(h.requests.filter(request => ['/api/jobs', '/api/reports'].includes(request.path)).sort(), ['/api/jobs', '/api/reports'].map(path => ({ path, method: 'GET', body: undefined })).sort());
    assert.equal(h.requests.some(request => request.path === '/api/datasets' || request.path.startsWith('/api/datasets/')), false);
    h.w.location.hash = 'report-builder';
    await h.until(() => h.document.querySelector('.nav-link[href="#report-builder"].active') && h.document.querySelector('#report-builder-form'));
    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Thông tin báo cáo');
    assert.equal(h.document.querySelector('.report-builder-stepper li.active > span').textContent.trim(), '1');
    h.document.querySelector('[name="name"]').value = 'Empty-state test';
    h.document.querySelector('[data-action="report-builder-next"]').click();
    await h.until(() => h.document.querySelector('.report-builder-empty'));
    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Chọn Dataset');
    assert.equal(h.document.querySelector('.report-builder-stepper li.complete strong').textContent, 'Thông tin báo cáo');
    assert.match(h.document.querySelector('#content').textContent, /Chưa có Dataset/);
    assert.equal(h.requests.slice(before.length).some(request => request.path === '/api/datasets' || request.path.startsWith('/api/datasets/')), false);
    assert.equal(h.requests.some(request => request.path === '/api/report-bundles'), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Dataset list uses unique IDs from real jobs and reports and filters loaded details locally', async () => {
  const jobs = [
    { id: 'job-alpha', kind: 'analysis', status: 'succeeded', dataset_id: 'dataset-alpha', params: { report_type: 'seo' }, created_at: '2026-10-04T12:00:00Z' },
    { id: 'job-beta', kind: 'analysis', status: 'partial', dataset_id: 'dataset-beta', params: { report_type: 'gmb' }, created_at: '2026-10-03T12:00:00Z' },
    { id: 'job-alpha-repeat', kind: 'export', status: 'succeeded', dataset_id: 'dataset-alpha', params: { report_type: 'seo' }, created_at: '2026-10-05T12:00:00Z' },
    { id: 'job-no-dataset', kind: 'analysis', status: 'failed', dataset_id: null, params: { report_type: 'seo' }, created_at: '2026-10-06T12:00:00Z' }
  ];
  const reports = [
    { id: 'report-alpha', dataset_id: 'dataset-alpha', report_type: 'seo', created_at: '2026-10-05T13:00:00Z' },
    { id: 'report-beta', dataset_id: 'dataset-beta', report_type: 'gmb', created_at: '2026-10-04T13:00:00Z' },
    { id: 'legacy-report', dataset_id: null, report_type: 'seo', created_at: '2026-10-02T13:00:00Z' }
  ];
  const datasetRecords = {
    'dataset-alpha': {
      id: 'dataset-alpha', params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28' },
      created_at: '2026-10-04T12:00:00Z', exportable: true, sources: { ga4: {}, gsc: {} }
    },
    'dataset-beta': {
      id: 'dataset-beta', params: { report_type: 'gmb', start: '2026-09-10', end: '2026-09-30' },
      created_at: '2026-10-03T12:00:00Z', exportable: false, sources: { gmb: {} }
    }
  };
  const h = await harness({ jobs, reports, datasetRecords }); try {
    h.w.location.hash = 'datasets';
    await h.until(() => h.document.querySelector('#datasets-table-region .datasets-table') || h.document.querySelector('#datasets-table-region table'));
    assert.equal(h.requests.filter(request => request.path === '/api/jobs').length, 1);
    assert.equal(h.requests.filter(request => request.path === '/api/reports').length, 1);
    assert.equal(h.requests.filter(request => request.path === '/api/datasets/dataset-alpha').length, 1);
    assert.equal(h.requests.filter(request => request.path === '/api/datasets/dataset-beta').length, 1);
    assert.equal(h.requests.some(request => request.path === '/api/datasets'), false);
    const table = h.document.querySelector('#datasets-table-region table');
    assert.equal(table.querySelectorAll('tbody tr').length, 2);
    assert.match(table.textContent, /dataset-alpha/);
    assert.match(table.textContent, /dataset-beta/);
    assert.match(table.textContent, /Website Traffic & SEO/);
    assert.match(table.textContent, /Google Business Profile/);
    assert.match(table.textContent, /Google Analytics 4, Search Console/);
    assert.match(table.textContent, /Hợp lệ/);
    assert.match(table.textContent, /Cần kiểm tra/);
    assert.ok(table.querySelector('a[href="#datasets/dataset-alpha"]'));
    assert.ok(table.querySelector('a[href="#analysis?dataset=dataset-alpha"]'));
    assert.equal(h.document.querySelector('.datasets-summary article:first-child strong').textContent, '2');
    assert.match(h.document.querySelector('.datasets-discovery-note').textContent, /tối đa 50/);

    h.document.querySelector('[name="status"]').value = 'valid';
    h.document.querySelector('[name="status"]').dispatchEvent(new h.w.Event('change', { bubbles: true }));
    assert.equal(h.document.querySelector('#datasets-table-region table tbody tr').textContent.includes('dataset-alpha'), true);
    assert.equal(h.document.querySelectorAll('#datasets-table-region table tbody tr').length, 1);
    h.document.querySelector('[name="query"]').value = 'beta';
    h.document.querySelector('[name="query"]').dispatchEvent(new h.w.Event('input', { bubbles: true }));
    assert.equal(h.document.querySelectorAll('#datasets-table-region table tbody tr').length, 0);
    assert.match(h.document.querySelector('#datasets-table-region').textContent, /Không có Dataset phù hợp/);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Dataset detail fetches and displays the real snapshot read-only with source tabs and compatible links', async () => {
  const record = {
    id: 'dataset-detail-42',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: true, previous_start: '2026-08-04', previous_end: '2026-08-31', exclude_products: true, demo: false, upload_id: 'upload-42' },
    created_at: '2026-09-29T07:00:00+00:00',
    exportable: true,
    sources: {
      ga4: { source: 'ga4', status: 'ready', latest_available_date: '2026-09-27', fetched_at: '2026-09-29T06:00:00+00:00', last_success_at: '2026-09-28T06:00:00+00:00', asset: 'property-42', timezone: 'Asia/Ho_Chi_Minh', warnings: [], daily: [{ date: '2026-09-27', sessions: 14 }], channels: [], pages: [] },
      gsc: { source: 'gsc', status: 'permission_denied', fetched_at: '2026-09-29T06:01:00+00:00', error: 'Thiếu quyền Search Console', warnings: ['Cần cấp quyền đọc dữ liệu'], daily: [], queries: [{ query: 'KinderHealth', clicks: 2 }] }
    }
  };
  const h = await harness({ datasetRecords: { 'dataset-detail-42': record } }); try {
    h.w.location.hash = 'datasets/dataset-detail-42';
    await h.until(() => h.document.querySelector('.dataset-detail-page .dataset-detail-identity'));
    assert.equal(h.requests.filter(request => request.path === '/api/datasets/dataset-detail-42').length, 1);
    const content = h.document.querySelector('#content');
    assert.match(content.textContent, /dataset-detail-42/);
    assert.match(content.textContent, /Website Traffic & SEO/);
    assert.match(content.textContent, /01\/09\/2026/);
    assert.match(content.textContent, /14:00 29\/9\/26/);
    assert.match(content.textContent, /Nguồn sẵn sàng\s*1 \/ 2/);
    assert.match(content.textContent, /Thiếu quyền Search Console/);
    assert.match(content.textContent, /Cần cấp quyền đọc dữ liệu/);
    assert.match(content.textContent, /Chưa có thông tin schema riêng cho Dataset này/);
    assert.match(content.textContent, /Các trường quan sát được trong dữ liệu/);
    assert.match(content.textContent, /sessions/);
    assert.match(content.textContent, /Dòng dữ liệu[\s\S]*Phân tích[\s\S]*Dataset snapshot/);
    assert.ok(content.querySelector('a[href="#analysis?dataset=dataset-detail-42"]'));
    assert.ok(content.querySelector('[data-action="dataset-detail-export"]'));
    assert.ok(content.querySelector('a[href="#datasets"]'));
    assert.doesNotMatch(content.textContent, /Chỉnh sửa|Xóa Dataset|Làm mới ngay/);
    assert.equal(content.querySelectorAll('[data-action="dataset-detail-tab"]').length, 3);
    content.querySelector('[data-action="dataset-detail-tab"][data-tab="gsc"]').click();
    await h.until(() => h.document.querySelector('#content .source-section h2')?.textContent === 'Search Console');
    assert.match(h.document.querySelector('#content .source-section').textContent, /Truy vấn tìm kiếm/);
    content.querySelector('[data-action="dataset-detail-export"]').click();
    await h.until(() => h.document.querySelector('#modal [data-action="export-confirm"]'));
    h.document.querySelector('#modal [data-action="export-confirm"]').click();
    await h.until(() => h.document.querySelector('#modal a[href="/api/jobs/detail-export-1/download"]'));
    assert.equal(h.requests.filter(request => request.path === '/api/datasets/dataset-detail-42/export').length, 1);
    h.document.querySelector('#modal [data-action="close-modal"]').click();
    content.querySelector('a[href="#analysis?dataset=dataset-detail-42"]').click();
    await h.until(() => h.document.querySelector('#analysis-form'));
    assert.ok(h.requests.filter(request => request.path === '/api/datasets/dataset-detail-42').length >= 2);
    assert.equal(h.document.querySelector('#analysis-form [name="report_type"]').value, 'seo');
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Dataset detail handles 404 safely and preserves permission errors', async () => {
  const notFound = await harness(); try {
    notFound.w.location.hash = 'datasets/missing-dataset';
    await notFound.until(() => notFound.document.querySelector('.dataset-detail-not-found'));
    assert.match(notFound.document.querySelector('.dataset-detail-not-found').textContent, /Không tìm thấy Dataset/);
    assert.ok(notFound.document.querySelector('.dataset-detail-not-found a[href="#datasets"]'));
    assert.equal(notFound.requests.filter(request => request.path === '/api/datasets/missing-dataset').length, 1);
    assert.deepEqual(notFound.errors, []);
  } finally { notFound.close(); }

  const forbidden = await harness({ datasetErrors: { forbidden: { status: 403, message: 'Không có quyền xem Dataset này.' } } }); try {
    forbidden.w.location.hash = 'datasets/forbidden';
    await forbidden.until(() => forbidden.document.querySelector('#content .empty h3')?.textContent === 'Không thể hiển thị màn hình');
    assert.match(forbidden.document.querySelector('#content').textContent, /Không có quyền xem Dataset này/);
    assert.doesNotMatch(forbidden.document.querySelector('#content').textContent, /Không tìm thấy Dataset/);
    assert.deepEqual(forbidden.errors, []);
  } finally { forbidden.close(); }
});

test('Non-exportable Dataset explains validation state and hides Excel action', async () => {
  const record = {
    id: 'dataset-review',
    params: { report_type: 'gmb', start: '2026-09-01', end: '2026-09-28' },
    exportable: false,
    sources: { gmb: { source: 'gmb', status: 'delayed', warnings: ['Dữ liệu cập nhật chưa đầy đủ.'], entries: [] } }
  };
  const h = await harness({ datasetRecords: { 'dataset-review': record } }); try {
    h.w.location.hash = 'datasets/dataset-review';
    await h.until(() => h.document.querySelector('.dataset-detail-page .dataset-detail-quality'));
    const content = h.document.querySelector('#content');
    assert.match(content.textContent, /chưa đủ điều kiện xuất Excel hoặc lưu báo cáo/);
    assert.match(content.textContent, /Dữ liệu có độ trễ/);
    assert.match(content.textContent, /Dữ liệu cập nhật chưa đầy đủ/);
    assert.equal(content.querySelector('[data-action="dataset-detail-export"]'), null);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Clients, assets, and sync routes render without invented API calls or records', async () => {
  const jobs = [{ id: 'sync-1', kind: 'connection', status: 'succeeded', params: { start: '2026-09-01', end: '2026-09-07' }, created_at: '2026-09-08T00:00:00Z', finished_at: '2026-09-08T00:01:00Z', actor: 'Test operator' }];
  const h = await harness({ jobs }); try {
    h.w.location.hash = 'clients';
    await h.until(() => h.document.querySelector('.nav-link[href="#clients"].active') && h.document.querySelector('.clients-table'));
    assert.match(h.document.querySelector('#content').textContent, /Chưa có khách hàng/);
    assert.equal(h.document.querySelector('.clients-workspace .clients-detail').hidden, false);
    assert.match(h.document.querySelector('.clients-detail').textContent, /Chọn khách hàng để xem chi tiết/);
    assert.equal(h.document.querySelector('.clients-toolbar input').disabled, true);
    assert.equal(h.document.querySelector('.page-heading .btn.primary').disabled, true);
    assert.match(h.document.querySelector('.page-heading .btn.primary').textContent, /Chưa khả dụng/);
    assert.equal(h.document.querySelector('.clients-table tbody tr td[colspan="8"]') !== null, true);
    assert.deepEqual(Array.from(h.document.querySelectorAll('.clients-table thead th'), cell => cell.textContent.trim()), ['#', 'Khách hàng', 'Domain', 'Ngành', 'Người phụ trách', 'Trạng thái kết nối', 'Ngày tạo', 'Thao tác']);
    assert.equal(h.requests.some(r => r.path === '/api/clients'), false);
    h.document.querySelector('[data-action="menu"]').click();
    await h.until(() => h.document.querySelector('#sidebar').classList.contains('open'));
    h.document.querySelector('[data-action="menu"]').click();
    await h.until(() => !h.document.querySelector('#sidebar').classList.contains('open'));

    h.w.location.hash = 'assets';
    await h.until(() => h.document.querySelector('.nav-link[href="#assets"].active') && h.document.querySelector('.assets-table'));
    assert.match(h.document.querySelector('#content').textContent, /property-config/);
    assert.match(h.document.querySelector('#content').textContent, /property-url/);
    assert.match(h.document.querySelector('#content').textContent, /sheet-config/);
    assert.equal(h.document.querySelectorAll('.assets-stats .assets-stat').length, 4);
    assert.match(h.document.querySelector('.assets-stats').textContent, /3/);
    assert.match(h.document.querySelector('.assets-table').textContent, /Google Analytics 4 property/);
    assert.doesNotMatch(h.document.querySelector('.assets-table').textContent, /Meta Ad Account|TikTok Advertiser|Facebook Page/);
    assert.equal(h.requests.filter(r => r.path === '/api/google').length, 1);
    assert.equal(h.requests.some(r => r.path === '/api/assets'), false);

    h.w.location.hash = 'sync';
    await h.until(() => h.document.querySelector('.nav-link[href="#sync"].active') && h.document.querySelector('.sync-history'));
    assert.match(h.document.querySelector('.sync-history').textContent, /Test operator/);
    assert.match(h.document.querySelector('.sync-history').textContent, /Thành công/);
    assert.equal(h.requests.filter(r => r.path === '/api/jobs').length, 1);
    assert.equal(h.requests.filter(r => r.path === '/api/google').length, 2);
    assert.equal(h.requests.some(r => r.path === '/api/sync'), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Permission-denied Google source status is consistent across connections, assets, and sync', async () => {
  const googleSources = { ga4: { status: 'permission_denied', error: 'Thiếu quyền đọc GA4' } };
  const h = await harness({ googleConfigured: true, googleConnected: true, googleSources }); try {
    h.w.location.hash = 'connections/google';
    await h.until(() => h.document.querySelector('.connection-source'));
    assert.match(h.document.querySelector('.connection-source').textContent, /Thiếu quyền/);
    assert.match(h.document.querySelector('.connection-summary').textContent, /0 \/ 1/);
    assert.match(h.document.querySelector('.connection-summary').textContent, /1/);
    assert.match(h.document.querySelector('.connection-google').textContent, /connected@example\.test/);

    h.w.location.hash = 'assets';
    await h.until(() => h.document.querySelector('.assets-table'));
    const assetStatus = h.document.querySelector('.assets-table tbody tr .badge');
    assert.equal(assetStatus.textContent.trim(), 'Thiếu quyền');

    h.w.location.hash = 'sync';
    await h.until(() => h.document.querySelector('.sync-sources tbody tr .badge'));
    const syncStatus = h.document.querySelector('.sync-sources tbody tr .badge');
    assert.equal(syncStatus.textContent.trim(), 'Thiếu quyền');
    assert.equal(syncStatus.className, assetStatus.className);
    assert.equal(h.requests.some(r => r.path === '/api/google'), true);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Google connection checks and disconnect use the existing routes and actions', async () => {
  const h = await harness({
    googleConfigured: true,
    googleConnected: true,
    googleSources: { ga4: { status: 'ready', latest_available_date: '2026-09-07', fetched_at: '2026-09-08T00:00:00Z' } }
  }); try {
    h.w.location.hash = 'connections/google';
    await h.until(() => h.document.querySelector('[data-action="disconnect-google"]'));
    assert.match(h.document.querySelector('#content').textContent, /connected@example\.test/);
    assert.match(h.document.querySelector('#content').textContent, /Sẵn sàng/);
    assert.ok(h.document.querySelector('[data-action="connect-google"]'));
    h.document.querySelector('[data-action="check-google"]').click();
    await h.until(() => h.requests.some(r => r.path === '/api/google/check'));
    await h.until(() => h.document.querySelector('#toasts').textContent.includes('Các nguồn đã được kiểm tra.'));
    h.document.querySelector('[data-action="disconnect-google"]').click();
    await h.until(() => h.document.querySelector('#modal').open);
    h.document.querySelector('[data-action="disconnect-confirm"]').click();
    await h.until(() => h.document.querySelector('#content').textContent.includes('Chưa kết nối Google'));
    assert.ok(h.requests.some(r => r.path === '/api/google' && r.method === 'DELETE'));
    assert.ok(h.requests.some(r => r.path === '/api/google/check' && r.method === 'POST'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Meta connection shows persisted identity and revokes through its own API only', async () => {
  const h = await harness({ metaStatus: { configured: true, connected: true, has_connection: true, status: 'connected', account_id: 'meta-user-test', account_name: '<img src=x onerror=alert(1)>', connected_at: '2026-09-01T00:00:00Z', expires_at: '2026-11-01T00:00:00Z', scopes: ['public_profile'] }, metaRevoked: false });
  try {
    const before = h.requests.length;
    h.w.location.hash = 'connections/facebook';
    await h.until(() => h.document.querySelector('[data-action="disconnect-meta"]'));
    const content = h.document.querySelector('#content');
    assert.match(content.textContent, /meta-user-test/);
    assert.match(content.textContent, /<img src=x onerror=alert\(1\)>/);
    assert.equal(content.querySelector('img'), null);
    assert.match(content.textContent, /Đã kết nối OAuth/);
    assert.match(content.textContent, /public_profile/);
    assert.match(content.textContent, /Đã xác thực Meta. Chưa chọn tài sản dữ liệu/);
    assert.match(content.textContent, /Chưa khám phá tài sản hoặc đồng bộ/);
    assert.equal(h.document.querySelector('[data-action="connect-facebook"]').disabled, false);
    h.document.querySelector('[data-action="disconnect-meta"]').click();
    assert.ok(h.document.querySelector('#modal').open);
    h.document.querySelector('[data-action="disconnect-meta-confirm"]').click();
    await h.until(() => !h.document.querySelector('[data-action="disconnect-meta"]'));
    assert.match(h.document.querySelector('#toasts').textContent, /Meta chưa xác nhận thu hồi/);
    assert.match(h.document.querySelector('.connection-meta').textContent, /Chưa kết nối/);
    assert.deepEqual(h.requests.slice(before).map(r => [r.method, r.path]), [['GET', '/api/meta'], ['DELETE', '/api/meta'], ['GET', '/api/meta']]);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Meta card exposes connect before authentication without fabricating assets', async () => {
  const h = await harness({ metaStatus: { configured: true, connected: false, has_connection: false, status: 'disconnected' } });
  try {
    h.w.location.hash = 'connections';
    await h.until(() => h.document.querySelector('.connection-meta'));
    const card = h.document.querySelector('.connection-meta');
    assert.match(card.textContent, /Facebook Content · Facebook Ads/);
    assert.match(card.textContent, /Chưa kết nối/);
    assert.doesNotMatch(card.textContent, /Đã xác thực Meta|Facebook Page|Ad Account|Lần đồng bộ/);
    const connect = card.querySelector('[data-action="connect-facebook"]');
    assert.equal(connect.textContent, 'Kết nối Meta');
    assert.equal(connect.disabled, false);
    connect.click();
    await h.until(() => h.w.location.hash === '#meta-test-authorization');
    assert.equal(h.requests.filter(r => r.path === '/api/meta/connect' && r.method === 'POST').length, 1);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Meta callback messages remain on Facebook and never start Google checks or job polling', async () => {
  const h = await harness({ metaStatus: { configured: true, connected: false, status: 'disconnected' } });
  try {
    const before = h.requests.length;
    for (const [result, message] of [['success', /Đã kết nối Meta. Chưa đồng bộ dữ liệu/], ['denied', /Bạn đã hủy cấp quyền Meta/], ['failed', /Kết nối chưa hoàn tất/]]) {
      h.w.location.hash = `connections/facebook?oauth=${result}&job=untrusted-job`;
      await h.until(() => h.w.location.hash === '#connections/facebook');
      assert.match(h.document.querySelector('#content').textContent, message);
      assert.equal(h.document.querySelector('#content h1').textContent, 'Facebook');
    }
    assert.ok(h.requests.slice(before).every(r => r.method === 'GET' && r.path === '/api/meta'));
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Meta connect redirects using the backend response and displays backend errors', async () => {
  for (const failure of [false, true]) {
    const h = await harness({ metaStatus: { configured: true, connected: false, status: 'disconnected' }, metaConnectError: failure ? { status: 503, message: 'Cần cấu hình Meta OAuth.' } : null });
    try {
      h.w.location.hash = 'connections/facebook';
      await h.until(() => h.document.querySelector('[data-action="connect-facebook"]'));
      h.document.querySelector('[data-action="connect-facebook"]').click();
      await h.until(() => failure ? h.document.querySelector('#toasts').textContent.includes('Cần cấu hình Meta OAuth.') : h.w.location.hash === '#meta-test-authorization');
      assert.equal(h.requests.filter(r => r.path === '/api/meta/connect' && r.method === 'POST').length, 1);
      assert.equal(h.w.localStorage.length, 0);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  }
});

test('Meta expiry and unreadable stored credentials permit reconnect without inventing ready sources', async () => {
  for (const [status, label] of [['expired', /Quyền đã hết hạn/], ['reconnect_required', /Cần kết nối lại/], ['error', /Không đọc được kết nối/]]) {
    const h = await harness({ metaStatus: { configured: true, connected: false, has_connection: true, status } });
    try {
      h.w.location.hash = 'connections/facebook';
      await h.until(() => h.document.querySelector('.connection-meta'));
      assert.match(h.document.querySelector('.connection-meta').textContent, label);
      assert.ok(h.document.querySelector('[data-action="disconnect-meta"]'));
      assert.equal(h.document.querySelector('[data-action="connect-facebook"]').disabled, false);
      assert.doesNotMatch(h.document.querySelector('.connection-meta').textContent, /Sẵn sàng|Đã kết nối OAuth/);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  }
});

test('Meta status failures do not invent disconnected accounts and viewer cannot load credentials UI', async () => {
  const h = await harness({ metaReadError: { status: 503, message: 'Trạng thái Meta tạm thời không đọc được.' } });
  try {
    h.w.location.hash = 'connections/facebook';
    await h.until(() => h.document.querySelector('#content').textContent.includes('Không thể hiển thị màn hình'));
    assert.match(h.document.querySelector('#content').textContent, /Trạng thái Meta tạm thời không đọc được/);
    assert.equal(h.document.querySelector('[data-action="connect-facebook"]'), null);
  } finally { h.close(); }
  const viewer = await harness({ role: 'viewer' });
  try {
    viewer.w.location.hash = 'connections/facebook';
    await viewer.until(() => viewer.document.querySelector('#content').textContent.includes('chỉ dành cho quản trị viên'));
    assert.equal(viewer.requests.some(r => r.path.startsWith('/api/meta')), false);
  } finally { viewer.close(); }
});

test('Late Meta status is discarded after navigating away', async () => {
  const h = await harness(); let release;
  try {
    release = h.hold('/api/meta');
    h.w.location.hash = 'connections/facebook';
    await h.until(() => h.requests.some(r => r.path === '/api/meta'));
    h.w.location.hash = 'reports';
    await h.until(() => h.document.querySelector('#content h1')?.textContent.includes('Báo cáo đã lưu'));
    release();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(h.document.querySelector('.connection-meta'), null);
    assert.deepEqual(h.errors, []);
  } finally { release?.(); h.close(); }
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
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan');
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
    await h.until(() => h.document.querySelector('h1')?.textContent === 'Tổng quan');
    h.w.location.hash = 'analysis'; await h.until(() => h.document.querySelector('#analysis-form'));
    release(); release = null; await new Promise(r => setTimeout(r, 50));
    assert.equal(h.document.querySelector('#export-button').disabled, true);
    assert.equal(h.document.querySelector('#analysis-results .kpi'), null);
    assert.match(h.document.querySelector('#applied-period').textContent, /Chưa có bộ lọc được áp dụng/);
  } finally { release?.(); h.close(); }
});

test('Report Builder discovers real Datasets, preselects by query, and saves only a draft', async () => {
  const dataset = {
    id: 'dataset-real-1',
    params: { report_type: 'ga4', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: { ga4: { source: 'ga4', status: 'ready' } }
  };
  const h = await harness({
    jobs: [{ id: 'job-real', dataset_id: dataset.id, created_at: '2026-09-29T08:00:00Z' }],
    reports: [{ id: 'legacy-report', dataset_id: dataset.id, created_at: '2026-09-30T08:00:00Z' }],
    datasetRecords: { [dataset.id]: dataset }
  });
  try {
    h.w.location.hash = `report-builder?dataset=${dataset.id}`;
    await h.until(() => h.document.querySelector('input[name="report-builder-dataset"]'));
    assert.equal(h.document.querySelector('input[name="report-builder-dataset"]').checked, true, JSON.stringify({ hash: h.w.location.hash, html: h.document.querySelector('.report-builder-dataset')?.outerHTML, requests: h.requests }));
    assert.match(h.document.querySelector('#content').textContent, /Chọn Dataset/);
    assert.match(h.document.querySelector('#content').textContent, /Cấu hình nội dung/);
    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Chọn Dataset');
    assert.equal(h.document.querySelector('.report-builder-stepper li.complete strong').textContent, 'Thông tin báo cáo');
    assert.equal(Array.from(h.document.querySelectorAll('.report-builder-stepper li[aria-disabled="true"]')).some(step => step.textContent.includes('Xem trước')), true);
    assert.equal(h.document.querySelector('select[name="client_id"]'), null);
    assert.equal(h.requests.filter(r => r.path === `/api/datasets/${dataset.id}`).length, 1);
    assert.equal(h.requests.some(r => r.path === '/api/datasets'), false);
    assert.equal(h.requests.some(r => /\/api\/(google|analyses|sync|providers)/.test(r.path)), false);

    h.document.querySelector('[data-action="report-builder-back"]').click();
    await h.until(() => h.document.querySelector('#report-builder-form'));
    h.document.querySelector('[name="name"]').value = 'Báo cáo tháng 9';
    h.document.querySelector('[name="start_date"]').value = dataset.params.start;
    h.document.querySelector('[name="end_date"]').value = dataset.params.end;
    h.document.querySelector('[data-action="report-builder-next"]').click();
    await h.until(() => h.document.querySelector('[data-action="report-builder-save"]'));
    assert.equal(h.document.querySelector('[data-action="report-builder-save"]').disabled, false);
    h.document.querySelector('[data-action="report-builder-save"]').click();
    await h.until(() => h.document.querySelector('.report-builder-saved'));
    const request = h.requests.find(r => r.path === '/api/report-bundles');
    assert.equal(request.method, 'POST');
    assert.deepEqual(request.body, {
      client_id: 'client_kinderhealth',
      name: 'Báo cáo tháng 9',
      start_date: dataset.params.start,
      end_date: dataset.params.end,
      default_section: 'overview',
      sections: [{ key: 'overview', dataset_id: dataset.id }]
    });
    assert.match(h.document.querySelector('.report-builder-saved').textContent, /DRAFT/);
    assert.equal(h.document.querySelector('[data-action="report-builder-save"]'), null);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Report Builder shows a truthful empty state when no Dataset references are available', async () => {
  const h = await harness({ jobs: [], reports: [] });
  try {
    h.w.location.hash = 'report-builder';
    await h.until(() => h.document.querySelector('#report-builder-form'));
    h.document.querySelector('[name="name"]').value = 'Empty-state test';
    h.document.querySelector('[data-action="report-builder-next"]').click();
    await h.until(() => h.document.querySelector('.report-builder-empty'));
    assert.match(h.document.querySelector('.report-builder-empty').textContent, /Chưa có Dataset/);
    assert.equal(h.document.querySelector('.report-builder-empty a[href="#analysis"]')?.textContent.includes('Tạo Dataset từ phân tích'), true);
    assert.equal(h.requests.some(r => r.path === '/api/datasets'), false);
    assert.equal(h.requests.some(r => r.path === '/api/report-bundles'), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Report Builder uses presentation sections, orders, assigns, validates, and persists real draft sections', async () => {
  const seoDataset = {
    id: 'dataset-seo-period',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: {
      ga4: { source: 'ga4', status: 'ready' },
      gsc: { source: 'gsc', status: 'ready' },
      keywords: { source: 'keywords', status: 'ready' }
    }
  };
  const gmbDataset = {
    id: 'dataset-gmb-period',
    params: { report_type: 'gmb', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-30T07:00:00Z',
    exportable: false,
    sources: { gmb: { source: 'gmb', status: 'permission_denied' } }
  };
  const h = await harness({
    jobs: [
      { id: 'job-seo', dataset_id: seoDataset.id, created_at: '2026-09-29T08:00:00Z' },
      { id: 'job-gmb', dataset_id: gmbDataset.id, created_at: '2026-09-30T08:00:00Z' }
    ],
    datasetRecords: { [seoDataset.id]: seoDataset, [gmbDataset.id]: gmbDataset }
  });
  try {
    h.w.location.hash = 'report-builder';
    await h.until(() => h.document.querySelector('#report-builder-form'));
    h.document.querySelector('[name="name"]').value = 'SEO September';
    h.document.querySelector('[name="start_date"]').value = seoDataset.params.start;
    h.document.querySelector('[name="end_date"]').value = seoDataset.params.end;
    h.document.querySelector('[data-action="report-builder-next"]').click();
    await h.until(() => h.document.querySelector(`input[name="report-builder-dataset"][value="${seoDataset.id}"]`));
    const selectedDataset = h.document.querySelector(`input[name="report-builder-dataset"][value="${seoDataset.id}"]`);
    selectedDataset.checked = true;
    selectedDataset.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    h.document.querySelector('[data-action="report-builder-save"]').click();
    await h.until(() => h.document.querySelector('[data-action="report-builder-configure"]'));
    h.document.querySelector('[data-action="report-builder-configure"]').click();
    await h.until(() => h.document.querySelector('.report-builder-section-list'));

    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Cấu hình nội dung');
    assert.deepEqual(Array.from(h.document.querySelectorAll('.report-builder-stepper li.complete strong'), step => step.textContent), ['Thông tin báo cáo', 'Chọn Dataset']);
    assert.equal(Array.from(h.document.querySelectorAll('.report-builder-stepper li[aria-disabled="true"]')).some(step => step.textContent.includes('Xem trước')), true);
    assert.equal(h.document.querySelector('[data-report-section-toggle="seo"]').disabled, false);
    assert.equal(h.document.querySelector('[data-report-section-toggle="gmb"]').disabled, false);
    for (const key of ['ga4', 'gsc', 'keywords']) assert.equal(h.document.querySelector(`[data-report-section-toggle="${key}"]`), null);
    for (const key of ['facebook_content', 'facebook_ads', 'tiktok', 'youtube']) {
      assert.equal(h.document.querySelector(`[data-report-section-toggle="${key}"]`).disabled, true);
      assert.match(h.document.querySelector(`[data-report-section-toggle="${key}"]`).closest('.report-section-card').textContent, /Chưa có Dataset phù hợp/);
    }

    const overviewToggle = h.document.querySelector('[data-report-section-toggle="overview"]');
    overviewToggle.click();
    await h.until(() => h.document.querySelector('.report-builder-validation').textContent.includes('Chọn ít nhất một section'));
    assert.equal(h.document.querySelector('[data-action="report-builder-save-config"]').disabled, true);
    h.document.querySelector('[data-report-section-toggle="overview"]').click();

    h.document.querySelector('[data-report-section-toggle="seo"]').click();
    h.document.querySelector('[data-report-section-toggle="overview"]').click();
    await h.until(() => h.document.querySelector('.report-builder-validation').textContent.includes('trang mặc định'));
    assert.equal(h.document.querySelector('[data-action="report-builder-save-config"]').disabled, true);
    h.document.querySelector('[data-report-section-toggle="overview"]').click();
    h.document.querySelector('[data-report-section-toggle="gmb"]').click();
    assert.equal(h.document.querySelector('[data-report-section-dataset="seo"]').value, seoDataset.id);
    assert.equal(h.document.querySelector('[data-report-section-dataset="gmb"]').value, gmbDataset.id);
    h.document.querySelector('input[name="report-default-section"][value="gmb"]').click();
    h.document.querySelector('[data-action="report-section-up"][data-section-key="gmb"]').click();
    assert.deepEqual(Array.from(h.document.querySelectorAll('.report-section-card.included .report-section-position'), item => item.textContent), ['1', '2', '3']);
    assert.equal(h.document.querySelector('[data-action="report-builder-save-config"]').disabled, false);
    h.document.querySelector('[data-action="report-builder-save-config"]').click();
    await h.until(() => h.document.querySelector('#toasts').textContent.includes('Đã lưu cấu hình section'));

    const patch = h.requests.find(request => request.method === 'PATCH' && request.path === '/api/report-bundles/rpt_test_bundle/revisions/1');
    assert.deepEqual(patch.body, {
      client_id: 'client_kinderhealth',
      name: 'SEO September',
      start_date: '2026-09-01',
      end_date: '2026-09-28',
      compare_start_date: null,
      compare_end_date: null,
      default_section: 'gmb',
      sections: [
        { key: 'seo', dataset_id: seoDataset.id },
        { key: 'gmb', dataset_id: gmbDataset.id },
        { key: 'overview', dataset_id: seoDataset.id }
      ]
    });
    assert.match(h.document.querySelector('.report-builder-card').textContent, /đã được lưu vào bản nháp revision 1/);
    assert.equal(h.requests.some(request => /\/api\/(google|analyses|sync|providers|facebook|tiktok|youtube)/.test(request.path)), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Report Builder renders non-draft bundle sections read-only', async () => {
  const dataset = {
    id: 'dataset-readonly',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: { ga4: { status: 'ready' } }
  };
  const h = await harness({
    jobs: [{ id: 'job-readonly', dataset_id: dataset.id, created_at: '2026-09-29T08:00:00Z' }],
    datasetRecords: { [dataset.id]: dataset },
    reportBundleDetail: {
      report: { id: 'rpt_test_bundle', revision: 1, status: 'final' },
      navigation: { default_section: 'overview', sections: ['overview'] },
      sections: { overview: { dataset_id: dataset.id, position: 0 } }
    }
  });
  try {
    h.w.location.hash = 'report-builder';
    await h.until(() => h.document.querySelector('#report-builder-form'));
    h.document.querySelector('[name="name"]').value = 'Read only report';
    h.document.querySelector('[name="start_date"]').value = dataset.params.start;
    h.document.querySelector('[name="end_date"]').value = dataset.params.end;
    h.document.querySelector('[data-action="report-builder-next"]').click();
    await h.until(() => h.document.querySelector(`input[name="report-builder-dataset"][value="${dataset.id}"]`));
    const radio = h.document.querySelector(`input[name="report-builder-dataset"][value="${dataset.id}"]`);
    radio.checked = true;
    radio.dispatchEvent(new h.w.Event('change', { bubbles: true }));
    h.document.querySelector('[data-action="report-builder-save"]').click();
    await h.until(() => h.document.querySelector('[data-action="report-builder-configure"]'));
    h.document.querySelector('[data-action="report-builder-configure"]').click();
    await h.until(() => h.document.querySelector('.report-builder-section-list'));
    assert.match(h.document.querySelector('.report-builder-card').textContent, /chỉ đọc/i);
    assert.equal(h.document.querySelector('[data-action="report-builder-save-config"]').disabled, true);
    assert.equal(h.requests.some(request => request.method === 'PATCH' && request.path.startsWith('/api/report-bundles/')), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

async function openReportBuilderConfiguration(h, dataset, name = 'Preview test') {
  h.w.location.hash = 'report-builder';
  await h.until(() => h.document.querySelector('#report-builder-form'));
  h.document.querySelector('[name="name"]').value = name;
  h.document.querySelector('[name="start_date"]').value = dataset.params.start;
  h.document.querySelector('[name="end_date"]').value = dataset.params.end;
  h.document.querySelector('[data-action="report-builder-next"]').click();
  await h.until(() => h.document.querySelector(`input[name="report-builder-dataset"][value="${dataset.id}"]`));
  const radio = h.document.querySelector(`input[name="report-builder-dataset"][value="${dataset.id}"]`);
  radio.checked = true;
  radio.dispatchEvent(new h.w.Event('change', { bubbles: true }));
  h.document.querySelector('[data-action="report-builder-save"]').click();
  await h.until(() => h.document.querySelector('[data-action="report-builder-configure"]'));
  h.document.querySelector('[data-action="report-builder-configure"]').click();
  await h.until(() => h.document.querySelector('.report-builder-section-list'));
}

test('Report Builder preview reads the saved revision and deduplicates Dataset reads in persisted section order', async () => {
  const seoDataset = {
    id: 'dataset-preview-seo',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false },
    report_type: 'seo',
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: {
      ga4: { source: 'ga4', status: 'ready', totals: { sessions: 120, activeUsers: 95, screenPageViews: 300, engagementRate: 0.42 }, daily: [{ date: '2026-09-01', sessions: 20 }, { date: '2026-09-28', sessions: 30 }] },
      gsc: { source: 'gsc', status: 'ready', totals: { clicks: 15, impressions: 100, ctr: 0.15, position: 4.2 }, queries: [{ query: 'KinderHealth', clicks: 15 }] },
      keywords: { source: 'keywords', status: 'ready', entries: [{ keyword: 'KinderHealth', position: 3 }] }
    }
  };
  const gmbDataset = {
    id: 'dataset-preview-gmb',
    params: { report_type: 'gmb', start: '2026-09-01', end: '2026-09-28', compare: false },
    report_type: 'gmb',
    created_at: '2026-09-30T07:00:00Z',
    exportable: true,
    sources: { gmb: { source: 'gmb', status: 'ready', totals: { views: 45, calls: 3, directions: 8, website_clicks: 6 }, entries: [{ name: 'KinderHealth', calls: 3 }] } }
  };
  const h = await harness({
    jobs: [
      { id: 'job-preview-seo', dataset_id: seoDataset.id, created_at: '2026-09-29T08:00:00Z' },
      { id: 'job-preview-gmb', dataset_id: gmbDataset.id, created_at: '2026-09-30T08:00:00Z' }
    ],
    datasetRecords: { [seoDataset.id]: seoDataset, [gmbDataset.id]: gmbDataset }
  });
  try {
    await openReportBuilderConfiguration(h, seoDataset, 'September report');
    h.document.querySelector('[data-report-section-toggle="seo"]').click();
    h.document.querySelector('[data-report-section-toggle="gmb"]').click();
    h.document.querySelector('input[name="report-default-section"][value="gmb"]').click();
    h.document.querySelector('[data-action="report-section-up"][data-section-key="gmb"]').click();
    h.document.querySelector('[data-action="report-section-up"][data-section-key="gmb"]').click();
    h.document.querySelector('[data-action="report-builder-save-config"]').click();
    await h.until(() => h.document.querySelector('#toasts').textContent.includes('Đã lưu cấu hình section'));
    const before = h.requests.length;
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-canvas'));

    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Xem trước');
    assert.deepEqual(Array.from(h.document.querySelectorAll('.report-builder-stepper li.complete strong'), step => step.textContent), ['Thông tin báo cáo', 'Chọn Dataset', 'Cấu hình nội dung']);
    assert.deepEqual(Array.from(h.document.querySelectorAll('.report-preview-section > header h2'), heading => heading.textContent), ['Google Maps & Hồ sơ doanh nghiệp', 'Tổng quan', 'Website Traffic & SEO']);
    assert.deepEqual(Array.from(h.document.querySelectorAll('.report-preview-navigation button'), button => button.textContent.replace(' ★', '')), ['1. Google Maps & Hồ sơ doanh nghiệp', '2. Tổng quan', '3. Website Traffic & SEO']);
    assert.match(h.document.querySelector('.report-preview-section#report-preview-gmb').textContent, /Trang mặc định/);
    assert.match(h.document.querySelector('.report-preview-section#report-preview-seo').textContent, /Google Analytics 4/);
    assert.match(h.document.querySelector('.report-preview-section#report-preview-seo').textContent, /Search Console/);
    assert.match(h.document.querySelector('.report-preview-section#report-preview-seo').textContent, /Keyword Tracking/);
    assert.match(h.document.querySelector('.report-preview-section#report-preview-seo').textContent, /120/);
    assert.match(h.document.querySelector('.report-preview-summary').textContent, /September report/);
    assert.match(h.document.querySelector('.report-preview-summary').textContent, /BẢN NHÁP/);
    assert.match(h.document.querySelector('.report-builder-preview').textContent, /báo cáo chưa được xuất bản/);
    assert.equal(h.document.querySelectorAll('.report-preview-section input, .report-preview-section select, .report-preview-section textarea').length, 0);
    assert.equal(h.document.querySelector('[data-action="publish-confirm"]'), null);
    assert.deepEqual(h.requests.slice(before), [
      { path: '/api/report-bundles/rpt_test_bundle?revision=1', method: 'GET', body: undefined },
      { path: `/api/datasets/${gmbDataset.id}`, method: 'GET', body: undefined },
      { path: `/api/datasets/${seoDataset.id}`, method: 'GET', body: undefined }
    ]);
    assert.equal(h.document.querySelectorAll('.report-preview-assignments li').length, 3);
    assert.match(h.document.querySelector('.report-preview-assignments').textContent, /dataset-preview-seo/);
    assert.equal(h.document.querySelectorAll('.report-builder-preview [data-action*="publish"], .report-builder-preview [data-action*="save"], .report-builder-preview [data-action*="export"]').length, 0);
    h.document.querySelector('[data-action="report-builder-preview-back"]').click();
    assert.equal(h.document.querySelector('.report-builder-stepper li[aria-current="step"] strong').textContent, 'Cấu hình nội dung');
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Report Builder preview warns and blocks content when a referenced Dataset is missing', async () => {
  const dataset = {
    id: 'dataset-preview-missing-ref',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: { ga4: { source: 'ga4', status: 'ready' } }
  };
  const h = await harness({
    jobs: [{ id: 'job-preview-missing-ref', dataset_id: dataset.id }],
    datasetRecords: { [dataset.id]: dataset },
    reportBundleDetail: {
      report: { id: 'rpt_test_bundle', revision: 1, status: 'draft', name: 'Missing Dataset test' },
      client: { id: 'client_kinderhealth', name: 'KinderHealth' },
      period: { start: dataset.params.start, end: dataset.params.end },
      comparison: null,
      quality: { warnings: [] },
      navigation: { default_section: 'seo', sections: ['seo'] },
      sections: { seo: { dataset_id: 'dataset-does-not-exist', position: 0 } }
    }
  });
  try {
    await openReportBuilderConfiguration(h, dataset);
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-blocked'));
    assert.match(h.document.querySelector('.report-preview-warnings').textContent, /Không tìm thấy Dataset/);
    assert.match(h.document.querySelector('.report-preview-blocked').textContent, /Dataset không khả dụng/);
    assert.equal(h.document.querySelector('.report-preview-section'), null);
    assert.equal(h.errors.length, 0);
  } finally { h.close(); }
});

test('Report Builder preview warns about period mismatch and invalid default without claiming readiness', async () => {
  const dataset = {
    id: 'dataset-preview-period',
    params: { report_type: 'seo', start: '2026-09-01', end: '2026-09-28', compare: false },
    created_at: '2026-09-29T07:00:00Z',
    exportable: true,
    sources: { ga4: { source: 'ga4', status: 'ready' } }
  };
  const h = await harness({
    jobs: [{ id: 'job-preview-period', dataset_id: dataset.id }],
    datasetRecords: { [dataset.id]: dataset },
    reportBundleDetail: {
      report: { id: 'rpt_test_bundle', revision: 1, status: 'draft', name: 'Period mismatch test' },
      client: { id: 'client_kinderhealth', name: 'KinderHealth' },
      period: { start: '2026-09-02', end: '2026-09-29' },
      comparison: null,
      quality: { warnings: [] },
      navigation: { default_section: 'overview', sections: ['seo'] },
      sections: { seo: { dataset_id: dataset.id, position: 0, data: dataset, report_type: 'seo', valid: true } }
    }
  });
  try {
    await openReportBuilderConfiguration(h, dataset);
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-blocked'));
    assert.match(h.document.querySelector('.report-preview-warnings').textContent, /không trùng hoàn toàn với kỳ báo cáo/);
    assert.match(h.document.querySelector('.report-preview-warnings').textContent, /Trang mặc định không nằm/);
    assert.match(h.document.querySelector('.report-preview-blocked').textContent, /trang mặc định không hợp lệ/i);
    assert.doesNotMatch(h.document.querySelector('.report-preview-quality').textContent, /Sẵn sàng cho bước tiếp theo/);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

function previewFixture(type = 'gmb') {
  const dataset = {
    id: 'preview-fixture', params: { report_type: type, start: '2026-09-01', end: '2026-09-28', compare: false },
    exportable: true, sources: { [type]: { status: 'ready', totals: { calls: 0 }, entries: [] } }
  };
  const bundle = {
    report: { id: 'rpt_test_bundle', revision: 1, status: 'draft', name: 'Preview regression fixture' },
    client: { id: 'client_kinderhealth', name: 'KinderHealth' },
    period: { start: dataset.params.start, end: dataset.params.end }, comparison: null,
    quality: { status: 'complete', warnings: [] },
    navigation: { default_section: type, sections: [type] },
    sections: { [type]: { dataset_id: dataset.id, position: 0, report_type: type, valid: true, data: dataset } }
  };
  return { dataset, bundle, options: { jobs: [{ id: 'fixture-job', dataset_id: dataset.id }], datasetRecords: { [dataset.id]: dataset }, reportBundleDetail: bundle } };
}

test('Preview preserves missing metrics, real zero values, partial quality and escaped source text', async () => {
  const { dataset, bundle, options } = previewFixture();
  bundle.quality.status = 'partial';
  bundle.sections.gmb.valid = false;
  dataset.exportable = false;
  Object.assign(bundle.sections.gmb.data.sources.gmb, {
    status: 'delayed', warnings: ['Fixture: incomplete period'],
    totals: { calls: 0, directions: null }, entries: [{ name: '<img src=x onerror=alert(1)>', calls: 0 }]
  });
  const h = await harness(options); try {
    await openReportBuilderConfiguration(h, dataset);
    const before = h.requests.length;
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-canvas'));
    assert.deepEqual(Array.from(h.document.querySelectorAll('#report-preview-gmb .kpi strong'), node => node.textContent), ['—', '0', '—', '—']);
    assert.match(h.document.querySelector('.report-preview-quality').textContent, /partial/);
    assert.match(h.document.querySelector('.report-preview-quality').textContent, /Fixture: incomplete period/);
    assert.doesNotMatch(h.document.querySelector('.report-preview-quality').textContent, /Không có cảnh báo/);
    assert.equal(h.document.querySelector('#report-preview-gmb img'), null);
    assert.match(h.document.querySelector('#report-preview-gmb').textContent, /<img src=x onerror=alert\(1\)>/);
    h.document.querySelector('[data-action="report-builder-preview-back-dataset"]').click();
    assert.match(h.document.querySelector('[aria-current="step"]').textContent, /Chọn Dataset/);
    assert.equal(h.requests.slice(before).every(request => request.method === 'GET'), true);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

test('Preview renders stored non-Google totals without a provider integration', async () => {
  const { dataset, bundle, options } = previewFixture('youtube');
  bundle.sections.youtube.data.sources.youtube.totals = { views: 37, watch_minutes: null };
  const h = await harness(options); try {
    await openReportBuilderConfiguration(h, dataset);
    const before = h.requests.length;
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('#report-preview-youtube'));
    assert.match(h.document.querySelector('#report-preview-youtube').textContent, /37/);
    assert.match(h.document.querySelector('#report-preview-youtube').textContent, /watch_minutes/);
    assert.equal(h.requests.slice(before).length, 2);
    assert.equal(h.requests.at(-1).path, '/api/datasets/' + dataset.id);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

for (const [label, change, expected] of [
  ['demo Dataset', bundle => { bundle.sections.gmb.data.params.demo = true; }, /Dataset DEMO/],
  ['demo source', bundle => { bundle.sections.gmb.data.sources.gmb.demo = true; }, /Dataset DEMO/],
  ['wrong client', bundle => { bundle.sections.gmb.data.params.client_id = 'another-client'; }, /không thuộc khách hàng/],
  ['wrong Dataset identity', bundle => { bundle.sections.gmb.data.id = 'another-dataset'; }, /Dataset ID không khớp/],
  ['incompatible Dataset', bundle => { bundle.sections.gmb.report_type = 'seo'; }, /không tương thích/],
  ['unknown section', bundle => { bundle.navigation = { sections: ['ga4'], default_section: 'ga4' }; bundle.sections.ga4 = bundle.sections.gmb; }, /không thuộc registry/],
  ['duplicate section', bundle => { bundle.navigation.sections.push('gmb'); }, /trùng lặp/]
]) {
  test(`Preview blocks ${label} without rendering business contents`, async () => {
    const { dataset, bundle, options } = previewFixture();
    const h = await harness(options); try {
      await openReportBuilderConfiguration(h, dataset);
      change(bundle);
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => h.document.querySelector('.report-preview-blocked'));
      assert.match(h.document.querySelector('.report-preview-blocked').textContent, expected);
      assert.equal(h.document.querySelector('.report-preview-canvas'), null);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  });
}

test('Builder excludes demo Dataset preselection without changing the Analysis demo workflow', async () => {
  const { dataset, options } = previewFixture();
  dataset.params.demo = true;
  const h = await harness(options); try {
    h.w.location.hash = `report-builder?dataset=${dataset.id}`;
    await h.until(() => h.document.querySelector('.report-builder-page'));
    assert.match(h.document.querySelector('#content').textContent, /Dataset DEMO/);
    assert.equal(h.document.querySelector('[name="report-builder-dataset"]'), null);
    assert.equal(h.requests.some(request => request.method !== 'GET'), false);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

for (const status of ['provisional', 'final']) {
  test(`Preview refuses a draft that has changed to ${status}`, async () => {
    const { dataset, bundle, options } = previewFixture();
    const h = await harness(options); try {
      await openReportBuilderConfiguration(h, dataset);
      bundle.report.status = status;
      const before = h.requests.length;
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => h.document.querySelector('.report-builder-card .notice.red'));
      assert.match(h.document.querySelector('.notice.red').textContent, /DRAFT/);
      assert.equal(h.document.querySelector('.report-preview-canvas'), null);
      assert.deepEqual(h.requests.slice(before), [{ path: '/api/report-bundles/rpt_test_bundle?revision=1', method: 'GET', body: undefined }]);
      h.document.querySelector('[data-action="report-builder-preview-back"]').click();
      assert.equal(h.document.querySelector('[data-action="report-builder-save-config"]').disabled, true);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  });
}

test('Preview does not silently switch to a different revision', async () => {
  const { dataset, bundle, options } = previewFixture();
  const h = await harness(options); try {
    await openReportBuilderConfiguration(h, dataset);
    bundle.report.revision = 2;
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.notice.red'));
    assert.match(h.document.querySelector('.notice.red').textContent, /không khớp bản nháp/);
    assert.equal(h.document.querySelector('.report-preview-canvas'), null);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

for (const status of [401, 403, 404, 500]) {
  test(`Preview handles HTTP ${status} without leaving a loading screen or stale contents`, async () => {
    const { dataset, options } = previewFixture();
    const error = {};
    const h = await harness({ ...options, reportBundleReadError: error }); try {
      await openReportBuilderConfiguration(h, dataset);
      Object.assign(error, { status, message: `Fixture HTTP ${status}` });
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => status === 401 ? h.document.querySelector('#auth-form') : h.document.querySelector('.report-builder-card .notice.red'));
      if (status !== 401) assert.match(h.document.querySelector('.notice.red').textContent, status === 404 ? /Không tìm thấy báo cáo/ : new RegExp(`Fixture HTTP ${status}`));
      assert.equal(h.document.querySelector('.report-preview-canvas, .report-builder-card .spinner'), null);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  });
}

test('Canceled Preview responses cannot overwrite configuration or a newer Preview', async () => {
  const { dataset, bundle, options } = previewFixture();
  const h = await harness(options); let release;
  try {
    await openReportBuilderConfiguration(h, dataset);
    release = h.hold('/api/report-bundles/rpt_test_bundle?revision=1');
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-builder-card .spinner'));
    h.document.querySelector('[data-action="report-builder-preview-back"]').click();
    assert.ok(h.document.querySelector('.report-builder-section-list'));
    release();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.ok(h.document.querySelector('.report-builder-section-list'));
    assert.equal(h.document.querySelector('.report-preview-canvas'), null);
    bundle.report.name = 'Newly loaded saved draft';
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-summary'));
    assert.match(h.document.querySelector('.report-preview-summary').textContent, /Newly loaded saved draft/);
    assert.deepEqual(h.errors, []);
  } finally { release?.(); h.close(); }
});

test('Preview navigation and session expiry discard in-flight snapshot responses', async () => {
  for (const expire of [false, true]) {
    const { dataset, options } = previewFixture();
    const h = await harness(options); let release;
    try {
      await openReportBuilderConfiguration(h, dataset);
      release = h.hold('/api/report-bundles/rpt_test_bundle?revision=1');
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => h.document.querySelector('.report-builder-card .spinner'));
      if (expire) h.expireAs('viewer');
      h.w.location.hash = 'overview';
      await h.until(() => expire ? h.document.querySelector('#auth-form') : h.document.querySelector('h1')?.textContent === 'Tổng quan');
      release();
      await new Promise(resolve => setTimeout(resolve, 20));
      assert.equal(h.document.querySelector('.report-preview-canvas'), null);
      if (!expire) {
        h.w.location.hash = 'report-builder';
        await h.until(() => h.document.querySelector('.report-builder-card .notice.red'));
        assert.match(h.document.querySelector('.notice.red').textContent, /Đã hủy tải/);
      }
      assert.deepEqual(h.errors, []);
    } finally { release?.(); h.close(); }
  }
});

test('Preview refuses changed snapshot contents instead of silently showing different business data', async () => {
  const { dataset, bundle, options } = previewFixture();
  bundle.sections.gmb.data = structuredClone(dataset);
  const h = await harness(options); try {
    await openReportBuilderConfiguration(h, dataset);
    dataset.sources.gmb.totals.calls = 999999;
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.document.querySelector('.report-preview-blocked'));
    assert.match(h.document.querySelector('.report-preview-blocked').textContent, /không khớp snapshot đã lưu/);
    assert.equal(h.document.querySelector('.report-preview-section'), null);
    assert.doesNotMatch(h.document.querySelector('.report-builder-preview').textContent, /999[.,]?999/);
    assert.deepEqual(h.errors, []);
  } finally { h.close(); }
});

for (const comparisonCase of ['matching', 'mismatched', 'missing', 'unconfigured']) {
  test(`Preview shows the saved comparison period with ${comparisonCase} Dataset comparison metadata`, async () => {
    const { dataset, bundle, options } = previewFixture();
    bundle.comparison = comparisonCase === 'unconfigured' ? null : { start: '2026-08-04', end: '2026-08-31' };
    Object.assign(dataset.params, {
      compare: comparisonCase !== 'missing', previous_start: comparisonCase === 'mismatched' ? '2026-08-01' : '2026-08-04', previous_end: '2026-08-31'
    });
    dataset.sources.gmb.previous = { calls: 3 };
    dataset.warnings = ['Fixture Dataset warning'];
    const h = await harness(options); try {
      await openReportBuilderConfiguration(h, dataset);
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => h.document.querySelector('.report-preview-canvas'));
      assert.match(h.document.querySelector('.report-preview-summary').textContent, comparisonCase === 'unconfigured' ? /Không cấu hình/ : /04\/08\/2026 → 31\/08\/2026/);
      assert.match(h.document.querySelector('.report-preview-warnings').textContent, /Fixture Dataset warning/);
      const section = h.document.querySelector('#report-preview-gmb');
      if (comparisonCase === 'matching') assert.match(section.textContent, /Kỳ trước: 3/);
      else assert.doesNotMatch(section.textContent, /Kỳ trước:/);
      if (['missing', 'mismatched'].includes(comparisonCase)) assert.match(h.document.querySelector('.report-preview-warnings').textContent, /thiếu hoặc không khớp kỳ so sánh/);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  });
}

for (const status of [401, 403, 404, 500]) {
  test(`Preview handles Dataset HTTP ${status} without falling back to inline or invented data`, async () => {
    const { dataset, options } = previewFixture();
    const errors = {};
    const h = await harness({ ...options, datasetErrors: errors }); try {
      await openReportBuilderConfiguration(h, dataset);
      errors[dataset.id] = { status, message: `Dataset HTTP ${status}` };
      const before = h.requests.length;
      h.document.querySelector('[data-action="report-builder-preview"]').click();
      await h.until(() => status === 401 ? h.document.querySelector('#auth-form') : h.document.querySelector('.report-preview-blocked'));
      assert.equal(h.document.querySelector('.report-preview-canvas'), null);
      if (status !== 401) assert.match(h.document.querySelector('.report-preview-warnings').textContent, status === 404 ? /Không tìm thấy Dataset/ : new RegExp(`Dataset HTTP ${status}`));
      assert.deepEqual(h.requests.slice(before).map(request => [request.method, request.path]), [
        ['GET', '/api/report-bundles/rpt_test_bundle?revision=1'], ['GET', '/api/datasets/' + dataset.id]
      ]);
      assert.deepEqual(h.errors, []);
    } finally { h.close(); }
  });
}

test('Preview discards Dataset responses after returning to configuration', async () => {
  const { dataset, options } = previewFixture();
  const h = await harness(options); let release;
  try {
    await openReportBuilderConfiguration(h, dataset);
    const before = h.requests.length;
    release = h.hold('/api/datasets/' + dataset.id);
    h.document.querySelector('[data-action="report-builder-preview"]').click();
    await h.until(() => h.requests.slice(before).some(request => request.path === '/api/datasets/' + dataset.id));
    assert.ok(h.document.querySelector('.report-builder-card .spinner'));
    h.document.querySelector('[data-action="report-builder-preview-back"]').click();
    release();
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.ok(h.document.querySelector('.report-builder-section-list'));
    assert.equal(h.document.querySelector('.report-preview-canvas'), null);
    assert.deepEqual(h.errors, []);
  } finally { release?.(); h.close(); }
});
