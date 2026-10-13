"""Read-only Meta Graph adapters for Facebook Ads and Page Content.

Requires an existing Meta user OAuth grant. Does not expose access tokens,
Page tokens, provider errors, or Meta's paging.next URLs to the browser.
This module does not attest provider origin for marketing publication.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timezone, timedelta
from zoneinfo import ZoneInfo
import json
import math
import re
import time

from .core import Problem, pack

SOURCES = {
    'facebook_ads': ('facebook_ad_account', 'act_'),
    'facebook_content': ('facebook_page', ''),
}
MAX_PAGES = 30
MAX_ROWS = 15000


def safe_number(value, default=None):
    if isinstance(value, bool) or value is None:
        return default
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return n if math.isfinite(n) and n >= 0 else default


def count(value, default=None):
    n = safe_number(value, default)
    return int(n) if n is not None else None


def validate_range(start, end):
    if not isinstance(start, str) or not isinstance(end, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', start) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', end):
        raise Problem('Ngày phải có định dạng YYYY-MM-DD.')
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise Problem('Ngày báo cáo không hợp lệ.') from None
    if first > last or (last - first).days > 89 or last >= datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date():
        raise Problem('Đồng bộ tối đa 90 ngày, kết thúc không vượt quá hôm nay.')
    return first, last


def dates(first, last):
    for delta in range((last - first).days + 1):
        yield (first + timedelta(days=delta)).isoformat()


def _action_count(actions, names):
    if not isinstance(actions, list):
        return None
    values = {str(row.get('action_type')): safe_number(row.get('value')) for row in actions if isinstance(row, dict)}
    for name in names:
        if values.get(name) is not None:
            return count(values[name])
    return None


def _total(daily, key):
    values = [row[key] for row in daily if row.get(key) is not None]
    return round(sum(values), 5) if values and len(values) == len(daily) else None


class MetaReportingReader:
    def __init__(self, meta):
        self.meta = meta

    def _token(self):
        if not self.meta.info()['connected']:
            raise Problem('Meta OAuth hết hạn hoặc chưa kết nối.', 409, 'meta_reconnect_required')
        token = self.meta.read() or {}
        if not isinstance(token.get('access_token'), str) or not token['access_token']:
            raise Problem('Meta không có Access Token hợp lệ.', 409, 'meta_reconnect_required')
        return token['access_token']

    def _page_rows(self, path, token, params):
        """Use cursor-based pagination only; never dereference untrusted next URL."""
        cursor = None
        seen = set()
        result = []
        for _ in range(MAX_PAGES):
            query = dict(params, limit=100)
            if cursor:
                query['after'] = cursor
            # Existing Meta.call supplies a bearer header and sanitizes API errors.
            # Do not include token in params, logs, or resulting data.
            for attempt in range(3):
                try:
                    payload = self.meta.call('GET', path, token=token, params=query)
                    break
                except Exception as exc:
                    from .google import SourceError
                    if not isinstance(exc, SourceError) or attempt == 2:
                        raise
                    time.sleep(attempt + 1)
            rows = payload.get('data')
            if not isinstance(rows, list):
                raise Problem('Meta trả về danh sách dữ liệu không hợp lệ.', 502, 'meta_bad_response')
            result.extend(rows)
            if len(result) > MAX_ROWS:
                raise Problem('Dữ liệu Meta quá lớn; hãy thu hẹp phạm vi đồng bộ.', 409, 'meta_too_many_rows')
            paging = payload.get('paging') or {}
            cursors = paging.get('cursors') or {}
            after = cursors.get('after') if paging.get('next') else None
            if paging.get('next') and not after:
                raise Problem('Meta thiếu con trỏ phân trang.', 502, 'meta_bad_paging')
            if not after:
                return result
            if not isinstance(after, str) or len(after) > 2048 or after == cursor or after in seen:
                raise Problem('Phân trang Meta không hợp lệ.', 502, 'meta_bad_paging')
            seen.add(after)
            cursor = after
        raise Problem('Đã đạt giới hạn số trang API Meta.', 409, 'meta_pagination_limit')

    def discover(self):
        token = self._token()
        accounts = self._page_rows('me/adaccounts', token, {
            'fields': 'id,name,account_status,currency,timezone_name',
        })
        pages = self._page_rows('me/accounts', token, {
            'fields': 'id,name,tasks,access_token',
        })
        clean_ads = []
        for item in accounts:
            if isinstance(item, dict) and re.fullmatch(r'act_\d+', str(item.get('id', ''))):
                clean_ads.append({key: item.get(key) for key in ('id', 'name', 'account_status', 'currency', 'timezone_name')})
        clean_pages = []
        for item in pages:
            if isinstance(item, dict) and re.fullmatch(r'\d+', str(item.get('id', ''))):
                clean_pages.append({'id': item['id'], 'name': item.get('name', ''),
                                    'tasks': item.get('tasks') if isinstance(item.get('tasks'), list) else []})
        return {'facebook_ads': clean_ads, 'facebook_content': clean_pages}

    def _page_token(self, page_id):
        # Tokens for Pages remain in memory; only assets and metrics are persisted.
        pages = self._page_rows('me/accounts', self._token(), {'fields': 'id,name,tasks,access_token'})
        for item in pages:
            if isinstance(item, dict) and item.get('id') == page_id:
                token = item.get('access_token')
                if isinstance(token, str) and token:
                    return token
                break
        raise Problem('Meta chưa cấp Page Access Token cho Trang được chọn.', 403, 'meta_page_permission')

    def ads(self, external_id, start, end):
        first, last = validate_range(start, end)
        if not re.fullmatch(r'act_\d+', external_id):
            raise Problem('Ad Account ID không hợp lệ.')
        token = self._token()
        common = {'fields': 'date_start,date_stop,spend,impressions,clicks,reach,actions',
                  'time_range': json.dumps({'since': start, 'until': end}, separators=(',', ':')),
                  'time_increment': 1}
        rows = self._page_rows(external_id + '/insights', token, dict(common, level='account'))
        campaigns = self._page_rows(external_id + '/insights', token,
            dict(common, level='campaign', fields=common['fields'] + ',campaign_id,campaign_name'))
        daily, details = [], []
        seen_days = set()
        for item in rows:
            if not isinstance(item, dict):
                continue
            day = item.get('date_start')
            if not isinstance(day, str) or not start <= day <= end or day in seen_days:
                raise Problem('Meta trả về ngày bị trùng hoặc ngoài kỳ.', 502, 'meta_bad_response')
            seen_days.add(day)
            daily.append({'date': day, 'spend': safe_number(item.get('spend')),
                'impressions': count(item.get('impressions')), 'clicks': count(item.get('clicks')),
                'reach': count(item.get('reach')),
                'leads': _action_count(item.get('actions'),
                    ('lead', 'onsite_conversion.lead_grouped', 'offsite_conversion.fb_pixel_lead'))})
        for item in campaigns:
            if not isinstance(item, dict) or not isinstance(item.get('campaign_id'), str):
                continue
            day = item.get('date_start')
            if not isinstance(day, str) or not start <= day <= end:
                raise Problem('Meta trả về campaign ngoài kỳ.', 502, 'meta_bad_response')
            details.append({'date': day, 'campaign_id': item['campaign_id'],
                'campaign_name': str(item.get('campaign_name') or '')[:180],
                'spend': safe_number(item.get('spend')),
                'impressions': count(item.get('impressions')),
                'clicks': count(item.get('clicks'))})
        daily.sort(key=lambda x: x['date'])
        totals = {key: _total(daily, key) for key in ('spend', 'impressions', 'clicks', 'leads')}
        # Reach across dates/campaigns is non-additive; do not invent a period total.
        totals['reach'] = None
        return {'source': 'facebook_ads', 'requested_start': start, 'requested_end': end,
            'status': 'ready' if daily else 'no_data', 'data_origin': 'meta_api_unverified',
            'latest_available_date': daily[-1]['date'] if daily else None,
            'daily': daily, 'entries': details, 'totals': totals,
            'warnings': ['Dữ liệu Meta chưa có receipt xác minh phục vụ phát hành Marketing.']}

    def content(self, page_id, start, end):
        first, last = validate_range(start, end)
        if not re.fullmatch(r'\d+', page_id):
            raise Problem('Page ID không hợp lệ.')
        token = self._page_token(page_id)
        rows = self._page_rows(page_id + '/posts', token, {'fields':
            'id,created_time,permalink_url,shares,reactions.limit(0).summary(true),comments.limit(0).summary(true)',
            'since': str(int(datetime.combine(first, dt_time.min, tzinfo=timezone.utc).timestamp())),
            'until': str(int(datetime.combine(last + timedelta(days=1), dt_time.min, tzinfo=timezone.utc).timestamp()))})
        # Post counters are lifetime values as of fetch time, NOT daily engagement.
        # Only post publication counts can safely be attributed to creation day.
        grouped = {day: {'date': day, 'posts_published': 0,
                           'reactions': None, 'comments': None, 'shares': None,
                           'engagements': None} for day in dates(first, last)}
        entries, seen = [], set()
        for item in rows:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                continue
            post_id, day = item['id'], str(item.get('created_time', ''))[:10]
            if not start <= day <= end or post_id in seen:
                continue
            seen.add(post_id)
            def nested_count(name):
                info = item.get(name) or {}
                return count((info.get('summary') or {}).get('total_count')) if isinstance(info, dict) else None
            reactions, comments = nested_count('reactions'), nested_count('comments')
            shares = count((item.get('shares') or {}).get('count')) if isinstance(item.get('shares'), dict) else None
            entries.append({'date': day, 'post_id': post_id,
                            'reactions_lifetime': reactions,
                            'comments_lifetime': comments,
                            'shares_lifetime': shares})
            grouped[day]['posts_published'] += 1
        daily = list(grouped.values())
        totals = {'posts_published': sum(row['posts_published'] for row in daily),
                  'reactions': None, 'comments': None, 'shares': None, 'engagements': None}

        return {'source': 'facebook_content', 'requested_start': start, 'requested_end': end,
            'status': 'ready', 'data_origin': 'meta_api_unverified',
            'latest_available_date': end, 'daily': daily, 'entries': entries, 'totals': totals,
            'warnings': ['Tương tác trên từng post là lifetime tại thời điểm lấy; không cộng vào KPI tương tác theo ngày.',
                         'Page/Post views, reach và follower Insights chưa được truy vấn; không suy đoán các giá trị này.',
                         'Dữ liệu Meta chưa có receipt xác minh phục vụ phát hành Marketing.']}
