#!/usr/bin/env python3
import requests
import sys

# Login
r = requests.post('http://localhost:8000/api/v1/auth/login', json={'username': 'admin', 'password': 'zKjACVBJxSXXgquV'})
if r.status_code != 200:
    print('Login failed:', r.status_code, r.text)
    sys.exit(1)

token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

tests = [
    ('/api/v1/research-reports/refresh', '研报库'),
    ('/api/v1/cninfo-reports/refresh', '巨潮报告'),
    ('/api/v1/search-trends/refresh', '搜索热度'),
    ('/api/v1/microstructure/refresh', '微结构数据'),
    ('/api/v1/futures/refresh', '商品期货'),
    ('/api/v1/macro/refresh-china', '中国宏观'),
]

for path, name in tests:
    try:
        resp = requests.post(f'http://localhost:8000{path}', headers=headers, timeout=180)
        print(f"{name}: {resp.status_code} - {resp.text[:300]}")
    except Exception as e:
        print(f"{name}: ERROR - {str(e)[:100]}")
    print()

# Check news sources
print("=== 资讯健康度 ===")
resp = requests.get('http://localhost:8000/api/v1/news/health', headers=headers)
if resp.status_code == 200:
    data = resp.json()
    print(f"调度器: {'运行中' if data.get('scheduler_running') else '未运行'}")
    print(f"数据源数量: {len(data.get('sources', []))}")
    for s in data.get('sources', []):
        print(f"  {s['source']}: 总数={s['total']}, 24h={s['last_24h']}")
