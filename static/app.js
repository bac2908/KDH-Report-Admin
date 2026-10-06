import { api, setCsrf } from './api.js';
import { esc, date, time, num, icon, badge, empty, button, notice, modal, toast, table, sourceNames, kindNames, roles } from './ui.js';
import { pages, connectionPlatforms, loginView, shell, overviewView, clientsView, assetsView, syncView, connectionsView, platformConnectionsView, platformDetailView, analysisView, analysisResults, datasetsView, datasetsTable, datasetDetailView, datasetDetailNotFoundView, reportBuilderView, reportBuilderPeriodWarning, reportsView, activityView, uploadsView, usersView, settingsView, schedulesView, skeletonView, jobProgress, dataTable } from './views.js';

const state = { user: null, overview: null, page: 'overview', generation: 0, authEpoch: 0, dataset: null, datasetDetail: null, datasetDetailTab: 'summary', datasets: [], reportBuilder: null, draft: null, job: null, tab: 'summary', tablePage: 0, uploads: [], reports: [], users: [], schedules: [], reportFilter: {}, jobFilter: '' };
const $ = s => document.querySelector(s);
function clearSessionData() { state.authEpoch++; state.generation++; state.dataset = null; state.datasetDetail = null; state.datasetDetailTab = 'summary'; state.datasets = []; state.reportBuilder = null; state.draft = null; state.job = null; state.overview = null; state.uploads = []; state.reports = []; state.users = []; state.schedules = []; state.jobs = []; state.events = []; state.connection = null; state.settings = null; state.reportFilter = {}; state.jobFilter = ''; state.tab = 'summary'; state.tablePage = 0; $('#modal').close(); $('#modal').replaceChildren(); }
function today() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
function offset(day, n) { const d = new Date(day + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function period(kind) { const t = today(); if (kind === 'this_month') return { start: t.slice(0, 8) + '01', end: t }; if (kind === 'previous_month') { const end = offset(t.slice(0, 8) + '01', -1); return { start: end.slice(0, 8) + '01', end }; } const end = offset(t, -1); return { start: offset(end, kind === 'last7' ? -6 : -27), end }; }
function sameFilters(a, b) { const fields = ['report_type', 'start', 'end', 'compare', 'exclude_products', 'demo']; if (a?.report_type === 'gmb') fields.push('upload_id', 'previous_upload_id'); return a && b && fields.every(k => (a[k] ?? (k === 'compare' || k === 'exclude_products' || k === 'demo' ? false : '')) === (b[k] ?? (k === 'compare' || k === 'exclude_products' || k === 'demo' ? false : ''))); }
function isDirty() { return !!state.dataset && !sameFilters(state.draft, state.dataset.params); }
function footer() { return `<footer class="page-footer"><span>KINDERHEALTH · BÁO CÁO MARKETING NỘI BỘ</span><span>Asia/Ho_Chi_Minh (UTC+7) · Dữ liệu được kiểm tra theo từng nguồn</span></footer>`; }
function errorInModal(err) { const b = $('#modal .modal-body'); if (b && $('#modal').open) { b.querySelector('.modal-error')?.remove(); const e = document.createElement('div'); e.className = 'modal-error'; e.innerHTML = notice(err.message, 'red'); b.append(e); } else toast(err.message, true); }
async function handleError(err) { if (err.cancelled) return; if (err.status === 401 && state.user) { clearSessionData(); state.user = null; setCsrf(''); $('#modal').close(); history.replaceState(null, '', '#overview'); $('#app').innerHTML = loginView(false, 'Phiên hết hạn. Vui lòng đăng nhập lại.'); } else errorInModal(err); }

async function discoverReferencedDatasets(read, version) {
    const [jobs, reports] = await Promise.all([read('/jobs'), read('/reports')]);
    const references = new Map();
    for (const item of [...jobs, ...reports]) {
        if (typeof item.dataset_id !== 'string' || !item.dataset_id) continue;
        const timestamp = Date.parse(item.created_at || '') || 0;
        references.set(item.dataset_id, Math.max(references.get(item.dataset_id) || 0, timestamp));
    }
    const ids = [...references].sort((a, b) => b[1] - a[1]).slice(0, 50).map(([id]) => id);
    const loaded = new Array(ids.length);
    const loadErrors = [];
    let next = 0;
    const loadWorker = async () => {
        while (next < ids.length) {
            const index = next++;
            try {
                loaded[index] = await read('/datasets/' + encodeURIComponent(ids[index]));
            } catch (err) {
                if (version !== state.generation) throw err;
                if (err.status === 404) loadErrors.push({ id: ids[index], message: err.message });
                else throw err;
            }
        }
    };
    await Promise.all(Array.from({ length: Math.min(6, ids.length) }, loadWorker));
    return { datasets: loaded.filter(Boolean), loadErrors };
}

async function start() { try { const session = await api('/auth/me'); state.user = session.user; setCsrf(session.csrf); if (!state.user) { $('#app').innerHTML = loginView(session.setup_required); return; } state.overview = await api('/overview'); state.draft ??= { report_type: state.overview.types.find(t => t.can_generate)?.id || 'seo', ...period('last28'), demo: !!state.overview.demo_enabled, compare: !!state.overview.demo_enabled, exclude_products: false, upload_id: '', previous_upload_id: '' }; await navigate(); } catch (err) { $('#app').innerHTML = `<main class="initial-loading">${empty('Không thể mở ứng dụng', err.message, button('Thử lại', 'restart', 'primary'))}</main>`; } }
async function navigate() {
    if (!state.user) return; const version = ++state.generation; const parts = location.hash.slice(1).split('?'); const route = parts[0].split('/'); const oauthResult = new URLSearchParams(parts[1]).get('oauth'); state.page = pages[route[0]] ? route[0] : 'overview'; state.connectionPlatform = state.page === 'connections' && connectionPlatforms[route[1]] ? route[1] : state.page === 'connections' && oauthResult ? 'google' : null; const page = state.page; $('#app').innerHTML = shell(state.user, state.overview, page, state.connectionPlatform); $('#content').innerHTML = '<div class="empty"><span class="spinner"></span><p>Đang tải dữ liệu…</p></div>'; try {
        const read = async path => { const result = await api(path); if (version !== state.generation) throw new Error('Đã chuyển màn hình hoặc phiên đăng nhập.'); return result; };
        let html = '';
        if (['connections', 'assets', 'users', 'settings', 'schedules', 'report-builder'].includes(page) && state.user.role !== 'admin') throw Object.assign(new Error('Màn hình này chỉ dành cho quản trị viên.'), { status: 403 });
        if (page === 'overview') { state.overview = await read('/overview'); html = overviewView(state.overview, state.user); }
        if (page === 'clients') html = clientsView();
        if (page === 'datasets') {
            if (route.length > 1) {
                let datasetId;
                try { datasetId = decodeURIComponent(route[1]); } catch { datasetId = ''; }
                if (!datasetId) html = datasetDetailNotFoundView();
                else {
                    try {
                        state.datasetDetail = await read('/datasets/' + encodeURIComponent(datasetId));
                        state.datasetDetailTab = 'summary';
                        state.tablePage = 0;
                        html = datasetDetailView(state.datasetDetail, state.overview.types, state.datasetDetailTab, state.tablePage);
                    } catch (err) {
                        if (err.status !== 404) throw err;
                        state.datasetDetail = null;
                        html = datasetDetailNotFoundView();
                    }
                }
            }
            else {
                const discovered = await discoverReferencedDatasets(read, version);
                state.datasets = discovered.datasets;
                html = datasetsView(state.datasets, state.overview.types, discovered.loadErrors);
            }
        }
        if (page === 'report-builder') {
            const requestedDatasetId = new URLSearchParams(parts[1]).get('dataset');
            const discovered = await discoverReferencedDatasets(read, version);
            let datasets = discovered.datasets;
            let preselectionError = '';
            if (requestedDatasetId && !datasets.some(item => item.id === requestedDatasetId)) {
                try {
                    datasets = [...datasets, await read('/datasets/' + encodeURIComponent(requestedDatasetId))];
                } catch (err) {
                    if (version !== state.generation) throw err;
                    if (err.status === 404) preselectionError = 'Dataset được yêu cầu không tìm thấy.';
                    else throw err;
                }
            }
            if (!state.reportBuilder) {
                const defaultPeriod = period('last28');
                state.reportBuilder = {
                    step: 1,
                    form: { name: '', start_date: defaultPeriod.start, end_date: defaultPeriod.end, compare_start_date: '', compare_end_date: '' },
                    selectedDatasetId: '',
                    datasets: [],
                    loadErrors: [],
                    preselectionError: '',
                    saveResult: null
                };
            }
            if (requestedDatasetId) {
                const found = datasets.some(item => item.id === requestedDatasetId);
                state.reportBuilder.selectedDatasetId = found ? requestedDatasetId : '';
                if (found) state.reportBuilder.step = 2;
            }
            state.reportBuilder.datasets = datasets;
            state.reportBuilder.loadErrors = discovered.loadErrors;
            state.reportBuilder.preselectionError = preselectionError;
            html = reportBuilderView(state.reportBuilder, state.overview.types);
        }
        if (page === 'assets') { state.connection = await read('/google'); html = assetsView(state.connection); }
        if (page === 'sync') { const sources = await Promise.all([read('/jobs'), state.user.role === 'admin' ? read('/google') : Promise.resolve(null)]); state.jobs = sources[0]; state.connection = sources[1]; html = syncView(state.jobs, state.overview, state.user, state.connection); }
        if (page === 'connections') { state.connection = await read('/google'); html = state.connectionPlatform === 'google' ? connectionsView(state.connection) : state.connectionPlatform ? platformDetailView(state.connectionPlatform) : platformConnectionsView(state.connection); if (oauthResult) { html = notice(oauthResult === 'success' ? 'Đã kết nối Google. Các nguồn đang được kiểm tra.' : oauthResult === 'denied' ? 'Bạn đã hủy cấp quyền Google.' : 'Kết nối chưa hoàn tất. Hãy thử kết nối lại.', oauthResult === 'success' ? 'green' : 'amber') + html; history.replaceState(null, '', '#connections/google'); } }
        if (page === 'analysis') { const requested = new URLSearchParams(parts[1]).get('dataset') || (!state.dataset && state.draft.demo && !state.draft.upload_id ? state.overview.demo_datasets?.[state.draft.report_type] : null); if (requested && state.dataset?.id !== requested) { state.dataset = await read('/datasets/' + encodeURIComponent(requested)); state.draft = { ...state.dataset.params }; state.tab = 'summary'; state.tablePage = 0; } if (state.overview.types.some(t => t.id === 'gmb')) state.uploads = await read('/uploads'); html = analysisView(state, state.overview.types, state.user); }
        if (page === 'reports') { state.reports = await read('/reports'); html = reportsView(state.reports, state.overview.types, state.user, state.reportFilter); }
        if (page === 'activity') { const results = await Promise.all([read('/jobs'), state.user.role === 'admin' ? read('/events') : Promise.resolve([])]); state.jobs = results[0]; state.events = results[1]; html = activityView(state.jobs, state.events, state.user, state.jobFilter); }
        if (page === 'uploads') { state.uploads = await read('/uploads'); html = uploadsView(state.uploads, state.user, state.overview.upload_limit_mb); }
        if (page === 'users') { state.users = await read('/users'); html = usersView(state.users); }
        if (page === 'settings') { state.settings = await read('/settings'); html = settingsView(state.settings); }
        if (page === 'schedules') { state.schedules = await read('/schedules'); html = schedulesView(state.schedules, state.overview.types, state.overview.job_mode); }
        if (version !== state.generation) return;
        $('#content').innerHTML = html + footer();
        if (page === 'analysis') { updateFilterState(); if (state.job) $('#job-progress').innerHTML = jobProgress(state.job); }
        const oauthJob = new URLSearchParams(parts[1]).get('job');
        if (page === 'connections' && oauthResult === 'success' && oauthJob) {
            void waitJob(oauthJob).then(() => { if (version === state.generation) return navigate(); }).catch(handleError);
        }
    } catch (err) { if (version !== state.generation) return; if (err.status === 401) { await handleError(err); return; } $('#content').innerHTML = empty('Không thể hiển thị màn hình', err.message, button('Thử lại', 'refresh-page', 'primary')) + footer(); }
}

function readDraft() { const form = $('#analysis-form'); if (!form) return; const data = new FormData(form); state.draft = { report_type: data.get('report_type'), start: data.get('start'), end: data.get('end'), compare: data.has('compare'), demo: data.has('demo'), exclude_products: data.has('exclude_products'), upload_id: data.get('upload_id') || '', previous_upload_id: data.get('previous_upload_id') || '' }; }
function updateFilterState() { const exportButton = $('#export-button'); if (exportButton) exportButton.disabled = !state.dataset?.exportable || isDirty() || !!state.job; const save = $('#save-report-button'); if (save) save.disabled = isDirty() || !!state.job; $('#dirty-note')?.classList.toggle('show', isDirty()); const compare = $('#comparison-period'); if (compare) { const p = state.draft; const days = Math.round((Date.parse(p.end) - Date.parse(p.start)) / 86400000) + 1; compare.textContent = p.compare && days > 0 ? `Kỳ so sánh dự kiến: ${date(offset(p.start, -days))} → ${date(offset(p.start, -1))}` : 'Múi giờ báo cáo: Asia/Ho_Chi_Minh · Kỳ trước có cùng số ngày.'; } }
function renderAnalysis() { if (state.page !== 'analysis' || !state.user) return; $('#content').innerHTML = analysisView(state, state.overview.types, state.user) + footer(); updateFilterState(); if (state.job) $('#job-progress').innerHTML = jobProgress(state.job); }
function readReportBuilderForm() {
    const form = $('#report-builder-form');
    if (!form || !state.reportBuilder) return;
    const data = new FormData(form);
    state.reportBuilder.form = {
        name: String(data.get('name') || ''),
        start_date: String(data.get('start_date') || ''),
        end_date: String(data.get('end_date') || ''),
        compare_start_date: String(data.get('compare_start_date') || ''),
        compare_end_date: String(data.get('compare_end_date') || '')
    };
}
function renderReportBuilder() {
    if (state.page === 'report-builder' && state.reportBuilder) $('#content').innerHTML = reportBuilderView(state.reportBuilder, state.overview.types) + footer();
}
function validateReportBuilderForm() {
    const form = state.reportBuilder.form;
    if (!form.name.trim() || form.name.trim().length > 200) throw new Error('Tên báo cáo cần từ 1 đến 200 ký tự.');
    if (!form.start_date || !form.end_date || form.start_date > form.end_date) throw new Error('Hãy nhập kỳ dữ liệu hợp lệ.');
    if (!!form.compare_start_date !== !!form.compare_end_date) throw new Error('Hãy nhập đủ ngày bắt đầu và kết thúc cho kỳ so sánh.');
    if (form.compare_start_date && form.compare_start_date > form.compare_end_date) throw new Error('Ngày bắt đầu kỳ so sánh phải trước hoặc bằng ngày kết thúc.');
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitJob(id, onProgress) {
    let errors = 0; const epoch = state.authEpoch;
    while (state.user && epoch === state.authEpoch) {
        let job;
        try {
            job = await api('/jobs/' + id);
            if (epoch !== state.authEpoch) break;
            onProgress?.(job);
            if (job.status === 'queued' && state.overview?.job_mode === 'request') {
                onProgress?.({ ...job, status: 'running' });
                job = await api('/jobs/' + id + '/process', 'POST', {});
            }
            errors = 0;
        } catch (err) {
            errors++;
            if (err.status === 401 || err.status === 403 || errors > 3) throw err;
            await delay(1800); continue;
        }
        if (epoch !== state.authEpoch) break;
        onProgress?.(job);
        if (!['queued', 'running'].includes(job.status)) return job;
        await delay(1200);
    }
    throw new Error('Phiên đã kết thúc. Có thể xem lại tác vụ trong Lịch sử sau khi đăng nhập.');
}
async function runAnalysis() {
    readDraft(); const epoch = state.authEpoch; const p = structuredClone(state.draft);
    if (!p.start || !p.end || p.start > p.end) throw new Error('Từ ngày phải trước hoặc bằng Đến ngày.');
    const result = await api('/analyses', 'POST', p); if (epoch !== state.authEpoch) return;
    state.job = { id: result.job_id, kind: 'analysis', status: 'queued', steps: [] }; renderAnalysis();
    try {
        const job = await waitJob(result.job_id, j => { state.job = j; if (state.page === 'analysis' && $('#job-progress')) $('#job-progress').innerHTML = jobProgress(j); });
        if (job.dataset_id) { const dataset = await api('/datasets/' + job.dataset_id); if (epoch !== state.authEpoch) return; state.dataset = dataset; state.tab = 'summary'; state.tablePage = 0; if (state.page === 'analysis') history.replaceState(null, '', '#analysis?dataset=' + job.dataset_id); }
        else if (job.error) toast(job.error, true);
        state.job = null; renderAnalysis(); if (job.status !== 'succeeded') toast('Tác vụ chưa đủ dữ liệu hợp lệ. Xem tình trạng từng nguồn.', true);
    } catch (err) { if (epoch !== state.authEpoch) return; state.job = null; renderAnalysis(); throw err; }
}

function exportModal(dataset = state.dataset) { if (!dataset?.exportable || (dataset === state.dataset && (isDirty() || state.job))) throw new Error('Cần kết quả hợp lệ khớp bộ lọc hiện tại trước khi xuất.'); const d = dataset; const p = d.params || {}; const sourceData = d.sources && typeof d.sources === 'object' ? d.sources : {}; const sheets = ['Tong_quan', ...Object.keys(sourceData).flatMap(k => ({ ga4: ['GA4_theo_ngay', 'GA4_nguon_truy_cap', 'GA4_trang'], gsc: ['GSC_theo_ngay', 'GSC_truy_van'], keywords: ['Keyword_tracking'], gmb: ['GMB_co_so'] }[k] || []))]; if (p.compare) for (const k of Object.keys(sourceData)) { const sheet = { ga4: 'GA4_ky_truoc', gsc: 'GSC_ky_truoc', keywords: 'Keyword_ky_truoc', gmb: 'GMB_ky_truoc' }[k]; if (sheet) sheets.push(sheet); } modal('Xuất Excel từ Dataset snapshot', `<div id="export-status"><div class="details"><dl><dt>Báo cáo</dt><dd>${esc(state.overview.types.find(t => t.id === p.report_type)?.label || p.report_type || '—')}</dd><dt>Khoảng ngày</dt><dd>${date(p.start)} → ${date(p.end)}</dd><dt>Kỳ so sánh</dt><dd>${p.compare ? date(p.previous_start) + ' → ' + date(p.previous_end) : 'Không so sánh'}</dd><dt>GSC</dt><dd>web · Loại trừ /san-pham/: ${p.exclude_products ? 'Có' : 'Không'}</dd><dt>Lấy dữ liệu</dt><dd>${time(d.created_at)}</dd><dt>Kết quả</dt><dd class="code">${esc(d.id)}</dd></dl></div><div class="source-summary-list spaced">${Object.values(sourceData).map(source => { const s = source || {}; return `<div><span>${esc(sourceNames[s.source] || s.source || 'Nguồn dữ liệu')}<br><small>Dữ liệu đến ${date(s.latest_available_date)}</small></span>${s.status ? badge(s.status) : ''}</div>${(s.warnings || []).map(w => notice(w, 'amber')).join('')}`; }).join('')}</div><h3 class="spaced">Các sheet trong file</h3><ul class="export-list">${sheets.map(s => `<li>${esc(s)}</li>`).join('')}</ul><p class="form-note">Dữ liệu nguồn được giữ nguyên theo Dataset snapshot này. Không gọi lấy một tập dữ liệu mới khi xuất.</p></div>`, button('Đóng', 'close-modal') + button(icon('download', 16) + ' Tạo file Excel', 'export-confirm', 'primary', `data-id="${esc(d.id)}"`)); }
async function createExport(id) { const result = await api('/datasets/' + id + '/export', 'POST', {}); $('#modal footer').innerHTML = button('Đóng', 'close-modal'); $('#export-status').innerHTML = '<div class="empty"><span class="spinner"></span><h3>Đang tạo file Excel…</h3><p>Dữ liệu và bộ lọc trên màn hình được giữ nguyên.</p></div>'; const job = await waitJob(result.job_id); if (job.status !== 'succeeded') throw new Error(job.error || 'Xuất Excel thất bại. Dữ liệu đang xem vẫn được giữ.'); const body = `${notice('File đã sẵn sàng. Bấm Tải Excel để lưu về máy.', 'green')}<a class="btn primary full" href="/api/jobs/${job.id}/download">${icon('download', 16)} Tải Excel</a>`; if ($('#modal').open && $('#export-status')) $('#export-status').innerHTML = body; else modal('File Excel đã sẵn sàng', body, button('Đóng', 'close-modal')); }

async function jobDetail(id) { const j = await api('/jobs/' + id); const p = j.params; modal('Chi tiết tác vụ', `${p.demo ? notice(p.simulated_history ? 'DEMO · Lịch sử minh họa được tạo sẵn.' : 'DEMO · Tác vụ sử dụng số liệu mô phỏng.', 'blue') : ''}${jobProgress(j)}<div class="details"><dl><dt>Mã tác vụ</dt><dd class="code">${j.id}</dd><dt>Kỳ dữ liệu</dt><dd>${date(p.start)} → ${date(p.end)}</dd><dt>Kỳ so sánh</dt><dd>${p.compare ? date(p.previous_start) + ' → ' + date(p.previous_end) : 'Không'}</dd><dt>Bộ lọc GSC</dt><dd>web · Loại trừ /san-pham/: ${p.exclude_products ? 'Có' : 'Không'}</dd><dt>Bắt đầu</dt><dd>${time(j.started_at)}</dd><dt>Kết thúc</dt><dd>${time(j.finished_at)}</dd></dl></div><div class="spaced">${j.steps.map(s => `${s.error ? notice(sourceNames[s.source] + ': ' + s.error, 'red') : ''}${(s.warnings || []).map(w => notice(w)).join('')}`).join('')}</div>`, button('Đóng', 'close-modal') + (j.dataset_id ? button('Xem kết quả', 'open-dataset', 'secondary', `data-id="${j.dataset_id}"`) : '') + (j.kind === 'export' && j.status === 'succeeded' ? `<a class="btn primary" href="/api/jobs/${j.id}/download">Tải Excel</a>` : '') + (['failed', 'partial', 'interrupted'].includes(j.status) ? button('Thử lại', 'retry-job', 'primary', `data-id="${j.id}"`) : '') + (j.status === 'queued' && state.overview?.job_mode === 'request' && (j.user_id === state.user.id || state.user.role === 'admin') ? button('Chạy tác vụ', 'process-job', 'primary', `data-id="${j.id}"`) : '') + (['running', 'queued'].includes(j.status) ? button('Cập nhật', 'job-detail', 'primary', `data-id="${j.id}"`) : '')); }

function userModal(id) { const user = id ? state.users.find(u => u.id === id) : { name: '', email: '', role: 'viewer', allowed: [], active: 1 }; modal(id ? 'Chỉnh sửa người dùng' : 'Thêm người dùng', `<form id="user-form" data-id="${id || ''}"><div class="form-grid"><div class="field"><label for="user-name">Tên hiển thị</label><input id="user-name" name="name" value="${esc(user.name)}" required maxlength="100"></div><div class="field"><label for="user-email">Email</label><input id="user-email" name="email" type="email" value="${esc(user.email)}" required></div><div class="field"><label for="user-password">${id ? 'Mật khẩu mới (để trống nếu giữ nguyên)' : 'Mật khẩu (ít nhất 12 ký tự)'}</label><input id="user-password" name="password" type="password" minlength="12" maxlength="200" ${id ? '' : 'required'} autocomplete="new-password"></div><div class="field"><label for="user-role">Vai trò</label><select id="user-role" name="role">${Object.entries(roles).map(([k, v]) => `<option value="${k}" ${k === user.role ? 'selected' : ''}>${v}</option>`).join('')}</select></div><div class="span-2"><label>Phạm vi báo cáo · Admin tự có quyền tất cả</label><div class="permission-list">${state.overview.types.map(t => `<label class="check"><input type="checkbox" name="allowed" value="${t.id}" ${user.allowed.includes(t.id) ? 'checked' : ''}> ${esc(t.label)}</label>`).join('')}</div></div>${id ? `<label class="check"><input name="active" type="checkbox" ${user.active ? 'checked' : ''}> Tài khoản hoạt động</label>` : ''}</div><p class="form-note">Đổi quyền hoặc mật khẩu sẽ thu hồi các phiên đăng nhập hiện có của tài khoản.</p><button class="btn primary" type="submit">Lưu người dùng</button></form>`); }
function scheduleModal() { modal('Tạo lịch tự động', `<form id="schedule-form"><div class="form-grid"><div class="field span-2"><label for="schedule-name">Tên lịch</label><input id="schedule-name" name="name" required maxlength="100" placeholder="Báo cáo SEO đầu tháng"></div><div class="field span-2"><label for="schedule-type">Báo cáo</label><select id="schedule-type" name="report_type">${state.overview.types.filter(t => t.can_generate && t.id !== 'gmb').map(t => `<option value="${t.id}">${esc(t.label)}</option>`).join('')}</select></div><div class="field"><label for="schedule-frequency">Tần suất</label><select id="schedule-frequency" name="frequency"><option value="daily">Hằng ngày</option><option value="weekly">Hằng tuần</option><option value="monthly">Hằng tháng</option></select></div><div class="field"><label for="schedule-time">Giờ Việt Nam</label><input id="schedule-time" name="run_time" type="time" value="07:00" required></div><div class="field"><label for="schedule-weekday">Ngày tuần (khi chạy tuần)</label><select id="schedule-weekday" name="weekday">${['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'].map((s, i) => `<option value="${i}">${s}</option>`).join('')}</select></div><div class="field"><label for="schedule-monthday">Ngày tháng (khi chạy tháng)</label><input id="schedule-monthday" name="monthday" type="number" value="1" min="1" max="28"></div><div class="field span-2"><label for="schedule-period">Kỳ dữ liệu</label><select id="schedule-period" name="period"><option value="last28">28 ngày gần nhất (đến hôm qua)</option><option value="last7">7 ngày gần nhất (đến hôm qua)</option><option value="previous_month">Tháng trước</option></select></div><label class="check"><input type="checkbox" name="compare"> So sánh kỳ trước</label><label class="check"><input type="checkbox" name="exclude_products"> GSC loại trừ /san-pham/</label><label class="check span-2"><input type="checkbox" name="publish"> Tự xuất bản nội bộ khi nguồn bắt buộc hợp lệ</label></div><p class="form-note">Mặc định tạo bản nháp HTML. Dữ liệu lỗi không thay thế phiên bản đã xuất bản.</p><button class="btn primary" type="submit">Tạo lịch</button></form>`); }

async function act(action, el) {
    const id = el?.dataset.id;
    switch (action) {
        case 'restart': return start();
        case 'refresh-page': return navigate();
        case 'menu': $('#sidebar').classList.toggle('open'); break;
        case 'close-modal': $('#modal').close(); break;
        case 'toggle-password': { const input = $('#auth-password'); input.type = input.type === 'password' ? 'text' : 'password'; break; }
        case 'forgot': modal('Khôi phục mật khẩu', `<p>Liên hệ quản trị viên để đặt lại mật khẩu tài khoản ứng dụng.</p><p class="muted">Nếu bạn là quản trị viên duy nhất, chạy trên máy chủ:</p><p class="code">.venv\Scripts\python.exe run.py reset-password --email EMAIL_CUA_BAN</p>`, button('Đóng', 'close-modal')); break;
        case 'logout': await api('/auth/logout', 'POST', {}); clearSessionData(); state.user = null; setCsrf(''); location.hash = ''; return start();
        case 'connect-google': { const r = await api('/google/connect', 'POST', {}); location.assign(r.url); break; }
        case 'connect-facebook': toast('Kết nối Facebook sẽ khả dụng khi backend Meta được cấu hình.', true); break;
        case 'connect-tiktok': toast('Kết nối TikTok sẽ khả dụng khi backend TikTok được cấu hình.', true); break;
        case 'check-google': { const r = await api('/google/check', 'POST', {}); toast(r.created ? 'Đã bắt đầu kiểm tra từng nguồn.' : 'Tác vụ kiểm tra này đang chạy.'); if (state.page === 'connections') await navigate(); const j = await waitJob(r.job_id); toast(j.status === 'succeeded' ? 'Các nguồn đã được kiểm tra.' : 'Đã kiểm tra. Một số nguồn cần xử lý.', j.status !== 'succeeded'); if (['overview', 'connections', 'activity', 'sync'].includes(state.page)) await navigate(); break; }
        case 'disconnect-google': modal('Ngắt kết nối Google', notice('Các báo cáo đã lưu được giữ. Lần phân tích tiếp theo sẽ cần Admin kết nối lại.', 'amber'), button('Giữ kết nối', 'close-modal') + button('Ngắt kết nối', 'disconnect-confirm', 'danger')); break;
        case 'disconnect-confirm': { const r = await api('/google', 'DELETE'); $('#modal').close(); toast(r.message); await navigate(); break; }
        case 'preset': readDraft(); Object.assign(state.draft, period(el.dataset.value)); renderAnalysis(); break;
        case 'analysis-tab': state.tab = el.dataset.tab; state.tablePage = 0; $('#analysis-results').innerHTML = analysisResults(state); break;
        case 'dataset-detail-tab': state.datasetDetailTab = el.dataset.tab; state.tablePage = 0; $('#content').innerHTML = datasetDetailView(state.datasetDetail, state.overview.types, state.datasetDetailTab, state.tablePage) + footer(); break;
        case 'table-prev': state.tablePage = Math.max(0, state.tablePage - 1); if (state.page === 'datasets' && state.datasetDetail) $('#content').innerHTML = datasetDetailView(state.datasetDetail, state.overview.types, state.datasetDetailTab, state.tablePage) + footer(); else $('#analysis-results').innerHTML = analysisResults(state); break;
        case 'table-next': state.tablePage++; if (state.page === 'datasets' && state.datasetDetail) $('#content').innerHTML = datasetDetailView(state.datasetDetail, state.overview.types, state.datasetDetailTab, state.tablePage) + footer(); else $('#analysis-results').innerHTML = analysisResults(state); break;
        case 'export-modal': exportModal(); break;
        case 'dataset-detail-export': exportModal(state.datasetDetail); break;
        case 'report-builder-next': readReportBuilderForm(); validateReportBuilderForm(); state.reportBuilder.step = 2; renderReportBuilder(); break;
        case 'report-builder-back': readReportBuilderForm(); state.reportBuilder.step = 1; renderReportBuilder(); break;
        case 'report-builder-save': {
            readReportBuilderForm();
            validateReportBuilderForm();
            const builder = state.reportBuilder;
            const selected = builder.datasets.find(dataset => dataset.id === builder.selectedDatasetId);
            if (!selected) throw new Error('Hãy chọn một Dataset có thể đọc được.');
            const params = selected.params || {};
            if ((params.start && params.start !== builder.form.start_date) || (params.end && params.end !== builder.form.end_date)) throw new Error('Kỳ báo cáo phải khớp chính xác với kỳ của Dataset.');
            if (builder.form.compare_start_date && params.compare === true && ((params.previous_start && params.previous_start !== builder.form.compare_start_date) || (params.previous_end && params.previous_end !== builder.form.compare_end_date))) throw new Error('Kỳ so sánh phải khớp chính xác với Dataset.');
            const payload = {
                client_id: 'client_kinderhealth',
                name: builder.form.name.trim(),
                start_date: builder.form.start_date,
                end_date: builder.form.end_date,
                default_section: 'overview',
                sections: [{ key: 'overview', dataset_id: selected.id }]
            };
            if (builder.form.compare_start_date) {
                payload.compare_start_date = builder.form.compare_start_date;
                payload.compare_end_date = builder.form.compare_end_date;
            }
            builder.saveResult = await api('/report-bundles', 'POST', payload);
            renderReportBuilder();
            toast('Đã lưu bản nháp báo cáo.');
            break;
        }
        case 'export-confirm': await createExport(id); break;
        case 'save-report': if (isDirty() || state.job) throw new Error('Áp dụng bộ lọc trước khi lưu.'); { const r = await api('/datasets/' + state.dataset.id + '/save', 'POST', {}); toast('Đã lưu bản nháp HTML.'); location.hash = 'reports'; break; }
        case 'import-reports': { const r = await api('/reports/import', 'POST', {}); toast(`Đã kiểm tra và nhập ${r.report_ids.length} báo cáo. Bản trùng được giữ nguyên.`); await navigate(); break; }
        case 'preview-report': { const r = state.reports.find(r => r.id === id); modal(r ? `${r.name} · v${r.version}` : 'Xem trước báo cáo', `${r?.origin === 'legacy' ? notice('Bản HTML từ hệ thống cũ, chưa kiểm chứng tính đầy đủ của dữ liệu. Ngày lưu không phải ngày dữ liệu.') : ''}<iframe src="/api/reports/${id}/html" sandbox="allow-scripts" title="Xem trước báo cáo"></iframe>`, `<a class="btn secondary" href="/api/reports/${id}/html" target="_blank" rel="noopener">Mở báo cáo</a><a class="btn primary" href="/api/reports/${id}/html?download=1">Tải HTML</a>`, true); break; }
        case 'report-versions': { const list = state.reports.filter(r => r.report_type === el.dataset.type).sort((a, b) => b.version - a.version); modal('Lịch sử phiên bản', table(['Phiên bản', 'Ngày lưu', 'Trạng thái', ''], list.map(r => [`v${r.version}`, time(r.created_at), r.published_at ? 'Đang xuất bản' : 'Bản lưu', button('Xem trước', 'preview-report', 'text', `data-id="${r.id}"`)]))); break; }
        case 'publish-report': { const r = state.reports.find(r => r.id === id); modal('Xuất bản báo cáo nội bộ', `<p>Chọn <strong>${esc(r.name)} · v${r.version}</strong> làm phiên bản hiện hành?</p><p class="muted">Phiên bản trước vẫn được giữ trong lịch sử. Chỉ người có quyền mới truy cập được báo cáo.</p>`, button('Hủy', 'close-modal') + button('Xuất bản nội bộ', 'publish-confirm', 'primary', `data-id="${id}"`)); break; }
        case 'publish-confirm': { const r = await api('/reports/' + id + '/publish', 'POST', {}); $('#modal').close(); toast(r.message); await navigate(); break; }
        case 'job-detail': await jobDetail(id); break;
        case 'retry-job': { const r = await api('/jobs/' + id + '/retry', 'POST', {}); $('#modal').close(); toast('Đang chạy lại tác vụ.'); location.hash = 'activity'; await navigate(); await waitJob(r.job_id); await navigate(); await jobDetail(r.job_id); break; }
        case 'process-job': await waitJob(id); await jobDetail(id); break;
        case 'seed-demo': modal('Thêm dữ liệu demo', notice('Tạo báo cáo và file Excel mô phỏng, có nhãn DEMO. Dữ liệu thật và kết nối Google được giữ nguyên.', 'blue'), button('Hủy', 'close-modal') + button('Thêm bộ demo', 'seed-demo-confirm', 'primary')); break;
        case 'seed-demo-confirm': await api('/demo/seed', 'POST', {}); $('#modal').close(); state.overview = await api('/overview'); toast('Đã thêm bộ dữ liệu demo.'); await navigate(); break;
        case 'open-dataset': $('#modal').close(); location.hash = 'analysis?dataset=' + id; break;
        case 'upload-preview': { const u = state.uploads.find(u => u.id === id); modal('Dữ liệu CSV đã kiểm tra', `<p>${esc(u.name)}</p><p class="muted">${date(u.start_date)} → ${date(u.end_date)} · ${u.locations} cơ sở</p><div class="upload-preview">${dataTable(u.preview, 'Chi tiết cơ sở')}</div>`, button('Đóng', 'close-modal'), true); break; }
        case 'analyze-upload': { const u = state.uploads.find(u => u.id === id); state.draft = { report_type: 'gmb', demo: !!u.demo, start: u.start_date, end: u.end_date, compare: false, exclude_products: false, upload_id: u.id, previous_upload_id: '' }; location.hash = 'analysis'; break; }
        case 'new-user': userModal(); break;
        case 'edit-user': userModal(id); break;
        case 'new-schedule': scheduleModal(); break;
        case 'toggle-schedule': await api('/schedules/' + id, 'PATCH', { enabled: el.dataset.enabled === 'true' }); await navigate(); break;
    }
}

document.addEventListener('click', async event => { const target = event.target.closest('[data-action]'); if (!target || target.disabled) return; event.preventDefault(); const action = target.dataset.action; const disabled = target.disabled; if (target.tagName === 'BUTTON') target.disabled = true; try { await act(action, target); } catch (err) { await handleError(err); } finally { if (target.isConnected) target.disabled = disabled; } });
document.addEventListener('submit', async event => {
    event.preventDefault(); const form = event.target; const btn = event.submitter; const text = btn?.innerHTML; if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Đang xử lý…'; } try {
        const data = new FormData(form), fields = Object.fromEntries(data.entries());
        if (form.id === 'auth-form') { if (form.dataset.setup === 'true') { await api('/auth/setup', 'POST', fields); $('#app').innerHTML = loginView(false); toast('Đã tạo tài khoản. Hãy đăng nhập để bắt đầu.'); } else { const r = await api('/auth/login', 'POST', fields); clearSessionData(); state.user = r.user; setCsrf(r.csrf); await start(); } }
        if (form.id === 'analysis-form') await runAnalysis();
        if (form.id === 'report-builder-form') { readReportBuilderForm(); validateReportBuilderForm(); state.reportBuilder.step = 2; renderReportBuilder(); }
        if (form.id === 'report-filter') { state.reportFilter = fields; $('#content').innerHTML = reportsView(state.reports, state.overview.types, state.user, state.reportFilter) + footer(); }
        if (form.id === 'upload-form') { await api('/uploads', 'POST', data); toast('CSV hợp lệ, đã lưu dữ liệu.'); await navigate(); }
        if (form.id === 'settings-form') { await api('/settings', 'PATCH', fields); toast('Đã lưu cài đặt.'); }
        if (form.id === 'user-form') { fields.allowed = data.getAll('allowed'); fields.active = form.dataset.id ? data.has('active') : true; await api('/users' + (form.dataset.id ? '/' + form.dataset.id : ''), form.dataset.id ? 'PATCH' : 'POST', fields); $('#modal').close(); toast('Đã lưu người dùng.'); if (form.dataset.id === state.user.id) { state.user = null; await start(); } else await navigate(); }
        if (form.id === 'schedule-form') { fields.compare = data.has('compare'); fields.exclude_products = data.has('exclude_products'); fields.publish = data.has('publish'); await api('/schedules', 'POST', fields); $('#modal').close(); toast('Đã tạo lịch.'); await navigate(); }
    } catch (err) { if (form.id === 'auth-form') { form.querySelector('.auth-error')?.remove(); const e = document.createElement('p'); e.className = 'auth-error'; e.setAttribute('role', 'alert'); e.textContent = err.message; form.querySelector('button[type=submit]').before(e); } else await handleError(err); } finally { if (btn?.isConnected) { btn.disabled = false; btn.innerHTML = text; updateFilterState(); } }
});

document.addEventListener('change', event => { const el = event.target; if (el.closest('#analysis-form')) { readDraft(); if (el.name === 'report_type' || el.name === 'compare' || el.name === 'demo') renderAnalysis(); else updateFilterState(); } if (el.matches('[name="report-builder-dataset"]')) { state.reportBuilder.selectedDatasetId = el.value; renderReportBuilder(); } if (el.id === 'job-status-filter') { state.jobFilter = el.value; $('#content').innerHTML = activityView(state.jobs, state.events, state.user, state.jobFilter) + footer(); } if (el.id === 'csv-file') { const name = el.files?.[0]?.name || ''; const dates = name.match(/\d{4}-\d{1,2}-\d{1,2}/g); if (dates?.length >= 2) { const iso = d => d.split('-').map((s, i) => i ? s.padStart(2, '0') : s).join('-'); $('#csv-start').value = iso(dates[0]); $('#csv-end').value = iso(dates[1]); } } });
document.addEventListener('input', event => { if (event.target.closest('#analysis-form')) { readDraft(); updateFilterState(); } });
document.addEventListener('input', event => { if (event.target.closest('#report-builder-form')) readReportBuilderForm(); });
document.addEventListener('input', event => { if (event.target.closest('#dataset-filters')) updateDatasetTable(); });
document.addEventListener('change', event => { if (event.target.closest('#dataset-filters')) updateDatasetTable(); });
function updateDatasetTable() {
    const form = $('#dataset-filters');
    const region = $('#datasets-table-region');
    if (!form || !region) return;
    const filters = Object.fromEntries(new FormData(form).entries());
    region.innerHTML = datasetsTable(state.datasets, state.overview.types, filters);
}
window.addEventListener('hashchange', () => { if ($('#modal').open) $('#modal').close(); navigate(); });
$('#modal').addEventListener('click', e => { if (e.target === $('#modal')) { const rect = e.target.getBoundingClientRect(); if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) e.target.close(); } });
start();
