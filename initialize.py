#!/usr/bin/env python3
"""Initialize a fresh loopback-only deployment; keep credentials root-readable."""
import json
import os
from pathlib import Path
import secrets
import urllib.parse

import requests

os.umask(0o077)
origin = os.environ['NEW_API_ORIGIN'].rstrip('/')
base = 'http://127.0.0.1:8091'
credentials_file = Path('/root/new-api-admin.json')
session = requests.Session()
session.headers['Origin'] = origin
setup = session.get(base + '/api/setup', timeout=30).json()
assert setup.get('success'), 'Cannot read setup status'
if not setup['data']['status']:
    if credentials_file.exists():
        credentials = json.loads(credentials_file.read_text())
    else:
        credentials = {'url': origin, 'username': 'admin', 'password': secrets.token_urlsafe(27)}
        credentials_file.write_text(json.dumps(credentials, indent=2) + '\n')
        credentials_file.chmod(0o600)
    payload = {
        'username': credentials['username'],
        'password': credentials['password'],
        'confirmPassword': credentials['password'],
        'SelfUseModeEnabled': True,
        'DemoSiteEnabled': False,
    }
    result = session.post(base + '/api/setup', json=payload, timeout=60).json()
    assert result.get('success'), result.get('message', 'Setup failed')
    print('Administrator initialized; credentials saved privately')
else:
    assert credentials_file.exists(), 'Already initialized; refusing to overwrite credentials'
    credentials = json.loads(credentials_file.read_text())

result = session.post(base + '/api/user/login', json={
    'username': credentials['username'], 'password': credentials['password'],
}, timeout=30).json()
assert result.get('success'), result.get('message', 'Administrator login failed')
assert result.get('data', {}).get('id'), 'Login did not return a user ID'
session.headers['New-Api-User'] = str(result['data']['id'])
# This bootstrap talks only over the server loopback; browsers retain Secure cookies.
for cookie in session.cookies:
    cookie.secure = False
for key, value in [('RegisterEnabled', 'false'), ('PasswordRegisterEnabled', 'false'), ('ServerAddress', origin)]:
    result = session.put(base + '/api/option/', json={'key': key, 'value': value}, timeout=30).json()
    assert result.get('success'), f'Cannot set {key}: ' + result.get('message', '')
print('Administrator login verified; registration disabled; public URL configured')
