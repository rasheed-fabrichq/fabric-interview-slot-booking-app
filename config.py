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
DATABASE_PATH = 'instance/slots.db'

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
