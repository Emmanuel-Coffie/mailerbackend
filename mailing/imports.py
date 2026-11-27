"""Bounded spreadsheet parsing and deterministic, inspectable column detection."""
import csv
import io
import re
from zipfile import BadZipFile, ZipFile
from django.conf import settings
from rest_framework.exceptions import ValidationError

ALIASES = {
    'email': ('email', 'emailaddress', 'emailid', 'e-mail'),
    'first_name': ('firstname', 'givenname', 'forename'),
    'last_name': ('lastname', 'surname', 'familyname'),
    'name': ('name', 'fullname', 'contactname'),
    'company': ('company', 'companyname', 'organization', 'organisation', 'business'),
    'phone': ('phone', 'phonenumber', 'mobile', 'telephone'),
    'position': ('position', 'jobtitle', 'title', 'role'),
    'group': ('group', 'groups', 'segment', 'segments', 'list', 'lists', 'category', 'tags'),
}

def normalize(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())

def read_contacts(upload):
    if upload.size > settings.CSV_MAX_BYTES:
        raise ValidationError('The file exceeds the upload size limit.')
    suffix = upload.name.lower().rsplit('.', 1)[-1]
    content = upload.read()
    try:
        if suffix == 'xlsx':
            from openpyxl import load_workbook
            with ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 50_000_000:
                    raise ValidationError('The expanded workbook is too large. Split it into smaller files.')
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                sheets = []
                for sheet in book.worksheets:
                    rows = []
                    for row in sheet.iter_rows(values_only=True):
                        if len(rows) >= 10001 or len(row) > 100:
                            raise ValidationError('Use at most 10,000 contacts and 100 columns per sheet.')
                        rows.append(row)
                    sheets.append((sheet.title, rows))
            finally:
                book.close()
        elif suffix == 'csv':
            text = content.decode('utf-8-sig')
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
            except csv.Error:
                dialect = csv.excel
            sheets = [('', list(csv.reader(io.StringIO(text), dialect, strict=True)))]
        else:
            raise ValidationError('Choose an Excel .xlsx or UTF-8 .csv file.')
    except (UnicodeDecodeError, csv.Error, BadZipFile, ValueError, KeyError, OSError):
        raise ValidationError('This file could not be read. Save it as .xlsx or UTF-8 CSV and try again.')
    records, detected = [], []
    for title, rows in sheets:
        rows = [row for row in rows if any(str(cell or '').strip() for cell in row)]
        if not rows:
            continue
        headers = [normalize(cell) for cell in rows[0]]
        mapping = {}
        for field, aliases in ALIASES.items():
            indexes = [i for i, header in enumerate(headers) if header in {normalize(a) for a in aliases}]
            if len(indexes) > 1:
                raise ValidationError(f'Multiple columns match {field}. Keep one column per contact field.')
            if indexes:
                mapping[field] = indexes[0]
        if 'email' not in mapping:
            raise ValidationError(f'{title or "File"}: add a column named Email or Email address.')
        detected.append({'sheet': title or 'CSV', 'fields': list(mapping)})
        for row in rows[1:]:
            values = {field: str(row[index] if index < len(row) and row[index] is not None else '').strip() for field, index in mapping.items()}
            if values.get('name') and not values.get('first_name'):
                parts = values['name'].split(None, 1)
                values['first_name'] = parts[0]
                values.setdefault('last_name', parts[1] if len(parts) > 1 else '')
            values['_sheet'] = title
            records.append(values)
            if len(records) > 10000:
                raise ValidationError('Import at most 10,000 contacts at a time.')
    if not detected:
        raise ValidationError('The file is empty. Add a header row and contact details.')
    return records, detected
