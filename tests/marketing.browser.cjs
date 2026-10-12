// Optional real-browser checks; receives only isolated fixture configuration.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.argv[2]);
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const widths = [1440, 768, 390];
const errors = [];
const measurements = [];

async function capture(page, name) {
    for (const width of widths) {
        await page.setViewportSize({ width, height: 960 });
        await page.evaluate(() => document.fonts.ready);
        const size = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
        measurements.push({ name, ...size });
        assert(size.scroll <= size.width + 1, `${name} overflows at ${width}: ${size.scroll}`);
        await page.screenshot({ path: path.join(config.output, `${name}-${width}.png`), fullPage: true });
        if (name === 'viewer-report') {
            await page.screenshot({ path: path.join(config.output, `${name}-${width}-viewport.png`) });
            await page.locator('.pb-chart-grid').screenshot({ path: path.join(config.output, `${name}-${width}-charts.png`) });
            await page.evaluate(() => scrollTo(0, 0));
        }
    }
}

async function ready(page) {
    await page.waitForSelector('#marketing-console:not([aria-busy])');
    assert.equal(await page.locator('#workflow-message').getAttribute('data-error'), 'false', await page.locator('#workflow-message').textContent());
}

async function action(page, selector, urlSuffix) {
    const response = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(urlSuffix));
    await page.locator(selector).click();
    const result = await response;
    assert(result.ok(), `${urlSuffix}: ${await result.text()}`);
    const body = await result.json();
    await ready(page);
    return body;
}

async function login(page, email, password, next = '') {
    await page.goto(config.new + '/login' + next);
    await page.locator('[name=email]').fill(email);
    await page.locator('[name=password]').fill(password);
    const submitted = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/login'));
    await page.locator('button[type=submit]').click();
    const response = await submitted;
    if (response.status() !== 303) {
        const html = await response.text();
        throw new Error(`Login ${response.status()}, origin=${response.request().headers().origin}: ${html.match(/role="alert">([^<]+)/)?.[1] || 'unexpected error'}`);
    }
    await page.waitForURL(url => !url.pathname.startsWith('/login'));
}

(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const adminContext = await browser.newContext();
        const session = await adminContext.request.post(config.admin + '/api/auth/login', {
            headers: { 'X-KDH-Request': '1' },
            data: { email: 'review-admin@example.test', password: 'Review-Password-12345' }
        });
        assert.equal(session.status(), 200);
        const admin = await adminContext.newPage();
        admin.on('pageerror', error => errors.push(String(error)));
        await admin.goto(config.admin + '/marketing');
        await ready(admin);
        await admin.locator('#source').selectOption('gsc');
        await admin.locator('#asset').selectOption(config.asset);
        await admin.locator('#start').fill('2026-09-01');
        await admin.locator('#end').fill('2026-09-03');
        const dataset = await action(admin, '#dataset-form button', '/api/marketing/datasets');
        await admin.locator('#review-note').fill('DEMO QA: independent browser review in isolated test database.');
        await action(admin, '#approve-internal', `/api/marketing/datasets/${dataset.dataset_id}/review`);
        const candidate = await action(admin, '#create-candidate', `/api/marketing/datasets/${dataset.dataset_id}/release-candidates`);
        const candidateId = candidate.release_dataset_id;
        await admin.locator('[name=opportunity]').first().check();
        await admin.locator('#release-note').fill('DEMO QA: approve selected evidence and recommendation for isolated testing only.');
        await action(admin, '#approve-release', `/api/marketing/release-candidates/${candidateId}/approval`);
        await capture(admin, 'admin-approved-candidate');
        await action(admin, '#create-release', `/api/marketing/release-candidates/${candidateId}/release-snapshots`);
        await admin.locator('#report-name').fill('DEMO QA - isolated browser report');
        const bundle = await action(admin, '#create-bundle', '/api/report-bundles');
        await action(admin, '#publish-final', `/api/report-bundles/${bundle.report_id}/revisions/1/publish`);
        await admin.locator('#viewer').selectOption(config.viewer);
        await action(admin, '#grant-access', `/api/report-bundles/${bundle.report_id}/access`);
        const href = await admin.locator('#published-link').getAttribute('href');
        assert.equal(href, `${config.new}/reports/${bundle.report_id}?revision=1`);
        await capture(admin, 'admin-published-access');

        const viewerContext = await browser.newContext();
        const viewer = await viewerContext.newPage();
        viewer.on('pageerror', error => errors.push(String(error)));
        await viewer.goto(config.new + '/login');
        await capture(viewer, 'viewer-login');
        await login(viewer, 'viewer@example.test', 'Viewer-test-password-123');
        await capture(viewer, 'viewer-list');
        await viewer.goto(href);
        await viewer.locator('[data-bundle-chart] svg').first().waitFor();
        assert((await viewer.locator('[data-bundle-chart] svg').count()) >= 2, 'comparison and trend charts render');
        for (const chart of await viewer.locator('[data-bundle-chart]').all()) {
            const ticks = await chart.locator('svg > text[text-anchor=end]').allTextContents();
            assert.equal(new Set(ticks).size, ticks.length, 'ratio axis ticks must remain distinguishable');
        }
        const point = viewer.locator('.pb-chart-surface svg [tabindex="0"]').first();
        await point.focus();
        assert(await viewer.locator('.pb-chart-tooltip').first().isVisible(), 'chart tooltip supports keyboard focus');
        await point.evaluate(element => element.blur());
        assert((await viewer.locator('body').textContent()).includes('360'), 'stored prior-period value present');
        assert((await viewer.locator('body').textContent()).includes('Đã duyệt phát hành'), 'approved recommendation label');
        assert(!(await viewer.content()).includes('test-viewer-service-only'), 'no service token in browser');
        await capture(viewer, 'viewer-report');
        await viewer.locator('#pb-menu').click();
        assert.equal(await viewer.locator('#pb-menu').getAttribute('aria-expanded'), 'true');
        await viewer.keyboard.press('Shift+Tab');
        assert.equal(await viewer.locator(':focus').getAttribute('type'), 'submit', 'logout is keyboard-accessible in mobile menu');
        await viewer.keyboard.press('Tab');
        assert(await viewer.locator('.pb-brand').evaluate(element => element === document.activeElement));
        await viewer.keyboard.press('Escape');
        assert.equal(await viewer.locator('#pb-menu').getAttribute('aria-expanded'), 'false');
        await viewer.locator('#pb-menu').click();
        await viewer.locator('[data-published-section=seo]').click();
        assert.equal(await viewer.locator('#pb-menu').getAttribute('aria-expanded'), 'false');
        assert(new URL(viewer.url()).searchParams.get('revision') === '1');

        await action(admin, '#revoke-access', `/api/report-bundles/${bundle.report_id}/access`);
        const denied = await viewer.goto(href);
        assert.equal(denied.status(), 404, 'revocation immediately enforced');
        await capture(viewer, 'viewer-access-denied');
        const previewContext = await browser.newContext();
        const preview = await previewContext.newPage();
        preview.on('pageerror', error => errors.push(String(error)));
        await login(preview, 'review-admin@example.test', 'Review-Password-12345', '?next=' + encodeURIComponent('/internal-preview/' + candidateId));
        assert((await preview.locator('body').textContent()).includes('CHƯA XUẤT BẢN'));
        await capture(preview, 'admin-internal-preview');
        assert.deepEqual(errors, [], 'no JavaScript runtime errors');
        fs.writeFileSync(path.join(config.output, 'result.json'), JSON.stringify({ status: 'PASS', fixture: 'isolated DEMO QA; never business data', widths, measurements, errors }, null, 2));
        console.log('PASS: browser create/review/approve/publish/grant/revoke, New login/charts/navigation/preview; 21 responsive screenshots; no overflow or JavaScript errors.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
