"""
Configuration file for Multi-Job Interview Slot Booking Application
"""


def get_jobs():
    """Get all jobs from database (lazy import to avoid circular dependency)"""
    from database import get_all_jobs
    return get_all_jobs()


def is_valid_job_id(job_id):
    """Check if job_id is valid"""
    jobs = get_jobs()
    return job_id in jobs


def get_job_name(job_id):
    """Get job name from job_id"""
    jobs = get_jobs()
    return jobs.get(job_id, 'Unknown Job')

# Database configuration
# Shared-slot-pool schema. The previous per-job schema lives in
# instance/slots.db and is left untouched for rollback.
DATABASE_PATH = 'instance/slots_shared.db'

# Number of interviews that can run concurrently in a single time slot,
# counted across ALL jobs. Used as the seed value for the
# 'slot_capacity' row in the settings table on a fresh database;
# after that, change it from the admin Job Configuration page.
DEFAULT_SLOT_CAPACITY = 15

# Default interview window and slot length, shared by every job.
# Seeded into the settings table on a fresh database; edit them
# afterwards from the admin Slot Configuration page.
DEFAULT_SLOT_START_TIME = '10:00'
DEFAULT_SLOT_END_TIME = '18:00'
DEFAULT_SLOT_DURATION_MINUTES = 30

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
