# Meta OAuth foundation

Admin supports connecting one Meta user account for KinderHealth (`client_kinderhealth`). This is an OAuth connection only: no Page/ad-account discovery, insights, sync jobs, Dataset creation, or KDH-Report-New integration. Google OAuth and its existing routes are unchanged.

## Configuration

Configure these backend environment variables (see `.env.example` and `compose.yaml`):

| Variable | Purpose |
| --- | --- |
| `META_APP_ID` | Numeric Meta App ID |
| `META_APP_SECRET` | App Secret; never expose to frontend or commit |
| `META_CONFIG_ID` | Numeric Facebook Login for Business configuration ID; select a user access token |
| `META_GRAPH_VERSION` | Explicit Graph API version; defaults to `v26.0` |
| `META_REDIRECT_URI` | Exact registered URI, ending in `/api/meta/callback` |

Enable Facebook Login for Business for the Meta app, create a configuration for a **user access token**, and register the exact callback URI. The callback must share the `APP_URL` origin; HTTPS is required except for loopback development. Use `COOKIE_SECURE=1` with production HTTPS. Access in Meta development mode depends on the app's configured roles/test users and permission access. System-user tokens are not supported by this user-token flow.

For the intended local configuration, use `APP_URL=http://localhost:8090` and `META_REDIRECT_URI=http://localhost:8090/api/meta/callback`, then open `http://localhost:8090` in the browser. Do not switch between `localhost` and `127.0.0.1` during login: they have different session cookies. If the Meta URI is omitted/empty, it derives from `APP_URL`; explicit values are preserved and checked. `.env.example` uses matching localhost origins for both providers. Existing deployments keep their own registered Google URI; runtime Google OAuth is unchanged.

The authorization URL passes `config_id`, `response_type=code` and `override_default_response_type=true`; it does not also pass a conflicting `scope` parameter. The app's Meta configuration must grant the read permissions centralized in `kdh/meta.py::REQUIRED_PERMISSIONS`: `pages_show_list`, `pages_read_engagement`, and `ads_read`. Callback validates the actual returned grant before saving. Configure only these required read permissions in the Meta dashboard; no write/manage-ad permission is needed. `read_insights` is deferred until its use and app access are confirmed for a later reporting integration. Grant validation does not enumerate assets or call Insights.

Restart the backend, sign in as an Admin, and choose **Kết nối Meta** on the Meta card under **Kết nối nền tảng** (or in its Facebook detail page). Approve the login and return to the same Admin browser session. A successful connection shows the confirmed account, timestamps, expiry, and granted scopes, with **Đã xác thực Meta. Chưa chọn tài sản dữ liệu.** It does not indicate that report data is available. To change accounts, disconnect the existing account before reconnecting.

## Admin API

All four routes require an active Admin session. POST/DELETE also require existing `X-KDH-Request`, CSRF, and Origin protections.

| Route | Behavior |
| --- | --- |
| `GET /api/meta` | Local, read-only status; never calls Meta or returns credentials |
| `POST /api/meta/connect` | Returns `{url}` for the authorization-code flow |
| `GET /api/meta/callback` | Consumes state, exchanges/validates the code, saves encrypted credentials, redirects to `/#connections/facebook?oauth=success\|denied\|failed` |
| `DELETE /api/meta` | Attempts provider revocation, clears local credentials and pending authorizations, returns `message` and `revoked_at_provider` |

Status fields: `configured`, `connected`, `has_connection`, `status`, `client_id`, `account_id`, `account_name`, `connected_at`, `expires_at`, `data_access_expires_at`, and `scopes`. Status is `disconnected`, `connected`, `expired`, `reconnect_required`, or `error`. Changing App ID/Config ID or lacking a required permission marks an existing connection for reauthorization. Expiry reflects stored Meta metadata. Status does **not** detect remote revocation; reconnect to validate a fresh grant. No automatic refresh or deauthorization webhook is implemented.

## Storage and security

Migration **3** appends `meta_oauth_states`; migrations 1–2 are unchanged. States are hashed, session/configuration-bound (including Config ID), expire after ten minutes, and can be claimed once (including denied callbacks). A new connect replaces pending attempts for this client. Disconnect cancels in-flight callbacks; expired/revoked Admin sessions cannot save credentials.

The legacy `oauth_states` table is Google-specific: it has no provider namespace, and Google deletes states by session. A separate Meta state table prevents one provider's connect from cancelling the other's state without changing the working Google flow. Both use the existing Store/transaction infrastructure.

Meta tokens and identity metadata use the existing Fernet cipher and `secrets` table under `meta:client_kinderhealth`. SQLite uses the existing `instance/encryption.key`; PostgreSQL requires the deployment's stable `ENCRYPTION_KEY`. Back up the key with the encrypted database. `connections` stores client/provider identity and a secret reference, never a token. Credential and connection updates are atomic. Provider errors are sanitized; audit events contain no codes or tokens.

Disconnect serializes with connect/callback through the existing database write transaction while attempting bounded provider revocation (3-second connect, 5-second read timeout). A failed revocation still clears the local connection and produces an explicit warning; the user can remove the app's permissions in Facebook. A crashed/uncompleted disconnect can be retried. Avoid enabling HTTP debug logging or recording callback query strings in proxy access logs.

## Provider calls and validation

Only backend OAuth operations call Meta:

- `/{version}/oauth/access_token`: code exchange, then long-lived user-token exchange.
- `/{version}/debug_token`: validate app, user, token type, scopes and expiry.
- `GET /{version}/me?fields=id,name`: confirm account identity using bearer authorization and `appsecret_proof`.
- `DELETE /{version}/me/permissions`: attempt revocation with bearer authorization and `appsecret_proof`.

Token exchange and inspection use Graph's POST transport with `method=GET` in the form body. This retains the read operation while keeping codes, App Secret, and token inputs out of request URLs. Bearer tokens remain in backend Authorization headers. Tests inspect prepared HTTP URLs and fail if credentials appear there; there is no fallback to credentials in query strings.

No asset, Page, ad-account, insights, Google, TikTok, or YouTube API is called by this flow. Report Builder and Preview continue to use immutable Dataset snapshots only.

Protocol references: Meta's [OAuth client implementation](https://github.com/facebookarchive/php-graph-sdk/blob/5.x/src/Facebook/Authentication/OAuth2Client.php), [POST method-override implementation](https://github.com/facebookarchive/facebook-php-sdk/blob/master/src/base_facebook.php), [User permissions implementation](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/user.py), and [Graph version configuration](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/apiconfig.py). The developer documentation site returned HTTP 429 during implementation; the method-override reference is Meta's archived SDK, so confirm this transport and app-specific setup in a live authorization trial before deployment.

Run `python -m unittest discover -s tests -p test_meta.py -v` and `npm.cmd test`. Provider calls are mocked; PostgreSQL cases require a disposable `TEST_DATABASE_URL`. Live authorization/revocation needs configured Meta credentials and is not covered by the mocked tests.
