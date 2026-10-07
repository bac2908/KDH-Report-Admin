"""The same bundle contract and lifecycle run on SQLite and isolated PostgreSQL."""
import copy
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_app
import test_postgres
from kdh import report_bundles as bundles
from kdh.core import now, pack, uid, Problem
from kdh.migrations import MIGRATIONS, apply_migrations


class BundleCases:
    def prepare(self):
        self.service_token = 'test-only-report-service-token-not-a-real-secret'
        self.app.config['REPORT_SERVICE_TOKEN'] = self.service_token
        self.dataset_id = self.dataset()
        self.fields = {
            'client_id': 'client_kinderhealth', 'name': 'Report September',
            'start_date': '2026-09-01', 'end_date': '2026-09-28',
            'default_section': 'overview',
            'sections': [{'key': 'overview', 'dataset_id': self.dataset_id},
                         {'key': 'seo', 'dataset_id': self.dataset_id}],
        }

    def dataset(self, valid=1, source_status='ready', latest='2026-09-28', metric=24_000_000, data=None):
        dataset_id = uid()
        if data is None:
            data = {'id': dataset_id, 'created_at': now(),
                    'params': {'report_type': 'ga4', 'start': '2026-09-01', 'end': '2026-09-28', 'compare': False},
                    'sources': {'ga4': {'source': 'ga4', 'status': source_status,
                        'latest_available_date': latest, 'requested_start': '2026-09-01', 'requested_end': '2026-09-28',
                        'totals': {'sessions': metric, 'activeUsers': None}, 'daily': [], 'warnings': []}}}
        self.store.execute('INSERT INTO datasets (id,user_id,report_type,created_at,valid,data) VALUES (?,?,?,?,?,?)',
                           (dataset_id, self.actor, 'ga4', now(), valid, pack(data)))
        return dataset_id

    def post(self, path, data=None):
        return self.client.post(path, json=data if data is not None else {}, headers=self.headers)

    def create(self, **changes):
        response = self.post('/api/report-bundles', {**self.fields, **changes})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['report_id']

    def publish(self, report_id, revision=1, status='provisional'):
        return self.post(f'/api/report-bundles/{report_id}/revisions/{revision}/publish', {'status': status})

    def internal(self, report_id, suffix='', header=None, client=None):
        return (client or self.app.test_client()).get('/api/internal/v1/report-bundles/'+report_id+suffix,
                      headers=header if header is not None else {'Authorization': 'Bearer '+self.service_token})

    def test_create_id_order_and_full_contract(self):
        report_id = self.create(sections=list(reversed(self.fields['sections'])))
        self.assertRegex(report_id, r'^rpt_[0-9a-f]{32}$')
        self.assertNotEqual(self.create(), report_id)
        stored = self.store.one('SELECT * FROM report_bundles WHERE bundle_key=?', (report_id,))
        self.assertNotEqual(stored['id'], report_id)
        self.assertEqual((stored['revision'], stored['status'], stored['parent_id']), (1, 'draft', None))
        sections = self.store.all('SELECT section_key,position FROM report_bundle_sections WHERE bundle_id=? ORDER BY position', (stored['id'],))
        self.assertEqual(sections, [{'section_key':'seo','position':0},{'section_key':'overview','position':1}])
        self.assertEqual(self.internal(report_id).status_code, 404)
        self.assertEqual(self.publish(report_id).status_code, 200)
        payload = self.internal(report_id).json
        self.assertEqual(set(payload), {'schema_version','report','client','period','comparison','freshness','quality','navigation','branding','sections'})
        self.assertEqual(payload['schema_version'], '1.0')
        self.assertEqual(payload['report'], {'id':report_id,'revision':1,'status':'provisional','name':'Report September'})
        self.assertEqual(payload['client'], {'id':'client_kinderhealth','name':'KinderHealth','slug':'kinderhealth','timezone':'Asia/Ho_Chi_Minh'})
        self.assertEqual(payload['period'], {'start':'2026-09-01','end':'2026-09-28'})
        self.assertIsNone(payload['comparison'])
        self.assertEqual(payload['navigation'], {'default_section':'overview','sections':['seo','overview']})
        self.assertEqual(list(payload['sections']), ['seo','overview'])
        self.assertEqual(payload['quality'], {'status':'complete','warnings':[]})
        self.assertTrue(payload['freshness']['generated_at'])
        self.assertTrue(payload['freshness']['published_at'])
        self.assertEqual(payload['branding'], {})
        original = json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(self.dataset_id,))['data'])
        self.assertEqual(payload['sections']['seo']['data'], original)
        self.assertIsNone(payload['sections']['seo']['data']['sources']['ga4']['totals']['activeUsers'])

    def test_admin_draft_preview_reads_captured_revision_without_writes_or_provider_calls(self):
        report_id = self.create()
        path = f'/api/report-bundles/{report_id}?revision=1'
        original = self.client.get(path).json
        # Simulate an out-of-band legacy row change; the saved draft must not drift.
        self.store.execute('UPDATE datasets SET data=? WHERE id=?', (pack({'changed': True}), self.dataset_id))
        before = {table: self.store.all('SELECT * FROM ' + table) for table in
                  ('datasets', 'report_bundles', 'report_bundle_sections', 'jobs', 'events')}
        with patch.object(self.app.extensions['google'], 'fetch', side_effect=AssertionError('Preview called a provider')) as fetch, \
             patch('kdh.google.requests.request', side_effect=AssertionError('Preview made an external request')) as request:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, original)
        self.assertEqual(response.json['report']['status'], 'draft')
        self.assertEqual(response.json['navigation']['sections'], ['overview', 'seo'])
        self.assertEqual(response.json['sections']['seo']['data']['sources']['ga4']['totals']['sessions'], 24_000_000)
        fetch.assert_not_called()
        request.assert_not_called()
        for table, rows in before.items():
            self.assertEqual(self.store.all('SELECT * FROM ' + table), rows, table)

    def test_preview_reads_persisted_section_assignments_and_datasets_without_mutation(self):
        report_id = self.create()
        sections = list(reversed(self.fields['sections']))
        response = self.client.patch(f'/api/report-bundles/{report_id}/revisions/1',
                                     json={'sections': sections, 'default_section': 'seo'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        before = {table: self.store.all('SELECT * FROM ' + table) for table in
                  ('datasets', 'report_bundles', 'report_bundle_sections', 'jobs', 'events')}
        with patch.object(self.app.extensions['google'], 'fetch', side_effect=AssertionError('Preview called a provider')), \
             patch('kdh.google.requests.request', side_effect=AssertionError('Preview made an external request')):
            bundle = self.client.get(f'/api/report-bundles/{report_id}?revision=1').json
            self.assertEqual(bundle['report']['status'], 'draft')
            self.assertEqual(bundle['report']['revision'], 1)
            self.assertEqual(bundle['navigation'], {'default_section': 'seo', 'sections': ['seo', 'overview']})
            for row in before['report_bundle_sections']:
                section = bundle['sections'][row['section_key']]
                self.assertEqual((section['dataset_id'], section['position']), (row['dataset_id'], row['position']))
            for dataset_id in {section['dataset_id'] for section in bundle['sections'].values()}:
                response = self.client.get('/api/datasets/' + dataset_id)
                self.assertEqual(response.status_code, 200)
                dataset = response.json
                self.assertTrue(dataset.pop('exportable'))
                self.assertEqual(dataset, bundle['sections']['seo']['data'])
        for table, rows in before.items():
            self.assertEqual(self.store.all('SELECT * FROM ' + table), rows, table)

    def test_validation_is_atomic_and_does_not_accept_inline_data(self):
        cases = [
            {'default_section':'absent'}, {'default_section':[]}, {'sections':[]}, {'sections':None},
            {'client_id':'absent'}, {'client_id':123}, {'name':''},
            {'start_date':'2026-10-01'}, {'start_date':'2026-02-31'},
            {'compare_start_date':'2026-08-01'}, {'compare_start_date':'2026-08-30','compare_end_date':'2026-08-01'},
            {'sections':[{'key':'overview','dataset_id':'not-found'}]},
            {'sections':[{'key':'overview','dataset_id':self.dataset_id}]*2},
            {'sections':[{'key':'Overview!','dataset_id':self.dataset_id}]},
            {'sections':[{'key':'overview','dataset_id':self.dataset_id,'data':{'sessions':1}}]},
            {'sections':[{'key':'overview','dataset_id':self.dataset_id,'position':9}]},
            {'status':'final'}, {'bundle_key':'rpt_chosen_by_caller'}, {'revision':99},
            {'access_token':'must-not-echo'}, {'branding':{'nested':{'refresh_token':'must-not-echo'}}},
        ]
        for change in cases:
            with self.subTest(change=change):
                response = self.post('/api/report-bundles', {**self.fields, **change})
                self.assertEqual(response.status_code,400,response.json)
                self.assertNotIn('must-not-echo', response.get_data(as_text=True))
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM report_bundles')['n'],0)
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM report_bundle_sections')['n'],0)
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM datasets')['n'],1)

    def test_provisional_partial_and_final_reject_invalid_or_stale_data(self):
        for dataset in (self.dataset(valid=0), self.dataset(source_status='delayed', latest='2026-09-27')):
            with self.subTest(dataset=dataset):
                report_id=self.create(sections=[{'key':'overview','dataset_id':dataset}])
                self.assertEqual(self.publish(report_id).status_code,200)
                previous=self.internal(report_id).json
                self.assertEqual(previous['quality']['status'],'partial')
                self.assertTrue(previous['quality']['warnings'])
                response=self.publish(report_id,status='final')
                self.assertEqual(response.status_code,409,response.json)
                self.assertEqual(self.internal(report_id).json,previous)

    def test_final_checks_every_section_and_all_required_seo_sources(self):
        data=json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(self.dataset_id,))['data'])
        data['params']['report_type']='seo'
        self.store.execute('UPDATE datasets SET data=?,report_type=? WHERE id=?',(pack(data),'seo',self.dataset_id))
        report_id=self.create(sections=[{'key':'overview','dataset_id':self.dataset()}, {'key':'seo','dataset_id':self.dataset_id}])
        self.assertEqual(self.publish(report_id,status='final').status_code,409)
        self.assertEqual(self.publish(report_id).status_code,200)
        quality=self.internal(report_id).json['sections']['seo']['quality']
        self.assertTrue(any('gsc' in w for w in quality['warnings']))
        self.assertTrue(any('keywords' in w for w in quality['warnings']))

    def test_unknown_and_failed_quality_do_not_become_zero_or_complete(self):
        unknown=self.dataset(data={'params':{'report_type':'ga4','start':'2026-09-01','end':'2026-09-28'},'sources':{}})
        failed=self.dataset(valid=0,source_status='api_error',latest=None,metric=None)
        for dataset, expected in ((unknown,'unknown'),(failed,'failed')):
            report_id=self.create(sections=[{'key':'overview','dataset_id':dataset}])
            self.assertEqual(self.publish(report_id).status_code,200)
            payload=self.internal(report_id).json
            self.assertEqual(payload['quality']['status'],expected)
            self.assertEqual(self.publish(report_id,status='final').status_code,409)
            self.assertEqual(payload['sections']['overview']['data'],json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(dataset,))['data']))

    def test_revision_preserves_old_data_and_latest_read_ignores_new_draft(self):
        report_id=self.create()
        self.assertEqual(self.publish(report_id,status='final').status_code,200)
        original=self.internal(report_id).json
        new_dataset=self.dataset(metric=24_500_000)
        response=self.post(f'/api/report-bundles/{report_id}/revisions',{'sections':[{'key':'overview','dataset_id':new_dataset}]})
        self.assertEqual(response.status_code,201,response.json)
        self.assertEqual(response.json,{'report_id':report_id,'revision':2,'status':'draft'})
        first,second=self.store.all('SELECT * FROM report_bundles WHERE bundle_key=? ORDER BY revision',(report_id,))
        self.assertEqual(second['parent_id'],first['id'])
        self.assertEqual(self.internal(report_id).json,original)
        self.assertEqual(self.internal(report_id,'?revision=2').status_code,404)
        self.assertEqual(self.publish(report_id,2).status_code,200)
        current=self.internal(report_id).json
        self.assertEqual(current['report']['revision'],2)
        self.assertEqual(current['sections']['overview']['data']['sources']['ga4']['totals']['sessions'],24_500_000)
        self.assertEqual(self.internal(report_id,'?revision=1').json,original)
        self.assertEqual(original['sections']['overview']['data']['sources']['ga4']['totals']['sessions'],24_000_000)

    def test_published_snapshots_survive_source_dataset_and_client_changes(self):
        report_id=self.create()
        self.publish(report_id)
        original=self.internal(report_id).get_data()
        self.store.execute('UPDATE datasets SET data=?,valid=0 WHERE id=?',(pack({'changed':True}),self.dataset_id))
        self.store.execute('UPDATE clients SET name=? WHERE id=?',('Changed name','client_kinderhealth'))
        self.store.set_setting('organization',{'name':'Changed branding'})
        with patch('kdh.google.Google.fetch', side_effect=AssertionError('must not call provider')), \
             patch('kdh.google.call', side_effect=AssertionError('must not refresh token')), \
             patch('requests.request', side_effect=AssertionError('must not use network')):
            self.assertEqual(self.internal(report_id).get_data(),original)
            self.assertEqual(self.internal(report_id,'?revision=1').get_data(),original)
        # The same dataset ID retains its captured values in a child revision.
        second=self.post(f'/api/report-bundles/{report_id}/revisions',{})
        self.assertEqual(second.status_code,201,second.json)
        preview=self.client.get(f'/api/report-bundles/{report_id}?revision=2').json
        self.assertEqual(preview['sections'],json.loads(original)['sections'])

    def test_draft_edits_and_published_immutability(self):
        report_id=self.create()
        path=f'/api/report-bundles/{report_id}/revisions/1'
        result=self.client.patch(path,json={'name':'Updated draft','default_section':'seo'},headers=self.headers)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.client.get('/api/report-bundles/'+report_id).json['report']['name'],'Updated draft')
        self.assertEqual(self.publish(report_id).status_code,200)
        provisional=self.internal(report_id).json
        for change in ({'name':'tampered'},{'sections':[]},{'status':'draft'}):
            self.assertIn(self.client.patch(path,json=change,headers=self.headers).status_code,(400,409))
            self.assertEqual(self.internal(report_id).json,provisional)
        self.assertEqual(self.publish(report_id,status='final').status_code,200)
        final=self.internal(report_id).json
        self.assertEqual(final['sections'],provisional['sections'])
        self.assertEqual(final['freshness'],provisional['freshness'])
        self.assertEqual(self.client.patch(path,json={'name':'tampered'},headers=self.headers).status_code,409)
        self.assertEqual(self.publish(report_id,status='provisional').status_code,409)
        self.assertEqual(self.publish(report_id,status='draft').status_code,400)
        self.assertEqual(self.publish(report_id,status='final').status_code,200)
        self.assertEqual(self.internal(report_id).json,final)

    def test_internal_auth_is_bearer_only_read_only_and_does_not_leak_token(self):
        report_id=self.create();self.publish(report_id)
        for headers in ({},{'Authorization':'Bearer wrong'},{'Authorization':'Bearer không-hợp-lệ'}):
            response=self.internal(report_id,header=headers,client=self.client)
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers['WWW-Authenticate'],'Bearer')
        self.assertEqual(self.internal(report_id,'?token='+self.service_token,header={}).status_code,401)
        self.assertEqual(self.internal('rpt_missing').status_code,404)
        self.assertEqual(self.internal(report_id,'?revision=1234').status_code,404)
        for value in ('0','-1','abc','1.0','1&revision=2'):
            self.assertEqual(self.internal(report_id,'?revision='+value).status_code,400)
        response=self.internal(report_id)
        self.assertEqual(response.status_code,200)
        self.assertIn('application/json',response.content_type)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertNotIn('Set-Cookie',response.headers)
        self.assertNotIn(self.service_token,response.get_data(as_text=True))
        for method in ('POST','PUT','PATCH','DELETE'):
            response=self.app.test_client().open('/api/internal/v1/report-bundles/'+report_id,method=method,headers={'Authorization':'Bearer '+self.service_token},json={})
            self.assertEqual(response.status_code,405)
        self.app.config['REPORT_SERVICE_TOKEN']=''
        self.assertEqual(self.internal(report_id).status_code,401)
        self.assertNotIn(self.service_token,self.client.get('/').get_data(as_text=True))
        self.assertNotIn(self.service_token,pack(self.store.all('SELECT * FROM events')))

    def test_admin_endpoints_require_admin_session_and_csrf(self):
        report_id=self.create()
        visitor=self.app.test_client()
        self.assertEqual(visitor.post('/api/report-bundles',json=self.fields,headers={'X-KDH-Request':'1','Authorization':'Bearer '+self.service_token}).status_code,401)
        self.assertEqual(self.client.post('/api/report-bundles',json=self.fields,headers={'X-KDH-Request':'1'}).status_code,403)
        for role in ('viewer','operator'):
            self.store.execute('UPDATE users SET role=? WHERE id=?',(role,self.actor))
            self.assertEqual(self.post('/api/report-bundles',self.fields).status_code,403)
            self.assertEqual(self.client.get('/api/report-bundles/'+report_id).status_code,403)
            self.assertEqual(self.publish(report_id).status_code,403)
            with self.assertRaises(Problem): bundles.create_bundle(self.store,self.actor,self.fields)

    def test_comparison_metadata_and_coverage(self):
        data=json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(self.dataset_id,))['data'])
        data['params'].update(compare=True,previous_start='2026-08-04',previous_end='2026-08-31')
        data['sources']['ga4'].update(previous={'sessions':12},previous_latest_available_date='2026-08-31')
        dataset=self.dataset(data=data)
        report_id=self.create(compare_start_date='2026-08-04',compare_end_date='2026-08-31',sections=[{'key':'overview','dataset_id':dataset}])
        self.assertEqual(self.publish(report_id,status='final').status_code,200)
        self.assertEqual(self.internal(report_id).json['comparison'],{'start':'2026-08-04','end':'2026-08-31'})
        data['sources']['ga4']['previous_latest_available_date']='2026-08-30'
        late=self.dataset(data=data)
        report_id=self.create(compare_start_date='2026-08-04',compare_end_date='2026-08-31',sections=[{'key':'overview','dataset_id':late}])
        self.assertEqual(self.publish(report_id,status='final').status_code,409)
        wrong=self.post('/api/report-bundles',{**self.fields,'compare_start_date':'2026-08-01','compare_end_date':'2026-08-31','sections':[{'key':'overview','dataset_id':dataset}]})
        self.assertEqual(wrong.status_code,400)

    def test_cross_client_and_period_mismatch_are_rejected(self):
        timestamp=now()
        self.store.execute('INSERT INTO clients (id,name,slug,timezone,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',('client_other','Other','other','UTC',1,timestamp,timestamp))
        response=self.post('/api/report-bundles',{**self.fields,'client_id':'client_other'})
        self.assertEqual(response.status_code,400)
        response=self.post('/api/report-bundles',{**self.fields,'start_date':'2026-09-02'})
        self.assertEqual(response.status_code,400)
        report_id=self.create()
        self.assertEqual(self.post('/api/report-bundles/'+report_id+'/revisions',{'client_id':'client_other'}).status_code,400)

    def test_credentials_in_persisted_metadata_rejected_without_echo(self):
        for contamination in ({'refresh_token':'sensitive-value'}, {'nested':{'Authorization':'Bearer sensitive-value'}}, {'url':'https://provider.invalid?access_token=sensitive-value'}):
            data=json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(self.dataset_id,))['data'])
            data['sources']['ga4']['extra']=contamination
            dataset=self.dataset(data=data)
            result=self.post('/api/report-bundles',{**self.fields,'sections':[{'key':'overview','dataset_id':dataset}]})
            self.assertEqual(result.status_code,400,result.json)
            self.assertNotIn('sensitive-value',result.get_data(as_text=True))
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM report_bundles')['n'],0)

    def test_concurrent_revisions_use_distinct_numbers_and_chain_parents(self):
        report_id=self.create();self.publish(report_id,status='final')
        before=self.internal(report_id).json
        barrier=threading.Barrier(2)
        def create():
            barrier.wait(timeout=5)
            return bundles.create_revision(self.store,self.actor,report_id,{})['revision']
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(create) for _ in range(2)]
            revisions=[future.result(timeout=15) for future in futures]
        self.assertEqual(sorted(revisions),[2,3])
        rows=self.store.all('SELECT id,parent_id,revision FROM report_bundles WHERE bundle_key=? ORDER BY revision',(report_id,))
        self.assertEqual(rows[1]['parent_id'],rows[0]['id'])
        self.assertEqual(rows[2]['parent_id'],rows[1]['id'])
        self.assertEqual(self.internal(report_id).json,before)

    def test_migration_is_registered_once_and_failure_is_atomic(self):
        apply_migrations(self.store)
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM schema_migrations WHERE version=2')['n'],1)
        broken=(9999,'rollback_test','CREATE TABLE bundle_migration_probe (id TEXT); INSERT INTO definitely_missing_table (id) VALUES (1);')
        with patch('kdh.migrations.MIGRATIONS',[*MIGRATIONS,broken]):
            with self.assertRaises(Exception): apply_migrations(self.store)
        self.assertIsNone(self.store.one('SELECT version FROM schema_migrations WHERE version=9999'))
        with self.assertRaises(Exception): self.store.one('SELECT id FROM bundle_migration_probe')

    def test_real_job_snapshot_can_be_bundled_without_altering_legacy_dataset(self):
        params={'report_type':'seo','start':'2026-09-01','end':'2026-09-28','compare':False}
        job=self.post('/api/analyses',params)
        self.assertEqual(job.status_code,202,job.json)
        with patch.object(self.app.extensions['google'],'fetch',side_effect=test_app.fixture) as fetch:
            self.app.extensions['worker'].run_one(job.json['job_id'])
            self.assertEqual(fetch.call_count,3)
        dataset_id=self.client.get('/api/jobs/'+job.json['job_id']).json['dataset_id']
        before=self.store.one('SELECT * FROM datasets WHERE id=?',(dataset_id,))
        with patch.object(self.app.extensions['google'],'fetch',side_effect=AssertionError('No refetch')):
            report_id=self.create(sections=[{'key':'overview','dataset_id':dataset_id},{'key':'seo','dataset_id':dataset_id}])
            self.assertEqual(self.publish(report_id,status='final').status_code,200)
            self.assertEqual(self.internal(report_id).json['sections']['seo']['data'],json.loads(before['data']))
        self.assertEqual(self.store.one('SELECT * FROM datasets WHERE id=?',(dataset_id,)),before)

    def test_mixed_sections_preserve_existing_non_google_dataset_without_adapter(self):
        data={'params':{'report_type':'facebook-ads','start':'2026-09-01','end':'2026-09-28'},
              'sources':{'ads':{'status':'ready','latest_available_date':'2026-09-28','totals':{'spend':24_000_000,'conversions':None}}}}
        dataset_id=self.dataset(data=data)
        self.store.execute('UPDATE datasets SET report_type=? WHERE id=?',('facebook-ads',dataset_id))
        report_id=self.create(sections=[*self.fields['sections'],{'key':'facebook-ads','dataset_id':dataset_id}])
        self.assertEqual(self.publish(report_id).status_code,200)
        result=self.internal(report_id).json
        self.assertEqual(result['navigation']['sections'],['overview','seo','facebook-ads'])
        self.assertEqual(result['sections']['facebook-ads']['data'],data)

    def test_demo_and_malformed_metadata_cannot_be_final(self):
        data=json.loads(self.store.one('SELECT data FROM datasets WHERE id=?',(self.dataset_id,))['data'])
        data['params']['demo']=True
        demo=self.dataset(data=data)
        report_id=self.create(sections=[{'key':'overview','dataset_id':demo}])
        self.assertEqual(self.publish(report_id,status='final').status_code,409)
        self.assertEqual(self.publish(report_id).status_code,200)
        self.assertTrue(any('DEMO' in warning for warning in self.internal(report_id).json['quality']['warnings']))
        data['sources']['ga4']['status']=[]
        malformed=self.dataset(data=data)
        self.assertEqual(self.post('/api/report-bundles',{**self.fields,'sections':[{'key':'overview','dataset_id':malformed}]}).status_code,400)


class SQLiteBundleTest(BundleCases, unittest.TestCase):
    def setUp(self):
        test_app.AppTest.setUp(self)
        self.actor=self.admin['id']
        self.prepare()

    tearDown=test_app.AppTest.tearDown


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to an isolated PostgreSQL test database')
class PostgresBundleTest(BundleCases, unittest.TestCase):
    def setUp(self):
        test_postgres.PostgresTest.setUp(self)
        self.app,self.client=self.apps[0],self.clients[0]
        self.prepare()
