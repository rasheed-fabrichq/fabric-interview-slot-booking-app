"""
Configuration file for Multi-Job Interview Slot Booking Application
"""

# Job definitions (actual job UUIDs and names)
JOBS = {
    'fc4c9c14-208c-427a-be2e-4d0080f286d6': 'Software Development Engineer I',
    'b4f5ea74-a44a-4c93-a0f2-08abfaa337ed': 'Data Scientist – I',
    'a6c802c5-4861-4003-98c2-451069dff950': 'Senior Associate – Business Management'
}


def is_valid_job_id(job_id):
    """Check if job_id is valid"""
    return job_id in JOBS

def get_job_name(job_id):
    """Get job name from job_id"""
    return JOBS.get(job_id, 'Unknown Job')

# Database configuration
DATABASE_PATH = 'instance/slots.db'

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
