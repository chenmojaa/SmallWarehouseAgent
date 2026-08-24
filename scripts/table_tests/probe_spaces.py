import sys
sys.path.insert(0, '.')
import httpx
from app.config import settings

r = httpx.post(f'{settings.feishu_api_base}/open-apis/auth/v3/tenant_access_token/internal',
               json={'app_id': settings.feishu_app_id, 'app_secret': settings.feishu_app_secret}, timeout=10)
tok = r.json()['tenant_access_token']

r = httpx.get(f'{settings.feishu_api_base}/open-apis/wiki/v2/spaces',
              params={'page_size': 20},
              headers={'Authorization': 'Bearer ' + tok}, timeout=10)
data = r.json()
print('spaces:', r.status_code, 'code', data.get('code'), 'msg', data.get('msg'))
items = data.get('data', {}).get('items', [])
print('total items:', len(items))
for sp in items:
    sid = sp.get('space_id')
    nm = sp.get('name')
    vis = sp.get('visibility')
    print('  space_id=', sid, ' name=', nm, ' visibility=', vis)
