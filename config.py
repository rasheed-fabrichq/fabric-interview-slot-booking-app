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

import os

# Database configuration. Override with DATABASE_PATH in the environment.
# The default is a new file: instance/slots_shared.db belongs to the
# earlier "candidates pick their job" version of this branch, whose
# candidates table has no job_id and is refused on startup.
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'instance/slots_pool.db')

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

# Fallback base URL for a candidate's interview link. The link uploaded
# with the candidate is used when there is one; otherwise it is built as:
#   <INTERVIEW_LINK_BASE>/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>
# start_time/end_time are appended for the booked window either way.
INTERVIEW_LINK_BASE = 'https://app.fabrichq.ai/jobs'

# Timezone the interview schedule is expressed in. Slot dates and times
# are stored as naive local strings, so "is this slot in the past?" is
# answered against this zone rather than the server's clock -- a server
# running in UTC would otherwise keep past IST slots bookable.
TIMEZONE = 'Asia/Kolkata'

# How long before a slot starts to stop accepting bookings, in minutes.
# 0 means a slot is bookable right up to its start time.
BOOKING_CUTOFF_MINUTES = 0


def now_local():
    """Current time in the interview timezone."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


def build_interview_link(job_id, candidate_id):
    """Build an interview link for a candidate who has none stored."""
    return f'{INTERVIEW_LINK_BASE}/{job_id}/?candidate_id={candidate_id}'

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
