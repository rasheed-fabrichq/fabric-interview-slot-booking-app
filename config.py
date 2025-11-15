"""
Configuration file for Interview Slot Booking Application
"""

# College to Day mapping
COLLEGE_DAY_MAPPING = {
    'IIT Bombay': 'Saturday',
    'IIT Delhi': 'Saturday',
    'IIT Madras': 'Saturday',
    'IIT Roorkee': 'Saturday',
    'IIT Guwahati': 'Saturday',
    'IIT Dhanbad': 'Saturday',
    'IIT Kharagpur (IIT KGP)': 'Sunday',
    'IIT BHU': 'Sunday',
    'IIT Kanpur': 'Sunday'
}

# List of colleges for dropdown
COLLEGES = list(COLLEGE_DAY_MAPPING.keys())

# Interview dates (to be configured)
INTERVIEW_DATES = {
    'Saturday': '15-11-2025',  # dd-MM-yyyy format
    'Sunday': '16-11-2025'
}

# Slot configuration
SLOT_CAPACITY = 10  # Max candidates per slot across all colleges
SLOT_DURATION_MINUTES = 30

# Full 24-hour coverage with 30-minute intervals (48 slots per day)
# Interviews are AI-conducted, so time is not a constraint
SLOT_TIMES = [f"{hour:02d}:{minute:02d}"
              for hour in range(24)
              for minute in [0, 30]]

# Database configuration
DATABASE_PATH = 'instance/slots.db'

# Admin credentials (simple authentication)
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change this in production
