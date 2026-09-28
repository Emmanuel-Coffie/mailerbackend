"""Regenerate the credential-free Postman collection with Python's stdlib."""
import json
from pathlib import Path

items = []

def request(name, method, path, body=None, capture=None, auth=True):
    item = {'name': name, 'request': {'method': method, 'header': [], 'url': '{{base_url}}' + path}}
    if not auth:
        item['request']['auth'] = {'type': 'noauth'}
    if body is not None:
        item['request']['header'] = [{'key': 'Content-Type', 'value': 'application/json'}]
        item['request']['body'] = {'mode': 'raw', 'raw': json.dumps(body, indent=2)}
    if capture:
        item['event'] = [{'listen': 'test', 'script': {'type': 'text/javascript', 'exec': capture}}]
    items.append(item)

request('Login', 'POST', '/api/auth/token/', {'username': '{{username}}', 'password': '{{password}}'},
        ['if (pm.response.code === 200) {', 'const data = pm.response.json();',
         'pm.collectionVariables.set("access_token", data.access);',
         'pm.collectionVariables.set("refresh_token", data.refresh);', '}'], auth=False)
request('Refresh token', 'POST', '/api/auth/token/refresh/', {'refresh': '{{refresh_token}}'},
        ['if (pm.response.code === 200) pm.collectionVariables.set("access_token", pm.response.json().access);'], auth=False)
for resource, singular, data in [
    ('contacts', 'contact', {'email': 'demo@example.com', 'first_name': 'Demo', 'company': 'Example'}),
    ('lists', 'list', {'name': 'Demo list'}),
    ('templates', 'template', {'name': 'Introduction', 'subject': 'Hello {{first_name}}', 'text_content': 'Welcome to {{company}}.'}),
    ('campaigns', 'campaign', {'name': 'Demo campaign', 'subject': 'Hello {{first_name}}', 'text_content': 'Welcome {{company}}', 'contact_lists': ['{{list_id}}']}),
]:
    base = '/api/email/' + resource + '/'
    detail = base + '{{' + singular + '_id}}/'
    request('Create ' + singular, 'POST', base, data,
            ['if (pm.response.code === 201) pm.collectionVariables.set("' + singular + '_id", pm.response.json().id);'])
    request('List ' + resource, 'GET', base)
    request('Get ' + singular, 'GET', detail)
    request('Update ' + singular, 'PATCH', detail, {'notes': 'Updated via API'} if singular == 'contact' else {'name': 'Updated name'})
    request('Delete ' + singular, 'DELETE', detail)
for action in ['add-contacts', 'remove-contacts']:
    request(action, 'POST', '/api/email/lists/{{list_id}}/' + action + '/', {'contact_ids': ['{{contact_id}}']})
request('Preview template', 'POST', '/api/email/templates/{{template_id}}/preview/', {'first_name': 'Ada', 'company': 'Example'})
request('Import contacts CSV', 'POST', '/api/email/contacts/import/')
items[-1]['request']['body'] = {'mode': 'formdata', 'formdata': [
    {'key': 'file', 'type': 'file', 'src': ''}, {'key': 'contact_list_id', 'type': 'text', 'value': '{{list_id}}'}]}
for action in ['prepare', 'send', 'cancel']:
    request(action.capitalize() + ' campaign', 'POST', '/api/email/campaigns/{{campaign_id}}/' + action + '/')
request('Test campaign (live email)', 'POST', '/api/email/campaigns/{{campaign_id}}/test/', {'email': '{{test_email}}'})
request('Schedule campaign', 'POST', '/api/email/campaigns/{{campaign_id}}/schedule/', {'scheduled_at': '{{scheduled_at}}'})
for action in ['analytics', 'recipients']:
    request('Campaign ' + action, 'GET', '/api/email/campaigns/{{campaign_id}}/' + action + '/')
request('Dashboard', 'GET', '/api/email/dashboard/')
request('Settings status', 'GET', '/api/email/settings/status/')
request('Unsubscribe', 'GET', '/api/email/unsubscribe/{{unsubscribe_token}}/', auth=False)
request('Resend webhook (requires signed raw body)', 'POST', '/api/email/webhooks/resend/', auth=False)
items[-1]['request']['description'] = 'Do not hand-edit a signed payload. Resend or the automated Svix tests supply the raw body and svix-id, svix-timestamp, svix-signature headers.'
collection = {
    'info': {'name': 'Bulkmailer backend', 'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
             'description': 'Run selected requests individually; send/test can deliver real email once configured. Do not run the full collection blindly.'},
    'auth': {'type': 'bearer', 'bearer': [{'key': 'token', 'value': '{{access_token}}', 'type': 'string'}]},
    'variable': [{'key': key, 'value': value} for key, value in {
        'base_url': 'http://localhost:8000', 'username': '', 'password': '', 'access_token': '', 'refresh_token': '',
        'contact_id': '', 'list_id': '', 'template_id': '', 'campaign_id': '', 'test_email': '',
        'scheduled_at': '2026-10-05T09:00:00Z', 'unsubscribe_token': ''}.items()],
    'item': items,
}
Path(__file__).with_name('Bulkmailer.postman_collection.json').write_text(json.dumps(collection, indent=2), encoding='utf-8')
