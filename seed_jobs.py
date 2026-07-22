"""
Reset the database and seed the 16 jobs for this drive.

Deletes ALL jobs, candidates, bookings, slots and interview dates, then
creates the jobs below with freshly generated UUIDs. Slot configuration,
interview dates and candidates are added afterwards from the admin UI.

Usage:
    python seed_jobs.py
"""
import sqlite3
import uuid

from config import DATABASE_PATH
from database import init_database, get_db_connection, create_job, get_all_jobs

JOB_NAMES = [
    'AI-Powered Negotiation Coach',
    'Should-Cost Model Builder',
    'RFQ Scenario Builder & Bid Analyser',
    'Commodity Buy / Hedge Decision Engine',
    'Tariff, Duty & Trade Scenario Optimizer',
    'Trade Flow Supplier Discovery Engine',
    'Range Availability & Stock Norms Optimizer',
    'Vendor Stock Availability & Fill-Rate Predictor',
    'OEE Loss Tree & Predictive Maintenance Prioritizer',
    'OTIF Performance Intelligence Engine',
    'Road Freight Lane Optimisation Agent',
    'Warehouse Intelligence & Opportunity Agent',
    'RFP Supplier Evaluation & Scoring Dashboard',
    'Ocean Freight Spend Leakage & Recovery Agent',
    'Logistics Spend Baseline Builder Agent',
    'Interactive Logistics Network Optimisation Agent',
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


def main():
    print(f'Database: {DATABASE_PATH}\n')

    # Make sure the schema exists before touching it
    init_database()

    removed = wipe()
    print('Cleared:')
    for table, count in removed.items():
        print(f'  {table:<16} {count}')

    print(f'\nCreating {len(JOB_NAMES)} jobs:\n')
    created = []
    for name in JOB_NAMES:
        job_id = str(uuid.uuid4())
        result = create_job(job_id, name)
        if 'error' in result:
            print(f'  ERROR  {name}: {result["error"]}')
            continue
        created.append((job_id, name))
        print(f'  {job_id}  {name}')

    jobs = get_all_jobs()
    print(f'\nCreated {len(created)} jobs; database now holds {len(jobs)}.')
    print('\nNext: set the slot configuration, add interview dates,')
    print('initialize slots, then upload candidates.')


if __name__ == '__main__':
    main()
