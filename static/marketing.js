import { api, setCsrf } from './api.js';

const root = document.querySelector('#marketing-console');
const $ = selector => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const valueText = value => value == null ? 'Chưa có dữ liệu' : typeof value === 'number' ? value.toLocaleString('vi-VN', { maximumFractionDigits: 4 }) : String(value);
const state = { meta: null, data: null, review: null, candidate: null, approval: null, release: null, report: null, busy: false };
const statusNames = { approved_internal: 'Đã duyệt nội bộ', needs_changes: 'Cần chỉnh sửa', awaiting_review: 'Chờ duyệt', needs_data: 'Thiếu dữ liệu', release_approved: 'Đã duyệt phát hành', release_blocked: 'Đang chặn phát hành', release_review: 'Chờ duyệt phát hành', provider_origin_confirmed: 'Đã xác nhận qua adapter', lineage_consistent: 'Truy vết khớp, chưa xác nhận nguồn', draft: 'Bản nháp', provisional: 'Đã xuất bản tạm thời', final: 'Đã xuất bản chính thức' };
const issueNames = { permission_denied: 'Chưa được cấp quyền nguồn', not_configured: 'Kết nối chưa sẵn sàng', no_data: 'Chưa có dữ liệu', partial: 'Chưa đủ kỳ dữ liệu', stale: 'Có lần đồng bộ mới hơn; cần tạo Dataset mới', provider_origin_unconfirmed: 'Thiếu bằng chứng từ adapter; cần đồng bộ lại bằng kết nối thật', source_snapshot_missing: 'Thiếu snapshot nguồn', sync_failed: 'Đồng bộ thất bại', demo_data: 'Dữ liệu demo không được dùng cho phát hành thật', candidate_changed: 'Bản chờ duyệt đã bị thay đổi', origin_dataset_changed: 'Dataset gốc đã thay đổi', review_superseded: 'Có quyết định duyệt mới hơn' };
const label = value => statusNames[value] || value;
const issueList = issues => issues?.length ? `<ul class="workflow-issues">${issues.map(item => `<li>${esc(issueNames[item] || item)}</li>`).join('')}</ul>` : '';

function message(text, error = false) {
    $('#workflow-message').textContent = text;
    $('#workflow-message').dataset.error = String(error);
}

async function run(work) {
    if (state.busy) return;
    state.busy = true;
    root.setAttribute('aria-busy', 'true');
    root.querySelectorAll('button').forEach(button => { button.disabled = true; });
    message('Đang xử lý…');
    try { await work(); message('Đã cập nhật theo kết quả từ hệ thống.'); }
    catch (error) { message(error.message, true); }
    finally {
        state.busy = false;
        root.removeAttribute('aria-busy');
        root.querySelectorAll('button').forEach(button => { button.disabled = false; });
        renderState();
    }
}

function setLink(selector, path) {
    const link = $(selector);
    link.hidden = !path || !state.meta?.new_url;
    if (!link.hidden) link.href = state.meta.new_url + path;
    else link.removeAttribute('href');
}

function renderState() {
    const review = state.review;
    $('#approve-internal').disabled = !review?.checks?.can_approve_internal;
    $('#needs-changes').disabled = !review || !!review.issues?.length;
    const approved = review?.latest_review?.decision === 'approved_internal' && review.latest_review.matches_current_snapshot;
    $('#create-candidate').disabled = !approved || !review.checks.can_approve_internal;
    $('#dataset-state').innerHTML = review ? `<p>${esc(label(review.latest_review?.decision || review.review_status))}</p><p class="workflow-id">Dataset ${esc(review.dataset_id)}</p>${issueList(review.issues)}` : 'Chọn hoặc tạo Dataset trước.';
    $('#check-source').disabled = !state.candidate;
    const checks = state.approval?.checks;
    const decision = state.approval?.latest_approval;
    $('#approve-release').disabled = !checks?.provider_origin_confirmed;
    $('#block-release').disabled = !state.candidate;
    $('#create-release').disabled = !checks?.provider_origin_confirmed || decision?.decision !== 'release_approved';
    $('#source-state').innerHTML = checks ? `<p>${esc(label(state.approval.state))} · ${esc(label(checks.state))}</p>${issueList(checks.issues)}<div class="workflow-table"><table><thead><tr><th>KPI</th><th>Kiểm tra</th></tr></thead><tbody>${checks.checks.map(item => `<tr><td>${esc(item.metric_id)}</td><td>${esc(label(item.status))}${issueList(item.issues)}</td></tr>`).join('')}</tbody></table></div>` : 'Chưa có bản chờ duyệt phát hành.';
    setLink('#internal-preview', state.candidate ? '/internal-preview/' + state.candidate : null);
    const report = state.report;
    $('#create-bundle').disabled = !state.release;
    $('#publish-provisional').disabled = !report || report.status !== 'draft';
    $('#publish-final').disabled = !report || !['draft', 'provisional'].includes(report.status);
    $('#grant-access').disabled = !report;
    $('#revoke-access').disabled = !report;
    $('#publication-state').innerHTML = report ? `<p>${esc(report.name)} · revision ${report.revision} · ${esc(label(report.status))}</p><p class="workflow-id">${esc(report.id)}</p>` : state.release ? `<p>Snapshot đã sẵn sàng tạo Report Bundle.</p><p class="workflow-id">${esc(state.release.id)}</p>` : 'Chưa có snapshot phát hành.';
    setLink('#published-link', report && report.status !== 'draft' ? `/reports/${report.id}?revision=${report.revision}` : null);
}

function preview(data) {
    const content = data.marketing?.preview || data.marketing || {};
    const widgets = content.widgets || [];
    const evidence = content.evidence_cards || data.evidence || [];
    $('#snapshot-preview').innerHTML = `<h2>Nội dung snapshot</h2><p>${esc(data.params.start)} → ${esc(data.params.end)} · So sánh ${esc(data.params.previous_start)} → ${esc(data.params.previous_end)}</p><p class="workflow-id">${esc(data.id)}</p>
        <div class="workflow-table"><table><thead><tr><th>KPI</th><th>Kỳ này</th><th>Kỳ trước</th><th>Đơn vị</th><th>Trạng thái</th></tr></thead><tbody>${widgets.map(item => `<tr><td>${esc(item.label || item.metric_id)}</td><td>${esc(valueText(item.value))}</td><td>${esc(valueText(item.comparison?.previous_value))}</td><td>${esc(item.unit)}</td><td>${esc(item.status)}</td></tr>`).join('')}</tbody></table></div>
        ${widgets.length ? '' : '<p>Chưa có KPI trong snapshot này.</p>'}<details><summary>Bằng chứng và truy vết (${evidence.length})</summary>${evidence.map(item => `<p><strong>${esc(item.metric_id)}</strong> · ${esc(item.verification || item.status)}<br><span class="workflow-id">Evidence: ${esc(item.evidence_id)} · Asset: ${esc(item.asset_id)} · Sync: ${esc(item.lineage?.sync_run_ids?.join(', '))}</span></p>`).join('') || '<p>Chưa có bằng chứng.</p>'}</details>`;
    const opportunities = content.opportunity_candidates || [];
    $('#opportunity-choices').innerHTML = state.candidate && opportunities.length ? `<h3>Đề xuất đưa vào bản phát hành</h3><p>Chọn từng đề xuất sau khi đọc bằng chứng. Không chọn nghĩa là không phát hành đề xuất đó.</p>${opportunities.map(item => `<label class="opportunity-choice"><input type="checkbox" name="opportunity" value="${esc(item.id)}"><span><strong>${esc(item.title)}</strong><br>${esc(item.suggested_action)}<br><small>Bằng chứng: ${esc((item.evidence || []).map(ref => ref.metric_id).join(', '))}</small></span></label>`).join('')}` : '<p>Không có đề xuất chờ chọn trong snapshot này.</p>';
}

async function refresh() {
    const [meta, reports, users] = await Promise.all([api('/marketing/workflow'), api('/report-bundles'), api('/users')]);
    state.meta = meta;
    const selected = $('#snapshot-id').value;
    $('#snapshot-id').innerHTML = '<option value="">Chọn snapshot đã lưu</option>' + meta.snapshots.map(item => `<option value="${esc(item.id)}">${esc(item.source)} · ${esc(item.start)} → ${esc(item.end)} · ${esc(item.kind.replace('marketing_', '').replace('_v1', ''))} · ${esc(item.id.slice(0, 8))}</option>`).join('');
    $('#snapshot-id').value = selected;
    $('#existing-report').innerHTML = '<option value="">Chọn báo cáo</option>' + reports.map(item => `<option value="${esc(item.report_id)}:${item.revision}">${esc(item.name)} · r${item.revision} · ${esc(label(item.status))}</option>`).join('');
    $('#viewer').innerHTML = '<option value="">Chọn tài khoản</option>' + users.filter(user => user.active).map(user => `<option value="${esc(user.id)}">${esc(user.name)} (${esc(user.email)})</option>`).join('');
    if (!$('#source').options.length) $('#source').innerHTML = meta.sources.map(item => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join('');
    $('#asset').innerHTML = '<option value="">Tự chọn nếu chỉ có một tài sản phù hợp</option>' + meta.assets.map(item => `<option value="${esc(item.id)}">${esc(item.name)} · ${esc(item.asset_type)}</option>`).join('');
}

async function loadSnapshot(id) {
    const data = await api('/datasets/' + encodeURIComponent(id));
    Object.assign(state, { data, review: null, candidate: null, approval: null, release: null, report: null });
    $('#access-list').textContent = '';
    if (data.dataset_kind === 'marketing_internal_preview_v1') state.review = await api(`/marketing/datasets/${id}/review`);
    else if (data.dataset_kind === 'marketing_release_candidate_v1') {
        state.candidate = id;
        state.review = await api(`/marketing/datasets/${data.release_candidate.origin_dataset_id}/review`);
        state.approval = await api(`/marketing/release-candidates/${id}/approval`);
    } else if (data.dataset_kind === 'marketing_release_snapshot_v1') state.release = data;
    else throw new Error('Snapshot không thuộc quy trình Marketing.');
    preview(data);
    const selected = JSON.parse(state.approval?.latest_approval?.approved_opportunity_ids || '[]');
    root.querySelectorAll('[name="opportunity"]').forEach(input => { input.checked = selected.includes(input.value); });
    $('#snapshot-id').value = id;
}

async function loadReport(id, revision) {
    const bundle = await api(`/report-bundles/${id}?revision=${revision}`);
    state.report = bundle.report;
    $('#min-revision').value = bundle.report.revision;
    $('#max-revision').value = bundle.report.revision;
    const grants = await api(`/report-bundles/${id}/access`);
    $('#access-list').innerHTML = `<h3>Quyền hiện tại</h3>${grants.map(item => `<p>${esc(item.email)} · r${item.min_revision}–${item.max_revision ?? 'các bản sau'} · ${item.active ? 'Đang cấp' : 'Đã thu hồi'}</p>`).join('') || '<p>Chưa cấp quyền xem riêng cho tài khoản nào.</p>'}`;
}

function submit(id, handler) {
    $(id).addEventListener('submit', event => {
        event.preventDefault();
        const data = new FormData(event.target);
        const decision = event.submitter?.value;
        run(() => handler(data, decision));
    });
}

submit('#dataset-form', async data => {
    const payload = Object.fromEntries(data);
    if (!payload.asset_id) delete payload.asset_id;
    const created = await api('/marketing/datasets', 'POST', payload);
    await refresh(); await loadSnapshot(created.dataset_id);
});
submit('#resume-form', () => loadSnapshot($('#snapshot-id').value));
submit('#report-resume-form', () => { const [id, revision] = $('#existing-report').value.split(':'); return loadReport(id, revision); });
submit('#review-form', async (data, decision) => {
    const id = state.review.dataset_id;
    await api(`/marketing/datasets/${id}/review`, 'POST', { decision, note: data.get('note'), expected_sha256: state.review.dataset_sha256 });
    await loadSnapshot(id);
});
$('#create-candidate').addEventListener('click', () => run(async () => {
    const result = await api(`/marketing/datasets/${state.review.dataset_id}/release-candidates`, 'POST', { expected_sha256: state.review.dataset_sha256, expected_review_id: state.review.latest_review.id });
    await refresh(); await loadSnapshot(result.release_dataset_id);
}));
$('#check-source').addEventListener('click', () => run(async () => { state.approval = await api(`/marketing/release-candidates/${state.candidate}/approval`); }));
submit('#release-review-form', async (data, decision) => {
    const checks = state.approval.checks;
    const approved = decision === 'release_approved' ? [...root.querySelectorAll('[name="opportunity"]:checked')].map(input => input.value) : [];
    await api(`/marketing/release-candidates/${state.candidate}/approval`, 'POST', { decision, note: data.get('note'), expected_candidate_sha256: checks.candidate_sha256, expected_dataset_sha256: checks.dataset_sha256, expected_review_id: checks.internal_review_id, approved_opportunity_ids: approved });
    state.approval = await api(`/marketing/release-candidates/${state.candidate}/approval`);
});
$('#create-release').addEventListener('click', () => run(async () => {
    const result = await api(`/marketing/release-candidates/${state.candidate}/release-snapshots`, 'POST', { expected_approval_id: state.approval.latest_approval.id, expected_candidate_sha256: state.approval.checks.candidate_sha256 });
    await refresh(); await loadSnapshot(result.dataset_id);
}));
submit('#bundle-form', async data => {
    const p = state.release.params;
    const section = ['ga4', 'gsc', 'keywords'].includes(p.source) ? 'seo' : ({ tiktok_ads: 'tiktok', tiktok_organic: 'tiktok' }[p.source] || p.source);
    const result = await api('/report-bundles', 'POST', { client_id: state.meta.client_id, name: data.get('name'), start_date: p.start, end_date: p.end, compare_start_date: p.previous_start, compare_end_date: p.previous_end, default_section: section, sections: [{ key: section, dataset_id: state.release.id }] });
    await refresh(); await loadReport(result.report_id, result.revision);
});
for (const status of ['provisional', 'final']) $(`#publish-${status}`).addEventListener('click', () => run(async () => {
    const { id, revision } = state.report;
    await api(`/report-bundles/${id}/revisions/${revision}/publish`, 'POST', { status });
    await refresh(); await loadReport(id, revision);
}));
submit('#access-form', async (_, active) => {
    await api(`/report-bundles/${state.report.id}/access`, 'POST', { user_id: $('#viewer').value, min_revision: Number($('#min-revision').value), max_revision: $('#max-revision').value ? Number($('#max-revision').value) : null, active: active === 'true' });
    await loadReport(state.report.id, state.report.revision);
});
$('#refresh-workflow').addEventListener('click', () => run(refresh));

run(async () => {
    const session = await api('/auth/me');
    if (!session.user || session.user.role !== 'admin') throw new Error('Cần đăng nhập tài khoản Admin. Quay lại trang chính để đăng nhập.');
    setCsrf(session.csrf);
    await refresh();
});
