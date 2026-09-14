"""Authlib authorization-code/PKCE verifier with pinned issuer/endpoints/algorithms.

No provider access on import/startup. Tests inject a cryptographically signed fake
IdP network transport. JWT parsing/signature/standard ID token validation are
Authlib's, not a home-built verifier. No userinfo request or provider token storage.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
import time
import math
import asyncio
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebToken, JsonWebKey
from authlib.oidc.core import CodeIDToken
from .errors import APIError


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    redirect_uri: str

    def validate(self):
        for value in (self.issuer, self.authorization_endpoint, self.token_endpoint, self.jwks_uri, self.redirect_uri):
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise ValueError('OIDC endpoints require configured HTTPS URLs without userinfo/fragment')
        if not self.client_id:
            raise ValueError('OIDC client_id required')
        # Endpoints are operator-pinned, not sourced from browser/ID token headers.


class BoundedOIDCTransport(httpx.AsyncBaseTransport):
    """Bound wire data before Authlib/HTTPX buffers or parses a token response.

    Only uncompressed responses are accepted so decoded data cannot exceed the
    wire limit. Operator-pinned IdP endpoints must honor Accept-Encoding: identity.
    """
    def __init__(self, transport=None, limit=131072):
        self.inner = transport if transport is not None else httpx.AsyncHTTPTransport(trust_env=False)
        self.limit = limit

    async def handle_async_request(self, request):
        request.headers['Accept-Encoding'] = 'identity'
        result = await self.inner.handle_async_request(request)
        try:
            if result.headers.get('content-encoding', 'identity').lower() not in ('', 'identity'):
                raise ValueError('Compressed OIDC response refused')
            chunks, size = [], 0
            if result.is_stream_consumed:
                # MockTransport may return an already buffered fixture response.
                body = result.content
                if len(body) > self.limit:
                    raise ValueError('OIDC response too large')
            else:
                async for chunk in result.aiter_raw():
                    size += len(chunk)
                    if size > self.limit:
                        raise ValueError('OIDC response too large')
                    chunks.append(chunk)
                body = b''.join(chunks)
            return httpx.Response(result.status_code, headers=result.headers, content=body,
                                  extensions=result.extensions, request=request)
        finally:
            await result.aclose()

    async def aclose(self):
        await self.inner.aclose()


class OIDCVerifier:
    total_timeout_seconds = 20

    def __init__(self, config: OIDCConfig, transport=None):
        config.validate()
        self.config, self.transport = config, transport
        self.jwt = JsonWebToken(['RS256'])

    def client(self):
        return AsyncOAuth2Client(
            client_id=self.config.client_id, redirect_uri=self.config.redirect_uri,
            scope='openid email profile', code_challenge_method='S256',
            token_endpoint_auth_method='none', transport=BoundedOIDCTransport(self.transport),
            timeout=10, follow_redirects=False, trust_env=False,
        )

    def authorization_url(self, state, nonce, verifier):
        with_client = self.client()
        url, _ = with_client.create_authorization_url(self.config.authorization_endpoint,
            state=state, nonce=nonce, code_verifier=verifier, response_type='code')
        return url

    async def complete(self, code, verifier, nonce):
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                return await self._complete(code, verifier, nonce)
        except Exception:
            raise APIError('INVALID_LOGIN', 401) from None

    async def _complete(self, code, verifier, nonce):
        try:
            async with self.client() as client:
                token = await client.fetch_token(self.config.token_endpoint, code=code,
                                                code_verifier=verifier, grant_type='authorization_code')
            raw = token.get('id_token')
            if not isinstance(raw, str) or len(raw) > 32768:
                raise ValueError('Missing or oversized ID token')
            # Pinned HTTPS JWKS endpoint, bounded response, no redirects, no token-header URLs.
            async with httpx.AsyncClient(transport=BoundedOIDCTransport(self.transport), timeout=10, follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET', self.config.jwks_uri) as result:
                    result.raise_for_status()
                    data = b''
                    async for chunk in result.aiter_bytes():
                        data += chunk
                        if len(data) > 131072:
                            raise ValueError('JWKS too large')
            import json
            jwks = json.loads(data)
            keys = jwks.get('keys')
            if not isinstance(keys, list) or not 1 <= len(keys) <= 20:
                raise ValueError('Invalid JWKS')

            def select_key(header, payload):
                if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
                    raise ValueError('Disallowed signing algorithm or missing kid')
                if any(k in header for k in ('jku', 'x5u', 'jwk', 'crit')):
                    raise ValueError('Untrusted key location/critical extension')
                matches = [k for k in keys if k.get('kid') == header['kid'] and k.get('kty') == 'RSA'
                           and k.get('use', 'sig') == 'sig' and k.get('alg', 'RS256') == 'RS256'
                           and 'd' not in k and ('key_ops' not in k or k['key_ops'] == ['verify'])]
                if len(matches) != 1:
                    raise ValueError('Ambiguous or unknown key')
                key = JsonWebKey.import_key(matches[0])
                if key.get_public_key().key_size < 2048:
                    raise ValueError('Weak RSA key')
                return key

            claims = self.jwt.decode(raw, select_key, claims_cls=CodeIDToken,
                claims_options={
                    'iss': {'essential': True, 'value': self.config.issuer},
                    'sub': {'essential': True}, 'aud': {'essential': True},
                    'exp': {'essential': True}, 'iat': {'essential': True},
                    'nonce': {'essential': True, 'value': nonce},
                }, claims_params={'nonce': nonce, 'client_id': self.config.client_id,
                                  'access_token': token.get('access_token')})
            claims.validate(leeway=0)
            aud = claims['aud']
            audiences = [aud] if isinstance(aud, str) else aud
            if not isinstance(audiences, list) or self.config.client_id not in audiences:
                raise ValueError('Wrong audience')
            if ('azp' in claims and claims['azp'] != self.config.client_id) or (len(audiences) > 1 and claims.get('azp') != self.config.client_id):
                raise ValueError('Wrong authorized party')
            if not isinstance(claims['sub'], str) or not claims['sub'] or len(claims['sub']) > 255:
                raise ValueError('Invalid subject')
            if any(type(claims[k]) not in (int, float) or not math.isfinite(claims[k]) for k in ('exp', 'iat')) or claims['exp'] <= time.time() or claims['iat'] > time.time() + 30 or claims['exp'] <= claims['iat']:
                raise ValueError('Invalid token lifetime')
            if claims.get('email_verified') is not True or not isinstance(claims.get('email'), str) or '@' not in claims['email'] or len(claims['email']) > 320:
                raise ValueError('Verified email required by current API contract')
            return {'issuer': claims['iss'], 'subject': claims['sub'], 'email': claims['email'],
                    'display_name': str(claims.get('name') or claims['sub'])[:200]}
        except Exception:
            # Provider payload/code/access token are never included in error/log output.
            raise APIError('INVALID_LOGIN', 401) from None
