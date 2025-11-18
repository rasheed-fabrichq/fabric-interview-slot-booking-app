"""
Configuration file for Multi-Job Interview Slot Booking Application
"""

# Job definitions (actual job UUIDs and names)
JOBS = {
    'e34e8e92-95ff-47f5-8e2f-86baa397c2a0': 'Software Development Engineer I',
    'd770069d-de27-4489-bdcc-0122ebf68a05': 'Data Scientist – I',
    '62566b89-8826-4140-8427-5413e4fa3ec7': 'Senior Associate – Business Management'
}

# Job slug mapping (slug -> job_id)
JOB_SLUGS = {
    'software-development-engineer-i': 'e34e8e92-95ff-47f5-8e2f-86baa397c2a0',
    'data-scientist-i': 'd770069d-de27-4489-bdcc-0122ebf68a05',
    'senior-associate-business-management': '62566b89-8826-4140-8427-5413e4fa3ec7'
}

# Reverse mapping (job_id -> slug)
JOB_ID_TO_SLUG = {v: k for k, v in JOB_SLUGS.items()}

def is_valid_job_id(job_id):
    """Check if job_id is valid"""
    return job_id in JOBS

def get_job_name(job_id):
    """Get job name from job_id"""
    return JOBS.get(job_id, 'Unknown Job')

def get_job_id_from_slug(slug):
    """Get job_id from slug"""
    return JOB_SLUGS.get(slug)

def get_job_slug(job_id):
    """Get slug from job_id"""
    return JOB_ID_TO_SLUG.get(job_id)

def is_valid_job_slug(slug):
    """Check if job slug is valid"""
    return slug in JOB_SLUGS

# Database configuration
DATABASE_PATH = 'instance/slots.db'

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
