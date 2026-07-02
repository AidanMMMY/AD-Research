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

# Test cninfo
print("=== cninfo-reports/refresh ===")
resp = requests.post('http://localhost:8000/api/v1/cninfo-reports/refresh', headers=headers, timeout=60)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:800]}")

print("\n=== microstructure/refresh ===")
resp = requests.post('http://localhost:8000/api/v1/microstructure/refresh', headers=headers, timeout=60)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:800]}")

print("\n=== sec-filings/refresh ===")
resp = requests.post('http://localhost:8000/api/v1/sec-filings/refresh', headers=headers, timeout=60)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:800]}")
