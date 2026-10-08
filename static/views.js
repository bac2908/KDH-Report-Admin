import { esc, date, time, num, icon, badge, empty, heading, button, notice, table, jobTable, chart, sourceNames, roles, kindNames } from './ui.js';

export const pages = { overview: 'Tổng quan', clients: 'Khách hàng', connections: 'Kết nối nền tảng', assets: 'Tài sản dữ liệu', sync: 'Đồng bộ dữ liệu', analysis: 'Phân tích & kiểm tra', datasets: 'Dataset', 'report-builder': 'Report Builder', reports: 'Báo cáo', activity: 'Lịch sử hoạt động', uploads: 'Dữ liệu đầu vào', schedules: 'Lịch tự động', users: 'Người dùng', settings: 'Cài đặt' };
export const navIcons = { overview: 'dashboard', clients: 'users', connections: 'link', assets: 'folder', sync: 'refresh', analysis: 'chart', datasets: 'folder', 'report-builder': 'file', reports: 'file', activity: 'history', uploads: 'upload', schedules: 'clock', users: 'users', settings: 'settings' };
export const connectionPlatforms = { google: 'Google', facebook: 'Facebook', tiktok: 'TikTok' };
export function loginView(setup = false, error = '') {
    return `<main class="auth-page login-screen"><section class="login-card">
        <header class="login-brand"><span class="login-brand-mark">${icon('chart', 34)}</span><div><strong>KDH-Report-Admin</strong><span>Hệ thống quản trị dữ liệu và báo cáo marketing</span></div></header>
        <form id="auth-form" class="auth-form login-form" data-setup="${setup}">
            <div class="login-heading"><h1>${setup ? 'Khởi tạo quản trị viên' : 'Đăng nhập'}</h1><p>${setup ? 'Tạo tài khoản quản trị đầu tiên trên máy chủ. Đây là bước thiết lập một lần.' : 'Đăng nhập để tiếp tục quản lý dữ liệu và báo cáo.'}</p></div>
            ${error ? `<div class="auth-error" role="alert">${esc(error)}</div>` : ''}
            ${setup ? '<div class="field"><label for="auth-name">Tên hiển thị</label><input id="auth-name" name="name" required maxlength="100" autocomplete="name" placeholder="Tên quản trị viên"></div>' : ''}
            <div class="field"><label for="auth-email">Email</label><input id="auth-email" name="email" type="email" required autocomplete="username" placeholder="Nhập địa chỉ email"></div>
            <div class="field"><label for="auth-password">Mật khẩu</label><div class="password-field"><input id="auth-password" name="password" type="password" required ${setup ? 'minlength="12"' : ''} maxlength="200" autocomplete="${setup ? 'new-password' : 'current-password'}" placeholder="${setup ? 'Tối thiểu 12 ký tự' : 'Nhập mật khẩu'}"><button class="icon-btn" type="button" data-action="toggle-password" aria-label="Hiện hoặc ẩn mật khẩu">${icon('eye')}</button></div>${setup ? '<small class="login-field-note">Mật khẩu cần có ít nhất 12 ký tự.</small>' : ''}</div>
            <div class="auth-help login-help">${setup ? '<span>Thiết lập bảo mật tài khoản quản trị</span>' : button('Quên mật khẩu?', 'forgot', 'text', 'type="button"')}</div>
            <button class="btn primary login-submit" type="submit">${setup ? 'Tạo tài khoản quản trị' : 'Đăng nhập'}</button>
            ${setup ? '' : `<div class="login-assurance">${icon('shield', 15)}<span>Tài khoản ứng dụng và kết nối dữ liệu Google được quản lý riêng.</span></div>`}
        </form>
    </section></main>`;
}

export function shell(user, overview, page, connectionPlatform = null) {
    const can = k => !['connections', 'assets', 'users', 'schedules', 'settings', 'report-builder'].includes(k) || user.role === 'admin';
    const link = k => can(k) ? `<a class="nav-link ${page === k ? 'active' : ''}" href="#${k}" ${page === k ? 'aria-current="page"' : ''}>${icon(navIcons[k], 18)}<span>${pages[k]}</span></a>` : '';
    const navGroup = (label, entries) => `<nav class="nav-group"><div class="nav-label">${label}</div>${entries.map(link).join('')}</nav>`;
    return `<aside class="sidebar" id="sidebar"><a class="brand" href="#overview"><img src="/static/logo.svg" width="35" alt=""><div><strong>KDH-Report-Admin</strong><small>Hệ thống quản trị dữ liệu và báo cáo marketing</small></div></a><div class="sidebar-nav">
${navGroup('TỔNG QUAN', ['overview'])}${navGroup('DỮ LIỆU', ['clients', 'connections', 'assets', 'sync', 'analysis', 'datasets'])}${navGroup('BÁO CÁO', ['report-builder', 'reports'])}${navGroup('VẬN HÀNH', ['activity', 'schedules', 'users', 'settings'])}</div><div class="sidebar-bottom"><div class="sidebar-status"><div><span class="dot"></span>${overview.google_connected ? 'Đã kết nối Google' : 'Chưa kết nối Google'}</div><p>Kiểm tra độ mới riêng từng nguồn</p></div><div class="version"><span>Hệ thống KDH</span><span>v1.0</span></div></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb"><button class="icon-btn mobile-menu" data-action="menu" aria-label="Mở menu">${icon('menu')}</button><span>KinderHealth</span><span>›</span><strong>${pages[page] || pages.overview}${connectionPlatform ? ` · ${connectionPlatforms[connectionPlatform]}` : ''}</strong></div><div class="topbar-right"><a class="btn secondary" href="${esc(overview.dashboard_url)}" target="_blank" rel="noopener noreferrer">${icon('external', 14)} Mở dashboard hiện tại</a>${overview.demo_enabled ? '<span class="badge blue">DEMO có sẵn</span>' : ''}<div class="account"><div class="avatar">${esc(user.name.charAt(0).toUpperCase())}</div><div class="account-name">${esc(user.name)}<small>${roles[user.role]}</small></div><button class="icon-btn" data-action="logout" title="Đăng xuất" aria-label="Đăng xuất">${icon('logout', 17)}</button></div></div></header><main class="content" id="content"></main></div>`;
}

export function skeletonView(page, datasetDetail = false) {
    if (page === 'datasets' && datasetDetail) {
        return heading('QUẢN LÝ DỮ LIỆU', 'Dataset', 'Các snapshot dữ liệu bất biến được tạo sau mỗi lần phân tích.') +
            `<section class="card">${empty('Chi tiết Dataset chưa khả dụng', 'Trang danh sách đã có sẵn. Màn hình chi tiết Dataset sẽ được triển khai ở giai đoạn tiếp theo.', `<a class="btn secondary" href="#datasets">Quay lại danh sách</a>`)}</section>`;
    }
    const copy = {
        datasets: ['QUẢN LÝ DỮ LIỆU', 'Dataset', 'Dataset sẽ cung cấp dữ liệu đầu vào cho quy trình tạo báo cáo.', 'Chưa có Dataset', 'Chưa có Dataset để hiển thị. Chức năng này chưa được cung cấp bởi backend.'],
        'report-builder': ['THIẾT KẾ BÁO CÁO', 'Report Builder', 'Trình tạo báo cáo chưa được triển khai.', 'Report Builder chưa khả dụng', 'Các báo cáo đã lưu vẫn có thể xem tại mục Báo cáo.']
    }[page];
    if (!copy) throw new Error(`Không có nội dung skeleton cho trang "${page}".`);
    return heading(copy[0], pages[page], copy[2]) + `<section class="card">${empty(copy[3], copy[4])}</section>`;
}

function reportBuilderPeriodState(dataset, form) {
    const params = dataset?.params || {};
    const mismatches = [];
    if (params.start && form.start_date && params.start !== form.start_date) mismatches.push('Kỳ bắt đầu phải khớp chính xác với Dataset.');
    if (params.end && form.end_date && params.end !== form.end_date) mismatches.push('Kỳ kết thúc phải khớp chính xác với Dataset.');
    if (form.compare_start_date && params.previous_start && params.previous_start !== form.compare_start_date) mismatches.push('Ngày bắt đầu kỳ so sánh phải khớp chính xác với Dataset.');
    if (form.compare_end_date && params.previous_end && params.previous_end !== form.compare_end_date) mismatches.push('Ngày kết thúc kỳ so sánh phải khớp chính xác với Dataset.');
    return mismatches;
}

const reportSectionDefinitions = [
    { key: 'overview', label: 'Tổng quan', description: 'Tổng quan báo cáo, tham chiếu một Dataset thật theo yêu cầu API hiện tại.', reportTypes: null },
    { key: 'seo', label: 'Website Traffic & SEO', description: 'Phần trình bày SEO; có thể sử dụng snapshot SEO gồm GA4, Search Console và Keywords.', reportTypes: ['seo'] },
    { key: 'facebook_content', label: 'Facebook Content', description: 'Nội dung Facebook; cần Dataset loại Facebook Content.', reportTypes: ['facebook-content', 'facebook-content-30d', 'facebook-content-6m'] },
    { key: 'facebook_ads', label: 'Facebook Ads', description: 'Quảng cáo Facebook; cần Dataset loại Facebook Ads.', reportTypes: ['facebook-ads'] },
    { key: 'tiktok', label: 'TikTok', description: 'Nội dung hoặc quảng cáo TikTok; cần Dataset TikTok.', reportTypes: ['tiktok'] },
    { key: 'youtube', label: 'YouTube', description: 'Nội dung YouTube; cần Dataset YouTube.', reportTypes: ['youtube'] },
    { key: 'gmb', label: 'Google Maps & Hồ sơ doanh nghiệp', description: 'Dữ liệu Google Business Profile.', reportTypes: ['gmb'] }
];

function reportBuilderDatasetsForPeriod(builder) {
    return builder.datasets.filter(dataset => {
        const params = dataset.params || {};
        const owners = [dataset.client_id, params.client_id].filter(Boolean);
        const comparisonMismatch = builder.form.compare_start_date && params.compare === true &&
            ((params.previous_start && params.previous_start !== builder.form.compare_start_date) ||
                (params.previous_end && params.previous_end !== builder.form.compare_end_date));
        return dataset.id && params.start === builder.form.start_date && params.end === builder.form.end_date &&
            owners.every(owner => owner === 'client_kinderhealth') && !comparisonMismatch;
    });
}

export function reportBuilderSectionOptions(builder) {
    const periodDatasets = reportBuilderDatasetsForPeriod(builder);
    return reportSectionDefinitions.map(definition => {
        const compatibleDatasets = periodDatasets.filter(dataset => !definition.reportTypes || definition.reportTypes.includes(dataset.report_type || dataset.params?.report_type));
        const backendSupportsKey = !definition.key.includes('_');
        return {
            ...definition,
            backendSupportsKey,
            compatibleDatasets,
            datasets: backendSupportsKey ? compatibleDatasets : []
        };
    });
}

export function reportBuilderConfigValidation(builder) {
    const errors = [];
    const sections = builder.configuration?.sections || [];
    const options = reportBuilderSectionOptions(builder);
    if (!sections.length) errors.push('Chọn ít nhất một section để đưa vào báo cáo.');
    if (new Set(sections.map(section => section.key)).size !== sections.length) errors.push('Thứ tự section không được chứa mục trùng lặp.');
    const included = new Set(sections.map(section => section.key));
    if (!included.has(builder.configuration?.defaultSection)) errors.push('Chọn một section đang được đưa vào báo cáo làm trang mặc định.');
    for (const section of sections) {
        const definition = options.find(option => option.key === section.key);
        if (!definition) {
            errors.push(`${section.key}: không phải section trình bày được hỗ trợ.`);
            continue;
        }
        if (!definition?.datasets.some(dataset => dataset.id === section.dataset_id)) {
            errors.push(`${definition?.label || section.key}: chọn Dataset thật có loại báo cáo và kỳ phù hợp.`);
        }
    }
    return errors;
}

export function reportBuilderPeriodWarning(dataset, form) {
    if (!dataset) return '';
    const mismatches = reportBuilderPeriodState(dataset, form);
    if (mismatches.length) return mismatches.map(message => notice(message, 'red')).join('');
    const params = dataset.params || {};
    const incomplete = [];
    if (!params.start || !params.end) incomplete.push('Kỳ của Dataset chưa đủ metadata để xác minh đầy đủ.');
    if (form.compare_start_date && params.compare !== true) incomplete.push('Dataset chưa xác nhận có dữ liệu kỳ so sánh; backend sẽ đánh giá chất lượng khi lưu.');
    else if (form.compare_start_date && (!params.previous_start || !params.previous_end)) incomplete.push('Dataset thiếu metadata kỳ so sánh để xác minh đầy đủ.');
    return incomplete.map(message => notice(message, 'amber')).join('');
}

function reportPreviewSections(bundle) {
    const sectionData = bundle?.sections && typeof bundle.sections === 'object' ? bundle.sections : {};
    const orderedKeys = Array.isArray(bundle?.navigation?.sections)
        ? bundle.navigation.sections
        : Object.entries(sectionData).sort((a, b) => (a[1]?.position ?? 0) - (b[1]?.position ?? 0)).map(([key]) => key);
    return orderedKeys.map(key => ({ ...(sectionData[key] || {}), key }));
}

function reportPreviewWarnings(builder, bundle, sections, datasets, datasetErrors) {
    const warnings = [];
    const add = value => { if (typeof value === 'string' && value.trim()) warnings.push(value.trim()); };
    for (const warning of bundle?.quality?.warnings || []) add(warning);
    if (bundle?.quality?.status !== 'complete') add(`Chất lượng Report Bundle: ${bundle?.quality?.status || 'chưa xác định'}.`);
    const included = new Set(sections.map(section => section.key));
    if (!included.size) add('Bản nháp chưa có section được đưa vào báo cáo.');
    if (!included.has(bundle?.navigation?.default_section)) add('Trang mặc định không nằm trong danh sách section được đưa vào báo cáo.');
    const knownKeys = new Set(reportSectionDefinitions.map(section => section.key));
    for (const section of sections) {
        if (!knownKeys.has(section.key)) add(`Section "${section.key}" không thuộc registry trình bày hiện tại.`);
        if (!section.dataset_id) add(`${section.key}: thiếu Dataset ID.`);
        if (section.quality?.warnings) for (const warning of section.quality.warnings) add(`${section.key}: ${warning}`);
        if (!section.dataset_id || datasetErrors[section.dataset_id]) {
            add(`${section.key}: ${datasetErrors[section.dataset_id] || 'Không có Dataset để tải.'}`);
            continue;
        }
        const dataset = datasets[section.dataset_id];
        if (!dataset) continue;
        for (const warning of dataset.warnings || []) add(`${section.key}: ${warning}`);
        const params = dataset.params || {};
        const reportPeriod = bundle.period || {};
        if (params.start !== reportPeriod.start || params.end !== reportPeriod.end) {
            add(`Dataset ${section.key} không trùng hoàn toàn với kỳ báo cáo.`);
        }
        if (dataset.exportable !== true) add(`Dataset ${section.key} cần kiểm tra theo trạng thái backend.`);
        if (!Object.keys(dataset.sources || {}).length) add(`Dataset ${section.key} không có dữ liệu nguồn.`);
        const hasComparison = !!bundle.comparison;
        if (hasComparison && (params.compare !== true ||
            params.previous_start !== bundle.comparison.start ||
            params.previous_end !== bundle.comparison.end)) {
            add(`Dataset ${section.key} thiếu hoặc không khớp kỳ so sánh.`);
        }
        for (const [sourceKey, source] of Object.entries(dataset.sources || {})) {
            if (source?.status !== 'ready') add(`${section.key} · ${sourceNames[sourceKey] || source?.source || sourceKey}: ${source?.status || 'chưa xác định'}.`);
            add(source?.error);
            for (const warning of source?.warnings || []) add(warning);
        }
    }
    if (builder.previewValidationErrors) for (const error of builder.previewValidationErrors) add(error);
    return [...new Set(warnings)];
}

function reportPreviewSource(sourceKey, source, params) {
    source = source && typeof source === 'object' ? source : {};
    if (['ga4', 'gsc', 'keywords', 'gmb'].includes(sourceKey)) return sourceSection(sourceKey, source, params, true);
    const rows = source.entries || source.daily || source.queries || [];
    const totals = source.totals && Object.keys(source.totals).length ? dataTable([source.totals], 'Chỉ số trong Dataset') : '';
    return `<section class="source-section"><div class="section-title"><h3>${esc(sourceNames[sourceKey] || source.source || sourceKey)}</h3>${source.status ? badge(source.status) : ''}</div>${source.error ? notice(source.error, 'red') : ''}${(source.warnings || []).map(warning => notice(warning, 'amber')).join('')}${totals}${rows.length ? dataTable(rows, 'Dữ liệu có trong Dataset') : empty('Không có dữ liệu chi tiết', 'Dataset không chứa hàng dữ liệu để xem trước.')}</section>`;
}

export function reportBuilderPreviewView(builder, types) {
    const preview = builder.preview;
    if (builder.previewLoading) return `<section class="card report-builder-card"><div class="empty" role="status"><span class="spinner"></span><h2>Đang tải bản xem trước</h2><p>Đang đọc Report Bundle và các Dataset snapshot đã gán.</p></div><div class="report-builder-actions">${button('Quay lại cấu hình', 'report-builder-preview-back', 'secondary')}</div></section>`;
    if (builder.previewError) {
        return `<section class="card report-builder-card">${notice(builder.previewError, 'red')}<div class="report-builder-actions">${button('Quay lại cấu hình', 'report-builder-preview-back', 'secondary')}</div></section>`;
    }
    const bundle = preview?.bundle;
    if (!bundle) return `<section class="card report-builder-card">${notice('Không có bản xem trước đã tải.', 'amber')}<div class="report-builder-actions">${button('Quay lại cấu hình', 'report-builder-preview-back', 'secondary')}</div></section>`;
    const report = bundle.report || {};
    const sections = reportPreviewSections(bundle);
    const datasets = preview.datasets || {};
    const datasetErrors = preview.datasetErrors || {};
    const uniqueIds = [...new Set(sections.map(section => section.dataset_id).filter(Boolean))];
    const loadedDatasets = uniqueIds.map(id => datasets[id]).filter(Boolean);
    const sources = loadedDatasets.flatMap(dataset => Object.values(dataset.sources || {}));
    const readySources = sources.filter(source => source?.status === 'ready').length;
    const warnings = reportPreviewWarnings(builder, bundle, sections, datasets, datasetErrors);
    const invalid = (builder.previewValidationErrors || []).length > 0;
    const period = bundle.period || {};
    const comparison = bundle.comparison;
    const orderedKeys = new Set(sections.map(section => section.key));
    const invalidDefault = !orderedKeys.has(bundle.navigation?.default_section);
    const reportTypeLabel = type => types.find(item => item.id === type)?.label || type || '—';
    const sectionCards = invalid ? '' : sections.map((section, index) => {
        const definition = reportSectionDefinitions.find(item => item.key === section.key);
        const datasetId = section.dataset_id || '';
        const dataset = datasets[datasetId];
        const params = dataset?.params || {};
        const sourceParams = {
            ...params, compare: !!comparison && params.compare === true &&
                params.previous_start === comparison.start && params.previous_end === comparison.end
        };
        const type = dataset?.report_type || params.report_type || section.report_type;
        const sectionWarnings = [];
        if (datasetErrors[datasetId]) sectionWarnings.push(datasetErrors[datasetId]);
        if (!datasetId) sectionWarnings.push('Section này chưa có Dataset ID.');
        if (dataset?.exportable === false) sectionWarnings.push('Dataset cần kiểm tra theo trạng thái backend.');
        const sourceKeys = Object.keys(dataset?.sources || {});
        const content = section.key === 'overview'
            ? `<div class="report-preview-overview-metrics"><article><span>Kỳ dữ liệu</span><strong>${period.start && period.end ? `${date(period.start)} → ${date(period.end)}` : '—'}</strong></article><article><span>Section trong báo cáo</span><strong>${sections.length}</strong></article><article><span>Dataset snapshot</span><strong>${uniqueIds.length}</strong></article><article><span>Nguồn sẵn sàng</span><strong>${readySources} / ${sources.length}</strong></article><article><span>Cảnh báo</span><strong>${warnings.length}</strong></article></div>`
            : dataset
                ? sourceKeys.map(key => reportPreviewSource(key, dataset.sources[key], sourceParams)).join('') || empty('Không có dữ liệu nguồn', 'Dataset không chứa nguồn dữ liệu để xem trước.')
                : empty('Không tải được Dataset', 'Section vẫn được giữ trong thứ tự đã lưu; nội dung không thể hiển thị khi Dataset không khả dụng.');
        const status = dataset ? dataset.exportable === true ? '<span class="badge green">Hợp lệ</span>' : dataset.exportable === false ? '<span class="badge amber">Cần kiểm tra</span>' : '<span class="badge neutral">Chưa xác định</span>' : '<span class="badge red">Không khả dụng</span>';
        const compactId = datasetId.length > 18 ? `${datasetId.slice(0, 8)}…${datasetId.slice(-6)}` : datasetId || '—';
        const sourceContent = sectionWarnings.map(warning => notice(warning, 'amber')).join('');
        return `<article class="report-preview-section" id="report-preview-${esc(section.key)}"><header><span class="report-section-position">${index + 1}</span><div><span class="eyebrow">SECTION ${index + 1}</span><h2>${esc(definition?.label || section.key)}</h2></div>${bundle.navigation?.default_section === section.key ? '<span class="badge blue report-preview-default">★ Trang mặc định</span>' : ''}</header><dl class="report-preview-technical"><div><dt>Dataset ID</dt><dd class="code" title="${esc(datasetId)}">${esc(compactId)}</dd></div><div><dt>Loại Dataset</dt><dd>${esc(reportTypeLabel(type))}</dd></div><div><dt>Kỳ dữ liệu</dt><dd>${params.start || params.end ? `${date(params.start)} → ${date(params.end)}` : '—'}</dd></div><div><dt>Chất lượng</dt><dd>${status}</dd></div><div><dt>Nguồn trong snapshot</dt><dd>${sourceKeys.length ? sourceKeys.map(key => esc(sourceNames[key] || key)).join(', ') : '—'}</dd></div></dl>${sourceContent}<div class="report-preview-content">${content}</div></article>`;
    }).join('');
    const invalidNotices = (builder.previewValidationErrors || []).map(message => notice(message, 'red')).join('');
    const summary = `<section class="report-preview-summary"><div><span>Tên báo cáo</span><strong>${esc(report.name || '—')}</strong></div><div><span>Khách hàng</span><strong>${esc(bundle.client?.name || '—')}</strong></div><div><span>Kỳ báo cáo</span><strong>${period.start && period.end ? `${date(period.start)} → ${date(period.end)}` : '—'}</strong></div><div><span>Kỳ so sánh</span><strong>${comparison?.start && comparison?.end ? `${date(comparison.start)} → ${date(comparison.end)}` : 'Không cấu hình'}</strong></div><div><span>Revision</span><strong>${report.revision ?? '—'}</strong></div><div><span>Trạng thái</span><strong>${report.status === 'draft' ? '<span class="badge amber">BẢN NHÁP</span>' : '<span class="badge neutral">Chỉ hỗ trợ bản nháp</span>'}</strong></div>${bundle.freshness?.generated_at ? `<div><span>Snapshot tạo lúc</span><strong>${time(bundle.freshness.generated_at)}</strong></div>` : ''}</section>`;
    const quality = `<section class="report-preview-quality"><header><div><span class="eyebrow">DATA QUALITY</span><h2>Chất lượng dữ liệu</h2></div><span class="badge ${warnings.length ? 'amber' : 'green'}">${warnings.length ? 'Cần kiểm tra dữ liệu' : 'Không có cảnh báo từ snapshot'}</span></header><div class="report-preview-quality-grid"><article><span>Section</span><strong>${sections.length}</strong></article><article><span>Dataset hợp lệ</span><strong>${loadedDatasets.filter(dataset => dataset.exportable === true).length} / ${uniqueIds.length}</strong></article><article><span>Nguồn sẵn sàng</span><strong>${readySources} / ${sources.length}</strong></article><article><span>Cảnh báo</span><strong>${warnings.length}</strong></article></div>${warnings.length ? `<div class="report-preview-warnings" role="status">${warnings.map(warning => notice(warning, 'amber')).join('')}</div>` : ''}</section>`;
    const navigation = `<nav class="report-preview-navigation" aria-label="Thứ tự section">${sections.map((section, index) => {
        const definition = reportSectionDefinitions.find(item => item.key === section.key);
        return `<button type="button" class="btn text" data-action="report-preview-section" data-target="report-preview-${esc(section.key)}">${index + 1}. ${esc(definition?.label || section.key)}${bundle.navigation?.default_section === section.key ? ' ★' : ''}</button>`;
    }).join('')}</nav>`;
    const canvas = invalid || report.status !== 'draft' || invalidDefault
        ? `<section class="report-preview-blocked">${invalidNotices || notice('Cấu hình section không hợp lệ. Quay lại cấu hình để sửa trước khi xem nội dung.', 'red')}${report.status !== 'draft' ? notice('Bước xem trước này chỉ hỗ trợ Report Bundle ở trạng thái DRAFT.', 'amber') : ''}</section>`
        : `<section class="report-preview-canvas"><div class="report-preview-watermark">BẢN XEM TRƯỚC · ADMIN</div>${sectionCards || empty('Chưa có section', 'Bản nháp hiện chưa có section để xem trước.')}</section>`;
    const assignments = `<ol class="report-preview-assignments">${sections.map(section => {
        const definition = reportSectionDefinitions.find(item => item.key === section.key);
        return `<li><strong>${esc(definition?.label || section.key)}</strong>${section.key === bundle.navigation?.default_section ? '<span class="badge blue">Trang mặc định</span>' : ''}<span class="code">${esc(section.dataset_id || 'Chưa gán Dataset')}</span></li>`;
    }).join('')}</ol>`;
    return `<section class="card report-builder-card report-builder-preview"><div class="report-builder-card-heading"><span class="eyebrow">BƯỚC 4 · XEM TRƯỚC</span><h2>Xem trước nội dung báo cáo</h2><p>Kiểm tra cấu trúc và dữ liệu snapshot đã lưu. Đây là bản xem trước trong Admin; báo cáo chưa được xuất bản.</p></div>${notice('Đây là bản xem trước trong Admin. Báo cáo chưa được xuất bản.', 'blue')}<div class="report-preview-workspace"><aside class="report-preview-config" aria-label="Tóm tắt cấu hình"><h3>Tóm tắt cấu hình báo cáo</h3>${summary}<h3>Section &amp; Dataset</h3>${assignments}</aside><div class="report-preview-document"><header><h3>Xem trước báo cáo</h3><span class="badge neutral">Chỉ đọc</span></header>${navigation}${invalidDefault ? notice('Cấu hình trang mặc định không hợp lệ. Preview nội dung bị khóa cho đến khi sửa cấu hình.', 'red') : ''}${canvas}</div><aside class="report-preview-inspection" aria-label="Chất lượng snapshot">${quality}</aside></div><div class="report-builder-actions">${button('Quay lại chọn Dataset', 'report-builder-preview-back-dataset', 'secondary')}${button('Quay lại cấu hình', 'report-builder-preview-back', 'primary')}</div></section>`;
}

export function reportBuilderView(builder, types) {
    const form = builder.form;
    const selected = builder.datasets.find(dataset => dataset.id === builder.selectedDatasetId);
    const steps = ['Thông tin báo cáo', 'Chọn Dataset', 'Cấu hình nội dung', 'Xem trước'];
    const currentStep = Math.min(Math.max(Number(builder.step) || 1, 1), 4);
    const stepper = `<ol class="report-builder-stepper">${steps.map((label, index) => {
        const number = index + 1;
        const future = number === 4 && currentStep < 4;
        const active = number === currentStep;
        const complete = number < currentStep;
        const upcoming = number > currentStep;
        return `<li class="${active ? 'active' : complete ? 'complete' : 'upcoming'} ${future ? 'disabled' : ''}" ${active ? 'aria-current="step"' : ''} ${upcoming ? 'aria-disabled="true"' : ''}><span>${complete ? icon('check', 14) : number}</span><strong>${label}</strong></li>`;
    }).join('')}</ol>`;
    const top = heading('THIẾT KẾ BÁO CÁO', 'Report Builder', 'Tạo bản nháp từ Dataset snapshot bất biến và kiểm tra nội dung trước các bước tiếp theo.', `<a class="btn secondary" href="#reports">Xem báo cáo</a>`);
    const errors = [
        builder.preselectionError ? notice(builder.preselectionError, 'amber') : '',
        builder.loadErrors.length ? notice(`${builder.loadErrors.length} Dataset tham chiếu không tải được; chỉ Dataset đọc được mới có thể chọn.`, 'amber') : '',
        builder.unsupportedSectionKeys?.length ? notice(`Các section cũ không còn được hỗ trợ như section trình bày (${builder.unsupportedSectionKeys.join(', ')}). Chúng sẽ được loại khỏi cấu hình khi lưu.`, 'amber') : ''
    ].join('');
    const stepContent = currentStep === 1
        ? `<section class="card report-builder-card"><div class="report-builder-card-heading"><span class="eyebrow">BƯỚC 1 · THÔNG TIN</span><h2>Thông tin báo cáo</h2><p>Nhập tên và kỳ dữ liệu cần dùng cho bản nháp.</p></div><form id="report-builder-form" class="report-builder-form" novalidate><div class="field report-builder-name"><label for="report-builder-name">Tên báo cáo</label><input id="report-builder-name" name="name" value="${esc(form.name)}" maxlength="200" required placeholder="Nhập tên báo cáo"></div><div class="report-builder-dates"><div class="field"><label for="report-builder-start">Từ ngày</label><input id="report-builder-start" name="start_date" type="date" value="${esc(form.start_date)}" required></div><div class="field"><label for="report-builder-end">Đến ngày</label><input id="report-builder-end" name="end_date" type="date" value="${esc(form.end_date)}" required></div></div><fieldset class="report-builder-comparison"><legend>Kỳ so sánh <span class="muted">(không bắt buộc)</span></legend><div class="report-builder-dates"><div class="field"><label for="report-builder-compare-start">Từ ngày</label><input id="report-builder-compare-start" name="compare_start_date" type="date" value="${esc(form.compare_start_date)}"></div><div class="field"><label for="report-builder-compare-end">Đến ngày</label><input id="report-builder-compare-end" name="compare_end_date" type="date" value="${esc(form.compare_end_date)}"></div></div><small class="form-note">Nếu nhập kỳ so sánh, cần cung cấp đủ cả ngày bắt đầu và kết thúc.</small></fieldset><div class="report-builder-flow">${icon('chart', 18)}<span>Phân tích</span><span aria-hidden="true">→</span><span>Dataset snapshot</span><span aria-hidden="true">→</span><span>Bản nháp báo cáo</span></div><div class="report-builder-actions"><span class="form-note">Trạng thái ban đầu của báo cáo là DRAFT.</span>${button('Tiếp tục chọn Dataset', 'report-builder-next', 'primary')}</div></form></section>`
        : currentStep === 2
            ? `<section class="card report-builder-card"><div class="report-builder-card-heading"><span class="eyebrow">BƯỚC 2 · DỮ LIỆU</span><h2>Chọn Dataset</h2><p>Chọn một snapshot đã tồn tại. Dữ liệu Dataset không bị thay đổi.</p></div><div class="report-builder-review"><div><span>Tên báo cáo</span><strong>${esc(form.name || '—')}</strong></div><div><span>Kỳ dữ liệu</span><strong>${form.start_date ? date(form.start_date) : '—'} → ${form.end_date ? date(form.end_date) : '—'}</strong></div>${form.compare_start_date && form.compare_end_date ? `<div><span>Kỳ so sánh</span><strong>${date(form.compare_start_date)} → ${date(form.compare_end_date)}</strong></div>` : ''}</div>${builder.datasets.length ? `<div class="report-builder-dataset-list">${builder.datasets.map(dataset => {
                const id = String(dataset.id || '');
                const params = dataset.params || {};
                const sourceKeys = Object.keys(dataset.sources || {});
                const period = params.start || params.end ? `${params.start ? date(params.start) : '—'} → ${params.end ? date(params.end) : '—'}` : '—';
                const status = dataset.exportable === true ? '<span class="badge green">Hợp lệ</span>' : dataset.exportable === false ? '<span class="badge amber">Cần kiểm tra</span>' : '<span class="badge neutral">Chưa xác định</span>';
                return `<label class="report-builder-dataset ${id === builder.selectedDatasetId ? 'selected' : ''}"><input type="radio" name="report-builder-dataset" value="${esc(id)}" ${id === builder.selectedDatasetId ? 'checked' : ''} ${builder.saveResult ? 'disabled' : ''}><span class="report-builder-dataset-body"><span class="report-builder-dataset-heading"><strong class="code" title="${esc(id)}">${esc(id)}</strong>${status}</span><span class="report-builder-dataset-meta"><span>${esc(types.find(type => type.id === params.report_type)?.label || params.report_type || '—')}</span><span>${period}</span><span>${sourceKeys.length ? sourceKeys.map(key => sourceNames[key] || key).map(esc).join(', ') : '—'}</span><span>${dataset.created_at ? time(dataset.created_at) : '—'}</span></span></span></label>`;
            }).join('')}</div>` : `<div class="report-builder-empty">${empty('Chưa có Dataset', 'Dataset sẽ xuất hiện sau khi hoàn tất một lần phân tích dữ liệu.', '<a class="btn primary" href="#analysis">Tạo Dataset từ phân tích</a>')}</div>`}<div id="report-builder-period-warning" class="report-builder-notices">${reportBuilderPeriodWarning(selected, form)}</div>${selected?.exportable === false ? notice('Dataset chưa đủ điều kiện xuất theo trạng thái backend. Có thể lưu bản nháp để giữ lại kết quả và cảnh báo chất lượng.', 'amber') : ''}${builder.saveResult ? `<div class="report-builder-saved">${notice('Đã lưu bản nháp theo phản hồi của backend.', 'green')}<dl><dt>Report ID</dt><dd class="code">${esc(builder.saveResult.report_id || '—')}</dd><dt>Revision</dt><dd>${builder.saveResult.revision ?? '—'}</dd><dt>Trạng thái</dt><dd><span class="badge neutral">${esc(String(builder.saveResult.status || '—').toUpperCase())}</span></dd></dl></div>` : ''}<div class="report-builder-actions">${button('Quay lại', 'report-builder-back', 'secondary')}${builder.saveResult ? button('Tiếp tục cấu hình nội dung', 'report-builder-configure', 'primary', builder.saveResult.status === 'draft' ? '' : '') : button('Lưu bản nháp', 'report-builder-save', 'primary', ` ${!selected || reportBuilderPeriodState(selected, form).length ? 'disabled' : ''}`)}</div></section>`
            : currentStep === 3 ? (() => {
                const options = reportBuilderSectionOptions(builder);
                const configuration = builder.configuration || { sections: [], defaultSection: '' };
                const included = new Set(configuration.sections.map(section => section.key));
                const validation = reportBuilderConfigValidation(builder);
                const readOnly = builder.bundleStatus !== 'draft';
                const orderedOptions = [...options].sort((a, b) => {
                    const positionA = configuration.sections.findIndex(section => section.key === a.key);
                    const positionB = configuration.sections.findIndex(section => section.key === b.key);
                    if (positionA >= 0 && positionB >= 0) return positionA - positionB;
                    if (positionA >= 0) return -1;
                    if (positionB >= 0) return 1;
                    return options.indexOf(a) - options.indexOf(b);
                });
                const rows = orderedOptions.map(option => {
                    const section = configuration.sections.find(item => item.key === option.key);
                    const position = section ? configuration.sections.indexOf(section) : -1;
                    const available = option.datasets.length > 0;
                    const availability = available
                        ? section ? 'Đang đưa vào' : 'Sẵn sàng'
                        : option.compatibleDatasets.length && !option.backendSupportsKey
                            ? 'Backend chưa hỗ trợ khóa section snake_case'
                            : 'Chưa có Dataset phù hợp';
                    const assignment = section?.dataset_id || '';
                    const selector = `<select data-report-section-dataset="${esc(option.key)}" aria-label="Dataset cho ${esc(option.label)}" ${!section || readOnly || !available ? 'disabled' : ''}><option value="">Chọn Dataset</option>${option.datasets.map(dataset => `<option value="${esc(dataset.id)}" ${dataset.id === assignment ? 'selected' : ''}>${esc(dataset.id)} · ${esc(types.find(type => type.id === (dataset.report_type || dataset.params?.report_type))?.label || dataset.report_type || dataset.params?.report_type || '—')}</option>`).join('')}</select>`;
                    const order = section ? `<span class="report-section-position">${position + 1}</span>` : '<span class="report-section-position muted">—</span>';
                    const reorder = section ? `<div class="report-section-order">${button('Lên', 'report-section-up', 'text', `data-section-key="${esc(option.key)}" aria-label="Di chuyển ${esc(option.label)} lên" ${position === 0 || readOnly ? 'disabled' : ''}`)}${button('Xuống', 'report-section-down', 'text', `data-section-key="${esc(option.key)}" aria-label="Di chuyển ${esc(option.label)} xuống" ${position === configuration.sections.length - 1 || readOnly ? 'disabled' : ''}`)}</div>` : '';
                    return `<article class="report-section-card ${section ? 'included' : ''} ${!available ? 'unavailable' : ''}"><div class="report-section-card-main">${order}<div class="report-section-card-copy"><strong>${esc(option.label)}</strong><p>${esc(option.description)}</p></div><span class="badge ${available ? section ? 'blue' : 'green' : 'neutral'}">${esc(availability)}</span></div><div class="report-section-card-controls"><label class="report-section-toggle"><input type="checkbox" data-report-section-toggle="${esc(option.key)}" ${section ? 'checked' : ''} ${!available || readOnly ? 'disabled' : ''}><span>Đưa vào báo cáo</span></label>${selector}${section ? `<label class="report-section-default"><input type="radio" name="report-default-section" value="${esc(option.key)}" ${configuration.defaultSection === option.key ? 'checked' : ''} ${readOnly ? 'disabled' : ''}><span>Trang mặc định</span></label>` : ''}${reorder}</div></article>`;
                }).join('');
                return `<section class="card report-builder-card"><div class="report-builder-card-heading"><span class="eyebrow">BƯỚC 3 · SECTION</span><h2>Cấu hình nội dung</h2><p>Chọn các section, gán Dataset thật và sắp xếp thứ tự hiển thị. Dataset snapshot không bị thay đổi.</p></div><div class="report-builder-review"><div><span>Tên báo cáo</span><strong>${esc(form.name || '—')}</strong></div><div><span>Kỳ dữ liệu</span><strong>${form.start_date ? date(form.start_date) : '—'} → ${date(form.end_date)}</strong></div><div><span>Report Bundle</span><strong class="code">${esc(builder.reportId || '—')} · v${builder.revision || '—'}</strong></div></div>${readOnly ? notice('Report Bundle không ở trạng thái DRAFT. Cấu hình chỉ đọc.', 'amber') : ''}<div class="report-builder-section-list">${rows}</div><section class="report-builder-validation" aria-live="polite">${validation.map(message => notice(message, 'red')).join('') || notice('Cấu hình section hợp lệ: thứ tự, Dataset và trang mặc định đã được xác định.', 'green')}</section>${builder.configurationSaved ? notice(`Cấu hình đã được lưu vào bản nháp revision ${builder.revision} theo phản hồi backend.`, 'green') : ''}<div class="report-builder-actions">${button('Quay lại Dataset', 'report-builder-back', 'secondary')}${button(readOnly ? 'Chỉ đọc' : 'Lưu cấu hình', 'report-builder-save-config', 'primary', `${readOnly || validation.length ? 'disabled' : ''}`)}${button('Tiếp tục đến xem trước', 'report-builder-preview', 'primary', `${readOnly || !builder.configurationSaved ? 'disabled' : ''}`)}</div></section>`;
            })() : reportBuilderPreviewView(builder, types);
    return `<div class="report-builder-page">${top}${stepper}${errors}${stepContent}<p class="report-builder-note">Report Builder chỉ đọc Dataset snapshot hiện có. Chọn một Dataset không gọi lại nền tảng dữ liệu hoặc làm mới dữ liệu nguồn.</p></div>`;
}

function datasetStatus(dataset) {
    if (dataset.exportable === true) return '<span class="badge green"><span class="dot"></span>Hợp lệ</span>';
    if (dataset.exportable === false) return '<span class="badge amber"><span class="dot"></span>Cần kiểm tra</span>';
    return '—';
}

function filteredDatasets(datasets, filters = {}) {
    const query = (filters.query || '').trim().toLowerCase();
    return datasets.filter(dataset =>
        (!query || String(dataset.id || '').toLowerCase().includes(query)) &&
        (!filters.report_type || dataset.params?.report_type === filters.report_type) &&
        (!filters.status || (filters.status === 'valid' ? dataset.exportable === true : dataset.exportable === false))
    );
}

export function datasetsTable(datasets, types, filters = {}) {
    const rows = filteredDatasets(datasets, filters);
    if (!rows.length) {
        const title = datasets.length ? 'Không có Dataset phù hợp' : 'Chưa có Dataset';
        const detail = datasets.length
            ? 'Thử thay đổi từ khóa hoặc bộ lọc.'
            : 'Dataset sẽ xuất hiện sau khi hoàn tất một lần phân tích dữ liệu.';
        return `<div class="datasets-empty">${empty(title, detail, `<a class="btn primary" href="#analysis">${icon('plus', 15)} Tạo Dataset từ phân tích</a>`)}</div><div class="datasets-result-count">Hiển thị 0 / ${datasets.length} Dataset đã tải</div>`;
    }
    const typeLabel = id => types.find(type => type.id === id)?.label || id || '—';
    const sourceLabel = dataset => Object.keys(dataset.sources || {}).map(key => sourceNames[key] || key).join(', ') || '—';
    return `${table(['Dataset ID', 'Loại báo cáo', 'Kỳ dữ liệu', 'Nguồn', 'Trạng thái', 'Ngày tạo', 'Thao tác'], rows.map(dataset => {
        const id = String(dataset.id || '');
        const params = dataset.params || {};
        const period = params.start || params.end
            ? `${params.start ? date(params.start) : '—'} → ${params.end ? date(params.end) : '—'}`
            : '—';
        const created = dataset.created_at ? date(dataset.created_at) : '—';
        return [
            `<span class="code dataset-id-cell" title="${esc(id)}">${esc(id)}</span>`,
            esc(typeLabel(params.report_type)),
            period,
            esc(sourceLabel(dataset)),
            datasetStatus(dataset),
            created,
            `<div class="actions datasets-row-actions"><a class="btn secondary" href="#datasets/${encodeURIComponent(id)}">Xem chi tiết</a><a class="btn text" href="#analysis?dataset=${encodeURIComponent(id)}">Phân tích</a></div>`
        ];
    }))}<div class="datasets-result-count">Hiển thị ${rows.length} / ${datasets.length} Dataset đã tải</div>`;
}

export function datasetsView(datasets, types, loadErrors = []) {
    const reportTypes = [...new Set(datasets.map(dataset => dataset.params?.report_type).filter(Boolean))];
    const validCount = datasets.filter(dataset => dataset.exportable === true).length;
    const needsReview = datasets.filter(dataset => dataset.exportable === false).length;
    const newest = datasets.reduce((latest, dataset) => {
        const timestamp = Date.parse(dataset.created_at || '');
        return Number.isFinite(timestamp) && (!latest || timestamp > latest.timestamp)
            ? { timestamp, date: dataset.created_at }
            : latest;
    }, null);
    const actions = `<a class="btn primary" href="#analysis">${icon('plus', 16)} Tạo Dataset từ phân tích</a>`;
    const errorNotice = loadErrors.length
        ? notice(`${loadErrors.length} Dataset tham chiếu không tải được: ${loadErrors.map(error => error.message).filter(Boolean).join(' · ')}`, 'amber')
        : '';
    return `<div class="datasets-page">${heading('QUẢN LÝ DỮ LIỆU', 'Dataset', 'Các snapshot dữ liệu bất biến được tạo sau mỗi lần phân tích.', actions)}${errorNotice}<section class="datasets-summary"><article><span>Tổng Dataset</span><strong>${datasets.length}</strong><small>Dataset đã tải từ các bản ghi tham chiếu</small></article><article><span>Dataset hợp lệ</span><strong>${validCount}</strong><small>Đủ điều kiện xuất theo trạng thái backend</small></article><article class="${needsReview ? 'needs-attention' : ''}"><span>Dataset cần kiểm tra</span><strong>${needsReview}</strong><small>Chưa đủ điều kiện xuất theo trạng thái backend</small></article><article><span>Dataset gần nhất</span><strong>${newest ? date(newest.date) : '—'}</strong><small>${newest ? time(newest.date) : 'Ngày tạo chưa có'}</small></article></section><section class="card datasets-toolbar-card"><form id="dataset-filters" class="datasets-toolbar"><label class="datasets-search"><span class="sr-only">Tìm kiếm theo Dataset ID</span><input type="search" name="query" placeholder="Tìm kiếm Dataset ID…" autocomplete="off"></label><label><span class="sr-only">Lọc theo loại báo cáo</span><select name="report_type" aria-label="Loại báo cáo"><option value="">Tất cả loại báo cáo</option>${reportTypes.map(id => `<option value="${esc(id)}">${esc(types.find(type => type.id === id)?.label || id)}</option>`).join('')}</select></label><label><span class="sr-only">Lọc theo trạng thái</span><select name="status" aria-label="Trạng thái Dataset"><option value="">Tất cả trạng thái</option><option value="valid">Hợp lệ</option><option value="review">Cần kiểm tra</option></select></label></form><div id="datasets-table-region">${datasetsTable(datasets, types)}</div></section><p class="datasets-discovery-note">Danh sách được suy ra từ tối đa 50 Dataset gần nhất có tham chiếu trong Lịch sử hoạt động hoặc Báo cáo. Không có API liệt kê Dataset.</p></div>`;
}

const datasetParameterLabels = {
    report_type: 'Loại báo cáo',
    start: 'Từ ngày',
    end: 'Đến ngày',
    compare: 'So sánh kỳ trước',
    previous_start: 'Bắt đầu kỳ trước',
    previous_end: 'Kết thúc kỳ trước',
    exclude_products: 'Loại trừ /san-pham/',
    demo: 'Chế độ DEMO',
    upload_id: 'CSV hiện tại'
};

function datasetParameterValue(key, value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'boolean') return value ? 'Có' : 'Không';
    if (['start', 'end', 'previous_start', 'previous_end'].includes(key)) return date(value);
    return String(value);
}

function datasetQuality(dataset, sources) {
    const messages = [];
    for (const [key, source] of Object.entries(sources)) {
        const name = sourceNames[key] || source.source || key;
        const statusSeverity = { delayed: 'amber', permission_denied: 'red', invalid_data: 'amber', api_error: 'red', disconnected: 'amber', empty: 'amber' }[source.status];
        if (statusSeverity) {
            const statusText = sourceNames[key] ? badgeText(source.status) : source.status;
            messages.push(notice(`${name}: ${statusText}${source.error ? ` — ${source.error}` : ''}`, statusSeverity));
        } else if (source.error) messages.push(notice(`${name}: ${source.error}`, 'red'));
        for (const warning of source.warnings || []) messages.push(notice(`${name}: ${warning}`, 'amber'));
    }
    if (dataset.exportable === false) {
        messages.unshift(notice('Dataset hiện chưa đủ điều kiện xuất Excel hoặc lưu báo cáo theo kiểm tra hiện có của backend.', 'amber'));
    }
    return messages.length
        ? `<section class="card dataset-detail-quality"><div class="dataset-detail-section-heading"><div><span class="eyebrow">DATA QUALITY</span><h2>Cảnh báo &amp; chất lượng</h2></div></div><div class="dataset-detail-quality-list">${messages.join('')}</div></section>`
        : '';
}

function badgeText(status) {
    return {
        invalid_data: 'Dữ liệu không hợp lệ',
        api_error: 'Lỗi API',
        disconnected: 'Chưa kết nối',
        empty: 'Chưa có dữ liệu'
    }[status] || status;
}

function datasetSourcePreview(key, source, params, page = 0) {
    if (['ga4', 'gsc', 'keywords', 'gmb'].includes(key)) {
        const rowCount = Math.max(source.daily?.length || 0, source.channels?.length || 0, source.pages?.length || 0, source.queries?.length || 0, source.entries?.length || 0);
        return `${sourceSection(key, source, params, true, { tablePage: page })}${rowCount > 50 ? `<div class="table-pagination">${button('← Trang trước', 'table-prev', 'secondary', page > 0 ? '' : 'disabled')}<span>Trang ${page + 1}</span>${button('Trang sau →', 'table-next', 'secondary', page * 50 < rowCount - 50 ? '' : 'disabled')}</div>` : ''}`;
    }
    const rows = source.entries || source.daily || source.queries || [];
    return `<section class="source-section"><div class="section-title"><span class="source-icon file">${icon('file')}</span><h2>${esc(sourceNames[key] || source.source || key)}</h2>${source.status ? badge(source.status) : ''}</div>${rows.length ? dataTable(rows, 'Dữ liệu chi tiết') : empty('Không có dữ liệu xem trước', 'Nguồn này không có hàng dữ liệu trong Dataset.')}</section>`;
}

export function datasetDetailNotFoundView() {
    return `<div class="dataset-detail-page">${heading('QUẢN LÝ DỮ LIỆU', 'Dataset', 'Snapshot dữ liệu đã chọn không khả dụng.')}<section class="card dataset-detail-not-found">${empty('Không tìm thấy Dataset', 'Dataset có thể không tồn tại hoặc không còn khả dụng với tài khoản hiện tại.', '<a class="btn secondary" href="#datasets">Quay lại danh sách Dataset</a>')}</section></div>`;
}

export function datasetDetailView(dataset, types, selectedTab = 'summary', tablePage = 0) {
    const params = dataset.params || {};
    const sources = dataset.sources && typeof dataset.sources === 'object'
        ? Object.fromEntries(Object.entries(dataset.sources).map(([key, source]) => [key, source && typeof source === 'object' ? source : {}]))
        : {};
    const sourceKeys = Object.keys(sources);
    const readyCount = sourceKeys.filter(key => sources[key]?.status === 'ready').length;
    const reportType = types.find(type => type.id === params.report_type)?.label || params.report_type || '—';
    const period = params.start && params.end ? `${date(params.start)} – ${date(params.end)}` : '—';
    const sourceNamesList = sourceKeys.map(key => sourceNames[key] || sources[key]?.source || key);
    const actions = `<a class="btn secondary" href="#analysis?dataset=${encodeURIComponent(dataset.id)}">Phân tích Dataset</a>${dataset.exportable === true ? button(icon('download', 16) + ' Xuất Excel', 'dataset-detail-export', 'primary', `data-id="${esc(dataset.id)}"`) : ''}`;
    const summary = `<section class="dataset-detail-summary"><article><span>Kỳ dữ liệu</span><strong>${esc(period)}</strong></article><article><span>Số nguồn</span><strong>${dataset.sources && typeof dataset.sources === 'object' ? sourceKeys.length : '—'}</strong></article><article><span>Nguồn sẵn sàng</span><strong>${dataset.sources && typeof dataset.sources === 'object' ? `${readyCount} / ${sourceKeys.length}` : '—'}</strong></article><article><span>Trạng thái Dataset</span><strong>${dataset.exportable === true ? '<span class="badge green"><span class="dot"></span>Hợp lệ</span>' : dataset.exportable === false ? '<span class="badge amber"><span class="dot"></span>Cần kiểm tra</span>' : '—'}</strong></article></section>`;
    const sourcesPanel = `<section class="card dataset-detail-sources"><div class="dataset-detail-section-heading"><div><span class="eyebrow">SOURCES</span><h2>Trạng thái nguồn dữ liệu</h2></div></div>${sourceKeys.length ? `<div class="dataset-detail-source-grid">${sourceKeys.map(key => {
        const source = sources[key] || {};
        const fields = [
            ['Nguồn', source.source || key],
            ['Trạng thái', source.status],
            ['Dữ liệu mới nhất', source.latest_available_date && date(source.latest_available_date)],
            ['Lấy lúc', source.fetched_at && time(source.fetched_at)],
            ['Thành công lần cuối', source.last_success_at && time(source.last_success_at)],
            ['Tài sản', source.asset],
            ['Múi giờ', source.timezone]
        ].filter(([, value]) => value !== undefined && value !== null && value !== '');
        return `<article class="dataset-detail-source"><div class="dataset-detail-source-heading"><h3>${esc(sourceNames[key] || source.source || key)}</h3>${source.status ? badge(source.status) : ''}</div><dl>${fields.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${label === 'Trạng thái' ? esc(badgeText(value)) : esc(value)}</dd></div>`).join('')}${(source.warnings || []).map(warning => `<div class="dataset-detail-source-message"><dt>Cảnh báo</dt><dd>${esc(warning)}</dd></div>`)}${source.error ? `<div class="dataset-detail-source-message is-error"><dt>Lỗi</dt><dd>${esc(source.error)}</dd></div>` : ''}</dl></article>`;
    }).join('')}</div>` : empty('Không có nguồn dữ liệu', 'Dataset payload không có nguồn dữ liệu để hiển thị.')}</section>`;
    const parameterEntries = Object.entries(datasetParameterLabels).filter(([key]) => Object.hasOwn(params, key));
    const parametersPanel = `<section class="card dataset-detail-parameters"><div class="dataset-detail-section-heading"><div><span class="eyebrow">PARAMETERS</span><h2>Tham số phân tích</h2></div><span class="dataset-immutable-label">Snapshot dữ liệu · Chỉ xem</span></div>${parameterEntries.length ? `<dl class="dataset-detail-parameter-grid">${parameterEntries.map(([key, label]) => `<div><dt>${label}</dt><dd>${esc(datasetParameterValue(key, params[key]))}</dd></div>`).join('')}</dl>` : empty('Không có tham số', 'Dataset payload không có tham số để hiển thị.')}</section>`;
    const tabContent = selectedTab === 'summary'
        ? `<div class="dataset-detail-overview">${sourcesPanel}${parametersPanel}</div>`
        : datasetSourcePreview(selectedTab, sources[selectedTab], params, tablePage);
    const tabs = ['summary', ...sourceKeys].map(key => `<button type="button" data-action="dataset-detail-tab" data-tab="${esc(key)}" class="${selectedTab === key ? 'active' : ''}" ${selectedTab === key ? 'aria-current="page"' : ''}>${key === 'summary' ? 'Tổng quan' : esc(sourceNames[key] || sources[key]?.source || key)}</button>`).join('');
    const sourceFlow = sourceNamesList.length
        ? `<div class="dataset-detail-lineage"><span>${sourceNamesList.map(esc).join(' · ')}</span><b aria-hidden="true">→</b><span>Phân tích</span><b aria-hidden="true">→</b><strong>Dataset snapshot</strong></div>`
        : empty('Chưa có thông tin nguồn', 'Dataset payload không chứa nguồn để thể hiện dòng dữ liệu.');
    const schema = dataset.schema || dataset.schema_metadata;
    const observedKeys = [...new Set(sourceKeys.flatMap(key => {
        const source = sources[key] || {};
        return ['daily', 'channels', 'pages', 'queries', 'entries']
            .flatMap(field => Array.isArray(source[field]) ? source[field].flatMap(row => row && typeof row === 'object' ? Object.keys(row) : []) : []);
    }))];
    const schemaPanel = schema
        ? `<section class="card dataset-detail-schema"><h2>Schema</h2><pre>${esc(JSON.stringify(schema, null, 2))}</pre></section>`
        : `<section class="card dataset-detail-schema"><h2>Schema</h2><p>Chưa có thông tin schema riêng cho Dataset này.</p>${observedKeys.length ? `<h3>Các trường quan sát được trong dữ liệu</h3><ul>${observedKeys.map(key => `<li><code>${esc(key)}</code></li>`).join('')}</ul>` : ''}</section>`;
    return `<div class="dataset-detail-page">${heading('QUẢN LÝ DỮ LIỆU', 'Chi tiết Dataset', 'Snapshot dữ liệu bất biến · Màn hình chỉ dùng để kiểm tra.', actions)}<section class="card dataset-detail-identity"><div><span class="eyebrow">SNAPSHOT DỮ LIỆU</span><h2 class="code" title="${esc(dataset.id)}">${esc(dataset.id || '—')}</h2><dl><div><dt>Loại báo cáo</dt><dd>${esc(reportType)}</dd></div><div><dt>Kỳ dữ liệu</dt><dd>${esc(period)}</dd></div><div><dt>Ngày tạo</dt><dd>${esc(dataset.created_at ? time(dataset.created_at) : '—')}</dd></div></dl></div><a class="btn text" href="#datasets">Quay lại danh sách Dataset</a></section>${summary}${datasetQuality(dataset, sources)}<section class="card dataset-detail-tab-card"><nav class="tabs dataset-detail-tabs" aria-label="Nội dung Dataset">${tabs}</nav><div class="dataset-detail-tab-content">${tabContent}</div></section><section class="card dataset-detail-lineage-card"><div class="dataset-detail-section-heading"><div><span class="eyebrow">LINEAGE</span><h2>Dòng dữ liệu</h2></div></div>${sourceFlow}</section>${schemaPanel}</div>`;
}

export function overviewView(o, user) {

    /*
     * Overview performance chart
     * Only renders persisted real-data series supplied by API.
     * Never falls back to demo data.
     */
    function overviewPerformance(o, availableSources) {
        const trend = o?.trend;

        const emptyState = () => `
        <div class="overview-performance-empty">
            ${empty(
            'Chưa có dữ liệu xu hướng',
            'Biểu đồ sẽ hiển thị khi hệ thống có dữ liệu thực tế theo ngày.'
        )}
        </div>
    `;

        // Only accept an explicitly real-data trend.
        if (
            !trend ||
            trend.origin !== 'real' ||
            !Array.isArray(trend.daily)
        ) {
            return emptyState();
        }

        const validDate = value =>
            typeof value === 'string' &&
            /^\d{4}-\d{2}-\d{2}$/.test(value) &&
            Number.isFinite(Date.parse(value));

        // Different metrics use different units.
        // Display one metric at a time, never mix their axes.
        const metrics = [
            {
                source: 'ga4',
                key: 'sessions',
                label: 'GA4 · Phiên truy cập'
            },
            {
                source: 'gsc',
                key: 'clicks',
                label: 'GSC · Lượt nhấp'
            }
        ];

        // Prefer GA4; use GSC if GA4 has no real series.
        const selected = metrics.find(metric =>
            availableSources.includes(metric.source) &&
            trend.daily.some(row =>
                validDate(row?.date) &&
                Number.isFinite(row[metric.key]) &&
                row[metric.key] >= 0
            )
        );

        if (!selected) {
            return emptyState();
        }

        const rows = trend.daily
            .filter(row =>
                validDate(row?.date) &&
                Number.isFinite(row[selected.key]) &&
                row[selected.key] >= 0
            )
            .sort((a, b) => a.date.localeCompare(b.date));

        if (!rows.length) {
            return emptyState();
        }

        const firstDate = rows[0].date;
        const lastDate = rows[rows.length - 1].date;

        const start = validDate(trend.start) &&
            trend.start <= firstDate
            ? trend.start
            : firstDate;

        const end = validDate(trend.end) &&
            trend.end >= lastDate
            ? trend.end
            : lastDate;

        return `
        <div class="overview-trend">
            <div class="overview-trend-head">
                <span class="overview-trend-legend ${selected.source}">
                    ${esc(selected.label)}
                </span>
                <span class="overview-trend-period">
                    ${date(start)} – ${date(end)}
                </span>
            </div>

            <div class="overview-trend-chart">
                ${chart(
            rows,
            selected.key,
            selected.source,
            start,
            end
        )}
            </div>

            <p class="overview-trend-note">
                Dữ liệu thực tế theo ngày.
                Rê chuột vào điểm trên biểu đồ để xem giá trị.
            </p>
        </div>
    `;
    }

    const availableSources = [...new Set((o.types || []).flatMap(t => t.id === 'seo' ? ['ga4', 'gsc', 'keywords'] : [t.id]))].filter(k => ['ga4', 'gsc', 'keywords'].includes(k));
    const recentReports = o.reports || [];
    const reportType = id => o.types?.find(t => t.id === id)?.label || id;
    const lastExport = o.last_export;
    const sources = availableSources.map(key => ({ key, source: o.sources?.[key] || {}, status: googleSourceStatus({ connected: o.google_connected, sources: o.sources }, key).status }));
    const jobs = o.jobs || [];
    const sourceLabel = key => key === 'ga4' ? 'Google Analytics 4' : key === 'gsc' ? 'Search Console' : 'Keyword Sheet';
    const recentReportRows = recentReports.slice(0, 5).map(r => [
        `<strong class="overview-report-name">${esc(r.name)}</strong>${r.origin === 'demo' ? '<small class="overview-report-meta">DEMO · Số liệu mô phỏng</small>' : r.origin === 'legacy' ? '<small class="overview-report-meta">Nhập từ hệ thống cũ</small>' : ''}`,
        esc(reportType(r.report_type)), `v${esc(r.version)}`, time(r.created_at),
        `<span class="badge ${r.valid ? 'green' : 'amber'}">${r.valid ? 'Hợp lệ' : 'Cần kiểm tra'}</span>`
    ]);
    return `<div class="overview-page">${heading('TRUNG TÂM BÁO CÁO', 'Tổng quan', 'Theo dõi dữ liệu, tác vụ và báo cáo từ một nơi.', `${user.role === 'admin' ? button(icon('refresh', 16) + ' Kiểm tra nguồn', 'check-google', 'secondary') : ''}<a class="btn primary" href="#analysis">${icon('chart', 16)} Phân tích & kiểm tra</a>`)}
        ${o.demo_enabled ? `<div class="overview-demo-banner"><span class="badge blue">DEMO · SỐ LIỆU MÔ PHỎNG</span><span>Chỉ dữ liệu mô phỏng được gắn nhãn DEMO.</span><a href="#analysis">Mở phân tích ${icon('arrow', 14)}</a></div>` : ''}
        <section class="overview-stats" aria-label="Chỉ số tổng quan">
            <article class="overview-stat"><span class="overview-stat-icon blue">${icon('file', 20)}</span><div class="overview-stat-copy"><span>Báo cáo đã lưu</span><strong>${num(o.report_count)}</strong><small>Tổng số phiên bản có sẵn</small></div></article>
            <article class="overview-stat"><span class="overview-stat-icon green">${icon('refresh', 20)}</span><div class="overview-stat-copy"><span>Tác vụ đang chạy</span><strong>${num(o.running)}</strong><small>Tác vụ gần đây đang xử lý</small></div></article>
            <article class="overview-stat"><span class="overview-stat-icon amber">${icon('alert', 20)}</span><div class="overview-stat-copy"><span>Tác vụ cần chú ý</span><strong>${num(o.failed)}</strong><small>Lỗi, thiếu nguồn hoặc gián đoạn</small></div></article>
            <article class="overview-stat"><span class="overview-stat-icon violet">${icon('download', 20)}</span><div class="overview-stat-copy"><span>Xuất Excel gần nhất</span><strong>${lastExport ? date(lastExport.finished_at) : '—'}</strong><small>${lastExport ? time(lastExport.finished_at) : 'Chưa có lần xuất thành công'}</small></div></article>
        </section>
        <section class="overview-dashboard-grid">
            <article class="overview-dashboard-card card">
                <div class="card-header"><div><span class="eyebrow">HIỆU SUẤT</span><h2>Hiệu suất dữ liệu</h2></div><span class="tag">Theo nguồn thực tế</span></div>
               ${overviewPerformance(o, availableSources)}
            </article>
            <article class="overview-dashboard-card card">
                <div class="card-header"><div><span class="eyebrow">TRẠNG THÁI NGUỒN</span><h2>Trạng thái đồng bộ theo nền tảng</h2></div><a class="btn text" href="#connections">Kết nối ${icon('arrow', 14)}</a></div>
                <div class="overview-status-list">${sources.length ? sources.map(({ key, source, status }) => `<div class="overview-status-row"><span class="source-icon ${key}">${icon(key === 'ga4' ? 'chart' : key === 'gsc' ? 'search' : 'file', 18)}</span><div><strong>${sourceLabel(key)}</strong><small>${source.latest_available_date ? `Dữ liệu đến ${date(source.latest_available_date)}` : `Kiểm tra gần nhất ${source.fetched_at ? time(source.fetched_at) : '—'}`}</small></div>${badge(status)}</div>`).join('') : empty('Chưa có trạng thái nguồn', 'Nguồn Google sẽ hiển thị sau khi backend ghi nhận trạng thái.')}</div>
                <div class="overview-status-footer"><a href="#assets">Xem tài sản dữ liệu</a><span>${o.google_connected ? esc(o.email || 'Tài khoản Google đã kết nối') : 'Chưa kết nối Google'}</span></div>
            </article>
        </section>
        <section class="overview-recent-section card">
            <div class="card-header"><div><span class="eyebrow">VẬN HÀNH</span><h2>Hoạt động gần đây</h2></div><a class="btn text" href="#activity">Xem tất cả hoạt động ${icon('arrow', 15)}</a></div>
            <div class="overview-recent-block"><div class="overview-recent-title"><h3>Tác vụ gần đây</h3><a href="#activity">Lịch sử hoạt động</a></div>${jobTable(jobs.slice(0, 5))}</div>
            <div class="overview-recent-block overview-reports-block"><div class="overview-recent-title"><h3>Báo cáo gần đây</h3><a href="#reports">Tất cả báo cáo</a></div>${recentReportRows.length ? table(['Tên báo cáo', 'Loại', 'Phiên bản', 'Ngày lưu', 'Tình trạng'], recentReportRows) : empty('Chưa có báo cáo', 'Báo cáo đã lưu sẽ xuất hiện tại đây.')}</div>
            <div class="overview-quick-links"><a href="#analysis">Phân tích & kiểm tra ${icon('arrow', 14)}</a><a href="#connections">Kết nối nền tảng ${icon('arrow', 14)}</a><a href="#uploads">Quản lý dữ liệu CSV ${icon('arrow', 14)}</a></div>
        </section>
    </div>`;
}

export function clientsView() {
    return heading('DỮ LIỆU', 'Khách hàng', 'Quản lý khách hàng, tài sản dữ liệu và trạng thái báo cáo.', `<button class="btn secondary" type="button" disabled title="Chức năng chưa được hỗ trợ bởi backend">${icon('upload', 16)} Nhập dữ liệu</button><button class="btn secondary" type="button" disabled title="Chức năng chưa được hỗ trợ bởi backend">${icon('download', 16)} Xuất danh sách</button><button class="btn primary" type="button" disabled title="Chức năng chưa được hỗ trợ bởi backend">${icon('plus', 16)} Thêm khách hàng · Chưa khả dụng</button>`) +
        `<section class="clients-workspace">
            <div class="clients-main">
                <section class="card clients-toolbar"><div class="toolbar"><label class="clients-search"><span class="sr-only">Tìm khách hàng</span><input type="search" placeholder="Tìm khách hàng, domain hoặc người phụ trách…" disabled aria-label="Tìm khách hàng"></label><select disabled aria-label="Lọc theo ngành"><option>Tất cả ngành</option></select><select disabled aria-label="Lọc theo trạng thái"><option>Tất cả trạng thái</option></select><input type="date" disabled aria-label="Chọn khoảng thời gian"></div></section>
                <section class="card clients-table"><div class="card-header"><div><h2>Danh sách khách hàng</h2><p class="muted">Chưa có API quản lý khách hàng. Bảng sẽ hiển thị dữ liệu khi backend hỗ trợ.</p></div><span class="tag">— khách hàng</span></div><div class="table-scroll"><table><thead><tr>${['#', 'Khách hàng', 'Domain', 'Ngành', 'Người phụ trách', 'Trạng thái kết nối', 'Ngày tạo', 'Thao tác'].map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody><tr><td colspan="8"><div class="clients-table-empty">${empty('Chưa có khách hàng', 'Chưa có dữ liệu khách hàng để hiển thị.')}</div></td></tr></tbody></table></div></section>
            </div>
            <aside class="clients-detail card"><div class="card-header"><h2>Chi tiết khách hàng</h2><button class="icon-btn" type="button" disabled aria-label="Đóng chi tiết">${icon('close', 17)}</button></div><div class="clients-detail-empty">${empty('Chọn khách hàng để xem chi tiết', 'Thông tin hồ sơ, kết nối và báo cáo sẽ hiển thị tại đây.')}</div><div class="clients-detail-actions"><button class="btn secondary" type="button" disabled title="Chức năng chưa được hỗ trợ bởi backend">${icon('file', 15)} Xem báo cáo</button><button class="btn secondary" type="button" disabled title="Chức năng chưa được hỗ trợ bởi backend">Chỉnh sửa</button></div></aside>
        </section>`;
}

const assetLabels = { ga4: 'Google Analytics 4 property', gsc: 'Search Console property', keywords: 'Keyword Sheet' };

function googleSourceStatus(connection, key) {
    const source = connection.sources?.[key] || {};
    return { source, status: source.status || (connection.connected ? 'pending' : 'disconnected') };
}

const optionalDate = value => value ? date(value) : '—';
const optionalTime = value => value ? time(value) : '—';

export function assetsView(d = {}) {
    const keys = ['ga4', 'gsc', 'keywords'].filter(key => Object.hasOwn(d.assets || {}, key));
    const knownStatuses = keys.map(key => d.sources?.[key]?.status).filter(Boolean);
    const attentionStatuses = ['permission_denied', 'api_error', 'invalid_data', 'incomplete', 'revoked', 'timeout'];
    const configuredCount = keys.length ? num(keys.length) : '—';
    const activeCount = knownStatuses.length ? num(knownStatuses.filter(status => status === 'ready').length) : '—';
    const attentionCount = knownStatuses.length ? num(knownStatuses.filter(status => attentionStatuses.includes(status)).length) : '—';
    const errorCount = knownStatuses.length ? num(knownStatuses.filter(status => status === 'api_error').length) : '—';
    return heading('DỮ LIỆU', 'Tài sản dữ liệu', 'Theo dõi tài sản Google được cấu hình và trạng thái truy cập nguồn.', `<a class="btn secondary" href="#connections">${icon('link', 16)} Kết nối nền tảng</a><button class="btn primary" type="button" disabled title="Chức năng quản lý tài sản chưa được hỗ trợ bởi backend">${icon('plus', 16)} Thêm tài sản · Chưa khả dụng</button>`) +
        `<section class="assets-stats" aria-label="Tình trạng tài sản">
            <article class="assets-stat"><span class="assets-stat-icon blue">${icon('folder', 19)}</span><div><strong>${configuredCount}</strong><span>Tài sản cấu hình</span></div></article>
            <article class="assets-stat"><span class="assets-stat-icon green">${icon('check', 19)}</span><div><strong>${activeCount}</strong><span>Nguồn sẵn sàng</span></div></article>
            <article class="assets-stat"><span class="assets-stat-icon amber">${icon('alert', 19)}</span><div><strong>${attentionCount}</strong><span>Cần kiểm tra</span></div></article>
            <article class="assets-stat"><span class="assets-stat-icon red">${icon('close', 19)}</span><div><strong>${errorCount}</strong><span>Lỗi kết nối</span></div></article>
        </section>
        <section class="assets-notice">${notice('Danh sách này chỉ phản ánh cấu hình Google và trạng thái nguồn do backend hiện có cung cấp. Chưa có API kiểm kê tài sản đa nền tảng.', 'blue')}</section>
        <section class="card assets-table"><div class="card-header"><div><h2>Danh mục tài sản dữ liệu</h2><p class="muted">Thông tin đọc từ cấu hình ứng dụng và lần kiểm tra nguồn gần nhất.</p></div><span class="tag">${configuredCount} tài sản cấu hình</span></div>
        <div class="assets-toolbar"><input type="search" disabled aria-label="Tìm tài sản" placeholder="Tìm tài sản hoặc mã cấu hình…"><select disabled aria-label="Lọc trạng thái"><option>Tất cả trạng thái</option></select><select disabled aria-label="Lọc loại tài sản"><option>Tất cả loại tài sản</option></select></div>
        <div class="table-scroll"><table><thead><tr>${['Tài sản / nguồn', 'Mã hoặc địa chỉ cấu hình', 'Trạng thái truy cập', 'Dữ liệu mới nhất', 'Kiểm tra gần nhất', 'Thao tác'].map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody>${keys.length ? keys.map(key => {
            const { source, status } = googleSourceStatus(d, key);
            return `<tr><td><div class="cell-title"><span class="source-icon ${key}">${icon(key === 'ga4' ? 'chart' : key === 'gsc' ? 'search' : 'file')}</span><span>${assetLabels[key]}<small>Google · ${esc(sourceNames[key])}</small></span></div></td><td><span class="asset-value">${esc(d.assets[key] || '—')}</span></td><td>${badge(status)}</td><td>${optionalDate(source.latest_available_date)}</td><td>${optionalTime(source.fetched_at)}</td><td><a class="btn text" href="#connections/google">Chi tiết ${icon('arrow', 14)}</a></td></tr>`;
        }).join('') : `<tr><td colspan="6"><div class="assets-table-empty">${empty('Chưa có tài sản dữ liệu', 'Chưa có cấu hình Google được backend cung cấp.')}</div></td></tr>`}</tbody></table></div>
        <div class="assets-footnote">${empty('Tài sản ngoài Google chưa được liệt kê', 'Meta, TikTok, YouTube và các tài sản khách hàng chỉ hiển thị khi backend cung cấp dữ liệu thật.')}</div></section>`;
}

export function syncView(jobs = [], overview = {}, user = {}, connection = null) {
    const checks = jobs.filter(job => job.kind === 'connection');
    const running = checks.filter(job => ['queued', 'running'].includes(job.status)).length;
    const latestSuccess = checks.find(job => job.status === 'succeeded');
    const sourceState = connection || { connected: overview.google_connected, sources: overview.sources };
    const sources = ['ga4', 'gsc', 'keywords'].filter(key => sourceState.sources && Object.hasOwn(sourceState.sources, key));
    return heading('DỮ LIỆU', 'Đồng bộ dữ liệu', 'Theo dõi các lần kiểm tra nguồn Google và trạng thái dữ liệu gần nhất.', `${user.role === 'admin' ? button(icon('refresh', 16) + ' Kiểm tra nguồn', 'check-google', 'primary') : ''}<a class="btn secondary" href="#activity">Lịch sử hoạt động ${icon('arrow', 15)}</a>`) +
        `<section class="sync-summary">
            <article class="sync-stat"><span class="sync-stat-icon blue">${icon('refresh', 20)}</span><div><span>Tác vụ kiểm tra đang chạy</span><strong>${num(running)}</strong></div></article>
            <article class="sync-stat"><span class="sync-stat-icon green">${icon('check', 20)}</span><div><span>Kiểm tra thành công gần nhất</span><strong>${latestSuccess ? time(latestSuccess.finished_at || latestSuccess.created_at) : '—'}</strong></div></article>
            <article class="sync-stat"><span class="sync-stat-icon violet">${icon('folder', 20)}</span><div><span>Nguồn có trạng thái ghi nhận</span><strong>${num(sources.length)}</strong></div></article>
        </section>
        <section class="card sync-sources"><div class="card-header"><div><h2>Tình trạng nguồn dữ liệu</h2><p class="muted">Độ mới được lấy từ lần xử lý dữ liệu thật gần nhất.</p></div><a class="btn text" href="#connections/google">Chi tiết kết nối ${icon('arrow', 15)}</a></div>${sources.length ? table(['Nguồn dữ liệu', 'Trạng thái', 'Dữ liệu đến', 'Lần lấy gần nhất'], sources.map(key => {
            const { source, status } = googleSourceStatus(sourceState, key);
            return [`<div class="cell-title"><span class="source-icon ${key}">${icon(key === 'ga4' ? 'chart' : key === 'gsc' ? 'search' : 'file')}</span><span>${sourceNames[key]}</span></div>`, badge(status), date(source.latest_available_date), time(source.fetched_at)];
        })) : empty('Chưa có dữ liệu nguồn', 'Trạng thái nguồn sẽ xuất hiện sau khi có dữ liệu được kiểm tra.')}</section>
        <section class="card sync-history"><div class="card-header"><div><h2>Lịch sử kiểm tra nguồn</h2><p class="muted">Chỉ hiển thị các tác vụ kiểm tra Google có trong lịch sử thật.</p></div></div>${checks.length ? table(['Tác vụ', 'Khoảng dữ liệu', 'Trạng thái', 'Thời gian', ''], checks.map(job => [
            `<div class="cell-title">${icon('refresh', 17)}<span>${esc(kindNames[job.kind] || 'Kiểm tra nguồn')}<small>${esc(job.actor || 'Người dùng hệ thống')}</small></span></div>`,
            `${date(job.params?.start)} → ${date(job.params?.end)}`,
            badge(job.status),
            time(job.created_at),
            button('Chi tiết', 'job-detail', 'text', `data-id="${esc(job.id)}"`)
        ])) : empty('Chưa có lịch sử đồng bộ', 'Các lần kiểm tra nguồn đã chạy sẽ xuất hiện tại đây.')}</section>`;
}

export function connectionsView(d, meta = {}) {
    const keys = ['ga4', 'gsc', 'keywords'];
    const attentionStatuses = ['permission_denied', 'api_error', 'invalid_data', 'incomplete', 'revoked', 'timeout'];
    const knownSources = keys.map(key => d.sources?.[key]).filter(source => source?.status);
    const readyCount = knownSources.filter(source => source.status === 'ready').length;
    const attentionCount = knownSources.filter(source => attentionStatuses.includes(source.status)).length;
    const connectedValue = knownSources.length ? `${num(readyCount)} / ${num(knownSources.length)}` : '—';
    const attentionValue = knownSources.length ? num(attentionCount) : '—';
    return heading('TÍCH HỢP DỮ LIỆU', 'Kết nối nền tảng', 'Quản lý tài khoản Google, tài sản dữ liệu và độ mới của từng nguồn.', d.connected ? button(icon('refresh', 16) + ' Kiểm tra nguồn', 'check-google', 'primary') : '') +
        (!d.configured ? notice('Chưa cấu hình Google OAuth ở backend. Quản trị hệ thống cần thêm Web client ID và secret trong file .env, sau đó khởi động lại ứng dụng. Không nhập token trên giao diện.', 'amber') : '') +
        `<section class="connection-summary" aria-label="Tóm tắt kết nối">
            <article class="connection-summary-card card"><span class="connection-summary-icon green">${icon('link', 20)}</span><div><span>Nguồn sẵn sàng</span><strong>${connectedValue}</strong><small>Chỉ tính nguồn Google có trạng thái thực</small></div></article>
            <article class="connection-summary-card card"><span class="connection-summary-icon amber">${icon('alert', 20)}</span><div><span>Nguồn cần chú ý</span><strong>${attentionValue}</strong><small>Quyền truy cập, lỗi API hoặc dữ liệu</small></div></article>
        </section>
        <section class="connection-google card"><div class="connection-google-head"><span class="connection-provider-icon google">${icon('google', 28)}</span><div class="connection-google-info"><span class="eyebrow">TÀI KHOẢN GOOGLE OAUTH</span><h2>${d.connected ? esc(d.email || 'Tài khoản Google đã kết nối') : 'Chưa kết nối Google'}</h2><p>${d.connected ? `Kết nối ${optionalTime(d.connected_at)} · Kiểm tra gần nhất ${optionalTime(d.checked_at)}` : 'Cấp quyền chỉ đọc để truy cập các nguồn Google được cấu hình.'}</p></div><span class="connection-status">${badge(d.connected ? 'ready' : 'disconnected')}</span></div><div class="connection-google-actions">${button(d.connected ? 'Kết nối lại' : 'Kết nối Google', 'connect-google', 'primary', !d.configured ? 'disabled' : '')}${d.connected ? button('Ngắt kết nối', 'disconnect-google', 'danger') : ''}<a class="btn text" href="#connections/google">Chi tiết Google ${icon('arrow', 15)}</a></div></section>
        <section class="connection-provider-grid">
            ${keys.map(key => {
            const { source, status } = googleSourceStatus(d, key);
            return `<article class="connection-source card"><div class="connection-card-title"><span class="source-icon ${key}">${icon(key === 'ga4' ? 'chart' : key === 'gsc' ? 'search' : 'file', 21)}</span><div><h2>${assetLabels[key]}</h2><p>${key === 'keywords' ? 'Google Sheets · bảng từ khóa' : 'Nguồn Google được cấp quyền'}</p></div>${badge(status)}</div><dl class="connection-facts"><div><dt>Tài khoản Google</dt><dd>${esc(d.connected ? d.email || 'Đã kết nối' : '—')}</dd></div><div><dt>Tài sản cấu hình</dt><dd>${esc(d.assets?.[key] || '—')}</dd></div><div><dt>Dữ liệu đến</dt><dd>${optionalDate(source.latest_available_date)}</dd></div><div><dt>Kiểm tra gần nhất</dt><dd>${optionalTime(source.fetched_at)}</dd></div>${source.error ? `<div><dt>Thông tin</dt><dd class="connection-error">${esc(source.error)}</dd></div>` : ''}</dl><div class="connection-provider-actions"><a class="btn text" href="#connections/google">Chi tiết nguồn ${icon('arrow', 14)}</a></div></article>`;
        }).join('')}
            ${metaConnectionCard(meta)}
            <article class="connection-source card connection-unsupported"><div class="connection-card-title"><span class="source-icon tiktok">${icon('link', 21)}</span><div><h2>TikTok</h2><p>TikTok Ads</p></div><span class="badge neutral">Chưa tích hợp</span></div><dl class="connection-facts"><div><dt>Tài khoản / tài sản</dt><dd>—</dd></div><div><dt>Trạng thái</dt><dd>Chưa có tích hợp backend</dd></div></dl><div class="connection-provider-actions"><a class="btn text" href="#connections/tiktok">Thông tin tích hợp ${icon('arrow', 15)}</a></div></article>
            <article class="connection-source card connection-unsupported"><div class="connection-card-title"><span class="source-icon youtube">${icon('file', 21)}</span><div><h2>YouTube</h2><p>YouTube Analytics</p></div><span class="badge neutral">Chưa tích hợp</span></div><dl class="connection-facts"><div><dt>Tài khoản / tài sản</dt><dd>—</dd></div><div><dt>Trạng thái</dt><dd>Chưa có tích hợp backend</dd></div></dl><div class="connection-provider-actions"><span class="connection-unavailable">Chưa kết nối · —</span></div></article>
            <article class="connection-source card connection-manual"><div class="connection-card-title"><span class="source-icon gmb">${icon('upload', 21)}</span><div><h2>Google Business Profile</h2><p>Nhập dữ liệu CSV thủ công</p></div><span class="badge blue">Nhập thủ công</span></div><dl class="connection-facts"><div><dt>Tài khoản / tài sản</dt><dd>—</dd></div><div><dt>Trạng thái</dt><dd>Quản lý qua CSV</dd></div></dl><div class="connection-provider-actions"><a class="btn text" href="#uploads">Quản lý dữ liệu CSV ${icon('arrow', 15)}</a></div></article>
        </section>
        <section class="card connection-help"><div class="card-body">${notice('Trạng thái nguồn Google phản ánh lần kiểm tra dữ liệu thực tế; trạng thái OAuth riêng lẻ không đảm bảo dữ liệu đã đồng bộ. Meta hỗ trợ kết nối OAuth; TikTok và YouTube chưa có tích hợp backend.', 'blue')}</div></section>`;
}

function metaConnectionCard(d, detail = false) {
    const labels = { connected: 'Đã kết nối OAuth', disconnected: 'Chưa kết nối', expired: 'Quyền đã hết hạn', reconnect_required: 'Cần kết nối lại', error: 'Không đọc được kết nối' };
    return `<article class="connection-source card connection-meta"><div class="connection-card-title"><span class="source-icon facebook">${icon('link', 21)}</span><div><h2>Meta</h2><p>Facebook Content · Facebook Ads</p></div><span class="badge ${d.connected ? 'green' : 'neutral'}">${esc(labels[d.status] || 'Chưa có trạng thái')}</span></div>
        ${!d.configured ? notice('Chưa cấu hình Meta OAuth. Quản trị hệ thống cần thiết lập App ID, App Secret, Config ID và redirect URI ở backend.', 'amber') : ''}
        ${d.status === 'error' ? notice('Không thể đọc thông tin kết nối đã lưu. Kiểm tra khóa mã hóa ở backend hoặc ngắt kết nối và cấp quyền lại.', 'amber') : ''}
        <dl class="connection-facts"><div><dt>Tài khoản</dt><dd>${esc(d.account_name || '—')}</dd></div><div><dt>ID tài khoản</dt><dd>${esc(d.account_id || '—')}</dd></div><div><dt>Ngày kết nối</dt><dd>${optionalTime(d.connected_at)}</dd></div><div><dt>Hết hạn token</dt><dd>${optionalTime(d.expires_at)}</dd></div>${detail ? `<div><dt>Hết hạn truy cập dữ liệu</dt><dd>${optionalTime(d.data_access_expires_at)}</dd></div><div><dt>Quyền đã xác nhận</dt><dd>${esc(d.scopes?.join(', ') || '—')}</dd></div>` : ''}</dl>
        ${d.connected ? '<p class="form-note">Đã xác thực Meta. Chưa chọn tài sản dữ liệu.</p>' : ''}
        <p class="form-note">Trạng thái từ lần cấp quyền đã lưu; chưa kiểm tra thu hồi tại Meta. Chưa khám phá tài sản hoặc đồng bộ dữ liệu Facebook.</p>
        <div class="connection-provider-actions">${button(d.has_connection ? 'Kết nối lại Meta' : 'Kết nối Meta', 'connect-facebook', 'primary', d.configured ? '' : 'disabled')}${d.has_connection ? button('Ngắt kết nối', 'disconnect-meta', 'danger') : ''}${detail ? '<a class="btn text" href="#connections">Quay lại danh sách</a>' : `<a class="btn text" href="#connections/facebook">Chi tiết kết nối ${icon('arrow', 15)}</a>`}</div></article>`;
}

export function platformConnectionsView(d = {}, meta = {}) {
    return connectionsView(d, meta);
}

export function platformDetailView(platform, meta = {}) {
    if (platform === 'facebook') return heading('TÍCH HỢP DỮ LIỆU', 'Facebook', 'Kết nối tài khoản Meta của KinderHealth.') + metaConnectionCard(meta, true);
    const providers = {
        tiktok: { name: 'TikTok', label: 'TikTok Business API', description: 'Quản lý kết nối tài khoản TikTok Business và dữ liệu quảng cáo.', status: 'TikTok API chưa được tích hợp ở backend. Hiện chưa thể xác thực hoặc đồng bộ dữ liệu TikTok.', setup: 'Cần đăng ký ứng dụng TikTok for Business, thiết lập OAuth và cấp quyền cho tài khoản quảng cáo.', url: 'https://business-api.tiktok.com/portal/docs' }
    };
    const provider = providers[platform];
    if (!provider) return '';
    return heading('TÍCH HỢP DỮ LIỆU', provider.name, provider.description) + `<section class="card"><div class="card-body"><div class="source-top"><span class="source-icon ${platform}">${icon('link', 22)}</span>${badge('disconnected')}</div><h2>${esc(provider.label)}</h2><p>${esc(provider.status)}</p><div class="details spaced"><dl><dt>Trạng thái</dt><dd>Chưa kết nối</dd><dt>Điều kiện tích hợp</dt><dd>${esc(provider.setup)}</dd></dl></div><div class="actions spaced"><button class="btn primary" type="button" disabled title="Backend kết nối nền tảng này chưa được triển khai">Kết nối ${esc(provider.name)}</button><a class="btn secondary" href="${provider.url}" target="_blank" rel="noopener noreferrer">${icon('external', 15)} Tài liệu chính thức</a><a class="btn text" href="#connections">Quay lại danh sách</a></div></div></section>`;
}

const metrics = { ga4: [['activeUsers', 'Người dùng hoạt động'], ['sessions', 'Phiên truy cập'], ['screenPageViews', 'Lượt xem trang'], ['engagementRate', 'Tỷ lệ tương tác', true]], gsc: [['clicks', 'Lượt nhấp'], ['impressions', 'Lượt hiển thị'], ['ctr', 'CTR', true], ['position', 'Vị trí trung bình']], keywords: [['top5', 'Top 5'], ['top10', 'Top 10'], ['top20', 'Top 20'], ['top100', 'Top 100']], gmb: [['views', 'Lượt hiển thị'], ['calls', 'Cuộc gọi'], ['directions', 'Lượt chỉ đường'], ['website_clicks', 'Nhấp website']] };
const columnNames = { date: 'Ngày', activeUsers: 'Người dùng', sessions: 'Phiên', screenPageViews: 'Lượt xem trang', engagementRate: 'Tỷ lệ tương tác', clicks: 'Lượt nhấp', impressions: 'Lượt hiển thị', ctr: 'CTR', position: 'Vị trí', query: 'Truy vấn', keyword: 'Từ khóa', url: 'URL đích', sessionDefaultChannelGroup: 'Kênh truy cập', pagePath: 'Trang', location: 'Mã cơ sở', name: 'Tên cơ sở', search_mobile: 'Tìm kiếm mobile', search_desktop: 'Tìm kiếm desktop', maps_mobile: 'Maps mobile', maps_desktop: 'Maps desktop', calls: 'Cuộc gọi', directions: 'Chỉ đường', website_clicks: 'Nhấp website' };
export function dataTable(rows, title, page = 0) {
    if (!rows?.length) return `<h3>${esc(title)}</h3>${empty('Không có dữ liệu', 'Nguồn không trả về hàng dữ liệu cho bảng này.')}`;
    const keys = Object.keys(rows[0]); const limited = rows.slice(page * 50, page * 50 + 50);
    return `<h3>${esc(title)} <span class="tag">${num(rows.length)} hàng</span></h3>${table(keys.map(k => columnNames[k] || k), limited.map(r => keys.map(k => `<span class="${typeof r[k] === 'string' && r[k].length > 50 ? 'wrap' : ''}">${k === 'date' ? date(r[k]) : typeof r[k] === 'number' ? num(r[k], ['ctr', 'engagementRate'].includes(k)) : esc(r[k])}</span>`)))}${rows.length > 50 ? `<p class="form-note">Đang hiển thị ${page * 50 + 1}–${Math.min((page + 1) * 50, rows.length)} / ${rows.length} hàng. Excel chứa toàn bộ ${rows.length} hàng của kết quả.</p>` : ''}`;
}
function sourceSection(key, s, p, detail = false, state = {}) {
    const error = s.error ? notice(s.error, 'red') : '';
    const warnings = (s.warnings || []).filter(w => !(p.demo && typeof w === 'string' && /^DEMO\s*[·:]/i.test(w)));
    const metadata = [
        s.latest_available_date && `Dữ liệu đến ${date(s.latest_available_date)}`,
        s.fetched_at && `Lấy lúc ${time(s.fetched_at)}`,
        s.last_success_at && `Thành công lần cuối ${time(s.last_success_at)}`
    ].filter(Boolean).join(' · ');
    const trend = s.daily?.length
        ? chart(s.daily, key === 'ga4' ? 'sessions' : 'clicks', key, p.start, p.end)
        : `<div class="analysis-no-trend">${empty('Chưa có dữ liệu xu hướng', 'Nguồn này không có dữ liệu phân bổ theo ngày trong Dataset hiện tại.')}</div>`;
    return `<section class="source-section"><div class="section-title"><span class="source-icon ${key}">${icon(key === 'gsc' ? 'search' : key === 'ga4' ? 'chart' : 'file')}</span><h2>${esc(sourceNames[key])}</h2>${badge(s.status)}${metadata ? `<small>${esc(metadata)}</small>` : ''}</div><div class="spaced">${error}${warnings.map(w => notice(w, 'amber')).join('')}</div>${s.totals ? `<div class="kpis">${metrics[key].map(([m, label, percent]) => `<div class="kpi"><label>${label}</label><strong>${num(s.totals[m], percent)}</strong>${p.compare ? `<small>Kỳ trước: ${num(s.previous?.[m], percent)}</small>` : ''}</div>`).join('')}</div>` : ''}${trend}${detail ? `<p class="form-note">Múi giờ nguồn: ${esc(s.timezone || '—')} · Tài sản: ${esc(s.asset || '—')}</p>${key === 'gsc' ? `<p class="form-note">Loại tìm kiếm: web · Loại trừ /san-pham/: ${p.exclude_products ? 'Có' : 'Không'}</p>` : ''}${s.daily ? dataTable(s.daily, 'Dữ liệu theo ngày', state.tablePage || 0) : ''}${s.queries ? dataTable(s.queries, 'Truy vấn tìm kiếm', state.tablePage || 0) : ''}${s.entries ? dataTable(s.entries, 'Dữ liệu chi tiết', state.tablePage || 0) : ''}${s.channels ? dataTable(s.channels, 'Nguồn truy cập', state.tablePage || 0) : ''}${s.pages ? dataTable(s.pages, 'Trang được xem', state.tablePage || 0) : ''}` : ''}</section>`;
}

function compactDatasetId(id) {
    return id.length > 18 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id;
}

export function analysisResults(state) {
    const d = state.dataset;
    if (!d) return `<section class="card">${empty('Sẵn sàng cho một góc nhìn mới', 'Chọn loại báo cáo và khoảng ngày, sau đó bấm Xem báo cáo. Dữ liệu sẽ được lấy trực tiếp từ các nguồn được cấu hình.')}</section>`;
    const selected = state.tab || 'summary';
    const keys = Object.keys(d.sources);
    const readyCount = keys.filter(k => d.sources[k]?.status === 'ready').length;
    const attentionCount = keys.length - readyCount;
    const sourceCards = keys.map(key => {
        const source = d.sources[key];
        const metadata = [
            source.latest_available_date && ['Dữ liệu đến', date(source.latest_available_date)],
            source.fetched_at && ['Lấy lúc', time(source.fetched_at)],
            source.last_success_at && ['Thành công lần cuối', time(source.last_success_at)]
        ].filter(Boolean);
        const messages = [
            source.error && notice(source.error, 'red'),
            ...(source.warnings || [])
                .filter(w => !(d.params.demo && typeof w === 'string' && /^DEMO\s*[·:]/i.test(w)))
                .map(w => notice(w, 'amber'))
        ].filter(Boolean);
        return `<article class="analysis-source-card"><div class="analysis-source-card-heading"><strong>${esc(sourceNames[key] || key)}</strong>${badge(source.status)}</div>${metadata.length ? `<dl>${metadata.map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>` : ''}${messages.length ? `<div class="analysis-source-card-messages">${messages.join('')}</div>` : ''}</article>`;
    }).join('');
    const datasetId = compactDatasetId(d.id);
    return `<div class="analysis-results-stack">${d.params.demo ? notice('DEMO · Số liệu mô phỏng để trình diễn. Bạn có thể đổi kỳ, xuất Excel và lưu bản HTML.', 'blue') : ''}<section class="analysis-quality-card card"><div class="analysis-section-heading"><div><span class="eyebrow">DATA QUALITY</span><h2>Chất lượng &amp; độ mới dữ liệu</h2></div><span class="analysis-snapshot-note">Snapshot phân tích · Không tự động làm mới</span></div><div class="analysis-quality-metrics"><article><span>Nguồn sẵn sàng</span><strong>${keys.length ? `${readyCount} / ${keys.length}` : '—'}</strong><small>Trạng thái nguồn: Sẵn sàng</small></article><article class="${attentionCount ? 'needs-attention' : ''}"><span>Nguồn cần chú ý</span><strong>${keys.length ? attentionCount : '—'}</strong><small>Đếm từ trạng thái nguồn thực tế</small></article><article><span>Kỳ dữ liệu</span><strong>${date(d.params.start)} – ${date(d.params.end)}</strong><small>${d.params.compare ? `So sánh ${date(d.params.previous_start)} – ${date(d.params.previous_end)}` : 'Không bật so sánh kỳ trước'}</small></article><article><span>Dataset snapshot</span><strong class="analysis-dataset-id" title="${esc(d.id)}">${esc(datasetId)}</strong><small>${d.exportable ? 'Đủ điều kiện xuất Excel' : 'Chưa đủ điều kiện xuất Excel'}</small></article></div><div class="analysis-source-status-grid">${sourceCards}</div></section><section class="card analysis-result-card"><div class="tabs"><button data-action="analysis-tab" data-tab="summary" class="${selected === 'summary' ? 'active' : ''}">Tổng hợp</button>${keys.map(k => `<button data-action="analysis-tab" data-tab="${k}" class="${selected === k ? 'active' : ''}">${esc(sourceNames[k] || k)}</button>`).join('')}</div>${(selected === 'summary' ? keys : keys.filter(k => k === selected)).map(k => sourceSection(k, d.sources[k], d.params, selected !== 'summary', state)).join('')}${selected !== 'summary' && Math.max(d.sources[selected]?.daily?.length || 0, d.sources[selected]?.queries?.length || 0, d.sources[selected]?.entries?.length || 0) > 50 ? `<div class="table-pagination">${button('← Trang trước', 'table-prev', 'secondary', state.tablePage > 0 ? '' : 'disabled')}<span>Trang ${(state.tablePage || 0) + 1}</span>${button('Trang sau →', 'table-next', 'secondary', ((state.tablePage || 1) * 50 < Math.max(d.sources[selected]?.daily?.length || 0, d.sources[selected]?.queries?.length || 0, d.sources[selected]?.entries?.length || 0)) ? '' : 'disabled')}</div>` : ''}<div class="card-footer"><span>Kết quả: <span class="code" title="${esc(d.id)}">${esc(datasetId)}</span> · Snapshot bất biến</span><span>${d.exportable ? 'Các nguồn bắt buộc hợp lệ' : 'Chưa thể xuất Excel'}</span></div></section></div>`;
}

export function analysisView(state, types, user) {
    const p = state.draft; const d = state.dataset;
    const select = (name, value, options) => `<select name="${name}" id="filter-${name}">${options.map(([v, l]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const uploadOptions = [['', 'Chọn file CSV'], ...(state.uploads || []).filter(u => !!u.demo === !!p.demo).map(u => [u.id, `${u.name} (${date(u.start_date)} → ${date(u.end_date)})`])];
    const fields = types.filter(t => t.can_generate);
    return `<div class="analysis-page">${heading('PHASE 4A · DATA QUALITY', 'Phân tích & kiểm tra', 'Chạy phân tích và kiểm tra độ mới, trạng thái, cảnh báo dữ liệu trước khi tạo báo cáo.', button(icon('download', 16) + ' Xuất Excel', 'export-modal', 'primary', 'id="export-button" disabled'))}
        <section class="card analysis-filter-card"><div class="card-header analysis-filter-heading"><div><span class="eyebrow">THIẾT LẬP</span><h2>Phạm vi phân tích</h2></div><span class="analysis-filter-hint">Phân tích tạo một Dataset snapshot mới</span></div><form id="analysis-form" class="filter-form">
            <div class="analysis-filter-grid"><div class="field"><label for="filter-report_type">Loại báo cáo</label>${select('report_type', p.report_type, fields.map(t => [t.id, t.label]))}</div><div class="field"><label for="filter-start">Từ ngày</label><input id="filter-start" name="start" type="date" value="${esc(p.start)}" required></div><div class="field"><label for="filter-end">Đến ngày</label><input id="filter-end" name="end" type="date" value="${esc(p.end)}" required></div><button class="btn primary analysis-run-button" type="submit" ${state.job ? 'disabled' : ''}>${state.job ? '<span class="spinner"></span> Đang phân tích' : icon('chart', 16) + ' Phân tích dữ liệu'}</button></div>
            <div class="analysis-filter-options"><div class="presets">${[['last7', '7 ngày'], ['last28', '28 ngày'], ['this_month', 'Tháng này'], ['previous_month', 'Tháng trước']].map(([k, l]) => `<button type="button" data-action="preset" data-value="${k}">${l}</button>`).join('')}</div><div class="analysis-filter-toggles"><label class="check"><input type="checkbox" name="compare" ${p.compare ? 'checked' : ''}> So sánh kỳ trước</label>${['seo', 'gsc'].includes(p.report_type) ? `<label class="check"><input type="checkbox" name="exclude_products" ${p.exclude_products ? 'checked' : ''}> GSC: loại trừ /san-pham/</label>` : ''}${state.overview?.demo_enabled ? `<label class="check demo-choice"><input type="checkbox" name="demo" ${p.demo ? 'checked' : ''}> Dữ liệu DEMO</label>` : ''}</div></div>
            <p class="form-note analysis-comparison-note" id="comparison-period"></p>${p.report_type === 'gmb' ? `<div class="form-grid spaced"><div class="field"><label for="filter-upload_id">CSV kỳ này · Phải khớp khoảng ngày</label>${select('upload_id', p.upload_id, uploadOptions)}</div>${p.compare ? `<div class="field"><label for="filter-previous_upload_id">CSV kỳ trước · Cùng cơ sở</label>${select('previous_upload_id', p.previous_upload_id, uploadOptions)}</div>` : ''}</div>` : ''}<div class="dirty" id="dirty-note">${icon('alert', 15)} Bộ lọc đã thay đổi — bấm Phân tích dữ liệu để áp dụng. Xuất Excel đang tạm khóa.</div>
        </form><div class="applied" id="applied-period">${d ? `<span>Đang hiển thị: <strong>${date(d.params.start)} → ${date(d.params.end)}</strong>${d.params.compare ? ` · So sánh: ${date(d.params.previous_start)} → ${date(d.params.previous_end)}` : ''}</span><span>Lấy lúc ${time(d.created_at)}</span>` : '<span>Chưa có bộ lọc được áp dụng.</span>'}</div></section><div id="job-progress"></div><div id="analysis-results">${analysisResults(state)}</div>${d && d.exportable && user.role !== 'viewer' ? `<div class="actions analysis-save-actions">${button(icon('folder', 16) + ' Lưu thành báo cáo HTML', 'save-report', 'secondary', 'id="save-report-button"')}<span class="form-note">Lưu bản nháp từ Dataset snapshot đang xem.</span></div>` : ''}</div>`;
}

export function reportsView(reports, types, user, filter = {}) {
    const list = reports.filter(r => (!filter.type || r.report_type === filter.type) && (!filter.q || r.name.toLowerCase().includes(filter.q.toLowerCase())) && (!filter.status || (filter.status === 'published' ? r.published_at : !r.published_at)));
    return heading('THƯ VIỆN BÁO CÁO', 'Báo cáo đã lưu', 'Các phiên bản HTML được lưu độc lập với kết quả phân tích đang xem.', `${user.role === 'admin' ? button(icon('download', 16) + ' Nhập báo cáo cũ', 'import-reports') : ''}<a class="btn primary" href="#analysis">${icon('plus', 16)} Tạo báo cáo mới</a>`) +
        `<section class="card"><form id="report-filter" class="toolbar"><input name="q" placeholder="Tìm tên báo cáo…" aria-label="Tìm tên báo cáo" value="${esc(filter.q || '')}"><select name="type" aria-label="Loại báo cáo"><option value="">Tất cả loại báo cáo</option>${types.map(t => `<option value="${t.id}" ${filter.type === t.id ? 'selected' : ''}>${esc(t.label)}</option>`).join('')}</select><select name="status" aria-label="Trạng thái"><option value="">Tất cả trạng thái</option><option value="published" ${filter.status === 'published' ? 'selected' : ''}>Đã xuất bản</option><option value="draft" ${filter.status === 'draft' ? 'selected' : ''}>Bản nháp / phiên bản cũ</option></select><button class="btn secondary">Lọc</button><span class="count">${list.length} phiên bản</span></form>${list.length ? table(['Báo cáo / nguồn', 'Kỳ dữ liệu', 'Ngày lưu', 'Trạng thái', 'Phiên bản', 'Thao tác'], list.map(r => [
            `<div class="cell-title">${icon('file', 19)}<span>${esc(r.name)}<small>${r.origin === 'demo' ? 'DEMO · Số liệu mô phỏng' : r.origin === 'legacy' ? 'HTML nhập từ hệ thống cũ · Chưa kiểm chứng dữ liệu' : 'Tạo từ dữ liệu nguồn đã kiểm tra'}</small></span></div>`, r.start_date ? `${date(r.start_date)} → ${date(r.end_date)}` : '<span class="muted">Chưa có metadata kỳ</span>', time(r.created_at), `<span class="badge ${r.published_at ? 'green' : 'neutral'}">${r.published_at ? 'Đã xuất bản' : 'Bản lưu'}</span>`, `<span class="tag">v${r.version}</span>`,
            `<div class="actions">${button(icon('eye', 15), 'preview-report', 'text', `data-id="${r.id}" title="Xem trước" aria-label="Xem trước ${esc(r.name)}"`)}<a class="btn text" href="/api/reports/${r.id}/html?download=1" aria-label="Tải HTML" title="Tải HTML">${icon('download', 15)}</a>${button('Lịch sử', 'report-versions', 'text', `data-type="${r.report_type}"`)}${user.role !== 'viewer' && r.origin !== 'demo' && r.valid && !r.published_at ? button('Xuất bản', 'publish-report', 'text', `data-id="${r.id}"`) : ''}</div>`])) : empty('Chưa có báo cáo phù hợp', 'Tạo báo cáo từ màn hình Phân tích hoặc nhập HTML sẵn có từ hệ thống cũ.')}</section>${notice('Xuất bản tại đây chọn phiên bản hiện hành trong ứng dụng nội bộ. Chỉ người được cấp quyền mới xem được. Xuất Excel là một thao tác riêng.', 'blue')}`;
}

export function activityView(jobs, events, user, filter = '') { const selected = filter ? jobs.filter(j => j.status === filter) : jobs; return heading('THEO DÕI VẬN HÀNH', 'Lịch sử hoạt động', 'Theo dõi từng lần chạy, từng nguồn dữ liệu và người thực hiện.', button(icon('refresh', 16) + ' Làm mới', 'refresh-page')) + `<section class="card"><div class="toolbar"><h2>Tác vụ gần đây</h2><select id="job-status-filter" aria-label="Lọc trạng thái"><option value="">Tất cả trạng thái</option>${['queued', 'running', 'succeeded', 'partial', 'failed', 'interrupted'].map(s => `<option value="${s}" ${filter === s ? 'selected' : ''}>${{ queued: 'Đang chờ', running: 'Đang chạy', succeeded: 'Thành công', partial: 'Thành công một phần', failed: 'Thất bại', interrupted: 'Bị gián đoạn' }[s]}</option>`).join('')}</select><span class="count">${selected.length} tác vụ · tối đa 300 lần gần nhất</span></div>${jobTable(selected)}</section>${user.role === 'admin' ? `<section class="card"><div class="card-header"><h2>Nhật ký quản trị</h2><span class="tag">200 thao tác gần nhất</span></div>${events.length ? table(['Người thực hiện', 'Thao tác', 'Thời gian'], events.map(e => [esc(e.actor || 'Hệ thống'), esc({ seed_demo: 'Thêm bộ dữ liệu demo', login: 'Đăng nhập', setup: 'Khởi tạo hệ thống', upload_csv: 'Tải CSV', import_legacy: 'Nhập báo cáo cũ', google_connect: 'Kết nối Google', google_disconnect: 'Ngắt kết nối Google', publish: 'Xuất bản báo cáo', save_report: 'Lưu báo cáo', create_user: 'Tạo người dùng', update_user: 'Cập nhật người dùng', update_settings: 'Cập nhật cài đặt', create_schedule: 'Tạo lịch', toggle_schedule: 'Đổi trạng thái lịch' }[e.action] || e.action), time(e.at)])) : empty('Chưa có thao tác quản trị')}</section>` : ''}`; }

export function uploadsView(uploads, user, uploadLimit = 5) {
    return heading('DỮ LIỆU ĐẦU VÀO', 'Dữ liệu Google Business Profile', 'Tải CSV, kiểm tra cơ sở và kỳ dữ liệu trước khi tạo báo cáo.', `<a class="btn secondary" href="/static/gmb-template.csv" download>${icon('download', 16)} Tải CSV mẫu cấu trúc</a>`) +
        `${user.role !== 'viewer' ? `<section class="card"><div class="card-body"><form id="upload-form"><div class="dropzone">${icon('upload', 30)}<label for="csv-file">Chọn file CSV Google Business Profile</label><input id="csv-file" type="file" name="file" accept=".csv,text/csv" required><small>CSV UTF-8 · Tối đa ${uploadLimit} MB · Hỗ trợ file Performance Report của Google</small></div><div class="form-grid spaced"><div class="field"><label for="csv-start">Kỳ CSV từ ngày</label><input id="csv-start" type="date" name="start" required></div><div class="field"><label for="csv-end">Kỳ CSV đến ngày</label><input id="csv-end" type="date" name="end" required></div></div><p class="form-note">Kỳ nhập phải khớp tên file nếu tên có ngày. File trùng và kỳ chồng lấn cùng cơ sở sẽ bị từ chối.</p><button class="btn primary" type="submit">${icon('upload', 16)} Kiểm tra & lưu dữ liệu</button></form></div></section>` : ''}<section class="card"><div class="card-header"><h2>CSV đã kiểm tra</h2><span class="tag">${uploads.length} file</span></div>${uploads.length ? table(['Tên file', 'Kỳ dữ liệu', 'Cơ sở', 'Ngày tải', ''], uploads.map(u => [`<div class="cell-title"><span class="source-icon gmb">${icon('file', 18)}</span><span class="table-truncate" title="${esc(u.name)}">${esc(u.name)}</span></div>`, `${date(u.start_date)} → ${date(u.end_date)}`, String(u.locations), time(u.created_at), `<div class="actions">${button('Xem dữ liệu', 'upload-preview', 'text', `data-id="${u.id}"`)}${button('Tạo báo cáo', 'analyze-upload', 'text', `data-id="${u.id}"`)}</div>`])) : empty('Chưa có file CSV', 'Dữ liệu hợp lệ sẽ được lưu theo mã cơ sở và khoảng ngày.')}</section>${notice('CSV chứa số tổng cho cả kỳ. Ứng dụng chỉ dùng khi khoảng ngày khớp chính xác; không tự chia thành số liệu ngày.', 'blue')}`;
}

export function usersView(users) { return heading('QUẢN TRỊ TRUY CẬP', 'Người dùng & phân quyền', 'Tài khoản ứng dụng, vai trò và phạm vi báo cáo được xem.', button(icon('plus', 16) + ' Thêm người dùng', 'new-user', 'primary')) + `<section class="card">${table(['Người dùng', 'Vai trò', 'Phạm vi báo cáo', 'Trạng thái', ''], users.map(u => [`<div class="cell-title"><span class="avatar">${esc(u.name.charAt(0))}</span><span>${esc(u.name)}<small>${esc(u.email)}</small></span></div>`, roles[u.role], u.role === 'admin' ? 'Tất cả báo cáo' : `${u.allowed.length} loại báo cáo`, `<span class="badge ${u.active ? 'green' : 'neutral'}">${u.active ? 'Hoạt động' : 'Đã vô hiệu hóa'}</span>`, button('Chỉnh sửa', 'edit-user', 'text', `data-id="${u.id}"`)]))}</section><div class="grid-3">${[['admin', 'Quản lý kết nối, tài khoản, lịch chạy và cài đặt.'], ['operator', 'Tải CSV, tạo bản nháp và xuất bản báo cáo trong phạm vi được cấp.'], ['viewer', 'Xem, phân tích và xuất Excel các báo cáo được cấp quyền.']].map(([role, desc]) => `<div class="card card-body"><h3>${roles[role]}</h3><p class="muted">${desc}</p></div>`).join('')}</div>`; }

export function settingsView(s) { return heading('CẤU HÌNH ỨNG DỤNG', 'Cài đặt báo cáo', 'Thông tin đơn vị và người lập được dùng cho các báo cáo tạo mới.', s.demo_enabled ? '' : button('Thêm dữ liệu demo', 'seed-demo', 'secondary')) + `<div class="grid-2"><section class="card"><div class="card-header"><h2>Thông tin đơn vị</h2></div><form id="settings-form" class="card-body stack"><div class="field"><label for="org-name">Tên đơn vị</label><input id="org-name" name="name" value="${esc(s.organization.name)}" maxlength="100" required></div><div class="field"><label for="org-author">Người lập báo cáo</label><input id="org-author" name="author" value="${esc(s.organization.author)}" maxlength="100" placeholder="Họ tên / Phòng Marketing"></div><button class="btn primary" type="submit">Lưu cài đặt</button></form></section><section class="card"><div class="card-header"><h2>Chính sách vận hành</h2></div><div class="card-body"><div class="source-meta"><div class="meta-row"><span>Múi giờ báo cáo</span><strong>${s.timezone}</strong></div><div class="meta-row"><span>Lưu phiên bản</span><strong>${s.versions}</strong></div><div class="meta-row"><span>Xuất bản</span><strong>Nội bộ · Yêu cầu đăng nhập</strong></div><div class="meta-row"><span>Google OAuth</span><strong>${s.oauth_configured ? 'Đã cấu hình' : 'Chưa cấu hình'}</strong></div></div>${notice('Bản đã xuất bản chỉ thay đổi khi bạn chọn xuất bản một phiên bản hợp lệ khác. Tác vụ lỗi không ghi đè bản tốt trước đó.', 'blue')}<p class="form-note">Xuất bản GCS và chính sách tự xóa phiên bản chưa được bật. Các bản cũ được giữ để đối chiếu.</p></div></section></div>`; }

export function schedulesView(schedules, types, jobMode = 'worker') { return heading('TỰ ĐỘNG HÓA', 'Lịch cập nhật báo cáo', 'Chạy theo giờ Việt Nam. Tạo bản nháp hoặc xuất bản khi tất cả nguồn bắt buộc hợp lệ.', button(icon('plus', 16) + ' Tạo lịch', 'new-schedule', 'primary')) + notice(jobMode === 'request' ? 'Lịch chạy khi dịch vụ gọi lịch được cấu hình và máy chủ đang hoạt động. Thời điểm chạy phụ thuộc tần suất gọi; tác vụ còn chờ có thể chạy tại Lịch sử hoạt động.' : 'Lịch chạy khi máy chủ ứng dụng đang hoạt động. Nếu máy chủ tắt, lần bị lỡ gần nhất sẽ được xử lý sau khi mở lại.', 'blue') + `<section class="card">${schedules.length ? table(['Tên lịch / Báo cáo', 'Lặp lại', 'Kỳ dữ liệu', 'Lần tới · Việt Nam', 'Hành động', ''], schedules.map(s => [`<div class="cell-title">${icon('clock')}<span>${esc(s.name)}<small>${esc(types.find(t => t.id === s.params.report_type)?.label || s.params.report_type)}</small></span></div>`, `${{ daily: 'Hằng ngày', weekly: 'Hằng tuần', monthly: 'Hằng tháng' }[s.frequency]} · ${s.run_time}${s.frequency === 'weekly' ? ` · ${['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'][s.weekday]}` : s.frequency === 'monthly' ? ` · Ngày ${s.monthday}` : ''}`, { last7: '7 ngày gần nhất', last28: '28 ngày gần nhất', previous_month: 'Tháng trước' }[s.period], s.enabled ? time(s.next_run) : 'Đã tắt', s.publish ? 'Xuất bản khi hợp lệ' : 'Lưu bản nháp', `<div class="actions">${button(s.enabled ? 'Tắt lịch' : 'Bật lịch', 'toggle-schedule', 'secondary', `data-id="${s.id}" data-enabled="${!s.enabled}"`)}${s.last_job ? button('Lần chạy gần nhất', 'job-detail', 'text', `data-id="${s.last_job}"`) : ''}</div>`])) : empty('Chưa có lịch tự động', 'Thêm lịch để tạo báo cáo Google theo ngày, tuần hoặc tháng.')}</section>`; }

export function jobProgress(job) { return `<div class="progress-card"><h3>${['queued', 'running'].includes(job.status) ? '<span class="spinner"></span>' : icon('file', 18)} ${kindNames[job.kind]} ${badge(job.status)}</h3><div class="progress-steps">${job.steps.map(s => `<div class="progress-step">${sourceNames[s.source]} ${badge(s.status)}</div>`).join('') || '<span>Đang chuẩn bị tác vụ…</span>'}</div>${job.error ? notice(job.error, 'red') : ''}</div>`; }
