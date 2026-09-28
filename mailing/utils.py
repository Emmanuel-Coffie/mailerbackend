import re
from html import escape

VARIABLES = ('first_name', 'last_name', 'company', 'position')

def render(content, data, html=False):
    def replace(match):
        key = match.group(1).strip()
        value = str(data.get(key) or '') if key in VARIABLES else ''
        return escape(value, quote=True) if html else value
    return re.sub(r'{{\s*([^{}]+)\s*}}', replace, content or '')

def render_content(subject, html_content, text_content, data):
    return {'subject': render(subject, data).replace('\r', '').replace('\n', ''),
            'html': render(html_content, data, html=True), 'text': render(text_content, data)}
