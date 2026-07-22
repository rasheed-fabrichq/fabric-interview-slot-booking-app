"""
Reset the database and seed the 16 case studies for this drive.

Deletes ALL jobs, candidates, bookings, slots and interview dates, then
creates the case studies below with their real job IDs. Slot
configuration, interview dates and candidates are added afterwards from
the admin UI.

The job IDs must match the ones on the interview platform: they are used
to build each candidate's interview link after they book.

Usage:
    python seed_jobs.py
"""
import sqlite3
import uuid

from config import DATABASE_PATH
from database import init_database, get_db_connection, create_job, get_all_jobs

# (job_id, case study name)
JOBS = [
    ('38901dc2-8836-48ba-b028-19def45b62bf', 'RFP Supplier Evaluation & Scoring Dashboard'),
    ('f9273b4c-028f-4e60-aab0-2877264b26af', 'Ocean Freight Spend Leakage & Recovery Agent'),
    ('6cf28384-180d-484c-9cdf-a82ecddced12', 'RFQ Scenario Builder & Bid Analyser'),
    ('245db9bd-dcfe-4643-b9a3-8e8cb011c643', 'Vendor Stock Availability & Fill-Rate Predictor'),
    ('39af67c7-8feb-4aad-8bc7-6cbdb8e11f58', 'Range Availability & Stock Norms Optimizer'),
    ('d26bbb3c-bae9-4a00-8bcf-69f2d0486065', 'Logistics Spend Baseline Builder Agent'),
    ('3b55a900-284f-412b-8761-de187902dd37', 'OEE Loss Tree & Predictive Maintenance Prioritizer'),
    ('5eeff5e2-30dd-40d5-9329-4d70b33c6aff', 'Trade Flow Supplier Discovery Engine'),
    ('dd095590-be51-4d29-9005-150f87315a8b', 'Tariff, Duty & Trade Scenario Optimizer'),
    ('4a8949d3-5f99-410b-be0e-069af8c9a44b', 'Commodity Buy / Hedge Decision Engine'),
    ('e2cf2c73-2ca9-4c81-9606-828b03fadb56', 'AI-Powered Negotiation Coach'),
    ('858625d6-f01d-4456-aeee-99f2d16dd0ac', 'Warehouse Intelligence & Opportunity Agent'),
    ('bd7a8993-14c9-4d29-ae73-000931c98355', 'Road Freight Lane Optimisation Agent'),
    ('a3573602-e196-4f68-b590-ac99c664ab47', 'OTIF Performance Intelligence Engine'),
    ('1d102491-fb35-449e-92e0-9865fd6c6194', 'Interactive Logistics Network Optimisation Agent'),
    ('b68005d4-b410-47a9-abb2-39ec9cece672', 'Should-Cost Model Builder'),
]


def wipe():
    """Delete all drive data. Order matters: bookings reference slots."""
    conn = get_db_connection()
    cursor = conn.cursor()

    counts = {}
    for table in ('bookings', 'candidates', 'slots', 'interview_dates',
                  'job_configs'):
        try:
            counts[table] = cursor.execute(
                f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = 0

    cursor.execute('DELETE FROM bookings')
    cursor.execute('DELETE FROM candidates')
    cursor.execute('DELETE FROM slots')
    cursor.execute('DELETE FROM interview_dates')
    cursor.execute('DELETE FROM job_configs')

    conn.commit()
    conn.close()
    return counts


def validate():
    """Catch a mistyped or duplicated entry before wiping anything."""
    problems = []

    ids = [j[0] for j in JOBS]
    names = [j[1] for j in JOBS]

    for job_id in ids:
        try:
            uuid.UUID(job_id, version=4)
        except (ValueError, AttributeError):
            problems.append(f'Not a valid UUID: {job_id}')

    for label, values in (('job ID', ids), ('name', names)):
        seen = set()
        for v in values:
            if v in seen:
                problems.append(f'Duplicate {label}: {v}')
            seen.add(v)

    return problems


def main():
    print(f'Database: {DATABASE_PATH}\n')

    problems = validate()
    if problems:
        print('Refusing to run -- fix these first:\n')
        for p in problems:
            print(f'  {p}')
        return

    # Make sure the schema exists before touching it
    init_database()

    removed = wipe()
    print('Cleared:')
    for table, count in removed.items():
        print(f'  {table:<16} {count}')

    print(f'\nCreating {len(JOBS)} case studies:\n')
    created = []
    for job_id, name in JOBS:
        result = create_job(job_id, name)
        if 'error' in result:
            print(f'  ERROR  {name}: {result["error"]}')
            continue
        created.append((job_id, name))
        print(f'  {job_id}  {name}')

    jobs = get_all_jobs()
    print(f'\nCreated {len(created)} of {len(JOBS)}; database now holds {len(jobs)}.')

    if len(created) != len(JOBS) or len(jobs) != len(JOBS):
        print('\nWARNING: count mismatch -- check the errors above.')
        return

    print('\nAs candidates will see them (alphabetical):\n')
    for i, name in enumerate(sorted(jobs.values(), key=str.lower), 1):
        print(f'  {i:2d}. {name}')

    print('\nNext: set the slot configuration, add interview dates,')
    print('initialize slots, then upload candidates.')


if __name__ == '__main__':
    main()
