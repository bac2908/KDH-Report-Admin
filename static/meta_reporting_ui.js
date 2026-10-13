
/**
 * Meta Reporting UI
 * Hiển thị danh sách Facebook Ads và Facebook Content.
 * Không đưa Access Token hoặc App Secret ra frontend.
 */

// Chống chèn HTML không an toàn
const esc = (value) =>
    String(value ?? "").replace(
        /[&<>"']/g,
        (ch) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            })[ch]
    );

/**
 * Render danh sách tài sản Meta.
 *
 * @param {Object} payload - Dữ liệu từ API Meta Assets
 * @param {Object} dates - Khoảng thời gian đồng bộ
 */
export function metaReportingCard(payload = {}, dates = {}) {
    const selected = Array.isArray(payload.selected)
        ? payload.selected
        : [];

    const discovered = payload.discovered ?? {};

    // Lập bảng tài sản đã lưu trong Admin
    const known = new Map(
        selected.map((asset) => [
            `${asset.asset_type}:${asset.external_id}`,
            asset,
        ])
    );

    // Hai nền tảng cần quản lý riêng biệt
    const types = [
        {
            source: "facebook_ads",
            type: "facebook_ad_account",
            label: "Facebook Ads (Ad Account)",
        },
        {
            source: "facebook_content",
            type: "facebook_page",
            label: "Facebook Content (Fanpage)",
        },
    ];

    // Render danh sách cho từng nền tảng
    const sections = types
        .map((spec) => {
            const remote = Array.isArray(discovered[spec.source])
                ? discovered[spec.source]
                : [];

            const assetCards = remote
                .map((item) => {
                    const externalId = String(item.id ?? "");

                    // Tìm tài sản trong danh sách đã chọn
                    const record = known.get(
                        `${spec.type}:${externalId}`
                    );

                    const active = Boolean(
                        record?.enabled && record?.id
                    );

                    // Chỉ hiện các nút Sync/KPI khi tài sản đã chọn
                    const activeButtons = active
                        ? `
                            <button
                                type="button"
                                class="btn primary"
                                data-action="meta-sync-asset"
                                data-id="${esc(record.id)}"
                            >
                                Đồng bộ dữ liệu
                            </button>

                            <button
                                type="button"
                                class="btn secondary"
                                data-action="meta-asset-history"
                                data-id="${esc(record.id)}"
                            >
                                Lịch sử Sync
                            </button>

                            <button
                                type="button"
                                class="btn secondary"
                                data-action="meta-view-kpis"
                                data-id="${esc(record.id)}"
                            >
                                Xem KPI
                            </button>
                        `
                        : "";

                    return `
                        <div class="details meta-asset-card">
                            <strong>
                                ${esc(item.name || externalId)}
                            </strong>

                            <br>

                            <small>
                                ID: ${esc(externalId)}

                                ${
                                    active
                                        ? " · Đã chọn để đồng bộ"
                                        : " · Chưa chọn"
                                }
                            </small>

                            <div class="spaced">
                                <button
                                    type="button"
                                    class="btn secondary"
                                    data-action="meta-select-asset"
                                    data-source="${esc(spec.source)}"
                                    data-external-id="${esc(externalId)}"
                                    data-enabled="${
                                        active ? "false" : "true"
                                    }"
                                >
                                    ${
                                        active
                                            ? "Bỏ chọn"
                                            : "Chọn tài sản"
                                    }
                                </button>

                                ${activeButtons}
                            </div>
                        </div>
                    `;
                })
                .join("");

            return `
                <div class="meta-platform-section">
                    <h3>${esc(spec.label)}</h3>

                    <div class="source-summary-list">
                        ${
                            assetCards ||
                            `
                            <p class="form-note">
                                Không có tài sản được Meta API
                                trả về cho tài khoản này.
                            </p>
                            `
                        }
                    </div>
                </div>
            `;
        })
        .join("");

    // Render toàn bộ giao diện Meta
    return `
        <section class="card meta-reporting-card">
            <span class="eyebrow">
                META API · CHỈ ĐỌC
            </span>

            <h2>
                Chọn tài khoản quảng cáo và Fanpage
            </h2>

            <p>
                Chỉ đồng bộ những tài sản mà Meta cấp quyền
                cho tài khoản đã đăng nhập.

                Dữ liệu phải qua kiểm tra nguồn trước
                khi phát hành báo cáo.
            </p>

            <p>
                <strong>Client:</strong>
                ${esc(payload.client_id)}
            </p>

            <div class="form-grid">
                <div class="field">
                    <label for="meta-sync-start">
                        Từ ngày
                    </label>

                    <input
                        type="date"
                        id="meta-sync-start"
                        value="${esc(dates.start)}"
                    >
                </div>

                <div class="field">
                    <label for="meta-sync-end">
                        Đến ngày
                    </label>

                    <input
                        type="date"
                        id="meta-sync-end"
                        value="${esc(dates.end)}"
                    >
                </div>
            </div>

            <p class="form-note">
                Khoảng thời gian tối đa 90 ngày.
                Không đồng bộ ngày hôm nay khi chưa kết thúc.
            </p>

            ${sections}

            <p class="form-note">
                Facebook Ads và Facebook Content là hai nguồn
                dữ liệu riêng biệt.

                Nếu tài khoản chưa từng chạy quảng cáo,
                Facebook Ads Insights có thể trả về 0 bản ghi.
            </p>

            <p class="form-note">
                KPI hiển thị từ dữ liệu đã lưu trong Admin.
                Dữ liệu chưa xác minh không được coi là
                bằng chứng báo cáo chính thức.
            </p>
        </section>
    `;
}
