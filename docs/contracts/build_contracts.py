#!/usr/bin/env python3
"""Deterministic M0 planned contracts. Never imports/changes runtime or calls providers."""
import argparse
import copy
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = {}
PATHS = {}
OPERATIONS = []

def text(**kw): return dict(type='string', **kw)
def enum(*values): return dict(type='string', enum=list(values))
def integer(minimum=0, **kw): return dict(type='integer', minimum=minimum, **kw)
def array(items, **kw): return dict(type='array', items=items, **kw)
def ref(name): return {'$ref': '#/components/schemas/' + name}
def nullable(schema): return {'anyOf': [schema, {'type': 'null'}]}
def obj(props, required=None, **kw):
    return dict(type='object', properties=props, required=list(props) if required is None else required, additionalProperties=False, **kw)
def define(name, props, required=None, **kw):
    S[name] = obj(props, required, **kw)
    return ref(name)
def extend(name, base, props, optional=()):
    merged = {**copy.deepcopy(S[base]['properties']), **props}
    return define(name, merged, [k for k in merged if k not in optional])
def ids(): return array(UUID, uniqueItems=True)
UUID = text(format='uuid')
DATE = text(format='date-time', pattern=r'Z$', description='UTC RFC3339 instant ending Z.')
URL = text(format='uri')
HASH = text(pattern='^[a-f0-9]{64}$')
BOOL = {'type': 'boolean'}
STR = text(minLength=1)
ROLES = ['OWNER', 'ADMIN', 'EDITOR', 'REVIEWER', 'PUBLISHER', 'VIEWER']
READ = ROLES
EDIT = ['OWNER', 'ADMIN', 'EDITOR']
REVIEW = ['OWNER', 'ADMIN', 'REVIEWER']
PUBLISH = ['OWNER', 'ADMIN', 'PUBLISHER']
ADMIN = ['OWNER', 'ADMIN']
OWNER = ['OWNER']
DESTINATIONS = ['YOUTUBE_LONG', 'YOUTUBE_SHORTS', 'LINKEDIN_TEXT', 'INSTAGRAM_REELS', 'FACEBOOK_PAGE_REELS', 'TIKTOK_VIDEO']
ASSET_TYPES = ['MAIN_VIDEO', 'CLIP', 'LINKEDIN_POST', 'ARTICLE', 'NEWSLETTER', 'SCRIPT', 'CAPTIONS', 'THUMBNAIL']
JOB_TRANSITIONS = {
    'QUEUED': ['RUNNING', 'CANCELLED'],
    'RUNNING': ['WAITING_PROVIDER', 'WAITING_USER', 'RECONCILING', 'SUCCEEDED', 'FAILED_RETRYABLE', 'FAILED_PERMANENT', 'CANCEL_REQUESTED'],
    'WAITING_PROVIDER': ['RUNNING', 'SUCCEEDED', 'RECONCILING', 'FAILED_RETRYABLE', 'FAILED_PERMANENT', 'CANCEL_REQUESTED'],
    'WAITING_USER': ['QUEUED', 'CANCELLED'],
    'RECONCILING': ['WAITING_PROVIDER', 'SUCCEEDED', 'FAILED_PERMANENT', 'CANCEL_REQUESTED'],
    'SUCCEEDED': [], 'FAILED_RETRYABLE': ['QUEUED', 'FAILED_PERMANENT', 'CANCELLED'],
    'FAILED_PERMANENT': [], 'CANCEL_REQUESTED': ['CANCELLED', 'SUCCEEDED', 'RECONCILING'], 'CANCELLED': []}
PUBLICATION_TRANSITIONS = {
    'DRAFT': ['SCHEDULED', 'CANCELLED'], 'SCHEDULED': ['PAUSED', 'SUBMITTING', 'CANCELLED'],
    'PAUSED': ['SCHEDULED', 'CANCELLED'], 'SUBMITTING': ['PROCESSING', 'PUBLISHED', 'RECONCILING', 'FAILED'],
    'PROCESSING': ['PUBLISHED', 'RECONCILING', 'FAILED'], 'PUBLISHED': ['TAKEDOWN_REQUESTED'],
    'RECONCILING': ['PROCESSING', 'PUBLISHED', 'FAILED', 'CANCELLED'],
    'FAILED': ['DRAFT', 'CANCELLED'], 'CANCELLED': [], 'TAKEDOWN_REQUESTED': ['TAKEN_DOWN', 'PUBLISHED', 'RECONCILING'], 'TAKEN_DOWN': []}
SCOPE = {'workspace_id': UUID, 'brand_id': UUID}
VERSION = {**SCOPE, 'created_at': DATE, 'created_by': UUID}

# Common precision, errors and execution envelopes.
S['Role'] = enum(*ROLES)
S['Destination'] = enum(*DESTINATIONS)
S['JobState'] = enum(*JOB_TRANSITIONS)
S['PublicationState'] = enum(*PUBLICATION_TRANSITIONS)
S['ApprovalStatus'] = enum('PENDING', 'APPROVED', 'REJECTED', 'INVALIDATED')
S['RightsStatus'] = enum('UNVERIFIED', 'VALID', 'EXPIRED', 'REVOKED', 'BLOCKED')
S['Freshness'] = enum('CURRENT', 'STALE')
S['AssetType'] = enum(*ASSET_TYPES)
S['ProductionStatus'] = enum('DRAFT', 'QUEUED', 'IN_PRODUCTION', 'PARTIAL_SUCCESS', 'READY', 'FAILED', 'CANCELLED')
S['ErrorCode'] = enum('UNAUTHENTICATED', 'FORBIDDEN', 'NOT_FOUND', 'CONFLICT', 'STALE_VERSION', 'IDEMPOTENCY_CONFLICT', 'INVALID_INPUT', 'INVALID_STATE', 'RATE_LIMITED', 'BUDGET_EXCEEDED', 'PRECONDITION_REQUIRED', 'IDEMPOTENCY_KEY_REQUIRED', 'APPROVAL_REQUIRED', 'RIGHTS_BLOCKED', 'STALE_DEPENDENCY', 'ALIGNMENT_REQUIRED', 'CLAIM_UNSUPPORTED', 'CAPABILITY_UNSUPPORTED', 'PROVIDER_UNAVAILABLE', 'RECONCILIATION_REQUIRED', 'UNSAFE_URL', 'UPLOAD_INVALID', 'DST_AMBIGUOUS', 'DST_NONEXISTENT', 'INTERNAL_ERROR')
define('FieldError', {'field': STR, 'code': ref('ErrorCode'), 'message': STR})
define('Error', {'code': ref('ErrorCode'), 'message': STR, 'field_errors': array(ref('FieldError')), 'retryable': BOOL, 'correlation_id': UUID})
define('Money', {'amount_micros': integer(), 'currency': text(pattern='^[A-Z]{3}$')}, description='Integer millionths of currency unit; never float USD. Zero is a hard zero.')
define('SignedMoney', {'amount_micros': {'type': 'integer'}, 'currency': text(pattern='^[A-Z]{3}$')})
define('ActionReason', {'reason': STR})
define('Acknowledgement', {'accepted': {'const': True}, 'correlation_id': UUID})
define('AsyncAccepted', {'job_id': UUID, 'status_url': text(format='uri-reference'), 'correlation_id': UUID}, description='202 acknowledges durable intent only, not provider success. GET status_url returns Job.')
define('VersionBinding', {'kind': enum('SOURCE', 'TRANSCRIPT', 'PACKAGE', 'PLAN', 'RECIPE', 'PERSONA', 'BRAND_PROFILE', 'TIMELINE', 'ASSET', 'RENDITION', 'RENDER_PRESET', 'CONSENT', 'VOICE_SAMPLE', 'CLIP_SELECTION'), 'entity_id': UUID, 'version_id': UUID, 'sha256': HASH}, description='SCRIPT is an ASSET binding: script_versions is an immutable detail extension sharing asset_versions.id, never a second registry kind. VOICE_SAMPLE and CLIP_SELECTION map to voice_sample_versions and clip_selection_versions.')
define('DependencyEdge', {**SCOPE, 'from_version_id': UUID, 'to_version_id': UUID, 'relationship': enum('DERIVED_FROM', 'USES_EVIDENCE', 'USES_RECIPE', 'USES_BRAND', 'USES_CONSENT')}, description='Immutable acyclic same-tenant edges. A clip references final-cut version and approved package.')

# Identity, membership and controlled onboarding.
define('User', {'user_id': UUID, 'oidc_subject': STR, 'display_name': STR, 'verified_email': text(format='email'), 'state': enum('ACTIVE', 'SUSPENDED', 'DELETED')})
define('Session', {'user': ref('User'), 'active_workspace_id': nullable(UUID), 'expires_at': DATE, 'csrf_token': STR}, description='Cookie is Secure, HttpOnly, SameSite; response CSRF token is not a provider credential.')
define('LoginStart', {'return_path': text(pattern='^/(?!/)[^\\\\]*$')})
define('AuthRedirect', {'authorization_url': URL, 'expires_at': DATE})
define('WorkspaceSwitch', {'workspace_id': UUID})
define('OnboardingStart', {'access_code': STR, 'email': text(format='email')}, description='Pilot invitation/bootstrap code, rate limited; does not grant identity or create users from an email string. No public signup in R1.')
define('OnboardingChallenge', {'challenge_id': UUID, 'expires_at': DATE, 'next_action': enum('VERIFY_IDENTITY')})
define('WorkspaceCreate', {'challenge_id': UUID, 'name': text(minLength=1, maxLength=200), 'timezone': STR}, description='Verified logged-in identity becomes owner; no arbitrary owner_email field.')
define('Workspace', {'workspace_id': UUID, 'name': STR, 'owner_user_id': UUID, 'timezone': STR, 'state': enum('ACTIVE', 'DELETION_PENDING', 'DELETED'), 'revision': integer(1)})
define('InviteCreate', {'email': text(format='email'), 'roles': array(enum(*ROLES[1:]), minItems=1, uniqueItems=True), 'brand_ids': ids()}, description='No OWNER invitation. Explicit brand grant required for each non-owner; seven-day expiry default.')
define('Invitation', {'revision': integer(1), 'invitation_id': UUID, 'workspace_id': UUID, 'email': text(format='email'), 'roles': array(ref('Role')), 'brand_ids': ids(), 'expires_at': DATE, 'state': enum('PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED')})
define('InviteAccept', {'token': STR}, description='Session verified intended identity must match invitation; token alone insufficient.')
define('MembershipEdit', {'roles': array(enum(*ROLES[1:]), minItems=1, uniqueItems=True), 'state': enum('ACTIVE', 'SUSPENDED')})
define('Membership', {'membership_id': UUID, 'workspace_id': UUID, 'user_id': UUID, 'roles': array(ref('Role')), 'state': enum('ACTIVE', 'SUSPENDED', 'REVOKED'), 'revision': integer(1)})
define('BrandGrantEdit', {'can_connect_social': BOOL})
define('BrandGrant', {'membership_id': UUID, 'workspace_id': UUID, 'brand_id': UUID, 'can_connect_social': BOOL})
define('OwnershipTransfer', {'new_owner_user_id': UUID, 'reauthentication_token': STR, 'confirmation': {'const': 'TRANSFER_OWNERSHIP'}}, description='Requires verified active membership and recent owner reauthentication; admin cannot self-promote.')

# Brands and policy are versioned, not credentials or runtime configuration blobs.
define('BrandWrite', {'name': STR, 'timezone': STR})
extend('Brand', 'BrandWrite', {**SCOPE, 'current_profile_version_id': nullable(UUID), 'revision': integer(1)})
define('Pronunciation', {'term': STR, 'pronunciation': STR})
define('BrandProfileWrite', {'audience': STR, 'positioning': STR, 'voice_examples': array(STR), 'logo_media_version_id': nullable(UUID), 'colors': array(text(pattern='^#[0-9A-Fa-f]{6}$')), 'fonts': array(STR), 'prohibited_terms': array(STR), 'pronunciation': array(ref('Pronunciation')), 'offers': array(STR), 'ctas': array(STR), 'designated_reviewer_ids': ids(), 'human_publication_review_required': {'const': True}})
extend('BrandProfileVersion', 'BrandProfileWrite', {**VERSION, 'profile_version_id': UUID, 'brand_id': UUID})
define('VoicePreviewRequest', {'profile_version_id': UUID, 'sample_topic': STR})
define('VoiceSample', {**SCOPE, 'sample_id': UUID, 'sample_version_id': UUID, 'profile_version_id': UUID, 'paragraph': STR, 'script': STR, 'approval_status': ref('ApprovalStatus')})

# Private upload handshake, immutable source and transcript snapshots.
S['SourceType'] = enum('TEXT', 'MARKDOWN', 'PDF', 'DOCX', 'PUBLIC_URL', 'YOUTUBE_REFERENCE', 'MP4', 'MOV', 'MP3', 'WAV', 'M4A', 'SRT', 'VTT')
define('RightsAssertion', {'asserted_by': UUID, 'permitted_uses': array(enum('PROCESS', 'DERIVE', 'PUBLISH', 'EXPORT'), minItems=1), 'rights_evidence': STR, 'expires_at': nullable(DATE)})
define('UploadIntentCreate', {'brand_id': UUID, 'filename': STR, 'source_type': ref('SourceType'), 'size_bytes': integer(1, maximum=2147483648), 'sha256': HASH, 'rights': ref('RightsAssertion')})
S['UploadIntentCreate']['properties']['source_type'] = enum('PDF', 'DOCX', 'MP4', 'MOV', 'MP3', 'WAV', 'M4A', 'SRT', 'VTT')
S['UploadIntentCreate']['allOf'] = [
    {'if': {'properties': {'source_type': enum('PDF', 'DOCX')}}, 'then': {'properties': {'size_bytes': integer(1, maximum=52428800)}}},
    {'if': {'properties': {'source_type': enum('SRT', 'VTT')}}, 'then': {'properties': {'size_bytes': integer(1, maximum=10485760)}}}]
S['UploadIntentCreate']['description'] = 'Default size limits encoded; PDF page count <=200 and audio/video duration <=60 minutes checked after probe. Rights actor must equal verified caller. Source URL/text use separate endpoints.'
define('UploadIntent', {**SCOPE, 'upload_id': UUID, 'source_id': UUID, 'part_size_bytes': integer(1), 'part_count': integer(1), 'expires_at': DATE, 'state': enum('QUARANTINE', 'FINALIZED', 'CANCELLED', 'EXPIRED')})
define('UploadPartRequest', {'part_number': integer(1, maximum=10000)})
define('UploadPartURL', {'part_number': integer(1), 'upload_url': URL, 'expires_at': DATE, 'method': {'const': 'PUT'}}, description='Private quarantine destination; signed URL grants only one scoped transfer, not read access.')
define('UploadPart', {'part_number': integer(1), 'etag': STR})
define('FinalizeSource', {'upload_id': UUID, 'parts': array(ref('UploadPart'), minItems=1), 'size_bytes': integer(1), 'sha256': HASH}, description='Server verifies multipart completion/hash/type/limits then scans/probes. Transfer completion never equals clearance.')
define('SourceURLCreate', {'brand_id': UUID, 'url': text(format='uri', pattern='^https?://'), 'source_type': enum('PUBLIC_URL', 'YOUTUBE_REFERENCE'), 'rights': ref('RightsAssertion')}, description='SSRF-safe bounded public fetch after DNS and every redirect; no login bypass. YouTube unavailable media requires authorized original/transcript.')
define('SourceTextCreate', {'brand_id': UUID, 'title': STR, 'source_type': enum('TEXT', 'MARKDOWN'), 'text': text(minLength=1, maxLength=100000), 'rights': ref('RightsAssertion')})
define('Source', {**SCOPE, 'source_id': UUID, 'title': STR, 'source_type': ref('SourceType'), 'current_version_id': nullable(UUID), 'state': enum('QUARANTINED', 'VERIFYING', 'SCANNING', 'PROCESSING', 'READY', 'WAITING_USER', 'FAILED', 'CANCELLED'), 'rights_status': ref('RightsStatus'), 'revision': integer(1)})
define('SourceVersion', {**VERSION, 'source_id': UUID, 'source_version_id': UUID, 'sha256': HASH, 'size_bytes': integer(), 'source_type': ref('SourceType'), 'original_uri': text(format='uri-reference'), 'snapshot_text': nullable(text()), 'duration_ms': nullable(integer(1)), 'extraction_complete': BOOL, 'missing_sections': array(STR)}, description='original_uri is an opaque private object reference, never a public credential-bearing URL.')
define('SourceProcess', {'source_version_id': UUID, 'operations': array(enum('EXTRACT', 'TRANSCRIBE', 'PROBE', 'ALIGN'), minItems=1, uniqueItems=True), 'budget_cap': ref('Money')})
define('TranscriptSegment', {'segment_id': UUID, 'speaker_label': STR, 'start_ms': integer(), 'end_ms': integer(1), 'original_text': text(), 'presentation_text': text(), 'confidence': nullable({'type': 'number', 'minimum': 0, 'maximum': 1})}, description='end_ms > start_ms, within original media. Original speech is immutable; correction does not invent spoken words.')
define('TranscriptWrite', {'source_version_id': UUID, 'segments': array(ref('TranscriptSegment'), minItems=1), 'edit_reason': STR})
extend('TranscriptVersion', 'TranscriptWrite', {**VERSION, 'transcript_version_id': UUID, 'alignment_status': enum('ALIGNED', 'NEEDS_ALIGNMENT', 'MANUALLY_CONFIRMED')})
define('AlignmentRequest', {'transcript_version_id': UUID, 'method': enum('PROVIDER', 'MANUAL_CONFIRM'), 'segment_ids': ids(), 'reason': STR}, description='Manual confirmation requires reviewed source bounds; provider method reserves spend. Emits a new immutable transcript version.')

# Package: canonical v6 snapshot plus concrete claims/evidence.
define('CTA', {'text': STR, 'destination_url': nullable(URL)})
define('EvidenceItem', {**SCOPE, 'evidence_id': UUID, 'source_version_id': UUID, 'url': nullable(URL), 'title': STR, 'locator': STR, 'quote': STR, 'retrieved_at': DATE})
define('Claim', {**SCOPE, 'claim_id': UUID, 'text': STR, 'classification': enum('FACTUAL', 'QUOTATION', 'OPINION', 'PERSONAL_ANECDOTE'), 'verification': enum('UNREVIEWED', 'SUPPORTED', 'UNSUPPORTED', 'CONTRADICTED', 'EXPIRED'), 'severity': enum('LOW', 'HIGH'), 'evidence_ids': ids(), 'reviewer_evidence': nullable(STR), 'jurisdiction': nullable(STR)}, description='SUPPORTED factual/quotation requires evidence IDs or explicit reviewer evidence; server verifies retrievability. High-severity unsupported/contradicted blocks final approval.')
S['Claim']['allOf'] = [{'if': {'properties': {'classification': enum('FACTUAL', 'QUOTATION'), 'verification': {'const': 'SUPPORTED'}}, 'required': ['classification', 'verification']}, 'then': {'anyOf': [{'properties': {'evidence_ids': {'minItems': 1}}}, {'properties': {'reviewer_evidence': STR}}]}}]
define('ContentAtom', {'atom_id': UUID, 'package_version_id': UUID, 'type': enum('HOOK', 'THESIS', 'CLAIM', 'STORY', 'CTA', 'QUOTE'), 'text': STR, 'source_version_ids': ids(), 'evidence_ids': ids()})
define('PackageWrite', {'schema_version': {'const': 1}, 'campaign_id': UUID, 'title': STR, 'primary_thesis': STR, 'business_objective': STR, 'target_audience': STR, 'funnel_stage': enum('awareness', 'consideration', 'conversion', 'retention'), 'offer_id': nullable(UUID), 'primary_cta': ref('CTA'), 'master_narrative': STR, 'brand_profile_version_id': UUID, 'source_version_ids': ids(), 'claim_ids': ids(), 'atom_ids': ids(), 'jurisdiction_context': nullable(STR)}, description='Opinion-only source-free packages allowed. Legal assertions require jurisdiction and designated reviewer by brand policy.')
extend('PackageCreate', 'PackageWrite', {'brand_id': UUID})
extend('PackageVersion', 'PackageWrite', {**VERSION, 'package_id': UUID, 'version_id': UUID})
define('Package', {**SCOPE, 'package_id': UUID, 'current_version_id': UUID, 'approval_status': ref('ApprovalStatus'), 'freshness': ref('Freshness'), 'revision': integer(1)})
define('PackageDraftRequest', {'brand_id': UUID, 'campaign_id': UUID, 'topic': STR, 'source_version_ids': ids(), 'brand_profile_version_id': UUID, 'research_required': BOOL, 'budget_cap': ref('Money')})
define('CampaignWrite', {'brand_id': UUID, 'name': STR, 'objective': STR, 'audience': STR, 'offer': nullable(STR), 'cta': ref('CTA')})
extend('Campaign', 'CampaignWrite', {'workspace_id': UUID, 'campaign_id': UUID, 'state': enum('DRAFT', 'IN_PRODUCTION', 'WAITING_USER', 'PARTIAL_SUCCESS', 'READY_FOR_REVIEW', 'READY_TO_SCHEDULE', 'COMPLETE', 'CANCELLED', 'FAILED'), 'revision': integer(1)})

# Version-bound executable plans, estimates and separated checkpoints.
define('EstimateCategory', {'category': enum('LANGUAGE_MODEL', 'TRANSCRIPTION', 'AVATAR', 'LICENSED_GENERATED_MEDIA', 'ASSEMBLY', 'STORAGE_EGRESS', 'PUBLISHING_ANALYTICS', 'OTHER_VARIABLE'), 'units': integer(), 'unit_name': STR, 'low': ref('Money'), 'high': ref('Money'), 'price_snapshot_at': DATE})
define('Estimate', {'estimate_id': UUID, 'plan_version_id': UUID, 'categories': array(ref('EstimateCategory')), 'low': ref('Money'), 'high': ref('Money'), 'expires_at': DATE}, description='Exclusive categories; high >= low; all currencies identical. Price changes outside cap require new approval.')
define('OutputConstraints', {'max_duration_ms': nullable(integer(1)), 'target_word_count': nullable(integer(1)), 'width': nullable(integer(1)), 'height': nullable(integer(1)), 'caption_mode': enum('NONE', 'BURNED_IN', 'SIDECAR', 'BOTH')})
define('PlanItem', {'item_id': UUID, 'asset_type': ref('AssetType'), 'destinations': array(ref('Destination'), uniqueItems=True), 'recipe_version_id': UUID, 'prerequisite_item_ids': ids(), 'dependencies': array(ref('VersionBinding')), 'rationale': STR, 'selected': BOOL, 'estimated_low': ref('Money'), 'estimated_high': ref('Money'), 'constraints': ref('OutputConstraints')})
define('PlanWrite', {'package_version_id': UUID, 'items': array(ref('PlanItem'), minItems=1), 'budget_ceiling': ref('Money'), 'estimate_id': UUID})
extend('PlanVersion', 'PlanWrite', {**VERSION, 'plan_id': UUID, 'plan_version_id': UUID})
define('Plan', {**SCOPE, 'plan_id': UUID, 'current_version_id': UUID, 'approval_status': ref('ApprovalStatus'), 'revision': integer(1)})
define('PlanProposal', {'package_version_id': UUID, 'requested_asset_types': array(ref('AssetType'), minItems=1, uniqueItems=True), 'destinations': array(ref('Destination'), uniqueItems=True), 'budget_ceiling': ref('Money')})
define('EstimateRequest', {'plan_version_id': UUID})
define('ExecutePlan', {'plan_version_id': UUID, 'package_approval_decision_id': UUID, 'plan_approval_decision_id': UUID, 'estimate_id': UUID, 'budget_ceiling': ref('Money')}, description='Plan, package and estimate must match decisions. Before avatar spending separate exact SCRIPT approval is mandatory. No dereference of latest.')
SUBJECTS = {'Package': ('PACKAGE', 'package_id', 'version_id'), 'Plan': ('PLAN', 'plan_id', 'plan_version_id'), 'Asset': ('ASSET', 'asset_id', 'asset_version_id'), 'Script': ('SCRIPT', 'asset_id', 'asset_version_id'), 'Publication': ('PUBLICATION', 'publication_id', 'publication_revision_id'), 'VoiceSample': ('VOICE_SAMPLE', 'sample_id', 'sample_version_id'), 'ClipSelection': ('CLIP_SELECTION', 'selection_id', 'selection_version_id'), 'Rendition': ('RENDITION', 'rendition_id', 'rendition_id')}
for name, (kind, entity, version) in SUBJECTS.items():
    define(name + 'ApprovalSubject', {'subject_type': {'const': kind}, 'subject_id': UUID, 'subject_version_id': UUID}, description=f'subject_id is {entity}; subject_version_id is exact {version}. Must equal path and persisted immutable snapshot; never latest.')
    define(name + 'DecisionCreate', {'subject': ref(name + 'ApprovalSubject'), 'decision': enum('APPROVED', 'REJECTED'), 'reason': STR}, description='Writes immutable actor-stamped decision; does not execute production or external publication. All path IDs must match the subject. Designated review policy enforced.')
S['ApprovalSubject'] = {'oneOf': [ref(n + 'ApprovalSubject') for n in SUBJECTS], 'discriminator': {'propertyName': 'subject_type', 'mapping': {v[0]: '#/components/schemas/' + n + 'ApprovalSubject' for n, v in SUBJECTS.items()}}}
define('ApprovalDecision', {**VERSION, 'decision_id': UUID, 'subject': ref('ApprovalSubject'), 'decision': enum('APPROVED', 'REJECTED'), 'reason': STR, 'actor_user_id': UUID, 'decided_at': DATE}, description='Immutable history; invalidation is separate event/projection, not destructive mutation of approval decision.')
define('ReviewTaskCreate', {'subject': ref('ApprovalSubject'), 'reviewer_user_ids': ids(), 'message': STR})
extend('ReviewTask', 'ReviewTaskCreate', {**SCOPE, 'review_task_id': UUID, 'state': enum('PENDING', 'COMPLETED', 'CANCELLED'), 'created_at': DATE})
define('CommentAnchor', {'asset_version_id': nullable(UUID), 'scene_id': nullable(UUID), 'start_ms': nullable(integer()), 'end_ms': nullable(integer(1)), 'block_id': nullable(UUID)})
define('CommentCreate', {'subject': ref('ApprovalSubject'), 'anchor': ref('CommentAnchor'), 'text': STR})
extend('Comment', 'CommentCreate', {**SCOPE, 'comment_id': UUID, 'actor_user_id': UUID, 'resolved': BOOL, 'created_at': DATE})

# Universal assets have discriminated content, not an all-fields catch-all.
define('TextBlock', {'block_id': UUID, 'kind': enum('HEADING', 'PARAGRAPH', 'LIST_ITEM', 'QUOTE', 'CTA'), 'text': text(), 'claim_ids': ids(), 'locked': BOOL})
define('WrittenContent', {'content_kind': {'const': 'WRITTEN'}, 'format': enum('LINKEDIN_POST', 'ARTICLE', 'NEWSLETTER'), 'title': STR, 'subject': nullable(STR), 'preheader': nullable(STR), 'blocks': array(ref('TextBlock'), minItems=1), 'cta': ref('CTA')})
define('ScriptContent', {'content_kind': {'const': 'SCRIPT'}, 'narration': STR, 'scene_version_ids': ids(), 'avatar_profile_version_id': nullable(UUID), 'voice_profile_version_id': nullable(UUID), 'consent_version_ids': ids()})
define('VideoContent', {'content_kind': {'const': 'VIDEO'}, 'route': enum('PRESERVE_AND_DERIVE', 'ADD_CAPTIONS', 'EDIT', 'AVATAR'), 'source_version_id': nullable(UUID), 'script_asset_version_id': nullable(UUID), 'timeline_version_id': nullable(UUID)})
define('CaptionCue', {'cue_id': UUID, 'start_ms': integer(), 'end_ms': integer(1), 'text': STR})
define('CaptionContent', {'content_kind': {'const': 'CAPTIONS'}, 'language': STR, 'cues': array(ref('CaptionCue')), 'style_version_id': UUID})
define('ImageContent', {'content_kind': {'const': 'IMAGE'}, 'media_version_id': UUID, 'alt_text': STR, 'template_version_id': nullable(UUID)})
S['AssetContent'] = {'oneOf': [ref(n) for n in ['WrittenContent', 'ScriptContent', 'VideoContent', 'CaptionContent', 'ImageContent']], 'discriminator': {'propertyName': 'content_kind'}}
define('AssetWrite', {'asset_type': ref('AssetType'), 'title': STR, 'package_version_id': UUID, 'plan_version_id': nullable(UUID), 'dependencies': array(ref('VersionBinding')), 'content': ref('AssetContent'), 'edit_reason': STR})
S['AssetWrite']['allOf'] = []
for kinds, content in [(['MAIN_VIDEO', 'CLIP'], 'VideoContent'), (['LINKEDIN_POST', 'ARTICLE', 'NEWSLETTER'], 'WrittenContent'), (['SCRIPT'], 'ScriptContent'), (['CAPTIONS'], 'CaptionContent'), (['THUMBNAIL'], 'ImageContent')]:
    S['AssetWrite']['allOf'].append({'if': {'properties': {'asset_type': enum(*kinds)}, 'required': ['asset_type']}, 'then': {'properties': {'content': ref(content)}}})
for written_type in ['LINKEDIN_POST', 'ARTICLE', 'NEWSLETTER']:
    S['AssetWrite']['allOf'].append({'if': {'properties': {'asset_type': {'const': written_type}}, 'required': ['asset_type']}, 'then': {'properties': {'content': {'properties': {'format': {'const': written_type}}}}}})
extend('AssetVersion', 'AssetWrite', {**VERSION, 'asset_id': UUID, 'asset_version_id': UUID})
S['AssetVersion']['allOf'] = copy.deepcopy(S['AssetWrite']['allOf'])
define('Asset', {**SCOPE, 'asset_id': UUID, 'current_version_id': UUID, 'asset_type': ref('AssetType'), 'production_status': ref('ProductionStatus'), 'approval_status': ref('ApprovalStatus'), 'rights_status': ref('RightsStatus'), 'freshness': ref('Freshness'), 'revision': integer(1)})
define('RegenerateRequest', {'base_asset_version_id': UUID, 'component_ids': ids(), 'instruction': STR, 'preserve_locked': {'const': True}, 'approved_plan_version_id': UUID, 'budget_cap': ref('Money')}, description='Only selected components; preserves unrelated successful assets/locked scenes. Returns new draft version, never silently overwrites approved version.')
define('RenditionRequest', {'asset_version_id': UUID, 'timeline_version_id': nullable(UUID), 'destination_profile_version_id': UUID, 'render_preset_version_id': UUID, 'caption_mode': enum('NONE', 'BURNED_IN', 'SIDECAR', 'BOTH'), 'budget_cap': ref('Money')})
define('Rendition', {**SCOPE, 'rendition_id': UUID, 'asset_version_id': UUID, 'destination_profile_version_id': UUID, 'sha256': HASH, 'private_object_uri': text(format='uri-reference'), 'duration_ms': nullable(integer(1)), 'width': nullable(integer(1)), 'height': nullable(integer(1)), 'size_bytes': integer(1), 'validation': enum('PENDING', 'PASSED', 'FAILED'), 'created_at': DATE})
define('ExportRequest', {'asset_version_ids': ids(), 'formats': array(enum('MP4', 'SRT', 'VTT', 'MARKDOWN', 'SANITIZED_HTML', 'TEXT', 'ARCHIVE'), minItems=1), 'include_manifest': {'const': True}})
define('Export', {'export_id': UUID, 'workspace_id': UUID, 'brand_id': nullable(UUID), 'state': enum('QUEUED', 'PREPARING', 'READY', 'EXPIRED', 'FAILED'), 'asset_version_ids': ids(), 'expires_at': nullable(DATE), 'job_id': UUID})
define('DownloadAccess', {'download_url': URL, 'expires_at': DATE, 'sha256': HASH}, description='Private access default 10 minutes; archive retention seven days. Rechecks grants; download never marks publication live.')

# Editing time is integer ms; frame-rate rational explicit.
define('FocalPoint', {'x': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'y': {'type': 'number', 'minimum': 0, 'maximum': 1}})
define('Shot', {'id': UUID, 'media_version_id': UUID, 'start_ms': integer(), 'duration_ms': integer(1), 'source_in_ms': integer(), 'fit': enum('cover', 'contain'), 'focal_point': ref('FocalPoint'), 'gain_db': {'type': 'number'}})
define('Track', {'id': STR, 'kind': enum('video', 'audio', 'image'), 'z_index': {'type': 'integer'}, 'shots': array(ref('Shot'))})
define('Canvas', {'width': integer(1, maximum=1920), 'height': integer(1, maximum=1920), 'fps_num': integer(1), 'fps_den': integer(1)})
define('TimelineWrite', {'schema_version': {'const': 1}, 'base_asset_version_id': UUID, 'duration_ms': integer(1), 'canvas': ref('Canvas'), 'tracks': array(ref('Track'), minItems=1), 'caption_track_version_id': nullable(UUID), 'brand_template_version_id': UUID, 'render_preset_version_id': UUID}, description='Shot intervals must fit timeline and actual decoded source duration; unique track/shot IDs; frame rounding deterministic. 1080p delivery constraints enforced by destination profile.')
extend('TimelineVersion', 'TimelineWrite', {**VERSION, 'timeline_version_id': UUID, 'asset_version_id': UUID})
S['TimelineWrite']['description'] += ' base_asset_version_id is the existing exact asset version for the path asset. Under If-Match the server atomically creates a fresh timeline, fresh output asset version pinning it, immutable video_asset_binding, current-pointer update and invalidations; failure rolls back all. Never mutates the base.'
S['TimelineVersion']['description'] = 'asset_version_id is the fresh output binding, not an input. It differs from base_asset_version_id and is excluded from timeline content/dependency hash and prerequisite edges to prevent a timeline/output cycle. Output asset depends on timeline; timeline may depend on base/actual inputs only.'
S['TimelineVersion']['properties']['asset_version_id'] = dict(UUID, readOnly=True)
S['TimelineVersion']['x-hash-excluded-fields'] = ['asset_version_id']
S['TimelineVersion']['x-output-binding'] = {'table': 'video_asset_bindings', 'direction': 'asset -> timeline', 'fresh_output_required': True}
define('SceneWrite', {'asset_version_id': UUID, 'base_scene_version_id': nullable(UUID), 'order': integer(), 'narration': text(), 'visual_direction': text(), 'source_version_id': nullable(UUID), 'source_in_ms': nullable(integer()), 'source_out_ms': nullable(integer(1)), 'media_version_ids': ids(), 'locked': BOOL})
extend('SceneVersion', 'SceneWrite', {**VERSION, 'scene_id': UUID, 'scene_version_id': UUID})
define('PreviewRequest', {'timeline_version_id': UUID, 'start_ms': integer(), 'duration_ms': integer(1), 'budget_cap': ref('Money')})
define('ClipCandidatesRequest', {'final_cut_asset_version_id': UUID, 'final_cut_rendition_id': UUID, 'package_version_id': UUID, 'transcript_version_id': UUID, 'desired_moments': integer(3, maximum=5), 'budget_cap': ref('Money')})
define('ClipCandidate', {'candidate_id': UUID, 'final_cut_asset_version_id': UUID, 'final_cut_rendition_id': UUID, 'package_version_id': UUID, 'transcript_version_id': UUID, 'source_in_ms': integer(), 'source_out_ms': integer(1), 'rationale': STR})
define('Crop', {'fit': enum('cover', 'contain'), 'focal_point': ref('FocalPoint'), 'destination_profile_version_id': UUID})
define('ClipMoment', {'moment_id': UUID, 'candidate_id': UUID, 'source_in_ms': integer(), 'source_out_ms': integer(1), 'crop': ref('Crop'), 'destinations': array(ref('Destination'), minItems=1, uniqueItems=True)})
define('ClipSelectionWrite', {'final_cut_asset_version_id': UUID, 'final_cut_rendition_id': UUID, 'package_version_id': UUID, 'transcript_version_id': UUID, 'moments': array(ref('ClipMoment'), minItems=1, maxItems=5), 'shortfall_accepted': BOOL, 'shortfall_reason': nullable(STR)}, description='Requires approved final cut and package, aligned transcript, valid meaningful bounds. Below 3 moments needs explicit user acceptance and reason; never invent candidates.')
S['ClipSelectionWrite']['allOf'] = [{'if': {'properties': {'moments': {'maxItems': 2}}}, 'then': {'properties': {'shortfall_accepted': {'const': True}, 'shortfall_reason': STR}}}]
extend('ClipSelectionVersion', 'ClipSelectionWrite', {**VERSION, 'selection_id': UUID, 'selection_version_id': UUID})
S['ClipSelectionVersion']['allOf'] = copy.deepcopy(S['ClipSelectionWrite']['allOf'])

# Jobs expose durable state and explicit operator reconciliation, not simulated outputs.
define('Job', {**SCOPE, 'job_id': UUID, 'job_type': enum('INGEST', 'TRANSCRIBE', 'ALIGN', 'DRAFT_PACKAGE', 'PROPOSE_PLAN', 'ESTIMATE', 'GENERATE', 'REGENERATE', 'RENDER', 'PREVIEW', 'CLIP_CANDIDATES', 'EXPORT', 'PUBLISH', 'TAKEDOWN', 'METRICS', 'VALIDATE_CONNECTION', 'WORKSPACE_EXPORT', 'WORKSPACE_DELETE'), 'state': ref('JobState'), 'logical_operation_id': UUID, 'inputs': array(ref('VersionBinding')), 'provider_mode': enum('LIVE', 'DEVELOPMENT_SIMULATED'), 'budget_cap': ref('Money'), 'known_actual_cost': ref('Money'), 'unsettled_cost': ref('Money'), 'error': nullable(ref('Error')), 'created_at': DATE, 'updated_at': DATE, 'revision': integer(1), 'result_version_ids': ids(), 'result_resource_urls': array(text(format='uri-reference'))})
define('JobStep', {**SCOPE, 'job_id': UUID, 'step_id': UUID, 'name': STR, 'state': ref('JobState'), 'input_sha256': HASH, 'logical_operation_id': UUID, 'submission_attempt_count': integer(0, maximum=3), 'next_attempt_at': nullable(DATE), 'lease_owner': nullable(STR), 'lease_expires_at': nullable(DATE), 'heartbeat_at': nullable(DATE), 'fencing_token': integer(), 'provider_request_id': nullable(STR), 'output_version_ids': ids(), 'error': nullable(ref('Error')), 'estimated_cost': ref('Money'), 'actual_cost': nullable(ref('Money'))})
define('ProviderAttempt', {**SCOPE, 'attempt_id': UUID, 'step_id': UUID, 'logical_operation_id': UUID, 'provider': STR, 'request_id': nullable(STR), 'attempt_number': integer(1, maximum=3), 'submitted_at': DATE, 'outcome': enum('PENDING', 'ACCEPTED', 'NOT_ACCEPTED', 'UNKNOWN', 'SUCCEEDED', 'FAILED'), 'safe_to_retry': BOOL, 'reconciliation_evidence': nullable(STR), 'cost': nullable(ref('Money'))})
define('JobRetry', {'failed_step_ids': ids(), 'reason': STR}, description='Only FAILED_RETRYABLE confirmed-safe submissions; <=3 total, remaining cap required. UNKNOWN must reconcile, not retry.')
define('OperatorResolution', {'attempt_id': UUID, 'established_outcome': enum('ACCEPTED_PENDING', 'SUCCEEDED', 'PROVEN_NOT_ACCEPTED', 'FAILED_FINAL', 'STILL_UNKNOWN'), 'provider_request_id': nullable(STR), 'evidence_reference': STR, 'reason': STR, 'actual_cost': nullable(ref('Money'))}, description='Requires explicit operator entitlement plus same-tenant admin role. STILL_UNKNOWN retains reservation and RECONCILING; cannot assert no charge/refund without provider evidence.')

# W-scoped storage with explicit branded/workspace context, not fake administrative brands.
S['Job']['properties']['job_type']['enum'].append('VOICE_SAMPLE')
JOB_CONTEXT = {'scope_type': enum('BRAND', 'WORKSPACE'), 'brand_id': nullable(UUID), 'campaign_id': nullable(UUID), 'job_type': copy.deepcopy(S['Job']['properties']['job_type']), 'purpose': enum('PREPRODUCTION', 'PRODUCTION', 'ADMIN', 'PUBLICATION'), 'originating_operation_id': STR}
JOB_SCOPE_CONSTRAINTS = [
    {'if': {'properties': {'scope_type': {'const': 'WORKSPACE'}}}, 'then': {'properties': {'brand_id': {'type': 'null'}, 'campaign_id': {'type': 'null'}, 'purpose': {'const': 'ADMIN'}, 'job_type': enum('WORKSPACE_EXPORT', 'WORKSPACE_DELETE')}}, 'else': {'properties': {'brand_id': UUID, 'job_type': {'not': enum('WORKSPACE_EXPORT', 'WORKSPACE_DELETE')}}}},
    {'if': {'properties': {'job_type': {'const': 'WORKSPACE_EXPORT'}}}, 'then': {'properties': {'originating_operation_id': {'const': 'requestWorkspaceExport'}}}},
    {'if': {'properties': {'job_type': {'const': 'WORKSPACE_DELETE'}}}, 'then': {'properties': {'originating_operation_id': {'const': 'requestWorkspaceDeletion'}}}}]
for job_schema in ['Job', 'JobStep', 'ProviderAttempt']:
    for field, schema in JOB_CONTEXT.items():
        S[job_schema]['properties'][field] = copy.deepcopy(schema)
        if field not in S[job_schema]['required']: S[job_schema]['required'].append(field)
    S[job_schema]['allOf'] = copy.deepcopy(JOB_SCOPE_CONSTRAINTS)
    S[job_schema]['description'] = 'Workspace-owned (W) execution record with explicit scope_type. WORKSPACE requires ADMIN purpose and only workspace export/delete with null brand/campaign; BRAND requires a real granted brand. Child context must equal originating job via composite constraints, not caller-supplied authority. Owner-only operations remain owner-only; no synthetic brand or all-brand grant.'
S['ProviderAttempt']['properties']['job_id'] = UUID
S['ProviderAttempt']['required'].append('job_id')
for field, schema in {'actor_user_id': UUID, 'work_authorization_id': UUID, 'preproduction_authorization_id': nullable(UUID), 'approved_plan_version_id': nullable(UUID), 'plan_approval_decision_id': nullable(UUID)}.items():
    S['Job']['properties'][field] = schema
    S['Job']['required'].append(field)
S['Job']['allOf'] += [
    {'if': {'properties': {'purpose': {'const': 'PREPRODUCTION'}}}, 'then': {'properties': {'scope_type': {'const': 'BRAND'}, 'preproduction_authorization_id': UUID, 'approved_plan_version_id': {'type': 'null'}, 'plan_approval_decision_id': {'type': 'null'}}}, 'else': {'properties': {'preproduction_authorization_id': {'type': 'null'}}}},
    {'if': {'properties': {'purpose': {'const': 'PRODUCTION'}}}, 'then': {'properties': {'scope_type': {'const': 'BRAND'}, 'campaign_id': UUID, 'approved_plan_version_id': UUID, 'plan_approval_decision_id': UUID}}}]
S['Job']['allOf'].append({'if': {'properties': {'purpose': enum('ADMIN', 'PUBLICATION')}}, 'then': {'properties': {'approved_plan_version_id': {'type': 'null'}, 'plan_approval_decision_id': {'type': 'null'}}}})
S['Job']['description'] += ' PREPRODUCTION binds immutable authorization actor/operation/input/cap before every paid step; PRODUCTION requires exact approved plan and decision. PUBLICATION additionally requires exact publication approval; ADMIN never authorizes production. Authorization ID cannot be swapped on retry. work_authorization_id binds originating actor, purpose, exact operation and inputs. ADMIN/PUBLICATION paid work requires this separate immutable work authorization and configured workspace/job/campaign-if-present caps, never a fabricated plan. Pure unpaid work cannot dispatch paid steps.'

# Social connections: no tokens in returned schemas.
define('OAuthStart', {'brand_id': UUID, 'destination': ref('Destination'), 'return_path': text(pattern='^/(?!/)[^\\\\]*$')}, description='Server stores random single-use state binding user/workspace/brand/destination and PKCE where supported; no caller-selected account substitution.')
define('Connection', {**SCOPE, 'connection_id': UUID, 'destination': ref('Destination'), 'remote_account_id': STR, 'remote_account_label': STR, 'account_type': STR, 'state': enum('CONNECTED', 'EXPIRED', 'REVOKED', 'BLOCKED'), 'granted_scopes': array(STR), 'capability_version_id': UUID, 'expires_at': nullable(DATE), 'revision': integer(1)})
define('Capability', {'capability_version_id': UUID, 'destination': ref('Destination'), 'account_type': STR, 'verified_at': DATE, 'required_scopes': array(STR), 'app_access': enum('APPROVED', 'PENDING', 'DENIED', 'UNVERIFIED'), 'can_publish': BOOL, 'can_schedule_remotely': BOOL, 'can_delete': BOOL, 'can_unpublish': BOOL, 'native_metric_names': array(STR), 'destination_profile_version_ids': ids(), 'limitations': array(STR)})
define('DestinationProfile', {'profile_version_id': UUID, 'destination': ref('Destination'), 'verified_at': DATE, 'official_documentation_url': URL, 'max_duration_ms': nullable(integer(1)), 'max_size_bytes': nullable(integer(1)), 'mime_types': array(STR), 'required_width': nullable(integer(1)), 'required_height': nullable(integer(1)), 'caption_rules': STR, 'safe_zone_rules': STR}, description='Provider-verified versioned limits, not universal hard-coded media assumptions.')

# Publication intent pins all changing publication inputs in one immutable revision.
define('PublicationMetadata', {'title': text(), 'description': text(), 'caption': text(), 'visibility': enum('PUBLIC', 'UNLISTED', 'PRIVATE'), 'thumbnail_rendition_id': nullable(UUID), 'language': STR})
define('Schedule', {'requested_local_time': text(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$'), 'timezone': STR, 'resolved_utc': DATE}, description='IANA zone; server verifies exact UTC mapping and rejects ambiguous/nonexistent local times with DST_AMBIGUOUS/DST_NONEXISTENT. Late >15 min pauses.')
define('TrackingTags', {'utm_source': nullable(STR), 'utm_medium': nullable(STR), 'utm_campaign': nullable(STR), 'utm_content': nullable(STR), 'cta_id': nullable(UUID)})
define('PublicationIntentWrite', {'brand_id': UUID, 'logical_publication_id': UUID, 'asset_version_id': UUID, 'rendition_id': nullable(UUID), 'destination': ref('Destination'), 'connection_id': UUID, 'destination_profile_version_id': UUID, 'metadata': ref('PublicationMetadata'), 'schedule': ref('Schedule'), 'tracking_tags': ref('TrackingTags'), 'asset_approval_decision_id': UUID}, description='New intent requires explicit logical ID, unique workspace-wide. Revisions preserve logical ID. Video needs validated rendition; LinkedIn text can omit it. Reposts require new intent. Metadata/account/schedule changes reset approval.')
S['PublicationIntentWrite']['allOf'] = [{'if': {'properties': {'destination': {'not': {'const': 'LINKEDIN_TEXT'}}}, 'required': ['destination']}, 'then': {'properties': {'rendition_id': UUID}}}]
S['PublicationIntentWrite']['properties']['rendition_approval_decision_id'] = nullable(UUID)
S['PublicationIntentWrite']['required'].append('rendition_approval_decision_id')
S['PublicationIntentWrite']['allOf'].append({'if': {'properties': {'rendition_id': {'type': 'null'}}}, 'then': {'properties': {'rendition_approval_decision_id': {'type': 'null'}}}, 'else': {'properties': {'rendition_approval_decision_id': UUID}}})
S['PublicationIntentWrite']['description'] += ' Any rendition requires its exact RENDITION/final_media decision, with matching rendition and asset ownership; dispatch rechecks it independently of final editorial and publication approvals.'
extend('PublicationIntent', 'PublicationIntentWrite', {'workspace_id': UUID, 'publication_id': UUID, 'publication_revision_id': UUID, 'schedule_revision': integer(1), 'publication_approval_decision_id': nullable(UUID), 'state': ref('PublicationState'), 'freshness': ref('Freshness'), 'rights_status': ref('RightsStatus'), 'created_at': DATE, 'created_by': UUID, 'revision': integer(1)})
S['PublicationIntent']['allOf'] = copy.deepcopy(S['PublicationIntentWrite']['allOf'])
define('PublicationSchedule', {'publication_revision_id': UUID, 'approval_decision_id': UUID}, description='Approval subject must be this exact publication revision. At dispatch recheck memberships, grants, account, version approval, freshness, media, rights, consent and caps.')
define('PublicationStatus', {**SCOPE, 'publication_id': UUID, 'publication_revision_id': UUID, 'state': ref('PublicationState'), 'remote_id': nullable(STR), 'remote_url': nullable(URL), 'verified_visibility': nullable(enum('PUBLIC', 'UNLISTED', 'PRIVATE')), 'verified_live_at': nullable(DATE), 'error': nullable(ref('Error')), 'revision': integer(1)}, description='Remote ID alone is not PUBLISHED. Remote verification and requested visibility must match.')
S['PublicationStatus']['allOf'] = [{'if': {'properties': {'state': {'const': 'PUBLISHED'}}}, 'then': {'properties': {'remote_id': STR, 'verified_visibility': enum('PUBLIC', 'UNLISTED', 'PRIVATE'), 'verified_live_at': DATE}}}]
define('PublicationAttempt', {**SCOPE, 'attempt_id': UUID, 'publication_id': UUID, 'publication_revision_id': UUID, 'logical_publication_id': UUID, 'provider_attempt_id': UUID, 'state': ref('PublicationState'), 'remote_id': nullable(STR), 'submitted_at': DATE})
define('TakedownRequest', {'publication_revision_id': UUID, 'reason': STR, 'confirmation': {'const': 'REQUEST_TAKEDOWN'}}, description='Authorized request only; adapter reports unsupported capability. Does not claim remote deletion occurred.')

# Native analytics, immutable usage and administrative operations.
define('MetricSnapshot', {**SCOPE, 'snapshot_id': UUID, 'publication_id': UUID, 'provider': STR, 'native_metric_name': STR, 'definition': STR, 'definition_version': STR, 'window_start': DATE, 'window_end': DATE, 'retrieved_at': DATE, 'measurement_kind': enum('CUMULATIVE', 'INTERVAL'), 'availability': enum('AVAILABLE', 'UNAVAILABLE', 'NOT_PERMITTED'), 'value': nullable({'type': 'number'})}, description='Unavailable is null, not zero. Never sum cumulative snapshots as interval activity.')
S['MetricSnapshot']['allOf'] = [{'if': {'properties': {'availability': enum('UNAVAILABLE', 'NOT_PERMITTED')}}, 'then': {'properties': {'value': {'type': 'null'}}}}]
define('ConversionCreate', {'brand_id': UUID, 'external_event_id': STR, 'source': STR, 'type': enum('LEAD', 'APPOINTMENT', 'PURCHASE', 'OTHER'), 'occurred_at': DATE, 'campaign_id': nullable(UUID), 'publication_id': nullable(UUID), 'cta_id': nullable(UUID), 'pseudonymous_reference': nullable(STR), 'value': nullable(ref('Money'))}, description='Unique workspace + source + external_event_id. Verify all tenant references. Keep occurrence separate from ingestion; no personal data required.')
extend('Conversion', 'ConversionCreate', {'workspace_id': UUID, 'conversion_id': UUID, 'ingested_at': DATE, 'deduplicated': BOOL})
USAGE_COMMON = {'entry_id': UUID, 'workspace_id': UUID, 'brand_id': nullable(UUID), 'campaign_id': nullable(UUID), 'job_id': nullable(UUID), 'logical_operation_id': UUID, 'reservation_id': nullable(UUID), 'kind': enum('SETTLEMENT', 'ADJUSTMENT'), 'provider_mode': enum('LIVE', 'DEVELOPMENT_SIMULATED'), 'occurred_at': DATE}
define('ProviderCostUsageEntry', {**USAGE_COMMON, 'ledger': {'const': 'PROVIDER_COST'}, 'amount': ref('SignedMoney'), 'units': integer(), 'unit_name': STR}, description='Signed currency micro-units for actual provider cost; corrections are immutable signed adjustments. Simulated work never settles as live spend.')
define('CustomerCreditsUsageEntry', {**USAGE_COMMON, 'ledger': {'const': 'CUSTOMER_CREDITS'}, 'credits': {'type': 'integer'}}, description='Signed integer customer credits; not money. No amount, amount_micros, currency or fabricated currency code. Database currency is NULL; unit is credits.')
S['UsageEntry'] = {'oneOf': [ref('ProviderCostUsageEntry'), ref('CustomerCreditsUsageEntry')], 'discriminator': {'propertyName': 'ledger', 'mapping': {'PROVIDER_COST': '#/components/schemas/ProviderCostUsageEntry', 'CUSTOMER_CREDITS': '#/components/schemas/CustomerCreditsUsageEntry'}}, 'description': 'Immutable discriminated ledger entries. Provider cost uses signed money; customer credits use signed integer credits, never fabricated currency. Event mirrors use this exact union.'}
define('Reservation', {'reservation_id': UUID, 'workspace_id': UUID, 'brand_id': nullable(UUID), 'campaign_id': nullable(UUID), 'job_id': UUID, 'logical_operation_id': UUID, 'state': enum('RESERVED', 'SETTLED', 'RELEASED'), 'amount': ref('Money'), 'created_at': DATE, 'resolved_at': nullable(DATE)})
define('BudgetWrite', {'workspace_cap': ref('Money'), 'campaign_cap': ref('Money'), 'job_cap': ref('Money'), 'warning_threshold_percent': integer(1, maximum=100, default=80)}, description='Unconfigured live caps zero. Atomic reserve across all applicable caps, 100% hard block; owner/admin authorization does not invent funds.')
extend('Budget', 'BudgetWrite', {'workspace_id': UUID, 'revision': integer(1)})
define('EntitlementWrite', {'max_users': integer(1, default=10), 'max_brands': integer(1, default=5), 'max_storage_bytes': integer(default=100000000000), 'max_concurrent_paid_jobs': integer(default=2)})
extend('Entitlement', 'EntitlementWrite', {'workspace_id': UUID, 'revision': integer(1)})
define('WorkspaceExportRequest', {'include_originals': BOOL, 'include_approved_outputs': BOOL, 'include_audit': BOOL})
define('WorkspaceDeleteRequest', {'confirmation': {'const': 'DELETE_WORKSPACE'}, 'reauthentication_token': STR, 'reason': STR})
define('DeletionStatus', {'workspace_id': UUID, 'deletion_id': UUID, 'tombstoned_at': DATE, 'state': enum('STOPPING_WORK', 'PURGING', 'WAITING_BACKUP_EXPIRY', 'COMPLETE', 'BLOCKED'), 'active_store_purge_target': DATE, 'backup_expiry_target': DATE, 'provider_exceptions': array(STR), 'retained_audit_usage_until': DATE}, description='Tombstone immediately stops jobs/dispatch. Default active purge 7 days, backups 35 days; disclose exceptions and retained financial/audit records.')
define('AuditEntry', {'audit_id': UUID, 'workspace_id': UUID, 'brand_id': nullable(UUID), 'actor_id': UUID, 'actor_kind': enum('USER', 'SCOPED_CREDENTIAL', 'WORKER', 'PROVIDER'), 'action': STR, 'entity_type': STR, 'entity_id': UUID, 'before_version_id': nullable(UUID), 'after_version_id': nullable(UUID), 'correlation_id': UUID, 'occurred_at': DATE}, description='Metadata only; no tokens, signed URLs, raw secrets or source bodies.')
define('Notification', {'notification_id': UUID, 'workspace_id': UUID, 'brand_id': nullable(UUID), 'recipient_user_id': UUID, 'type': enum('REVIEW_REQUESTED', 'JOB_FAILED', 'CONNECTION_EXPIRING', 'BUDGET_BLOCKED', 'SCHEDULE_LATE'), 'message': STR, 'resource_url': text(format='uri-reference'), 'created_at': DATE, 'read_at': nullable(DATE)})

# Cross-contract M0 freeze: registry/review targets are persistence identities, not aliases.
REVIEW_TARGETS = {
    'Package': ('package', 'editorial', 'content_package_versions'),
    'Plan': ('plan', 'production_budget', 'asset_plan_versions'),
    'Asset': ('asset', 'final_editorial', 'asset_versions'),
    'Script': ('asset', 'narration', 'asset_versions'),
    'Publication': ('publication_revision', 'publication', 'publication_revisions'),
    'VoiceSample': ('voice_sample', 'brand_voice', 'voice_sample_versions'),
    'ClipSelection': ('clip_selection', 'clip_selection', 'clip_selection_versions'),
    'Rendition': ('rendition', 'final_media', 'renditions')}
for subject_name, (registry_kind, review_scope, table) in REVIEW_TARGETS.items():
    subject = S[subject_name + 'ApprovalSubject']
    subject['x-registry-kind'] = registry_kind
    subject['x-review-scope'] = review_scope
    subject['x-version-table'] = table
    subject['description'] += f' Resolves only to {registry_kind}/{review_scope} in {table}; service enforces exact subject hash and tenant.'
S['ScriptApprovalSubject']['description'] += ' Requires asset_type SCRIPT and immutable script_versions detail with id = asset_version_id; no independent script registry row.'
S['RenditionApprovalSubject']['properties']['scope'] = {'const': 'final_media'}
S['RenditionApprovalSubject']['required'].append('scope')
S['RenditionApprovalSubject']['description'] += ' Rendition is itself an immutable version: subject_id and subject_version_id both equal path rendition_id.'
define('ScriptVersionDetail', {**VERSION, 'asset_version_id': UUID, 'content': ref('ScriptContent')}, description='Immutable script_versions detail extension of asset_versions, sharing the same primary ID. Requires asset_type SCRIPT; content matches parent snapshot at seal. Registry kind asset only; approvals target asset_version_id.')
S['ScriptVersionDetail']['x-version-table'] = 'script_versions'
S['ScriptVersionDetail']['x-registry-kind'] = 'asset'
S['ScriptVersionDetail']['x-shared-primary-key'] = 'asset_versions.id'
define('VoiceSampleVersion', {**VERSION, 'sample_id': UUID, 'sample_version_id': UUID, 'profile_version_id': UUID, 'paragraph': STR, 'script': STR}, description='Sealed immutable voice_sample_versions snapshot, registry kind voice_sample. Approval status is a separate projection on VoiceSample.')
S['VoiceSampleVersion']['x-version-table'] = 'voice_sample_versions'
S['VoiceSampleVersion']['x-registry-kind'] = 'voice_sample'
S['ClipSelectionVersion']['x-version-table'] = 'clip_selection_versions'
S['ClipSelectionVersion']['x-registry-kind'] = 'clip_selection'

# Paid pre-plan work uses a separate immutable, narrowly bound authorization.
PREPRODUCTION_OPERATIONS = {
    'previewBrandVoice': 'VoicePreviewRequest',
    'createSourceFromURL': 'SourceURLCreate',
    'processSource': 'SourceProcess',
    'alignTranscript': 'AlignmentRequest',
    'draftPackage': 'PackageDraftRequest',
    'proposePlan': 'PlanProposal'}
PRODUCTION_OPERATIONS = ['executePlan', 'regenerateComponents', 'requestRendition', 'previewTimeline', 'generateClipCandidates']
JOB_PURPOSE_CONSTRAINTS = [
    {'if': {'properties': {'originating_operation_id': enum(*PREPRODUCTION_OPERATIONS)}}, 'then': {'properties': {'purpose': {'const': 'PREPRODUCTION'}}}},
    {'if': {'properties': {'originating_operation_id': enum(*PRODUCTION_OPERATIONS)}}, 'then': {'properties': {'purpose': {'const': 'PRODUCTION'}}}},
    {'if': {'properties': {'job_type': enum('GENERATE', 'REGENERATE', 'RENDER', 'PREVIEW', 'CLIP_CANDIDATES')}}, 'then': {'properties': {'purpose': {'const': 'PRODUCTION'}}}},
    {'if': {'properties': {'purpose': {'const': 'PREPRODUCTION'}}}, 'then': {'properties': {'originating_operation_id': enum(*PREPRODUCTION_OPERATIONS), 'preproduction_authorization_id': UUID}}, 'else': {'properties': {'preproduction_authorization_id': {'type': 'null'}}}}]
for job_schema in ['Job', 'JobStep', 'ProviderAttempt']:
    S[job_schema]['properties']['preproduction_authorization_id'] = nullable(UUID)
    if 'preproduction_authorization_id' not in S[job_schema]['required']: S[job_schema]['required'].append('preproduction_authorization_id')
    S[job_schema]['allOf'] += copy.deepcopy(JOB_PURPOSE_CONSTRAINTS)
    S[job_schema]['description'] += ' Every billable PREPRODUCTION step/attempt stores the same immutable preproduction_authorization_id as its job and cannot change purpose to evade plan/authorization gates.'
PREPRODUCTION_BINDING = 'SHA-256 of canonical operation ID, workspace/brand, actor, campaign when present, exact input versions/hashes and full normalized operation request excluding only preproduction_authorization_id. Includes logical_operation_id, supplied budget limits and relevant If-Match; never latest. Research and schema-repair substeps are covered only when described in the bound request and share the same cumulative cap.'
define('PreproductionAuthorizationCreate', {'brand_id': UUID, 'actor_user_id': UUID, 'campaign_id': nullable(UUID), 'job_id': nullable(UUID), 'logical_operation_id': UUID, 'operation_id': enum(*PREPRODUCTION_OPERATIONS), 'input_sha256': HASH, 'inputs': array(ref('VersionBinding')), 'cap': ref('Money'), 'expires_at': DATE, 'reason': STR}, description='Owner/admin with explicit brand grant creates under current budget policy. Not a production-plan approval. Cap, operation, actor, scope, exact inputs and expiry are immutable; changes require a new authorization. Unconfigured allowance is zero. job_id is nullable before job allocation; if present must equal consuming job. Unique logical operation prevents reuse across new jobs; retry resumes that operation only. ' + PREPRODUCTION_BINDING)
extend('PreproductionAuthorization', 'PreproductionAuthorizationCreate', {'workspace_id': UUID, 'preproduction_authorization_id': UUID, 'created_by': UUID, 'created_at': DATE, 'budget_policy_revision': integer(1)})
S['PreproductionAuthorization']['x-immutable'] = True
S['PreproductionAuthorization']['x-default-live-cap-micros'] = 0
S['PreproductionAuthorization']['x-version-table'] = 'preproduction_authorizations'
for request_name in PREPRODUCTION_OPERATIONS.values():
    request = S[request_name]
    for field, schema in {'preproduction_authorization_id': UUID, 'logical_operation_id': UUID, 'campaign_id': nullable(UUID)}.items():
        if field not in request['properties']:
            request['properties'][field] = copy.deepcopy(schema)
            request['required'].append(field)
    request['description'] = request.get('description', '') + ' Every billable pre-plan step must reference this authorization; match actor, operation, logical operation, scope, expiry, exact input hash and versions. Atomic reservation checks workspace/job/campaign where present plus immutable authorization cap. Missing/mismatch/expired authorization fails closed; no implied production approval. ' + PREPRODUCTION_BINDING
# Owner/admin reviews the actual typed operation input, not an unexplained hash.
PREPRODUCTION_INPUTS = {}
for operation_id, request_name in PREPRODUCTION_OPERATIONS.items():
    input_name = 'Preproduction' + request_name + 'Input'
    S[input_name] = copy.deepcopy(S[request_name])
    del S[input_name]['properties']['preproduction_authorization_id']
    S[input_name]['required'].remove('preproduction_authorization_id')
    S[input_name]['description'] = 'Exact normalized operation request before authorization ID is issued. Canonical request stored immutably and compared with consuming operation; actor/scope/logical operation and SHA-256 must match authorization.'
    PREPRODUCTION_INPUTS[operation_id] = input_name
for authorization_name in ['PreproductionAuthorizationCreate', 'PreproductionAuthorization']:
    S[authorization_name]['properties']['operation_input'] = {'oneOf': [ref(n) for n in PREPRODUCTION_INPUTS.values()]}
    S[authorization_name]['required'].append('operation_input')
    etag = text(minLength=3, pattern='^"[^" ]+"$')
    S[authorization_name]['properties']['operation_if_match'] = {'anyOf': [{'type': 'null'}, etag]}
    S[authorization_name]['required'].append('operation_if_match')
    S[authorization_name]['allOf'] = [
        {'if': {'properties': {'operation_id': enum('processSource', 'alignTranscript')}}, 'then': {'properties': {'operation_if_match': etag}}, 'else': {'properties': {'operation_if_match': {'type': 'null'}}}}] + [
        {'if': {'properties': {'operation_id': {'const': operation_id}}}, 'then': {'properties': {'operation_input': ref(input_name)}}}
        for operation_id, input_name in PREPRODUCTION_INPUTS.items()]
    S[authorization_name]['description'] = S[authorization_name].get('description', '') + ' operation_input is the typed canonical_request persisted by the database; service recomputes input_sha256 and rejects a mismatch. One job redemption atomically binds the authorization and explicitly approved job cap; no second-job reuse. Revocation is append-only and checked at dispatch.'
# Explicit production authority on downstream render/regeneration requests.
for request_name in ['RegenerateRequest', 'RenditionRequest', 'PreviewRequest', 'ClipCandidatesRequest']:
    request = S[request_name]
    for field in ['approved_plan_version_id', 'plan_approval_decision_id']:
        if field not in request['properties']:
            request['properties'][field] = UUID
            request['required'].append(field)
    request['description'] = request.get('description', '') + ' Requires matching approved production plan, exact selected inputs and remaining plan cap; preproduction authorization cannot fund this work.'

# Operation generator: every method carries explicit auth, errors, scope and milestone.
PARAMETERS = {
    'IfMatch': {'name': 'If-Match', 'in': 'header', 'required': True, 'schema': text(minLength=3, pattern='^"[^" ]+"$'), 'description': 'Strong quoted ETag (no wildcard). Compare current aggregate revision; mismatch 409 STALE_VERSION, missing 428. Immutable version path does not waive current-pointer check.'},
    'IdempotencyKey': {'name': 'Idempotency-Key', 'in': 'header', 'required': True, 'schema': text(minLength=16, maxLength=255), 'description': 'Workspace/actor/operation scoped normalized request hash, original response replay. Different hash 409 IDEMPOTENCY_CONFLICT. Billable/publication logical identity retained through ledger retention, replay cache default 7 days.'},
    'Cursor': {'name': 'cursor', 'in': 'query', 'required': False, 'schema': STR, 'description': 'Opaque tenant/filter/sort-bound cursor; stable created_at,id ordering. Invalid/mismatched cursor 422.'},
    'Limit': {'name': 'limit', 'in': 'query', 'required': False, 'schema': integer(1, maximum=100, default=25)}}
ERROR_STATUS = {'401': 'UNAUTHENTICATED', '403': 'FORBIDDEN', '404': 'NOT_FOUND', '409': 'CONFLICT / STALE_VERSION / IDEMPOTENCY_CONFLICT', '422': 'INVALID_INPUT / INVALID_STATE / BUDGET_EXCEEDED / capability or rights constraints', '429': 'RATE_LIMITED', '500': 'INTERNAL_ERROR', '503': 'PROVIDER_UNAVAILABLE'}
RESPONSES = {code: {'description': desc, 'content': {'application/json': {'schema': ref('Error')}}} for code, desc in ERROR_STATUS.items()}
RESPONSES['428'] = {'description': 'PRECONDITION_REQUIRED: missing If-Match', 'content': {'application/json': {'schema': ref('Error')}}}
RESPONSES['429']['headers'] = {'Retry-After': {'schema': integer(1), 'description': 'Seconds before retry.'}}

def query(name, schema, required=False): return {'name': name, 'in': 'query', 'required': required, 'schema': schema}
def op(group, milestone, method, path, name, response, request=None, roles=READ, scope='brand', async_=False, paid=False, publishing=False, match=False, public=False, session_only=False, page=False, description='', extra_params=None, operator=False):
    if scope in ['identity', 'verified-identity', 'verified-onboarding']:
        roles = []  # A verified user need not already belong to a workspace.
    params = [{'name': p, 'in': 'path', 'required': True, 'schema': UUID} for p in re.findall(r'\{([^}]+)\}', path)]
    if match: params.append({'$ref': '#/components/parameters/IfMatch'})
    idem = method in ['post', 'put', 'patch', 'delete'] and not public and group != 'Identity'
    if paid or publishing: idem = True
    if idem: params.append({'$ref': '#/components/parameters/IdempotencyKey'})
    if page:
        params += [{'$ref': '#/components/parameters/Cursor'}, {'$ref': '#/components/parameters/Limit'}]
        paged = response + 'Page'
        if paged not in S: define(paged, {'items': array(ref(response)), 'next_cursor': nullable(STR), 'has_more': BOOL})
        response = paged
    params += extra_params or []
    status = '202' if async_ else ('201' if method == 'post' and request and name.startswith('create') else '200')
    if async_: response = 'AsyncAccepted'
    responses = {code: {'$ref': '#/components/responses/' + code} for code in ERROR_STATUS}
    if match: responses['428'] = {'$ref': '#/components/responses/428'}
    headers = {'X-Correlation-ID': {'schema': UUID}, 'ETag': {'schema': STR, 'description': 'Strong quoted current aggregate ETag, including for version reads.'}}
    if async_: headers = {'Location': {'schema': text(format='uri-reference'), 'description': 'Same as status_url'}, 'Retry-After': {'schema': integer(1, default=2)}, 'X-Correlation-ID': {'schema': UUID}}
    responses[status] = {'description': 'Durably accepted; no completion claim.' if async_ else 'Authorized typed response.', 'headers': headers, 'content': {'application/json': {'schema': ref(response)}}}
    mut = method != 'get'
    security = [{'SessionCookie': [], **({'CSRFToken': []} if mut else {})}]
    if not session_only: security.append({'ScopedCredential': []})
    if public: security = []
    operation = {'operationId': name, 'tags': [group], 'summary': name, 'description': description or 'Planned target-v6 operation; not implemented by the legacy runtime.', 'x-implementation-status': 'planned', 'x-milestone': milestone, 'x-permissions': {'scope': scope, 'roles_any_of': roles, 'explicit_brand_grant_required_for_non_owner': scope == 'brand', 'same_workspace_references_required': True, 'operator_entitlement_required': operator}, 'x-billable': paid, 'x-publishing': publishing, 'x-concurrency': 'if-match' if match else 'not-applicable', 'security': security, 'parameters': params, 'responses': responses}
    if name in PREPRODUCTION_OPERATIONS:
        operation['x-work-authorization'] = {'purpose': 'PREPRODUCTION', 'required_request_field': 'preproduction_authorization_id', 'default_live_cap_micros': 0, 'approved_plan_required': False, 'immutable_binding': ['actor_user_id', 'workspace_id', 'brand_id', 'campaign_id', 'job_id_when_present', 'logical_operation_id', 'operation_id', 'input_sha256', 'inputs', 'cap', 'expires_at'], 'reserve_against': ['workspace', 'job', 'campaign_when_present', 'preproduction_authorization'], 'input_hash_rule': PREPRODUCTION_BINDING}
    elif name in ['executePlan', 'regenerateComponents', 'requestRendition', 'previewTimeline', 'generateClipCandidates']:
        operation['x-work-authorization'] = {'purpose': 'PRODUCTION', 'approved_plan_required': True, 'preproduction_authorization_permitted': False, 'reserve_against': ['workspace', 'campaign', 'job', 'approved_plan']}
    if group == 'Jobs':
        operation['x-permissions']['scope'] = 'resource-derived-job'
        operation['x-permissions']['workspace_scoped_job_roles_any_of'] = ADMIN
        operation['x-permissions']['originating_operation_authority_required'] = True
        operation['x-permissions']['description'] = 'Brand jobs require current grant. Retry/cancel derive current authority from originating operation without an EDIT intersection: viewer asset export and publisher publication jobs remain available. WORKSPACE ADMIN jobs allow only workspace export/delete and require original operation authority; owner-only stays owner-only. Operator reconcile still requires owner/admin AND operator entitlement.'
        if name in ['retrySafeJob', 'cancelJob']:
            operation['x-permissions']['roles_any_of'] = READ
            operation['x-permissions']['role_resolution'] = 'originating-operation-only'
            operation['x-permissions']['additional_edit_role_required'] = False
            operation['x-permissions']['origin_examples'] = {'requestExport': READ, 'schedulePublication': PUBLISH, 'requestPublicationTakedown': PUBLISH, 'requestWorkspaceExport': OWNER, 'requestWorkspaceDeletion': OWNER}
            operation['x-work-authorization'] = {'purpose': 'INHERIT_ORIGIN', 'retain_immutable_authorization': True, 'recheck_remaining_cap_before_paid_retry': True}
    if request: operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': ref(request)}}}
    PATHS.setdefault(path, {})[method] = operation
    OPERATIONS.append({'group': group, 'milestone': milestone, 'method': method.upper(), 'path': path, 'operation_id': name, 'request_schema': request, 'response_schema': response, 'success_status': int(status), 'billable': paid, 'publishing': publishing, 'if_match': match, 'idempotency_key': idem, 'implementation_status': 'planned'})

W = '/workspaces/{workspace_id}'
op('Administration', 'M1', 'post', W + '/preproduction-authorizations', 'createPreproductionAuthorization', 'PreproductionAuthorization', 'PreproductionAuthorizationCreate', roles=ADMIN, description='Creates an immutable capped preproduction authorization under current owner/admin budget policy and explicit brand grant. Server stamps approving actor/policy; target actor must have originating-operation authority. Zero default. Rechecks actual normalized input hash at consumption; no production-plan requirement or production spending grant.')
op('Administration', 'M1', 'get', W + '/preproduction-authorizations/{preproduction_authorization_id}', 'getPreproductionAuthorization', 'PreproductionAuthorization')
# Identity and administration bootstrap deliberately not legacy /v1/workspaces.
op('Identity', 'M1', 'post', '/auth/login', 'startLogin', 'AuthRedirect', 'LoginStart', public=True, scope='controlled-public', roles=[], description='Rate-limited OIDC initiation; allowlisted relative redirect, state/nonce/PKCE; sets transient login cookies. No workspace creation.')
op('Identity', 'M1', 'get', '/auth/callback', 'completeLogin', 'Session', public=True, scope='verified-callback', roles=[], extra_params=[query('code', STR, True), query('state', STR, True)], description='Verify OIDC issuer/audience/nonce, single-use state and code; bind verified subject, rotate secure session. Not an arbitrary identity endpoint.')
op('Identity', 'M1', 'get', '/auth/session', 'getSession', 'Session', scope='identity', session_only=True)
op('Identity', 'M1', 'post', '/auth/logout', 'logout', 'Acknowledgement', scope='identity', session_only=True)
op('Identity', 'M1', 'get', '/users/me', 'getCurrentUser', 'User', scope='identity', session_only=True)
op('Identity', 'M1', 'post', '/auth/workspace', 'switchWorkspace', 'Session', 'WorkspaceSwitch', scope='identity', session_only=True)
op('Identity', 'M1', 'post', '/onboarding/initiate', 'initiateOnboarding', 'OnboardingChallenge', 'OnboardingStart', public=True, scope='controlled-public', roles=[], description='Pilot code controlled and rate limited; no public signup, email invitation or account creation as a side effect.')
op('Identity', 'M1', 'post', '/workspaces', 'createWorkspace', 'Workspace', 'WorkspaceCreate', scope='verified-onboarding', session_only=True)
op('Identity', 'M1', 'get', '/workspaces', 'listWorkspaces', 'Workspace', scope='identity', page=True)
op('Identity', 'M1', 'get', W, 'getWorkspace', 'Workspace', scope='workspace')
op('Identity', 'M1', 'post', W + '/invitations', 'createInvitation', 'Invitation', 'InviteCreate', roles=ADMIN, scope='workspace', description='Explicit authorized send action. Never infer invitation authority from seed labels; verified intended identity only.')
op('Identity', 'M1', 'get', W + '/invitations', 'listInvitations', 'Invitation', roles=ADMIN, scope='workspace', page=True)
op('Identity', 'M1', 'post', '/invitations/accept', 'acceptInvitation', 'Membership', 'InviteAccept', scope='verified-identity', session_only=True)
op('Identity', 'M1', 'delete', W + '/invitations/{invitation_id}', 'revokeInvitation', 'Invitation', roles=ADMIN, scope='workspace', match=True)
op('Identity', 'M1', 'get', W + '/memberships', 'listMemberships', 'Membership', roles=ADMIN, scope='workspace', page=True)
op('Identity', 'M1', 'patch', W + '/memberships/{membership_id}', 'editMembership', 'Membership', 'MembershipEdit', roles=ADMIN, scope='workspace', match=True)
op('Identity', 'M1', 'delete', W + '/memberships/{membership_id}', 'revokeMembership', 'Membership', roles=ADMIN, scope='workspace', match=True)
op('Identity', 'M1', 'get', W + '/memberships/{membership_id}/brand-grants', 'listBrandGrants', 'BrandGrant', roles=ADMIN, scope='workspace', page=True)
op('Identity', 'M1', 'put', W + '/memberships/{membership_id}/brand-grants/{brand_id}', 'setBrandGrant', 'BrandGrant', 'BrandGrantEdit', roles=ADMIN, scope='workspace', match=True)
op('Identity', 'M1', 'delete', W + '/memberships/{membership_id}/brand-grants/{brand_id}', 'revokeBrandGrant', 'Acknowledgement', roles=ADMIN, scope='workspace', match=True)
op('Identity', 'M1', 'post', W + '/ownership-transfer', 'transferOwnership', 'Workspace', 'OwnershipTransfer', roles=OWNER, scope='workspace', session_only=True, match=True)

op('Brands', 'M1', 'post', W + '/brands', 'createBrand', 'Brand', 'BrandWrite', roles=ADMIN, scope='workspace')
op('Brands', 'M1', 'get', W + '/brands', 'listBrands', 'Brand', scope='workspace', page=True, description='Filter results to explicitly granted brands; owner sees all. Workspace membership alone does not expose brands.')
op('Brands', 'M1', 'get', W + '/brands/{brand_id}', 'getBrand', 'Brand')
op('Brands', 'M1', 'patch', W + '/brands/{brand_id}', 'editBrand', 'Brand', 'BrandWrite', roles=EDIT, match=True)
op('Brands', 'M2', 'post', W + '/brands/{brand_id}/profile-versions', 'createBrandProfileVersion', 'BrandProfileVersion', 'BrandProfileWrite', roles=EDIT, match=True)
op('Brands', 'M2', 'get', W + '/brands/{brand_id}/profile-versions', 'listBrandProfileVersions', 'BrandProfileVersion', page=True)
op('Brands', 'M2', 'get', W + '/brands/{brand_id}/profile-versions/{profile_version_id}', 'getBrandProfileVersion', 'BrandProfileVersion')
op('Brands', 'M2', 'post', W + '/brands/{brand_id}/voice-preview', 'previewBrandVoice', 'AsyncAccepted', 'VoicePreviewRequest', roles=EDIT, async_=True, paid=True)
op('Brands', 'M2', 'get', W + '/brands/{brand_id}/voice-samples/{sample_id}', 'getVoiceSample', 'VoiceSample')
op('Brands', 'M2', 'post', W + '/brands/{brand_id}/voice-samples/{sample_id}/versions/{sample_version_id}/decisions', 'decideVoiceSample', 'ApprovalDecision', 'VoiceSampleDecisionCreate', roles=REVIEW, match=True)
op('Packages', 'M2', 'post', W + '/campaigns', 'createCampaign', 'Campaign', 'CampaignWrite', roles=EDIT)
op('Packages', 'M2', 'get', W + '/campaigns', 'listCampaigns', 'Campaign', page=True)
op('Packages', 'M2', 'get', W + '/campaigns/{campaign_id}', 'getCampaign', 'Campaign')

op('Sources', 'M1', 'post', W + '/upload-intents', 'createUploadIntent', 'UploadIntent', 'UploadIntentCreate', roles=EDIT)
op('Sources', 'M1', 'post', W + '/upload-intents/{upload_id}/parts', 'signUploadPart', 'UploadPartURL', 'UploadPartRequest', roles=EDIT)
op('Sources', 'M1', 'get', W + '/upload-intents/{upload_id}', 'getUploadIntent', 'UploadIntent')
op('Sources', 'M1', 'delete', W + '/upload-intents/{upload_id}', 'cancelUpload', 'UploadIntent', roles=EDIT, match=True)
op('Sources', 'M1', 'post', W + '/sources/{source_id}/finalize', 'finalizeSource', 'AsyncAccepted', 'FinalizeSource', roles=EDIT, async_=True, match=True)
op('Sources', 'M2', 'post', W + '/sources/from-url', 'createSourceFromURL', 'AsyncAccepted', 'SourceURLCreate', roles=EDIT, async_=True, paid=True)
op('Sources', 'M2', 'post', W + '/sources/from-text', 'createSourceFromText', 'Source', 'SourceTextCreate', roles=EDIT)
op('Sources', 'M2', 'get', W + '/sources', 'listSources', 'Source', page=True)
op('Sources', 'M2', 'get', W + '/sources/{source_id}', 'getSource', 'Source')
op('Sources', 'M2', 'get', W + '/sources/{source_id}/versions/{source_version_id}', 'getSourceVersion', 'SourceVersion')
op('Sources', 'M2', 'post', W + '/sources/{source_id}/process', 'processSource', 'AsyncAccepted', 'SourceProcess', roles=EDIT, async_=True, paid=True, match=True)
op('Sources', 'M2', 'post', W + '/sources/{source_id}/cancel', 'cancelSourceProcessing', 'AsyncAccepted', 'ActionReason', roles=EDIT, async_=True, match=True)
op('Sources', 'M3', 'get', W + '/sources/{source_id}/transcript-versions', 'listTranscriptVersions', 'TranscriptVersion', page=True)
op('Sources', 'M3', 'get', W + '/sources/{source_id}/transcript-versions/{transcript_version_id}', 'getTranscriptVersion', 'TranscriptVersion')
op('Sources', 'M3', 'post', W + '/sources/{source_id}/transcript-versions', 'createTranscriptVersion', 'TranscriptVersion', 'TranscriptWrite', roles=EDIT, match=True)
op('Sources', 'M3', 'post', W + '/sources/{source_id}/alignment', 'alignTranscript', 'AsyncAccepted', 'AlignmentRequest', roles=EDIT, async_=True, paid=True, match=True)
op('Packages', 'M2', 'get', W + '/evidence', 'listEvidence', 'EvidenceItem', page=True, extra_params=[query('q', STR), query('brand_id', UUID)])
op('Packages', 'M2', 'get', W + '/claims', 'listClaims', 'Claim', page=True, extra_params=[query('package_version_id', UUID)])
op('Packages', 'M2', 'get', W + '/packages/{package_id}/versions/{version_id}/atoms', 'listPackageAtoms', 'ContentAtom', page=True)
op('Packages', 'M2', 'post', W + '/packages/draft', 'draftPackage', 'AsyncAccepted', 'PackageDraftRequest', roles=EDIT, async_=True, paid=True)
op('Packages', 'M2', 'post', W + '/packages', 'createPackage', 'Package', 'PackageCreate', roles=EDIT)

for group, milestone, resource, entity, version_param, write, snapshot, decision in [
    ('Packages', 'M2', 'packages', 'package_id', 'version_id', 'PackageWrite', 'PackageVersion', 'Package'),
    ('Plans', 'M2', 'plans', 'plan_id', 'plan_version_id', 'PlanWrite', 'PlanVersion', 'Plan'),
    ('Assets', 'M2', 'assets', 'asset_id', 'asset_version_id', 'AssetWrite', 'AssetVersion', 'Asset')]:
    base = W + '/' + resource
    item = base + '/{' + entity + '}'
    versions = item + '/versions'
    exact = versions + '/{' + version_param + '}'
    op(group, milestone, 'get', base, 'list' + resource.title(), decision, page=True, extra_params=[query('brand_id', UUID)])
    op(group, milestone, 'get', item, 'get' + decision, decision)
    op(group, milestone, 'get', versions, 'list' + decision + 'Versions', snapshot, page=True)
    op(group, milestone, 'get', exact, 'get' + decision + 'Version', snapshot)
    op(group, milestone, 'post', versions, 'create' + decision + 'Version', snapshot, write, roles=EDIT, match=True)
    op(group, milestone, 'post', exact + '/review', 'request' + decision + 'Review', 'ReviewTask', 'ReviewTaskCreate', roles=EDIT, match=True)
    op(group, milestone, 'post', exact + '/decisions', 'decide' + decision + 'Version', 'ApprovalDecision', decision + 'DecisionCreate', roles=REVIEW, match=True)
    op(group, milestone, 'get', exact + '/dependencies', 'list' + decision + 'Dependencies', 'DependencyEdge', page=True)
op('Plans', 'M2', 'post', W + '/plans/proposal', 'proposePlan', 'AsyncAccepted', 'PlanProposal', roles=EDIT, async_=True, paid=True)
op('Plans', 'M2', 'post', W + '/plans/{plan_id}/estimate', 'estimatePlan', 'AsyncAccepted', 'EstimateRequest', roles=EDIT, async_=True, match=True)
op('Plans', 'M2', 'get', W + '/plans/{plan_id}/estimates/{estimate_id}', 'getPlanEstimate', 'Estimate')
op('Plans', 'M2', 'post', W + '/plans/{plan_id}/execute', 'executePlan', 'AsyncAccepted', 'ExecutePlan', roles=EDIT, async_=True, paid=True, match=True)
op('Assets', 'M2', 'post', W + '/assets/{asset_id}/regenerate', 'regenerateComponents', 'AsyncAccepted', 'RegenerateRequest', roles=EDIT, async_=True, paid=True, match=True)
op('Assets', 'M3', 'post', W + '/assets/{asset_id}/renditions', 'requestRendition', 'AsyncAccepted', 'RenditionRequest', roles=EDIT, async_=True, paid=True, match=True)
op('Assets', 'M3', 'get', W + '/assets/{asset_id}/renditions', 'listRenditions', 'Rendition', page=True)
op('Assets', 'M3', 'get', W + '/renditions/{rendition_id}', 'getRendition', 'Rendition')
op('Assets', 'M3', 'post', W + '/renditions/{rendition_id}/decisions', 'decideRendition', 'ApprovalDecision', 'RenditionDecisionCreate', roles=REVIEW, match=True, description='Approve/reject exact immutable rendition with scope final_media. Both subject IDs equal path rendition_id. Technical validation is separate and must pass before approval; final asset approval does not imply final_media approval.')
op('Assets', 'M2', 'post', W + '/exports', 'requestExport', 'AsyncAccepted', 'ExportRequest', async_=True, paid=True)
op('Assets', 'M2', 'get', W + '/exports/{export_id}', 'getExport', 'Export')
op('Assets', 'M2', 'post', W + '/exports/{export_id}/download-access', 'issueDownloadAccess', 'DownloadAccess')
op('Assets', 'M2', 'get', W + '/reviews', 'listReviewTasks', 'ReviewTask', page=True)
op('Assets', 'M2', 'post', W + '/comments', 'createComment', 'Comment', 'CommentCreate')
op('Assets', 'M2', 'get', W + '/comments', 'listComments', 'Comment', page=True, extra_params=[query('subject_version_id', UUID, True)])
op('Assets', 'M2', 'post', W + '/comments/{comment_id}/resolve', 'resolveComment', 'Comment', 'ActionReason', match=True)

op('Video', 'M4', 'post', W + '/assets/{asset_id}/script-versions/{asset_version_id}/decisions', 'decideScriptVersion', 'ApprovalDecision', 'ScriptDecisionCreate', roles=REVIEW, match=True)
for resource, singular, snapshot, write, version_id in [('scenes', 'Scene', 'SceneVersion', 'SceneWrite', 'scene_version_id'), ('timelines', 'Timeline', 'TimelineVersion', 'TimelineWrite', 'timeline_version_id')]:
    base = W + '/assets/{asset_id}/' + resource + '/versions'
    op('Video', 'M3' if singular == 'Timeline' else 'M4', 'post', base, 'create' + singular + 'Version', snapshot, write, roles=EDIT, match=True)
    op('Video', 'M3' if singular == 'Timeline' else 'M4', 'get', base, 'list' + singular + 'Versions', snapshot, page=True)
    op('Video', 'M3' if singular == 'Timeline' else 'M4', 'get', base + '/{' + version_id + '}', 'get' + singular + 'Version', snapshot)
op('Video', 'M3', 'post', W + '/assets/{asset_id}/preview', 'previewTimeline', 'AsyncAccepted', 'PreviewRequest', roles=EDIT, async_=True, paid=True)
op('Video', 'M3', 'post', W + '/assets/{asset_id}/clip-candidates', 'generateClipCandidates', 'AsyncAccepted', 'ClipCandidatesRequest', roles=EDIT, async_=True, paid=True)
op('Video', 'M3', 'get', W + '/assets/{asset_id}/clip-candidates', 'listClipCandidates', 'ClipCandidate', page=True)
op('Video', 'M3', 'post', W + '/assets/{asset_id}/clip-selections', 'createClipSelection', 'ClipSelectionVersion', 'ClipSelectionWrite', roles=EDIT, match=True)
op('Video', 'M3', 'post', W + '/assets/{asset_id}/clip-selections/{selection_id}/versions', 'reviseClipSelectionCrop', 'ClipSelectionVersion', 'ClipSelectionWrite', roles=EDIT, match=True)
op('Video', 'M3', 'get', W + '/assets/{asset_id}/clip-selections/{selection_id}/versions/{selection_version_id}', 'getClipSelectionVersion', 'ClipSelectionVersion')
op('Video', 'M3', 'post', W + '/assets/{asset_id}/clip-selections/{selection_id}/versions/{selection_version_id}/decisions', 'decideClipSelection', 'ApprovalDecision', 'ClipSelectionDecisionCreate', roles=REVIEW, match=True)

op('Jobs', 'M1', 'get', W + '/jobs', 'listJobs', 'Job', page=True, extra_params=[query('state', ref('JobState'))])
op('Jobs', 'M1', 'get', W + '/jobs/{job_id}', 'getJob', 'Job')
op('Jobs', 'M1', 'get', W + '/jobs/{job_id}/steps', 'listJobSteps', 'JobStep', page=True)
op('Jobs', 'M1', 'get', W + '/jobs/{job_id}/attempts', 'listJobAttempts', 'ProviderAttempt', page=True)
op('Jobs', 'M1', 'post', W + '/jobs/{job_id}/retry', 'retrySafeJob', 'AsyncAccepted', 'JobRetry', roles=READ, async_=True, paid=True, match=True)
op('Jobs', 'M1', 'post', W + '/jobs/{job_id}/cancel', 'cancelJob', 'AsyncAccepted', 'ActionReason', roles=READ, async_=True, match=True)
op('Jobs', 'M1', 'post', W + '/jobs/{job_id}/operator-reconciliation', 'reconcileJob', 'Job', 'OperatorResolution', roles=ADMIN, match=True, operator=True)

op('Connections', 'M5', 'post', W + '/connections/oauth/start', 'startSocialOAuth', 'AuthRedirect', 'OAuthStart', roles=PUBLISH, session_only=True, description='Publisher additionally needs can_connect_social grant. State binds initiating identity/workspace/brand; requested account type capability verified.')
op('Connections', 'M5', 'get', '/connections/oauth/callback', 'completeSocialOAuth', 'Connection', public=True, scope='verified-callback', roles=[], extra_params=[query('code', STR, True), query('state', STR, True)], description='Single-use expiring state derives tenant and actor; verify provider flow, initiating browser binding and current grants. Do not trust callback-supplied workspace/brand. Tokens encrypted server-side, never returned.')
op('Connections', 'M5', 'get', W + '/connections', 'listConnections', 'Connection', page=True)
op('Connections', 'M5', 'get', W + '/connections/{connection_id}', 'getConnection', 'Connection')
op('Connections', 'M5', 'get', W + '/connections/{connection_id}/capabilities', 'getConnectionCapabilities', 'Capability')
op('Connections', 'M5', 'get', W + '/destination-profiles/{profile_version_id}', 'getDestinationProfile', 'DestinationProfile')
op('Connections', 'M5', 'post', W + '/connections/{connection_id}/validate', 'validateConnection', 'AsyncAccepted', roles=PUBLISH, async_=True, paid=True, match=True)
op('Connections', 'M5', 'delete', W + '/connections/{connection_id}', 'disconnectConnection', 'Connection', roles=PUBLISH, match=True, description='Revoke local authorization immediately, pause affected schedules; do not report provider token revocation unless confirmed. Publisher needs connection-management grant.')
op('Publications', 'M5', 'post', W + '/publications', 'createPublicationIntent', 'PublicationIntent', 'PublicationIntentWrite', roles=PUBLISH, publishing=True)
op('Publications', 'M5', 'get', W + '/publications', 'listPublications', 'PublicationIntent', page=True, extra_params=[query('from', DATE), query('to', DATE), query('state', ref('PublicationState')), query('destination', ref('Destination'))])
op('Publications', 'M5', 'get', W + '/publications/{publication_id}', 'getPublicationIntent', 'PublicationIntent')
op('Publications', 'M5', 'post', W + '/publications/{publication_id}/revisions', 'revisePublicationIntent', 'PublicationIntent', 'PublicationIntentWrite', roles=PUBLISH, publishing=True, match=True)
op('Publications', 'M5', 'get', W + '/publications/{publication_id}/revisions', 'listPublicationRevisions', 'PublicationIntent', page=True)
op('Publications', 'M5', 'get', W + '/publications/{publication_id}/revisions/{publication_revision_id}', 'getPublicationRevision', 'PublicationIntent')
op('Publications', 'M5', 'post', W + '/publications/{publication_id}/revisions/{publication_revision_id}/decisions', 'decidePublicationRevision', 'ApprovalDecision', 'PublicationDecisionCreate', roles=REVIEW, publishing=True, match=True)
op('Publications', 'M5', 'post', W + '/publications/{publication_id}/schedule', 'schedulePublication', 'AsyncAccepted', 'PublicationSchedule', roles=PUBLISH, async_=True, publishing=True, paid=True, match=True, description='202 durable scheduled job, not dispatch/live success; can wait until scheduled UTC. Requires exact publication approval, independent of generation approval.')
for action in ['pause', 'cancel']:
    op('Publications', 'M5', 'post', W + '/publications/{publication_id}/' + action, action + 'Publication', 'PublicationStatus', 'ActionReason', roles=PUBLISH, publishing=True, match=True, description='Pre-submit only; in-flight uncertain acceptance enters reconciliation, never false cancellation. Live item requires authorized takedown.')
op('Publications', 'M5', 'get', W + '/publications/{publication_id}/status', 'getPublicationStatus', 'PublicationStatus')
op('Publications', 'M5', 'get', W + '/publications/{publication_id}/attempts', 'listPublicationAttempts', 'PublicationAttempt', page=True)
op('Publications', 'M5', 'post', W + '/publications/{publication_id}/takedown', 'requestPublicationTakedown', 'AsyncAccepted', 'TakedownRequest', roles=PUBLISH, async_=True, paid=True, publishing=True, match=True)

op('Analytics', 'M6', 'get', W + '/metrics', 'queryMetrics', 'MetricSnapshot', page=True, extra_params=[query('publication_id', UUID), query('native_metric_name', STR), query('from', DATE), query('to', DATE)])
op('Analytics', 'M6', 'post', W + '/conversions', 'createConversion', 'Conversion', 'ConversionCreate', roles=EDIT)
op('Analytics', 'M6', 'get', W + '/conversions', 'listConversions', 'Conversion', page=True)
op('Analytics', 'M1', 'get', W + '/usage', 'listUsage', 'UsageEntry', page=True, extra_params=[query('ledger', enum('PROVIDER_COST', 'CUSTOMER_CREDITS')), query('from', DATE), query('to', DATE)])
op('Analytics', 'M1', 'get', W + '/reservations', 'listReservations', 'Reservation', page=True)
op('Administration', 'M1', 'get', W + '/budgets', 'getBudgets', 'Budget', roles=ADMIN, scope='workspace')
op('Administration', 'M1', 'put', W + '/budgets', 'setBudgets', 'Budget', 'BudgetWrite', roles=ADMIN, scope='workspace', match=True)
op('Administration', 'M1', 'get', W + '/entitlements', 'getEntitlements', 'Entitlement', roles=ADMIN, scope='workspace')
op('Administration', 'M1', 'put', W + '/entitlements', 'setEntitlements', 'Entitlement', 'EntitlementWrite', roles=ADMIN, scope='workspace', match=True)
op('Administration', 'M6', 'post', W + '/workspace-export', 'requestWorkspaceExport', 'AsyncAccepted', 'WorkspaceExportRequest', roles=OWNER, scope='workspace', async_=True, paid=True, description='Owner-wide data export. Other roles use scoped asset exports; job result_resource_urls resolves to Export, then private download access.')
op('Administration', 'M6', 'post', W + '/deletion', 'requestWorkspaceDeletion', 'AsyncAccepted', 'WorkspaceDeleteRequest', roles=OWNER, scope='workspace', async_=True, match=True, session_only=True)
op('Administration', 'M6', 'get', W + '/deletion', 'getWorkspaceDeletion', 'DeletionStatus', roles=OWNER, scope='workspace', description='Owner access to minimal deletion progress survives tombstone until final retention cutoff.')
op('Administration', 'M1', 'get', W + '/audit', 'listAudit', 'AuditEntry', roles=ADMIN, scope='workspace', page=True, description='Brand-related rows are filtered to explicit grants for non-owner admin; never expose other brands through audit.')
op('Administration', 'M6', 'get', W + '/notifications', 'listNotifications', 'Notification', scope='recipient', page=True, description='Only current recipient and still-authorized resource scope; read-only role does not expose other recipients.')
op('Administration', 'M6', 'post', W + '/notifications/{notification_id}/read', 'markNotificationRead', 'Notification', scope='recipient', match=True)

# Event schemas: required type-specific payloads and explicit lifecycle metadata.
EVENTS = {}
def event(name, data, milestone):
    schema_name = ''.join(part.title() for part in re.split(r'[._]', name)) + 'Event'
    define(schema_name, {'event_id': UUID, 'schema_version': {'const': 1}, 'type': {'const': name}, 'occurred_at': DATE, 'workspace_id': UUID, 'aggregate_id': UUID, 'aggregate_version': integer(1), 'correlation_id': UUID, 'data': obj(data)}, description='Transactional outbox event; persisted with originating mutation. Tenant in payload must match envelope; immutable version references never latest.')
    EVENTS[name] = {'schema': schema_name, 'milestone': milestone}

event('source.version_created', {'source_id': UUID, 'source_version_id': UUID, 'brand_id': UUID, 'sha256': HASH}, 'M2')
event('source.processing_completed', {'source_id': UUID, 'source_version_id': UUID, 'brand_id': UUID, 'job_id': UUID, 'extraction_complete': BOOL, 'transcript_version_id': nullable(UUID)}, 'M3')
event('source.transcript_version_created', {'source_id': UUID, 'transcript_version_id': UUID, 'previous_version_id': nullable(UUID), 'brand_id': UUID, 'alignment_status': enum('ALIGNED', 'NEEDS_ALIGNMENT', 'MANUALLY_CONFIRMED')}, 'M3')
for kind, entity, version, milestone in [('package', 'package_id', 'version_id', 'M2'), ('plan', 'plan_id', 'plan_version_id', 'M2'), ('asset', 'asset_id', 'asset_version_id', 'M2')]:
    event(kind + '.version_created', {entity: UUID, version: UUID, 'previous_version_id': nullable(UUID), 'brand_id': UUID, 'dependency_version_ids': ids()}, milestone)
event('plan.execution_requested', {'plan_id': UUID, 'plan_version_id': UUID, 'approval_decision_id': UUID, 'job_id': UUID, 'budget_cap': ref('Money'), 'brand_id': UUID}, 'M2')
event('asset.stale', {'asset_id': UUID, 'asset_version_id': UUID, 'changed_dependency_version_id': UUID, 'paused_publication_ids': ids(), 'brand_id': UUID}, 'M2')
event('job.state_changed', {'job_id': UUID, 'previous_state': ref('JobState'), 'state': ref('JobState'), 'step_id': nullable(UUID), 'logical_operation_id': UUID, 'fencing_token': integer(), 'error': nullable(ref('Error')), 'brand_id': nullable(UUID)}, 'M1')
event('job.reconciliation_required', {'job_id': UUID, 'attempt_id': UUID, 'logical_operation_id': UUID, 'reason': STR, 'reservation_id': UUID, 'brand_id': nullable(UUID)}, 'M1')
event('review.requested', {'review_task_id': UUID, 'subject': ref('ApprovalSubject'), 'reviewer_user_ids': ids(), 'brand_id': UUID}, 'M2')
event('review.decision_recorded', {'decision_id': UUID, 'subject': ref('ApprovalSubject'), 'decision': enum('APPROVED', 'REJECTED'), 'actor_user_id': UUID, 'reason': STR, 'brand_id': UUID}, 'M2')
event('review.invalidated', {'decision_id': UUID, 'subject': ref('ApprovalSubject'), 'changed_version_id': UUID, 'reason': STR, 'brand_id': UUID}, 'M2')
event('publication.revision_created', {'publication_id': UUID, 'publication_revision_id': UUID, 'logical_publication_id': UUID, 'previous_revision_id': nullable(UUID), 'brand_id': UUID}, 'M5')
event('publication.state_changed', {'publication_id': UUID, 'publication_revision_id': UUID, 'logical_publication_id': UUID, 'previous_state': ref('PublicationState'), 'state': ref('PublicationState'), 'attempt_id': nullable(UUID), 'remote_id': nullable(STR), 'verified_live_at': nullable(DATE), 'verified_visibility': nullable(enum('PUBLIC', 'UNLISTED', 'PRIVATE')), 'brand_id': UUID}, 'M5')
event('publication.late_paused', {'publication_id': UUID, 'publication_revision_id': UUID, 'scheduled_at': DATE, 'detected_at': DATE, 'late_by_seconds': integer(901), 'brand_id': UUID}, 'M5')
event('metrics.snapshot_recorded', {'snapshot': ref('MetricSnapshot')}, 'M6')
event('usage.reserved', {'reservation': ref('Reservation')}, 'M1')
event('usage.settled', {'reservation_id': UUID, 'usage_entry': ref('UsageEntry')}, 'M1')
event('usage.released', {'reservation_id': UUID, 'job_id': UUID, 'amount': ref('Money'), 'reason': STR}, 'M1')
event('usage.budget_blocked', {'job_id': UUID, 'code': {'const': 'BUDGET_EXCEEDED'}, 'required_amount': ref('Money'), 'available_amount': ref('Money')}, 'M1')
event('connection.state_changed', {'connection_id': UUID, 'brand_id': UUID, 'previous_state': enum('CONNECTED', 'EXPIRED', 'REVOKED', 'BLOCKED'), 'state': enum('CONNECTED', 'EXPIRED', 'REVOKED', 'BLOCKED'), 'reason': STR}, 'M5')

event('usage.preproduction_authorized', {'authorization': ref('PreproductionAuthorization')}, 'M1')
for ev_name in ['job.state_changed', 'job.reconciliation_required']:
    data = S[EVENTS[ev_name]['schema']]['properties']['data']
    for field, schema in {**JOB_CONTEXT, 'preproduction_authorization_id': nullable(UUID)}.items():
        data['properties'][field] = copy.deepcopy(schema)
        if field not in data['required']: data['required'].append(field)
    data['allOf'] = copy.deepcopy(JOB_SCOPE_CONSTRAINTS + JOB_PURPOSE_CONSTRAINTS)
    data['description'] = 'Scope/purpose/operation/authorization mirror originating job and must match persisted parent. Null brand/campaign permitted only for constrained WORKSPACE ADMIN export/delete.'

def transition_constraint(mapping):
    return {'oneOf': [obj({'previous_state': {'const': old}, 'state': enum(*new)}, ['previous_state', 'state']) for old, new in mapping.items() if new]}
# Do not close the transition fragment: the enclosing concrete payload has more fields.
for ev_name, transitions in [('job.state_changed', JOB_TRANSITIONS), ('publication.state_changed', PUBLICATION_TRANSITIONS)]:
    schema = S[EVENTS[ev_name]['schema']]['properties']['data']
    schema.setdefault('allOf', []).append({'oneOf': [{'properties': {'previous_state': {'const': old}, 'state': enum(*new)}, 'required': ['previous_state', 'state']} for old, new in transitions.items() if new]})
pub_data = S[EVENTS['publication.state_changed']['schema']]['properties']['data']
pub_data['allOf'].append({'if': {'properties': {'state': {'const': 'PUBLISHED'}}}, 'then': {'properties': {'remote_id': STR, 'verified_live_at': DATE, 'verified_visibility': enum('PUBLIC', 'UNLISTED', 'PRIVATE')}}})
S[EVENTS['usage.reserved']['schema']]['properties']['data']['properties']['reservation'] = {'allOf': [ref('Reservation'), {'properties': {'state': {'const': 'RESERVED'}}}]}
S['DomainEvent'] = {'oneOf': [ref(v['schema']) for v in EVENTS.values()], 'discriminator': {'propertyName': 'type', 'mapping': {k: '#/components/schemas/' + v['schema'] for k, v in EVENTS.items()}}}

OPENAPI = {
    'openapi': '3.1.0', 'jsonSchemaDialect': 'https://json-schema.org/draft/2020-12/schema',
    'info': {'title': 'Content OS — PLANNED target v6 API', 'version': '6.0.0-m0-planned', 'description': 'Design contract only. No endpoint in this document is claimed implemented. Legacy FastAPI runtime /v1 remains separate. Generated from build_contracts.py; authority docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md. /api/v6 is a proposed namespace, not a deployed server.'},
    'servers': [{'url': '/api/v6', 'description': 'Proposed future namespace; NOT an implemented server'}],
    'x-implementation-status': 'planned', 'x-specification-version': '6.0',
    'x-authorization-rules': {'default': 'Deny; verify global identity, active workspace membership and explicit brand grant for each non-owner, including admins. Owners span own workspace only.', 'reference_checks': 'All IDs same workspace/authorized brand. Inaccessible object is 404; known accessible resource prohibited action is 403.', 'roles_combine': True, 'side_effect_recheck': 'Recheck actor role/grants, current consent/rights, approvals and deletion tombstone immediately before paid or publication side effects.', 'legacy_key': 'X-API-Key is NOT accepted as user identity by this contract; migration scope cannot bypass brand grants.', 'scoped_credentials': 'Bound to actor/workspace/brand/operation scopes, revocable and rotatable; never bypass role authority. Identity/session endpoints require cookie session.', 'provider_callbacks': 'Provider-specific verified ingress not standardized as a fake generic HMAC route; see event delivery policy.'},
    'tags': [{'name': n} for n in ['Identity', 'Brands', 'Sources', 'Packages', 'Plans', 'Assets', 'Video', 'Jobs', 'Connections', 'Publications', 'Analytics', 'Administration']],
    'paths': PATHS,
    'components': {'schemas': S, 'parameters': PARAMETERS, 'responses': RESPONSES, 'securitySchemes': {
        'SessionCookie': {'type': 'apiKey', 'in': 'cookie', 'name': '__Host-contentos-session', 'description': 'OIDC-derived server session; Secure/HttpOnly/SameSite, expiry and rotation enforced.'},
        'CSRFToken': {'type': 'apiKey', 'in': 'header', 'name': 'X-CSRF-Token', 'description': 'Required together with cookie authentication on browser mutations; server validates Origin as well.'},
        'ScopedCredential': {'type': 'http', 'scheme': 'bearer', 'description': 'Separate revocable scoped API credential, not legacy workspace key. Scope/role intersection only.'}}}}

def event_document():
    needed = set()
    def visit(node):
        if isinstance(node, dict):
            if '$ref' in node:
                name = node['$ref'].rsplit('/', 1)[-1]
                if name not in needed:
                    needed.add(name)
                    visit(S[name])
            for k, v in node.items():
                if k != '$ref': visit(v)
        elif isinstance(node, list):
            for v in node: visit(v)
    visit(ref('DomainEvent'))
    def remap(node):
        if isinstance(node, dict): return {k: (v.replace('#/components/schemas/', '#/$defs/') if k == '$ref' else remap(v)) for k, v in node.items() if k != 'discriminator'}
        if isinstance(node, list): return [remap(v) for v in node]
        return node
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'urn:content-os:planned:target-v6:events', 'title': 'Planned Content OS v6 domain event envelope and typed payloads', 'x-implementation-status': 'planned', '$ref': '#/$defs/DomainEvent', '$defs': {n: remap(S[n]) for n in sorted(needed)}}

LIFECYCLE = {
    'contract_status': 'planned', 'schema_version': 1,
    'job': {'initial': 'QUEUED', 'transitions': JOB_TRANSITIONS, 'authority': 'Spec section 13 exact transition table', 'guards': ['Claim lease atomically, heartbeat and monotonically increasing fencing token.', 'Persist intent before submit. UNKNOWN acceptance => RECONCILING, no blind resubmit.', 'At most 3 total safe submission attempts; polling is separate.', 'Cancellation may finish SUCCEEDED remotely; retain actual spend, stop downstream.', 'Terminal state never regresses because a callback is duplicated or arrives late.']},
    'publication': {'initial': 'DRAFT', 'transitions': PUBLICATION_TRANSITIONS, 'authority': 'Proposed M5 transition graph derived from section 15 states; product/adapter review required', 'guards': ['DRAFT/PAUSED -> SCHEDULED requires exact revision approval, current rights and permissions.', 'Revising scheduled/paused metadata/account/time pauses and creates new pending revision, never mutates an approved snapshot.', 'SUBMITTING/PROCESSING/RECONCILING -> PUBLISHED requires independently verified destination state and requested visibility.', 'FAILED -> DRAFT only after proven nonacceptance/safe reconciliation; new approval required. Unknown stays RECONCILING.', 'TAKEDOWN_REQUESTED -> PUBLISHED only on verified takedown failure; preserve history and notify.', 'Do not cancel accepted remote work as if unpublished; request takedown after reconciliation.', 'Dispatch >15 minutes late pauses and notifies; no surprising stale post.']},
    'reservation': {'initial': 'RESERVED', 'transitions': {'RESERVED': ['SETTLED', 'RELEASED'], 'SETTLED': [], 'RELEASED': []}, 'guards': ['Unknown outcome retains reservation.', 'Adjustments are new immutable ledger entries, not state rewind.', 'Simulated attempts cannot settle as live spend.']},
    'delivery': {'mechanism': 'Transactional outbox + deduplicated inbox', 'delivery_semantics': 'at-least-once', 'deduplicate_by': ['consumer_id', 'event_id'], 'ordering': 'Aggregate version is monotonic within workspace/aggregate; consumer checks versions and fetches/reconciles gaps, not global delivery order.', 'atomicity': 'Persist domain mutation and outbox together; persist inbox dedup and projection mutation together.', 'tenant_binding': 'Envelope workspace, payload references, known attempt/provider remote identifiers must agree before state update.', 'outbound_webhooks': {'enabled_by_default': False, 'signature': 'HMAC over timestamp plus raw body, per-endpoint secret; exact header/canonicalization frozen before enabling', 'timestamp_tolerance_seconds': 300, 'replay_id': 'event_id'}, 'inbound_callbacks': 'Use provider-supported verification only; signature scheme/payload/route are provider-specific and frozen in M4/M5. Do not invent HMAC support. Dedup callbacks and resolve to known local attempts before tenant mutation.', 'schema_evolution': 'Envelope schema_version=1; compatible additions require explicit optional schema change. Required fields/meaning changes require new schema version. Unsupported type/version quarantined; never executed as instruction.'},
    'events': EVENTS}

LIFECYCLE['job']['guards'] += [
    'PREPRODUCTION reserves against immutable owner/admin authorization plus workspace/job/campaign caps where present; unconfigured live allowance zero. Every paid step binds authorization actor, operation, logical operation and exact input hash; no approved production plan needed or implied.',
    'PRODUCTION always requires exact approved production plan; PREPRODUCTION authorization never substitutes. ADMIN workspace jobs are restricted to workspace export/delete with null brand/campaign and explicit WORKSPACE scope.',
    'Retry/cancel rechecks originating operation authority without universal EDIT intersection; viewer asset export and publisher publication work are supported. Owner-only deletion/export and operator reconcile restrictions are unchanged.',
    'Timeline write atomically returns a fresh output asset version; output binding is excluded from timeline hash/dependencies, preventing a timeline/output cycle.']
OPENAPI['x-review-targets'] = {name: {'registry_kind': kind, 'scope': scope, 'table': table} for name, (kind, scope, table) in REVIEW_TARGETS.items()}
OPENAPI['x-preproduction-policy'] = {'default_live_cap_micros': 0, 'immutable': True, 'operations': list(PREPRODUCTION_OPERATIONS), 'input_hash_rule': PREPRODUCTION_BINDING, 'does_not_authorize_production': True}

COVERAGE = {'status': 'planned-not-runtime', 'spec_section': 16, 'operations': OPERATIONS,
    'deferred_details': [
        {'milestone': 'M1', 'detail': 'OIDC vendor configuration, API credential provisioning/rotation UX, storage multipart provider details and production cookie domain selected in implementation ADRs.'},
        {'milestone': 'M2', 'detail': 'Claim/evidence creation and reclassification commands, advanced comments/diff/restore and recipe/persona library management are represented by typed snapshots but their additional CRUD routes must be frozen before corresponding UI.'},
        {'milestone': 'M4', 'detail': 'Avatar/voice/media consent administration and provider-specific callback payloads require provider authority and lifecycle review; no invented callback security shape.'},
        {'milestone': 'M5', 'detail': 'OAuth error callback query variants, platform native payloads/limits and callback routes are adapter-specific contracts; no provider tokens in public domain schemas.'},
        {'milestone': 'M6', 'detail': 'Operational backup/provider-deletion exceptions and retention policies require owner validation. Workspace export/download token behavior is design only.'},
        {'milestone': 'M7', 'detail': 'Public signup, subscription checkout, invoices and payment lifecycle require separate R2 commercial contract.'}]}

def render_artifacts():
    objects = {'target-v6.openapi.json': OPENAPI, 'target-v6.events.schema.json': event_document(), 'target-v6.lifecycle.json': LIFECYCLE, 'target-v6.coverage.json': COVERAGE}
    return {name: json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n' for name, value in objects.items()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if committed artifacts differ from deterministic generation.')
    args = parser.parse_args()
    for name, content in render_artifacts().items():
        path = HERE / name
        if args.check:
            if not path.exists() or path.read_text() != content: raise SystemExit('Contract drift: ' + name)
        else: path.write_text(content)
    print(f'{"Checked" if args.check else "Generated"} 4 artifacts; {len(PATHS)} paths, {len(OPERATIONS)} operations, {len(S)} schemas, {len(EVENTS)} event types.')

if __name__ == '__main__': main()
