"""Chromium UI→actual ASGI/PostgreSQL workflow. Network bridge stays local.
The IdP is a signed test fixture; upload bytes, SQL, worker and rendering are real.
"""
import json
from http.cookies import SimpleCookie
from urllib.parse import urlsplit,parse_qs,urlencode
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright,expect

from conftest import ORIGIN,ISSUER,PREFIX,EVIDENCE
from test_workflow import workflow


def test_browser_signin_upload_worker_and_source_preview(workflow,tmp_path):
    t=workflow;data='Browser-tested private source.\nMānoa to Ontario, with clear source ownership.\n'
    file=tmp_path/'permitted-source.txt';file.write_text(data)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1280,'height':1000})
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        with TestClient(t.api.app,base_url=ORIGIN,raise_server_exceptions=False) as bridge:
            def route_request(route):
                request=route.request;url=urlsplit(request.url)
                if url.netloc==urlsplit(ISSUER).netloc and url.path=='/authorize':
                    code,state=t.api.fake.issue(request.url,t.owner.subject,t.owner.email)
                    callback=ORIGIN+PREFIX+'/auth/callback?'+urlencode({'code':code,'state':state})
                    route.fulfill(status=200,content_type='text/html',body='<script>location.replace('+json.dumps(callback)+')</script>')
                    return
                assert url.netloc==urlsplit(ORIGIN).netloc,'Unexpected browser network destination'
                bridge.cookies.clear()
                headers=request.all_headers()
                response=bridge.request(request.method,url.path+('?' +url.query if url.query else ''),
                    headers=headers,content=request.post_data_buffer,follow_redirects=False)
                print(request.method,url.path,response.status_code,response.headers.get('content-type'), 'cookie present' if headers.get('cookie') else 'no cookie')
                if response.status_code>=400: print(response.json().get('code'))
                for value in response.headers.get_list('set-cookie'):
                    parsed=SimpleCookie();parsed.load(value)
                    for name,morsel in parsed.items():
                        cookie={'name':name,'value':morsel.value,'domain':url.netloc,'path':morsel['path'] or '/',
                                'secure':bool(morsel['secure']),'httpOnly':bool(morsel['httponly']),'sameSite':'Lax'}
                        if morsel['max-age']=='0':cookie['expires']=1
                        context.add_cookies([cookie])
                result_headers={k:v for k,v in response.headers.items() if k not in ('set-cookie','content-length','content-encoding','transfer-encoding')}
                if response.status_code==303:
                    assert response.headers['location']==PREFIX+'/workflow'
                    route.fulfill(status=200,content_type='text/html',body='<script>location.replace('+json.dumps(ORIGIN+response.headers['location'])+')</script>')
                else:
                    route.fulfill(status=response.status_code,headers=result_headers,body=response.content)
            page.route('**/*',route_request)
            page.goto(ORIGIN+PREFIX+'/workflow')
            page.get_by_role('button',name='Sign in',exact=True).click()
            expect(page.locator('#logout')).to_be_visible()
            page.locator('#workspace').select_option(t.w)
            expect(page.locator('#brand option[value="'+t.b+'"]')).to_have_count(1)
            page.locator('#brand').select_option(t.b)
            page.locator('#title').fill('Browser acceptance source')
            page.locator('#rights').fill('Owned fixture source; used only for this test')
            page.locator('#file').set_input_files(file)
            page.get_by_role('button',name='Upload source',exact=True).click()
            expect(page.locator('#jobState')).to_have_text('QUEUED')
            assert t.worker.process_one(t.w,t.b)['status']=='SUCCEEDED'
            page.get_by_role('button',name='Refresh status',exact=True).click()
            expect(page.locator('#jobState')).to_have_text('SUCCEEDED')
            expect(page.locator('#preview')).to_have_text(data.strip())
            expect(page.locator('#lineage')).to_contain_text('TEXT_POLICY_V1')
            assert not errors,errors
            page.screenshot(path=str(EVIDENCE/'working-workflow.png'),full_page=True)
        context.close();browser.close()
