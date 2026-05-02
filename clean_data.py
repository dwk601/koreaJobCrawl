#!/usr/bin/env python3
"""
Data Cleaning Pipeline for Korea Job Crawler
- Removes spam/non-job postings
- Removes 구직 (job-seeking) posts
- Cleans HTML content
- Extracts contact info (emails, phones)
- Extracts salary info
- Computes content hash for deduplication
"""

import re
import sqlite3
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime
import html

DB_PATH = 'deploy/data/jobs.db'

# Spam keywords to flag/remove
SPAM_KEYWORDS = [
    '보톡스', '필러', '실리프팅', '리쥬란', '마사지', '피부관리',
    '반영구', '속눈썹', '네일', '태닝', '왁싱', '다이어트',
    '성형', '시술', '클리닉', '미용실', '헤어샵',
    '도박', '카지노', '성인', '마사지샵', '스파',
]

# Job-seeking keywords
JOB_SEEKING_KEYWORDS = [
    '구직', '구직합니다', '일자리 찾습니다', '일 구합니다',
    'job seeking', 'looking for job', '일 구함',
]

# Salary patterns
SALARY_PATTERNS = [
    r'\$[\d,]+(?:\.\d+)?\s*(?:/hr|/hour| hourly| per hour)?',
    r'\$[\d,]+(?:\.\d+)?\s*(?:/~|이상|up to|starting|시작)?',
    r'연봉\s*[:\-]?\s*\$?[\d,]+',
    r'시급\s*[:\-]?\s*\$?[\d,]+',
    r'주\s*\$[\d,]+(?:\.\d+)?',
    r'월\s*\$[\d,]+(?:\.\d+)?',
    r'\$\d{1,2}(?:,\d{3})+',
    r'\$\d{2,3}\s*/\s*(?:hr|hour|주|week)',
]

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_PATTERN = r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'


def clean_html(raw_html):
    """Strip HTML tags and clean whitespace."""
    if not raw_html:
        return ''
    soup = BeautifulSoup(raw_html, 'html.parser')
    text = soup.get_text(separator='\n')
    text = html.unescape(text)
    # Remove excessive whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def extract_emails(text):
    """Extract all email addresses from text."""
    if not text:
        return ''
    emails = re.findall(EMAIL_PATTERN, text)
    return ', '.join(set(emails)) if emails else ''


def extract_phones(text):
    """Extract all phone numbers from text."""
    if not text:
        return ''
    phones = re.findall(PHONE_PATTERN, text)
    return ', '.join(set(phones)) if phones else ''


def extract_salary(text):
    """Extract salary information from text."""
    if not text:
        return ''
    salaries = []
    for pattern in SALARY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        salaries.extend(matches)
    return ', '.join(set(salaries)) if salaries else ''


def compute_hash(text):
    """Compute MD5 hash of cleaned text for deduplication."""
    if not text:
        return ''
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def is_spam(title, content):
    """Check if post is spam/non-job."""
    text = f"{title or ''} {content or ''}".lower()
    for keyword in SPAM_KEYWORDS:
        if keyword.lower() in text:
            return True
    return False


def is_job_seeking(title, content, category):
    """Check if post is from someone seeking a job (구직)."""
    text = f"{title or ''} {content or ''} {category or ''}".lower()
    for keyword in JOB_SEEKING_KEYWORDS:
        if keyword.lower() in text:
            return True
    # Also check if category is explicitly 구직
    if category and '구직' in category:
        return True
    return False


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"[{datetime.now()}] Starting data cleaning pipeline...")
    print(f"Database: {DB_PATH}")

    # 1. Add new columns if they don't exist
    print("\n[1/6] Adding new columns...")
    new_columns = [
        ('cleaned_content', 'TEXT'),
        ('content_hash', 'TEXT'),
        ('quality_score', 'INTEGER'),
        ('job_type', 'TEXT'),
        ('contact_email', 'TEXT'),
        ('contact_phone', 'TEXT'),
        ('salary_info', 'TEXT'),
        ('is_spam', 'BOOLEAN'),
        ('is_job_seeker', 'BOOLEAN'),
    ]
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
            print(f"  + Added column: {col_name}")
        except sqlite3.OperationalError:
            print(f"  ~ Column exists: {col_name}")

    conn.commit()

    # 2. Get all records
    print("\n[2/6] Fetching all records...")
    cursor.execute("SELECT id, title, content, category FROM jobs")
    rows = cursor.fetchall()
    total = len(rows)
    print(f"  Total records: {total}")

    # 3. Process each record
    print("\n[3/6] Processing records (cleaning, extracting)...")
    spam_count = 0
    job_seeker_count = 0
    processed = 0

    for row in rows:
        job_id, title, content, category = row

        cleaned = clean_html(content)
        content_hash = compute_hash(cleaned)
        emails = extract_emails(cleaned)
        phones = extract_phones(cleaned)
        salary = extract_salary(cleaned)
        spam = is_spam(title, cleaned)
        job_seeker = is_job_seeking(title, cleaned, category)

        # Quality score: 100 = good, 0 = spam/job-seeker
        quality = 100
        if spam:
            quality = 0
            spam_count += 1
        elif job_seeker:
            quality = 0
            job_seeker_count += 1

        cursor.execute("""
            UPDATE jobs SET
                cleaned_content = ?,
                content_hash = ?,
                quality_score = ?,
                contact_email = ?,
                contact_phone = ?,
                salary_info = ?,
                is_spam = ?,
                is_job_seeker = ?
            WHERE id = ?
        """, (cleaned, content_hash, quality, emails, phones, salary, spam, job_seeker, job_id))

        processed += 1
        if processed % 500 == 0:
            print(f"  ... processed {processed}/{total}")

    conn.commit()
    print(f"  Done. Spam flagged: {spam_count}, Job-seeker flagged: {job_seeker_count}")

    # 4. Remove spam and job-seeking posts
    print("\n[4/6] Removing spam and job-seeking posts...")
    cursor.execute("DELETE FROM jobs WHERE is_spam = 1")
    spam_deleted = cursor.rowcount
    cursor.execute("DELETE FROM jobs WHERE is_job_seeker = 1")
    seeker_deleted = cursor.rowcount
    conn.commit()
    print(f"  Deleted spam posts: {spam_deleted}")
    print(f"  Deleted job-seeking posts: {seeker_deleted}")

    # 5. Report stats
    print("\n[5/6] Final statistics...")
    cursor.execute("SELECT COUNT(*) FROM jobs")
    remaining = cursor.fetchone()[0]
    cursor.execute("SELECT source_site, COUNT(*) FROM jobs GROUP BY source_site")
    by_source = cursor.fetchall()
    cursor.execute("SELECT COUNT(DISTINCT content_hash) FROM jobs")
    unique_hashes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE contact_email != ''")
    with_email = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE contact_phone != ''")
    with_phone = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE salary_info != ''")
    with_salary = cursor.fetchone()[0]

    print(f"  Remaining job postings: {remaining}")
    print(f"  Unique content hashes: {unique_hashes}")
    print(f"  Posts with email: {with_email}")
    print(f"  Posts with phone: {with_phone}")
    print(f"  Posts with salary info: {with_salary}")
    print("\n  By source:")
    for source, count in by_source:
        print(f"    {source}: {count}")

    # 6. Sample output
    print("\n[6/6] Sample cleaned record:")
    cursor.execute("""
        SELECT title, cleaned_content, contact_email, contact_phone, salary_info
        FROM jobs WHERE contact_email != '' AND contact_phone != ''
        LIMIT 1
    """)
    sample = cursor.fetchone()
    if sample:
        print(f"  Title: {sample[0][:80]}...")
        print(f"  Emails: {sample[2]}")
        print(f"  Phones: {sample[3]}")
        print(f"  Salary: {sample[4]}")
        print(f"  Content preview:\n{sample[1][:300]}...")

    conn.close()
    print(f"\n[{datetime.now()}] Cleaning pipeline complete!")


if __name__ == '__main__':
    main()
