#!/usr/bin/env python3
import requests
import json

# Login
r = requests.post('http://localhost:8000/api/v1/auth/login', json={'username': 'admin', 'password': 'Admin123!Test'})
if r.status_code != 200:
    print('Login failed:', r.status_code, r.text)
    exit(1)

token = r.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Get scheduler jobs
jobs = requests.get('http://localhost:8000/api/v1/scheduler/jobs', headers=headers)
print('Status:', jobs.status_code)
print('Response:', json.dumps(jobs.json(), indent=2, ensure_ascii=False)[:3000])
