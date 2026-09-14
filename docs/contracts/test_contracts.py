#!/usr/bin/env python3
"""Offline M0 contract checks, not runtime/API/provider acceptance tests.

Run: python3 -m unittest discover -s docs/contracts -p 'test_*.py' -v
Stdlib validates local references, operation policies and representative schemas.
When installed, jsonschema additionally checks all schemas with Draft 2020-12.
"""
import copy
import importlib.util
import json
import re
import unittest
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('contract_builder', HERE / 'build_contracts.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
OPENAPI = json.loads((HERE / 'target-v6.openapi.json').read_text())
EVENT_DOC = json.loads((HERE / 'target-v6.events.schema.json').read_text())
LIFECYCLE = json.loads((HERE / 'target-v6.lifecycle.json').read_text())
COVERAGE = json.loads((HERE / 'target-v6.coverage.json').read_text())
SCHEMAS = OPENAPI['components']['schemas']
UUID = '10000000-0000-4000-8000-000000000001'
OTHER_UUID = '10000000-0000-4000-8000-000000000002'
NOW = '2026-09-11T12:00:00Z'


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)


def resolve(document, pointer):
    if not pointer.startswith('#/'): raise AssertionError('Non-local reference: ' + pointer)
    node = document
    for token in pointer[2:].split('/'):
        node = node[token.replace('~1', '/').replace('~0', '~')]
    return node


def check(value, schema, document=OPENAPI, path='$'):
    """Small documented validator for keywords emitted by this generator.

    This is NOT advertised as a complete OpenAPI or JSON Schema implementation.
    Failure raises AssertionError; format checks cover UUID/UTC date-time only.
    """
    if '$ref' in schema: check(value, resolve(document, schema['$ref']), document, path)
    if 'const' in schema: assert value == schema['const'], (path, 'const')
    if 'enum' in schema: assert value in schema['enum'], (path, 'enum')
    for keyword in ['oneOf', 'anyOf']:
        if keyword in schema:
            count = 0
            for branch in schema[keyword]:
                try: check(value, branch, document, path)
                except AssertionError: pass
                else: count += 1
            assert count == 1 if keyword == 'oneOf' else count >= 1, (path, keyword, count)
    for branch in schema.get('allOf', []): check(value, branch, document, path)
    if 'not' in schema:
        try: check(value, schema['not'], document, path)
        except AssertionError: pass
        else: raise AssertionError((path, 'not'))
    if 'if' in schema:
        try: check(value, schema['if'], document, path)
        except AssertionError:
            if 'else' in schema: check(value, schema['else'], document, path)
        else:
            if 'then' in schema: check(value, schema['then'], document, path)
    typ = schema.get('type')
    if typ:
        matches = {'object': isinstance(value, dict), 'array': isinstance(value, list), 'string': isinstance(value, str), 'integer': isinstance(value, int) and not isinstance(value, bool), 'number': isinstance(value, (int, float)) and not isinstance(value, bool), 'boolean': isinstance(value, bool), 'null': value is None}
        assert matches[typ], (path, 'type', typ)
    if isinstance(value, dict):
        assert set(schema.get('required', [])).issubset(value), (path, 'required')
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False: assert set(value).issubset(props), (path, 'unknown field')
        for key, val in value.items():
            if key in props: check(val, props[key], document, path + '.' + key)
    if isinstance(value, list):
        assert len(value) >= schema.get('minItems', 0), (path, 'minItems')
        assert len(value) <= schema.get('maxItems', float('inf')), (path, 'maxItems')
        if schema.get('uniqueItems'): assert len({json.dumps(v, sort_keys=True) for v in value}) == len(value), (path, 'uniqueItems')
        if 'items' in schema:
            for index, val in enumerate(value): check(val, schema['items'], document, path + '[' + str(index) + ']')
    if isinstance(value, str):
        assert len(value) >= schema.get('minLength', 0), (path, 'minLength')
        assert len(value) <= schema.get('maxLength', float('inf')), (path, 'maxLength')
        if 'pattern' in schema: assert re.search(schema['pattern'], value), (path, 'pattern')
        if schema.get('format') == 'uuid':
            try: uuid.UUID(value)
            except ValueError as exc: raise AssertionError((path, 'uuid')) from exc
        if schema.get('format') == 'date-time':
            try: datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as exc: raise AssertionError((path, 'date-time')) from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        assert value >= schema.get('minimum', float('-inf')), (path, 'minimum')
        assert value <= schema.get('maximum', float('inf')), (path, 'maximum')


def sample(schema, document=OPENAPI):
    """Deterministic shape fixture. Domain-specific constraints are patched below."""
    if '$ref' in schema: return sample(resolve(document, schema['$ref']), document)
    if 'const' in schema: return schema['const']
    if 'enum' in schema: return schema['enum'][0]
    if 'oneOf' in schema: return sample(schema['oneOf'][0], document)
    if 'anyOf' in schema: return sample(schema['anyOf'][0], document)
    if 'allOf' in schema and 'type' not in schema: return sample(schema['allOf'][0], document)
    typ = schema.get('type')
    if typ == 'object': return {k: sample(schema['properties'][k], document) for k in schema.get('required', [])}
    if typ == 'array': return [sample(schema['items'], document) for _ in range(schema.get('minItems', 0))]
    if typ in ['number', 'integer']: return schema.get('minimum', 1)
    if typ == 'boolean': return False
    if typ == 'null': return None
    if typ == 'string':
        fmt = schema.get('format')
        if fmt == 'uuid': return UUID
        if fmt == 'date-time': return NOW
        if fmt in ['uri', 'uri-reference']: return 'https://example.invalid/private-reference'
        if fmt == 'email': return 'fixture@example.invalid'
        if schema.get('pattern') == '^[a-f0-9]{64}$': return 'a' * 64
        if schema.get('pattern') == '^[A-Z]{3}$': return 'USD'
        if schema.get('pattern', '').startswith('^\\d{4}'): return '2026-09-11T12:00:00'
        return 'fixture'
    raise AssertionError('Cannot sample schema ' + repr(schema))


def fixture(name):
    value = sample(SCHEMAS[name])
    if name in ['AssetWrite', 'AssetVersion']:
        value['content'] = sample(SCHEMAS['VideoContent'])
    if name in ['PublicationIntent', 'PublicationIntentWrite']:
        value['schedule']['timezone'] = 'Etc/UTC'
    if name in ['Job', 'JobStep', 'ProviderAttempt']:
        value['originating_operation_id'] = 'processSource'
    if name == 'Job':
        value.update(approved_plan_version_id=None, plan_approval_decision_id=None)
    if name == 'TimelineVersion':
        value['asset_version_id'] = OTHER_UUID
    return value


class StructureTests(unittest.TestCase):
    def test_generated_artifacts_exactly_match_source(self):
        for name, content in builder.render_artifacts().items():
            self.assertEqual((HERE / name).read_text(), content, name)

    def test_openapi_version_and_planned_boundary(self):
        self.assertEqual(OPENAPI['openapi'], '3.1.0')
        self.assertEqual(OPENAPI['x-implementation-status'], 'planned')
        self.assertNotIn('/v1/videos', OPENAPI['paths'])
        self.assertIn('NOT', OPENAPI['servers'][0]['description'])
        self.assertNotIn('X-API-Key', [x.get('name') for x in OPENAPI['components']['securitySchemes'].values()])

    def test_no_dangling_local_references(self):
        for document in [OPENAPI, EVENT_DOC]:
            for node in walk(document):
                if isinstance(node, dict) and '$ref' in node:
                    self.assertIsInstance(resolve(document, node['$ref']), dict, node['$ref'])
                if isinstance(node, dict) and 'discriminator' in node:
                    for value in node['discriminator'].get('mapping', {}).values(): resolve(document, value)

    def test_every_operation_has_typed_success_errors_scope_and_auth(self):
        names = set()
        expected_errors = {'401', '403', '404', '409', '422', '429'}
        for path, item in OPENAPI['paths'].items():
            for method, operation in item.items():
                with self.subTest(path=path, method=method):
                    self.assertNotIn(operation['operationId'], names)
                    names.add(operation['operationId'])
                    self.assertEqual(operation['x-implementation-status'], 'planned')
                    self.assertRegex(operation['x-milestone'], '^M[1-6]$')
                    self.assertTrue(expected_errors <= operation['responses'].keys())
                    for code in expected_errors:
                        error = resolve(OPENAPI, operation['responses'][code]['$ref'])
                        self.assertEqual(error['content']['application/json']['schema']['$ref'], '#/components/schemas/Error')
                    self.assertIn('scope', operation['x-permissions'])
                    self.assertIn('security', operation)
                    for status, response in operation['responses'].items():
                        if status.startswith('2'): self.assertIn('schema', response['content']['application/json'])
                    declared = {p['name'] for p in operation['parameters'] if p.get('in') == 'path'}
                    self.assertEqual(declared, set(re.findall(r'\{([^}]+)\}', path)))
                    for p in operation['parameters']:
                        if p.get('in') == 'path': self.assertTrue(p['required'])
        self.assertEqual(len(names), len(COVERAGE['operations']))

    def test_anonymous_exceptions_are_explicit_and_bounded(self):
        public = {op['operationId'] for item in OPENAPI['paths'].values() for op in item.values() if not op['security']}
        self.assertEqual(public, {'startLogin', 'completeLogin', 'initiateOnboarding', 'completeSocialOAuth'})
        for item in OPENAPI['paths'].values():
            for method, op in item.items():
                if op['security'] and method != 'get':
                    sessions = [s for s in op['security'] if 'SessionCookie' in s]
                    self.assertTrue(sessions)
                    self.assertTrue(all('CSRFToken' in s for s in sessions))

    def test_async_and_idempotent_and_optimistic_contracts(self):
        for item in OPENAPI['paths'].values():
            for method, operation in item.items():
                parameters = [resolve(OPENAPI, p['$ref']) if '$ref' in p else p for p in operation['parameters']]
                headers = {p['name']: p for p in parameters if p['in'] == 'header'}
                if operation['x-billable'] or operation['x-publishing']:
                    self.assertTrue(headers['Idempotency-Key']['required'], operation['operationId'])
                if operation['x-concurrency'] == 'if-match' or method in ['patch', 'put', 'delete']:
                    self.assertTrue(headers['If-Match']['required'])
                    self.assertIn('428', operation['responses'])
                if '202' in operation['responses']:
                    result = operation['responses']['202']
                    self.assertEqual(result['content']['application/json']['schema']['$ref'], '#/components/schemas/AsyncAccepted')
                    self.assertIn('Location', result['headers'])
                    self.assertIn('Retry-After', result['headers'])

    def test_all_list_queries_paginate(self):
        count = 0
        for item in OPENAPI['paths'].values():
            for operation in item.values():
                if operation['operationId'].startswith('list') or operation['operationId'] == 'queryMetrics':
                    count += 1
                    params = {p.get('$ref') for p in operation['parameters']}
                    self.assertIn('#/components/parameters/Limit', params)
                    self.assertIn('#/components/parameters/Cursor', params)
                    success = operation['responses']['200']['content']['application/json']['schema']
                    page = resolve(OPENAPI, success['$ref'])
                    self.assertEqual(set(page['required']), {'items', 'next_cursor', 'has_more'})
        self.assertGreater(count, 25)
        limit = OPENAPI['components']['parameters']['Limit']['schema']
        self.assertEqual((limit['default'], limit['maximum']), (25, 100))

    def test_section16_groups_and_required_operations_present(self):
        by_name = {row['operation_id']: row for row in COVERAGE['operations']}
        expected = {
            'Identity': ['getSession', 'startLogin', 'logout', 'getCurrentUser', 'switchWorkspace', 'createInvitation', 'acceptInvitation', 'revokeInvitation', 'listMemberships', 'setBrandGrant', 'initiateOnboarding', 'createWorkspace'],
            'Brands': ['createBrand', 'getBrand', 'editBrand', 'createBrandProfileVersion', 'previewBrandVoice', 'decideVoiceSample'],
            'Sources': ['createUploadIntent', 'signUploadPart', 'finalizeSource', 'createSourceFromURL', 'getSource', 'processSource', 'cancelSourceProcessing', 'createTranscriptVersion', 'alignTranscript'],
            'Packages': ['createPackage', 'getPackage', 'createPackageVersion', 'requestPackageReview', 'decidePackageVersion', 'listPackageDependencies'],
            'Plans': ['proposePlan', 'createPlanVersion', 'estimatePlan', 'decidePlanVersion', 'executePlan'],
            'Assets': ['getAsset', 'listAssets', 'createAssetVersion', 'regenerateComponents', 'requestAssetReview', 'decideAssetVersion', 'requestRendition', 'requestExport'],
            'Video': ['createSceneVersion', 'createTimelineVersion', 'previewTimeline', 'generateClipCandidates', 'createClipSelection', 'reviseClipSelectionCrop', 'decideClipSelection', 'decideScriptVersion'],
            'Jobs': ['getJob', 'listJobSteps', 'listJobAttempts', 'retrySafeJob', 'cancelJob', 'reconcileJob'],
            'Connections': ['startSocialOAuth', 'completeSocialOAuth', 'getConnectionCapabilities', 'validateConnection', 'disconnectConnection'],
            'Publications': ['createPublicationIntent', 'revisePublicationIntent', 'decidePublicationRevision', 'schedulePublication', 'pausePublication', 'cancelPublication', 'getPublicationStatus', 'requestPublicationTakedown'],
            'Analytics': ['queryMetrics', 'createConversion', 'listUsage', 'listReservations'],
            'Administration': ['getEntitlements', 'setBudgets', 'requestWorkspaceExport', 'requestWorkspaceDeletion', 'listAudit', 'listNotifications']}
        self.assertEqual(set(expected), {row['group'] for row in COVERAGE['operations']})
        for group, names in expected.items():
            for name in names: self.assertEqual(by_name[name]['group'], group)

    def test_core_objects_are_closed_typed_and_version_bound(self):
        core = {'PackageVersion': ['package_id', 'version_id', 'master_narrative', 'claim_ids', 'brand_profile_version_id'], 'PlanVersion': ['plan_version_id', 'package_version_id', 'items', 'budget_ceiling'], 'TimelineVersion': ['timeline_version_id', 'asset_version_id', 'tracks', 'canvas'], 'PublicationIntent': ['publication_revision_id', 'asset_version_id', 'rendition_id', 'connection_id', 'schedule', 'publication_approval_decision_id'], 'Job': ['job_id', 'logical_operation_id', 'inputs', 'state', 'known_actual_cost']}
        for name, required in core.items():
            schema = SCHEMAS[name]
            self.assertFalse(schema['additionalProperties'])
            self.assertTrue(set(required) <= set(schema['required']))
        for node in walk(SCHEMAS):
            if isinstance(node, dict) and node.get('type') == 'object':
                self.assertTrue(node.get('properties'), 'Opaque object schema')
                self.assertFalse(node.get('additionalProperties', True), 'Unbounded object')
        self.assertEqual(SCHEMAS['Money']['properties']['amount_micros']['type'], 'integer')
        self.assertEqual(SCHEMAS['Money']['properties']['amount_micros']['minimum'], 0)

    def test_exact_approval_subject_discrimination(self):
        for name, (kind, _, _) in builder.SUBJECTS.items():
            subject = SCHEMAS[name + 'ApprovalSubject']
            self.assertEqual(subject['properties']['subject_type']['const'], kind)
            self.assertEqual(set(subject['required']), {'subject_type', 'subject_id', 'subject_version_id'} | ({'scope'} if name == 'Rendition' else set()))
            good = sample(SCHEMAS[name + 'DecisionCreate'])
            check(good, SCHEMAS[name + 'DecisionCreate'])
            bad = copy.deepcopy(good)
            del bad['subject']['subject_version_id']
            with self.assertRaises(AssertionError): check(bad, SCHEMAS[name + 'DecisionCreate'])
        operations = {op['operationId']: op for item in OPENAPI['paths'].values() for op in item.values()}
        self.assertEqual(operations['decidePublicationRevision']['x-permissions']['roles_any_of'], ['OWNER', 'ADMIN', 'REVIEWER'])
        self.assertEqual(operations['schedulePublication']['x-permissions']['roles_any_of'], ['OWNER', 'ADMIN', 'PUBLISHER'])
        self.assertTrue(operations['reconcileJob']['x-permissions']['operator_entitlement_required'])


class PayloadTests(unittest.TestCase):
    def test_representative_valid_core_snapshots(self):
        for name in ['PackageVersion', 'PlanVersion', 'AssetVersion', 'TimelineVersion', 'PublicationIntent', 'Job', 'TranscriptVersion', 'AsyncAccepted', 'ConversionCreate', 'Error']:
            with self.subTest(schema=name): check(fixture(name), SCHEMAS[name])

    def test_required_fields_cannot_be_omitted(self):
        for name in ['PackageVersion', 'PlanVersion', 'TimelineVersion', 'PublicationIntent', 'Job', 'AsyncAccepted']:
            for field in SCHEMAS[name]['required']:
                bad = fixture(name)
                del bad[field]
                with self.subTest(schema=name, field=field):
                    with self.assertRaises(AssertionError): check(bad, SCHEMAS[name])

    def test_no_opaque_content_no_float_money_or_timing(self):
        cases = []
        wrong = fixture('AssetVersion'); wrong['content'] = {'unexpected': 'opaque'}; cases.append(('AssetVersion', wrong))
        wrong = fixture('TimelineVersion'); wrong['duration_ms'] = 1.5; cases.append(('TimelineVersion', wrong))
        wrong = fixture('Money'); wrong['amount_micros'] = 0.01; cases.append(('Money', wrong))
        wrong = fixture('Money'); wrong['amount_micros'] = -1; cases.append(('Money', wrong))
        wrong = fixture('Job'); wrong['state'] = 'SIMULATED_SUCCESS'; cases.append(('Job', wrong))
        wrong = fixture('PackageVersion'); wrong['master_narrative'] = {}; cases.append(('PackageVersion', wrong))
        wrong = fixture('UploadIntentCreate'); wrong['source_type'] = 'PUBLIC_URL'; cases.append(('UploadIntentCreate', wrong))
        wrong = fixture('UploadIntentCreate'); wrong.update(source_type='PDF', size_bytes=52428801); cases.append(('UploadIntentCreate', wrong))
        wrong = fixture('UploadIntentCreate'); wrong.update(source_type='VTT', size_bytes=10485761); cases.append(('UploadIntentCreate', wrong))
        for name, bad in cases:
            with self.subTest(schema=name):
                with self.assertRaises(AssertionError): check(bad, SCHEMAS[name])
        check({'amount_micros': 0, 'currency': 'USD'}, SCHEMAS['Money'])

    def test_asset_type_must_match_content_variant(self):
        bad = fixture('AssetWrite')
        bad['asset_type'] = 'SCRIPT'
        with self.assertRaises(AssertionError): check(bad, SCHEMAS['AssetWrite'])
        bad['content'] = sample(SCHEMAS['ScriptContent'])
        check(bad, SCHEMAS['AssetWrite'])
        bad.update(asset_type='ARTICLE', content=sample(SCHEMAS['WrittenContent']))
        bad['content']['format'] = 'NEWSLETTER'
        with self.assertRaises(AssertionError): check(bad, SCHEMAS['AssetWrite'])
        bad['content']['format'] = 'ARTICLE'
        check(bad, SCHEMAS['AssetWrite'])

    def test_supported_claim_needs_evidence_and_opinion_can_be_source_free(self):
        value = fixture('Claim')
        value.update(classification='FACTUAL', verification='SUPPORTED', evidence_ids=[], reviewer_evidence=None)
        with self.assertRaises(AssertionError): check(value, SCHEMAS['Claim'])
        value['evidence_ids'] = [UUID]
        check(value, SCHEMAS['Claim'])
        package = fixture('PackageVersion'); package['claim_ids'] = []; package['source_version_ids'] = []
        check(package, SCHEMAS['PackageVersion'])

    def test_clip_shortfall_requires_explicit_reason(self):
        selection = fixture('ClipSelectionWrite')
        selection['shortfall_accepted'] = False
        selection['shortfall_reason'] = None
        with self.assertRaises(AssertionError): check(selection, SCHEMAS['ClipSelectionWrite'])
        selection.update(shortfall_accepted=True, shortfall_reason='Only two coherent moments after review.')
        check(selection, SCHEMAS['ClipSelectionWrite'])

    def test_live_publication_requires_verified_remote_state(self):
        status = fixture('PublicationStatus')
        status.update(state='PUBLISHED', remote_id=None, verified_live_at=None, verified_visibility=None)
        with self.assertRaises(AssertionError): check(status, SCHEMAS['PublicationStatus'])
        status.update(remote_id='remote-confirmed', verified_live_at=NOW, verified_visibility='PRIVATE')
        check(status, SCHEMAS['PublicationStatus'])
        intent = fixture('PublicationIntentWrite'); intent['rendition_id'] = None
        with self.assertRaises(AssertionError): check(intent, SCHEMAS['PublicationIntentWrite'])
        intent.update(destination='LINKEDIN_TEXT', rendition_approval_decision_id=None)
        check(intent, SCHEMAS['PublicationIntentWrite'])

    def test_missing_metrics_are_null_not_zero(self):
        value = fixture('MetricSnapshot')
        value.update(availability='UNAVAILABLE', value=0)
        with self.assertRaises(AssertionError): check(value, SCHEMAS['MetricSnapshot'])
        value['value'] = None
        check(value, SCHEMAS['MetricSnapshot'])


class EventTests(unittest.TestCase):
    def event_fixture(self, event_name):
        schema_name = builder.EVENTS[event_name]['schema']
        value = sample(SCHEMAS[schema_name])
        if event_name in ['job.state_changed', 'job.reconciliation_required']:
            value['data']['originating_operation_id'] = 'processSource'
        if event_name == 'job.state_changed': value['data'].update(previous_state='QUEUED', state='RUNNING')
        if event_name == 'publication.state_changed': value['data'].update(previous_state='DRAFT', state='SCHEDULED')
        return value

    def test_all_required_families_have_typed_payloads(self):
        self.assertEqual({event.split('.')[0] for event in builder.EVENTS}, {'source', 'package', 'plan', 'asset', 'job', 'review', 'publication', 'metrics', 'usage', 'connection'})
        for event_name, item in builder.EVENTS.items():
            schema = SCHEMAS[item['schema']]
            self.assertEqual(schema['properties']['type']['const'], event_name)
            self.assertTrue(schema['properties']['data']['required'])
            self.assertFalse(schema['properties']['data']['additionalProperties'])
            good = self.event_fixture(event_name)
            check(good, EVENT_DOC, EVENT_DOC)
            for field in list(good['data']):
                bad = copy.deepcopy(good)
                del bad['data'][field]
                with self.subTest(event=event_name, field=field):
                    with self.assertRaises(AssertionError): check(bad, EVENT_DOC, EVENT_DOC)

    def test_envelope_and_wrong_type_payload_rejected(self):
        good = self.event_fixture('asset.version_created')
        for field in ['event_id', 'schema_version', 'type', 'occurred_at', 'workspace_id', 'aggregate_id', 'aggregate_version', 'correlation_id', 'data']:
            bad = copy.deepcopy(good); del bad[field]
            with self.assertRaises(AssertionError): check(bad, EVENT_DOC, EVENT_DOC)
        bad = copy.deepcopy(good); bad['data'] = {}
        with self.assertRaises(AssertionError): check(bad, EVENT_DOC, EVENT_DOC)
        bad = copy.deepcopy(good); bad['type'] = 'usage.reserved'
        with self.assertRaises(AssertionError): check(bad, EVENT_DOC, EVENT_DOC)
        bad = copy.deepcopy(good); bad['schema_version'] = 99
        with self.assertRaises(AssertionError): check(bad, EVENT_DOC, EVENT_DOC)

    def test_lifecycle_enum_coverage_and_terminal_safety(self):
        self.assertEqual(set(LIFECYCLE['job']['transitions']), set(SCHEMAS['JobState']['enum']))
        self.assertEqual(set(LIFECYCLE['publication']['transitions']), set(SCHEMAS['PublicationState']['enum']))
        for terminal in ['SUCCEEDED', 'FAILED_PERMANENT', 'CANCELLED']:
            self.assertEqual(LIFECYCLE['job']['transitions'][terminal], [])
        self.assertNotIn('QUEUED', LIFECYCLE['job']['transitions']['RECONCILING'])
        self.assertEqual(LIFECYCLE['reservation']['transitions']['RESERVED'], ['SETTLED', 'RELEASED'])
        self.assertEqual(LIFECYCLE['delivery']['delivery_semantics'], 'at-least-once')

    def test_transition_payload_checks_every_state_pair(self):
        for event_name, family in [('job.state_changed', 'job'), ('publication.state_changed', 'publication')]:
            transitions = LIFECYCLE[family]['transitions']
            # Validate the concrete event, not only the lifecycle metadata.
            schema = SCHEMAS[builder.EVENTS[event_name]['schema']]
            for previous in transitions:
                for current in transitions:
                    value = self.event_fixture(event_name)
                    value['data'].update(previous_state=previous, state=current)
                    if current == 'PUBLISHED': value['data'].update(remote_id='verified-id', verified_live_at=NOW, verified_visibility='PUBLIC')
                    with self.subTest(event=event_name, previous=previous, current=current):
                        if current in transitions[previous]: check(value, schema)
                        else:
                            with self.assertRaises(AssertionError): check(value, schema)

    def test_published_event_also_requires_remote_verification(self):
        value = self.event_fixture('publication.state_changed')
        value['data'].update(previous_state='PROCESSING', state='PUBLISHED', remote_id='not-enough', verified_live_at=None)
        with self.assertRaises(AssertionError): check(value, EVENT_DOC, EVENT_DOC)


class CrossContractRegressionTests(unittest.TestCase):
    """Shape/policy regression checks only; no DB or side-effect execution claims."""
    def assertPayload(self, value, name, valid=True, document=OPENAPI):
        schema = document['components']['schemas'][name] if document is OPENAPI else document
        if valid:
            check(value, schema, document)
        else:
            with self.assertRaises(AssertionError): check(value, schema, document)
        if jsonschema is not None:
            root = {'$ref': '#/components/schemas/' + name, 'components': document['components']} if document is OPENAPI else document
            validator = jsonschema.Draft202012Validator(root)
            if valid: validator.validate(value)
            else:
                with self.assertRaises(jsonschema.ValidationError): validator.validate(value)

    def operations(self):
        return {op['operationId']: op for item in OPENAPI['paths'].values() for op in item.values()}

    def test_script_is_universal_asset_with_one_registry_identity(self):
        self.assertIn('SCRIPT', SCHEMAS['AssetType']['enum'])
        self.assertNotIn('SCRIPT', SCHEMAS['VersionBinding']['properties']['kind']['enum'])
        detail = SCHEMAS['ScriptVersionDetail']
        self.assertEqual(detail['x-registry-kind'], 'asset')
        self.assertEqual(detail['x-shared-primary-key'], 'asset_versions.id')
        subject = SCHEMAS['ScriptApprovalSubject']
        self.assertEqual((subject['x-registry-kind'], subject['x-review-scope']), ('asset', 'narration'))
        self.assertEqual(builder.SUBJECTS['Script'][2], 'asset_version_id')
        value = fixture('AssetVersion'); value.update(asset_type='SCRIPT', content=sample(SCHEMAS['ScriptContent']))
        self.assertPayload(value, 'AssetVersion')
        value['asset_type'] = 'ASSET_SCRIPT'
        self.assertPayload(value, 'AssetVersion', False)
        binding = fixture('VersionBinding'); binding['kind'] = 'SCRIPT'
        self.assertPayload(binding, 'VersionBinding', False)

    def test_voice_and_clip_selection_have_real_version_targets(self):
        for subject, kind, table, snapshot in [('VoiceSample', 'voice_sample', 'voice_sample_versions', 'VoiceSampleVersion'), ('ClipSelection', 'clip_selection', 'clip_selection_versions', 'ClipSelectionVersion')]:
            self.assertEqual(SCHEMAS[subject + 'ApprovalSubject']['x-version-table'], table)
            self.assertEqual(SCHEMAS[snapshot]['x-registry-kind'], kind)
            self.assertIn(kind.upper(), SCHEMAS['VersionBinding']['properties']['kind']['enum'])
        self.assertNotIn('approval_status', SCHEMAS['VoiceSampleVersion']['properties'])

    def test_rendition_decisions_require_exact_final_media_scope(self):
        op = self.operations()['decideRendition']
        self.assertEqual(op['x-permissions']['roles_any_of'], builder.REVIEW)
        self.assertEqual(op['x-concurrency'], 'if-match')
        subject = SCHEMAS['RenditionApprovalSubject']
        self.assertEqual((subject['x-registry-kind'], subject['x-review-scope']), ('rendition', 'final_media'))
        for decision in ['APPROVED', 'REJECTED']:
            value = fixture('RenditionDecisionCreate'); value['decision'] = decision
            self.assertPayload(value, 'RenditionDecisionCreate')
        value['subject']['scope'] = 'final_editorial'
        self.assertPayload(value, 'RenditionDecisionCreate', False)
        del value['subject']['scope']
        self.assertPayload(value, 'RenditionDecisionCreate', False)

    def test_publication_rendition_needs_separate_decision(self):
        for name in ['PublicationIntentWrite', 'PublicationIntent']:
            value = fixture(name)
            self.assertPayload(value, name)
            value['rendition_approval_decision_id'] = None
            self.assertPayload(value, name, False)
            value.update(destination='LINKEDIN_TEXT', rendition_id=None)
            self.assertPayload(value, name)

    def test_preproduction_authorization_is_immutable_capped_and_admin_created(self):
        op = self.operations()['createPreproductionAuthorization']
        self.assertEqual(op['x-permissions']['roles_any_of'], builder.ADMIN)
        self.assertTrue(op['x-permissions']['explicit_brand_grant_required_for_non_owner'])
        schema = SCHEMAS['PreproductionAuthorization']
        self.assertTrue(schema['x-immutable'])
        self.assertEqual(schema['x-default-live-cap-micros'], 0)
        required = {'actor_user_id', 'brand_id', 'campaign_id', 'job_id', 'logical_operation_id', 'operation_id', 'input_sha256', 'inputs', 'cap', 'expires_at'}
        self.assertTrue(required <= set(SCHEMAS['PreproductionAuthorizationCreate']['required']))
        value = fixture('PreproductionAuthorizationCreate'); value.update(job_id=None, campaign_id=None)
        value['cap']['amount_micros'] = 0
        self.assertPayload(value, 'PreproductionAuthorizationCreate')
        value['cap']['amount_micros'] = -1
        self.assertPayload(value, 'PreproductionAuthorizationCreate', False)
        value['cap']['amount_micros'] = 1
        value['operation_id'] = 'executePlan'
        self.assertPayload(value, 'PreproductionAuthorizationCreate', False)
        path = '/workspaces/{workspace_id}/preproduction-authorizations/{preproduction_authorization_id}'
        self.assertEqual(set(OPENAPI['paths'][path]), {'get'})

    def test_authorization_carries_exact_typed_operation_input_and_precondition(self):
        for operation_id, input_name in builder.PREPRODUCTION_INPUTS.items():
            value = fixture('PreproductionAuthorizationCreate')
            value.update(operation_id=operation_id, operation_input=fixture(input_name), operation_if_match='"revision-1"' if operation_id in ['processSource', 'alignTranscript'] else None)
            self.assertPayload(value, 'PreproductionAuthorizationCreate')
            value['operation_input']['preproduction_authorization_id'] = UUID
            self.assertPayload(value, 'PreproductionAuthorizationCreate', False)
            value['operation_input'] = {'unbound': 'request'}
            self.assertPayload(value, 'PreproductionAuthorizationCreate', False)
        value = fixture('PreproductionAuthorizationCreate')
        value.update(operation_id='processSource', operation_input=fixture('PreproductionSourceProcessInput'), operation_if_match=None)
        self.assertPayload(value, 'PreproductionAuthorizationCreate', False)

    def test_every_billable_preplan_operation_references_authorization(self):
        ops = self.operations()
        self.assertEqual(set(builder.PREPRODUCTION_OPERATIONS), {'previewBrandVoice', 'createSourceFromURL', 'processSource', 'alignTranscript', 'draftPackage', 'proposePlan'})
        for name, request in builder.PREPRODUCTION_OPERATIONS.items():
            op = ops[name]
            self.assertTrue(op['x-billable'])
            policy = op['x-work-authorization']
            self.assertEqual(policy['purpose'], 'PREPRODUCTION')
            self.assertFalse(policy['approved_plan_required'])
            self.assertIn('preproduction_authorization', policy['reserve_against'])
            value = fixture(request)
            self.assertPayload(value, request)
            for field in ['preproduction_authorization_id', 'logical_operation_id']:
                bad = copy.deepcopy(value); del bad[field]
                self.assertPayload(bad, request, False)

    def test_production_never_substitutes_preplan_authorization(self):
        ops = self.operations()
        for name in builder.PRODUCTION_OPERATIONS:
            self.assertTrue(ops[name]['x-work-authorization']['approved_plan_required'])
            self.assertFalse(ops[name]['x-work-authorization']['preproduction_authorization_permitted'])
        for name in ['RenditionRequest', 'PreviewRequest', 'ClipCandidatesRequest', 'RegenerateRequest']:
            value = fixture(name)
            self.assertPayload(value, name)
            del value['approved_plan_version_id']
            self.assertPayload(value, name, False)
        job = fixture('Job')
        job.update(purpose='PRODUCTION', job_type='RENDER', originating_operation_id='requestRendition', preproduction_authorization_id=None, approved_plan_version_id=UUID, plan_approval_decision_id=UUID)
        self.assertPayload(job, 'Job')
        job.update(approved_plan_version_id=None, preproduction_authorization_id=UUID)
        self.assertPayload(job, 'Job', False)
        job.update(purpose='ADMIN', preproduction_authorization_id=None)
        self.assertPayload(job, 'Job', False)

    def test_preproduction_job_steps_attempts_retain_bound_authorization(self):
        for name in ['Job', 'JobStep', 'ProviderAttempt']:
            value = fixture(name)
            self.assertPayload(value, name)
            value['preproduction_authorization_id'] = None
            self.assertPayload(value, name, False)
            value['purpose'] = 'ADMIN'
            self.assertPayload(value, name, False)

    def test_timeline_input_and_fresh_output_binding_do_not_form_hash_cycle(self):
        request = fixture('TimelineWrite')
        self.assertPayload(request, 'TimelineWrite')
        self.assertNotIn('asset_version_id', request)
        bad = copy.deepcopy(request); bad['asset_version_id'] = bad.pop('base_asset_version_id')
        self.assertPayload(bad, 'TimelineWrite', False)
        response = fixture('TimelineVersion')
        self.assertPayload(response, 'TimelineVersion')
        self.assertNotEqual(response['asset_version_id'], response['base_asset_version_id'])
        self.assertEqual(SCHEMAS['TimelineVersion']['x-hash-excluded-fields'], ['asset_version_id'])
        self.assertTrue(SCHEMAS['TimelineVersion']['x-output-binding']['fresh_output_required'])
        self.assertEqual(self.operations()['createTimelineVersion']['x-concurrency'], 'if-match')
        # Fresh-ID equality, atomicity and hashes are database/service invariants, not JSON Schema claims.

    def test_workspace_admin_scope_rejects_null_brand_production_and_fake_brands(self):
        for name in ['Job', 'JobStep', 'ProviderAttempt']:
            value = fixture(name)
            for job_type, origin in [('WORKSPACE_EXPORT', 'requestWorkspaceExport'), ('WORKSPACE_DELETE', 'requestWorkspaceDeletion')]:
                value.update(scope_type='WORKSPACE', brand_id=None, campaign_id=None, purpose='ADMIN', job_type=job_type, originating_operation_id=origin, preproduction_authorization_id=None)
                self.assertPayload(value, name)
                for patch in [{'brand_id': UUID}, {'campaign_id': UUID}, {'purpose': 'PRODUCTION'}, {'job_type': 'RENDER'}, {'scope_type': 'BRAND'}, {'originating_operation_id': 'requestExport'}]:
                    self.assertPayload(dict(value, **patch), name, False)
            value = fixture(name); value['brand_id'] = None
            self.assertPayload(value, name, False)

    def test_retry_cancel_derive_origin_without_edit_intersection(self):
        ops = self.operations()
        for name in ['retrySafeJob', 'cancelJob']:
            policy = ops[name]['x-permissions']
            self.assertEqual(policy['role_resolution'], 'originating-operation-only')
            self.assertFalse(policy['additional_edit_role_required'])
            self.assertIn('VIEWER', policy['roles_any_of'])
            self.assertIn('PUBLISHER', policy['roles_any_of'])
            self.assertEqual(policy['origin_examples']['requestExport'], ops['requestExport']['x-permissions']['roles_any_of'])
            self.assertEqual(policy['origin_examples']['schedulePublication'], ops['schedulePublication']['x-permissions']['roles_any_of'])
            self.assertEqual(policy['origin_examples']['requestWorkspaceDeletion'], ['OWNER'])
        self.assertEqual(ops['reconcileJob']['x-permissions']['roles_any_of'], builder.ADMIN)
        self.assertTrue(ops['reconcileJob']['x-permissions']['operator_entitlement_required'])
        self.assertEqual(ops['requestWorkspaceDeletion']['x-permissions']['roles_any_of'], ['OWNER'])

    def test_usage_dimensions_cannot_mix_money_and_credits(self):
        for amount in [-100, 0, 100]:
            cost = fixture('ProviderCostUsageEntry'); cost['amount']['amount_micros'] = amount
            credit = fixture('CustomerCreditsUsageEntry'); credit['credits'] = amount
            self.assertPayload(cost, 'UsageEntry')
            self.assertPayload(credit, 'UsageEntry')
        for patch in [{'currency': 'USD'}, {'currency': None}, {'amount': {'amount_micros': 1, 'currency': 'USD'}}, {'credits': 0.1}]:
            self.assertPayload(dict(credit, **patch), 'UsageEntry', False)
        self.assertPayload(dict(cost, credits=1), 'UsageEntry', False)
        self.assertPayload(dict(cost, ledger='CUSTOMER_CREDITS'), 'UsageEntry', False)

    def test_event_mirrors_enforce_new_ledger_and_admin_scope(self):
        events = EventTests()
        event = events.event_fixture('usage.settled')
        event['data']['usage_entry'] = fixture('CustomerCreditsUsageEntry')
        event['data']['usage_entry']['credits'] = -3
        self.assertPayload(event, '', document=EVENT_DOC)
        event['data']['usage_entry']['currency'] = 'USD'
        self.assertPayload(event, '', False, document=EVENT_DOC)
        for name in ['job.state_changed', 'job.reconciliation_required']:
            event = events.event_fixture(name)
            event['data'].update(scope_type='WORKSPACE', brand_id=None, campaign_id=None, purpose='ADMIN', job_type='WORKSPACE_DELETE', originating_operation_id='requestWorkspaceDeletion', preproduction_authorization_id=None)
            self.assertPayload(event, '', document=EVENT_DOC)
            event['data']['job_type'] = 'RENDER'
            self.assertPayload(event, '', False, document=EVENT_DOC)
        event = events.event_fixture('review.decision_recorded')
        event['data']['subject'] = fixture('RenditionApprovalSubject')
        self.assertPayload(event, '', document=EVENT_DOC)
        event['data']['subject']['scope'] = 'editorial'
        self.assertPayload(event, '', False, document=EVENT_DOC)


try:
    import jsonschema
except ImportError:
    jsonschema = None


@unittest.skipUnless(jsonschema is not None, 'Optional jsonschema not installed; stdlib policy/payload checks still run.')
class OptionalJSONSchemaTests(unittest.TestCase):
    def test_all_schema_definitions_are_draft202012_valid(self):
        for name, schema in SCHEMAS.items():
            with self.subTest(schema=name): jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator.check_schema(EVENT_DOC)

    def test_jsonschema_validates_core_examples_and_events(self):
        for name in ['PackageVersion', 'PlanVersion', 'AssetVersion', 'TimelineVersion', 'PublicationIntent', 'Job']:
            document = {'$ref': '#/components/schemas/' + name, 'components': OPENAPI['components']}
            jsonschema.Draft202012Validator(document).validate(fixture(name))
        validator = jsonschema.Draft202012Validator(EVENT_DOC)
        events = EventTests()
        for event_name in builder.EVENTS: validator.validate(events.event_fixture(event_name))
        invalid = events.event_fixture('job.state_changed')
        invalid['data'].update(previous_state='SUCCEEDED', state='QUEUED')
        with self.assertRaises(jsonschema.ValidationError): validator.validate(invalid)


try:
    from openapi_spec_validator import validate as validate_openapi
except ImportError:
    validate_openapi = None


@unittest.skipUnless(validate_openapi is not None, 'Optional openapi-spec-validator not installed.')
class OptionalOpenAPIValidationTests(unittest.TestCase):
    def test_openapi_document_is_valid(self):
        validate_openapi(OPENAPI)


if __name__ == '__main__': unittest.main(verbosity=2)
