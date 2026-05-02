#!/usr/bin/env python3
"""
SQLite Data Cleaner + PocketBase Migration Pipeline
- Deduplicates jobs by content_hash (keeps most recent)
- Extracts location from cleaned_content
- Extracts company from title/content
- Normalizes salary_info
- Creates PocketBase collections (sources, companies, locations, categories, job_postings)
- Migrates data with relations
"""

import re
import sqlite3
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# Config
DB_PATH = 'deploy/data/jobs.db'
PB_URL = 'http://100.92.189.13:8020'
PB_ADMIN_EMAIL = 'kdoim100@gmail.com'
PB_ADMIN_PASSWORD = 'smh7K6zmqmSdGfa0qQZP'

# Location extraction patterns
LOCATION_PATTERNS = [
    r'위치\s*[:\-]?\s*([^\n]+?)(?=\n|$)',
    r'근무지역\s*[:\-]?\s*([^\n]+?)(?=\n|$)',
    r'근무\s*지역\s*[:\-]?\s*([^\n]+?)(?=\n|$)',
    r'지역\s*[:\-]?\s*([^\n]+?)(?=\n|$)',
    r'[Ll]ocation\s*[:\-]?\s*([^\n]+?)(?=\n|$)',
    r'([\uac00-\ud7af]+)\s*\(([A-Za-z\s]+),?\s*([A-Z]{2})',
    r'([A-Za-z\s\.]+),?\s*([A-Z]{2})(?:\s+\d{5})?',
    r'([\uac00-\ud7af\s]+)에서',
    r'([\uac00-\ud7af\s]+)에\s*위치한',
]

COMPANY_PATTERNS = [
    r'\[([^\]]{2,50})\]',
    r'([A-Za-z0-9\s&\.\-]+(?:Group|LLC|Inc|Corp|Ltd|Company|Co\.?|Center|Shop|Restaurant|Cafe|Market|Store))\s*에서',
    r'([A-Za-z0-9\s&\.\-]+)\s*에서\s*(?:구인|모집|채용)',
    r'([\uac00-\ud7af\s]+(?:회사|그룹|센터|샵|식당|카페|마켓|스토어|병원|클리닉))\s*에서',
]


def pb_auth():
    data = json.dumps({"identity": PB_ADMIN_EMAIL, "password": PB_ADMIN_PASSWORD}).encode('utf-8')
    req = urllib.request.Request(f"{PB_URL}/api/collections/_superusers/auth-with-password", data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))['token']


def pb_request(method, endpoint, token, data=None):
    url = f"{PB_URL}{endpoint}"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    body = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def pb_request_ignore_404(method, endpoint, token, data=None):
    try:
        return pb_request(method, endpoint, token, data)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def extract_location(text):
    if not text:
        return '', '', '', ''
    for pattern in LOCATION_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            match = matches[0]
            full_text = ' '.join(m.strip() for m in match if m) if isinstance(match, tuple) else match.strip()
            city, state, country = '', '', 'US'
            state_match = re.search(r',\s*([A-Z]{2})\b', full_text)
            if state_match:
                state = state_match.group(1)
                city_part = full_text[:state_match.start()].strip()
                city = re.sub(r'^[\uac00-\ud7af\s]+\(', '', city_part)
                city = re.sub(r'\)$', '', city).strip()
            else:
                if re.search(r'[\uac00-\ud7af]', full_text):
                    city = full_text
                    country = 'KR'
                else:
                    city = full_text
            return city, state, country, full_text
    return '', '', '', ''


def extract_company(title, content):
    text = f"{title or ''} {content or ''}"
    bracket_match = re.search(r'\[([^\]]{2,50})\]', text)
    if bracket_match:
        return bracket_match.group(1).strip()
    for pattern in COMPANY_PATTERNS[1:]:
        matches = re.findall(pattern, text)
        if matches:
            return matches[0].strip() if isinstance(matches[0], str) else matches[0][0].strip()
    return ''


def clean_salary(salary_text):
    if not salary_text:
        return ''
    parts = [p.strip() for p in salary_text.split(',')]
    seen = set()
    unique = []
    for p in parts:
        key = re.sub(r'\s+', '', p.lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return ', '.join(unique)


def get_or_create_record(token, collection, data, filter_query):
    try:
        result = pb_request("POST", f"/api/collections/{collection}/records", token, data)
        return result['id']
    except urllib.error.HTTPError as e:
        if e.code == 400:
            list_result = pb_request("GET", f"/api/collections/{collection}/records?filter={urllib.parse.quote(filter_query)}", token)
            if list_result.get('items'):
                return list_result['items'][0]['id']
        raise


def main():
    print(f"[{datetime.now()}] Starting SQLite -> PocketBase migration")
    
    # Phase 1: Clean SQLite data
    print("\n[Phase 1] Cleaning SQLite data...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("  1.1 Deduplicating by content_hash (keep most recent)...")
    cursor.execute("""
        DELETE FROM jobs
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY content_hash 
                    ORDER BY date_posted DESC, scraped_at DESC
                ) as rn
                FROM jobs
                WHERE is_spam = 0 AND is_job_seeker = 0
            ) WHERE rn = 1
        )
    """)
    print(f"    Deleted {cursor.rowcount} duplicate records")
    conn.commit()
    
    print("  1.2 Extracting locations from content...")
    cursor.execute("SELECT id, title, cleaned_content, location FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0")
    location_updates = []
    for row in cursor.fetchall():
        if not row['location'] or not row['location'].strip():
            city, state, country, full_text = extract_location(row['cleaned_content'])
            if full_text:
                location_updates.append((full_text, row['id']))
    if location_updates:
        cursor.executemany("UPDATE jobs SET location = ? WHERE id = ?", location_updates)
        conn.commit()
    print(f"    Extracted location for {len(location_updates)} records")
    
    print("  1.3 Extracting companies from title/content...")
    cursor.execute("SELECT id, title, cleaned_content, company FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0")
    company_updates = []
    for row in cursor.fetchall():
        if not row['company'] or not row['company'].strip():
            company = extract_company(row['title'], row['cleaned_content'])
            if company:
                company_updates.append((company, row['id']))
    if company_updates:
        cursor.executemany("UPDATE jobs SET company = ? WHERE id = ?", company_updates)
        conn.commit()
    print(f"    Extracted company for {len(company_updates)} records")
    
    print("  1.4 Cleaning salary info...")
    cursor.execute("SELECT id, salary_info FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0 AND salary_info != ''")
    salary_updates = []
    for row in cursor.fetchall():
        cleaned = clean_salary(row['salary_info'])
        if cleaned != row['salary_info']:
            salary_updates.append((cleaned, row['id']))
    if salary_updates:
        cursor.executemany("UPDATE jobs SET salary_info = ? WHERE id = ?", salary_updates)
        conn.commit()
    print(f"    Cleaned salary for {len(salary_updates)} records")
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0")
    final_count = cursor.fetchone()[0]
    print(f"\n  Final cleaned dataset: {final_count} unique job postings")
    
    # Phase 2: Authenticate and get collection IDs
    print("\n[Phase 2] Authenticating with PocketBase...")
    token = pb_auth()
    print("  Authenticated successfully")
    
    # Get existing collection IDs
    sources_coll = pb_request("GET", "/api/collections/sources", token)
    companies_coll = pb_request("GET", "/api/collections/companies", token)
    locations_coll = pb_request("GET", "/api/collections/locations", token)
    categories_coll = pb_request("GET", "/api/collections/categories", token)
    
    coll_ids = {
        'sources': sources_coll["id"],
        'companies': companies_coll["id"],
        'locations': locations_coll["id"],
        'categories': categories_coll["id"],
    }
    print(f"  Collection IDs: {coll_ids}")
    
    # Ensure job_postings exists with correct schema
    print("\n[Phase 3] Ensuring job_postings collection exists...")
    jp = pb_request_ignore_404("GET", "/api/collections/job_postings", token)
    if not jp:
        job_postings_coll = {
            "name": "job_postings",
            "type": "base",
            "fields": [
                {"name": "source", "type": "relation", "required": True, "collectionId": coll_ids['sources'], "options": {"cascadeDelete": False, "maxSelect": 1}},
                {"name": "company", "type": "relation", "collectionId": coll_ids['companies'], "options": {"cascadeDelete": False, "maxSelect": 1}},
                {"name": "location", "type": "relation", "collectionId": coll_ids['locations'], "options": {"cascadeDelete": False, "maxSelect": 1}},
                {"name": "category", "type": "relation", "collectionId": coll_ids['categories'], "options": {"cascadeDelete": False, "maxSelect": 1}},
                {"name": "external_id", "type": "text", "required": True},
                {"name": "title", "type": "text", "required": True},
                {"name": "cleaned_content", "type": "text"},
                {"name": "salary_info", "type": "text"},
                {"name": "contact_email", "type": "text"},
                {"name": "contact_phone", "type": "text"},
                {"name": "detail_url", "type": "url"},
                {"name": "date_posted", "type": "date"},
                {"name": "scraped_at", "type": "date"},
                {"name": "views", "type": "number"},
                {"name": "votes", "type": "number"},
                {"name": "is_active", "type": "bool", "required": True},
                {"name": "content_hash", "type": "text"},
                {"name": "quality_score", "type": "number"},
            ],
            "listRule": "",
            "viewRule": "",
        }
        pb_request("POST", "/api/collections", token, job_postings_coll)
        print("  + Created job_postings collection")
    else:
        print("  ~ job_postings collection exists")
    
    # Phase 4: Import data
    print("\n[Phase 4] Importing data to PocketBase...")
    
    print("  4.1 Importing sources...")
    source_map = {
        'gtksa': {'name': 'gtksa', 'url': 'https://gtksa.net', 'is_active': True},
        'workingus': {'name': 'workingus', 'url': 'https://www.workingus.com', 'is_active': True},
        'texasksa': {'name': 'texasksa', 'url': 'https://www.texasksa.org', 'is_active': True},
        'jobkoreausa': {'name': 'jobkoreausa', 'url': 'https://jobkoreausa.com', 'is_active': True},
    }
    source_id_map = {}
    for key, data in source_map.items():
        source_id_map[key] = get_or_create_record(token, 'sources', data, f"name='{data['name']}'")
    print(f"    Sources: {len(source_id_map)}")
    
    print("  4.2 Importing companies...")
    cursor.execute("SELECT DISTINCT trim(company) as company FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0 AND company != ''")
    company_id_map = {}
    for row in cursor.fetchall():
        company = row['company']
        company_id_map[company] = get_or_create_record(token, 'companies', {"name": company}, f"name='{company}'")
    print(f"    Companies: {len(company_id_map)}")
    
    print("  4.3 Importing locations...")
    cursor.execute("SELECT DISTINCT trim(location) as location FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0 AND location != ''")
    location_id_map = {}
    for row in cursor.fetchall():
        loc = row['location']
        city, state, country, full_text = extract_location(loc)
        if not full_text:
            full_text = loc
        data = {"city": city or None, "state": state or None, "country": country or 'US', "full_text": full_text}
        location_id_map[loc] = get_or_create_record(token, 'locations', data, f"full_text='{full_text}'")
    print(f"    Locations: {len(location_id_map)}")
    
    print("  4.4 Importing categories...")
    cursor.execute("SELECT DISTINCT trim(category) as category FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0 AND category != ''")
    category_id_map = {}
    for row in cursor.fetchall():
        cat = row['category']
        if cat:
            category_id_map[cat] = get_or_create_record(token, 'categories', {"name": cat}, f"name='{cat}'")
    print(f"    Categories: {len(category_id_map)}")
    
    print("  4.5 Importing job postings...")
    cursor.execute("SELECT * FROM jobs WHERE is_spam = 0 AND is_job_seeker = 0 ORDER BY date_posted DESC")
    
    imported = 0
    failed = 0
    for row in cursor.fetchall():
        row_dict = dict(row)
        
        job_data = {
            "source": source_id_map.get(row_dict['source_site']),
            "external_id": str(row_dict['external_id']),
            "title": row_dict['title'],
            "cleaned_content": row_dict['cleaned_content'],
            "detail_url": row_dict['detail_url'],
            "date_posted": row_dict['date_posted'],
            "scraped_at": row_dict['scraped_at'],
            "views": row_dict['views'] or 0,
            "votes": row_dict['votes'] or 0,
            "is_active": bool(row_dict['is_active']),
            "content_hash": row_dict['content_hash'],
            "quality_score": row_dict['quality_score'] or 100,
        }
        
        if row_dict.get('company') and row_dict['company'] in company_id_map:
            job_data["company"] = company_id_map[row_dict['company']]
        if row_dict.get('location') and row_dict['location'] in location_id_map:
            job_data["location"] = location_id_map[row_dict['location']]
        if row_dict.get('category') and row_dict['category'] in category_id_map:
            job_data["category"] = category_id_map[row_dict['category']]
        if row_dict.get('salary_info'):
            job_data["salary_info"] = row_dict['salary_info']
        if row_dict.get('contact_email'):
            job_data["contact_email"] = row_dict['contact_email']
        if row_dict.get('contact_phone'):
            job_data["contact_phone"] = row_dict['contact_phone']
        
        try:
            pb_request("POST", "/api/collections/job_postings/records", token, job_data)
            imported += 1
            if imported % 100 == 0:
                print(f"    ... imported {imported}")
        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"    ! Failed: {row_dict['title'][:50]} - {e}")
    
    print(f"    Imported {imported} job postings, {failed} failed")
    
    conn.close()
    print(f"\n[{datetime.now()}] Migration complete!")
    print(f"  Sources: {len(source_id_map)}")
    print(f"  Companies: {len(company_id_map)}")
    print(f"  Locations: {len(location_id_map)}")
    print(f"  Categories: {len(category_id_map)}")
    print(f"  Job postings: {imported}")


if __name__ == '__main__':
    main()
