# Multi-Job Interview Slot Booking Application - Requirements & Documentation

## Project Overview
A Flask-based web application for managing interview slot bookings for multiple job positions. Built for FabricHQ with support for multiple independent job configurations.

## Core Requirements

### 1. Multi-Job Support
- **3 Independent Job Positions:**
  - Software Development Engineer I (UUID: `e34e8e92-95ff-47f5-8e2f-86baa397c2a0`)
  - Data Scientist – I (UUID: `d770069d-de27-4489-bdcc-0122ebf68a05`)
  - Senior Associate – Business Management (UUID: `62566b89-8826-4140-8427-5413e4fa3ec7`)
- Each job has independent configuration:
  - Custom time ranges (start time, end time)
  - Different slot durations (15, 30, 45, 60, 90, 120 minutes)
  - Different capacity per slot
  - Independent interview dates
  - Independent booking enable/disable controls

### 2. Candidate Management
- Admin uploads candidates per job with CSV containing:
  - `name` - Candidate's full name
  - `email` - Valid email address
  - `interview_link` - Format: `https://app.fabrichq.ai/jobs/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>`
- Interview link is parsed to extract:
  - `job_id` from URL path (`/jobs/<JOB_UUID>/`)
  - `candidate_id` from query parameter (`?candidate_id=<UUID>`)
- Each candidate receives **slot booking link**: `https://slot-booking.fabrichq.ai/book?candidate_id=<UUID>&job_id=<UUID>`
- **Multi-job booking support:**
  - Candidates CAN book slots for MULTIPLE different jobs
  - Candidates CANNOT book multiple slots for the SAME job (enforced by `UNIQUE(candidate_id, job_id)` constraint)

### 3. Slot Booking Rules
- **Per-job capacity** - Each job has configurable capacity per slot
- **Dynamic slot generation** - Slots created based on job configuration:
  - Start time and end time define the booking window
  - Slot duration determines interval length
  - Automatically generates all slots within the time range
- **Multiple interview dates** - Each job can have multiple interview dates
- **Two-step booking flow:**
  1. Select interview date
  2. Select time slot for that date
- **Back navigation** - Candidates can go back and change their date selection

### 4. Candidate Status Tracking
- `pending` → Initial state after upload
- `clicked` → When candidate opens booking link
- `booked` → After successful slot confirmation
- Once `booked` for a job, candidate cannot book again for that same job

### 5. Concurrent Booking Handling
- Multiple candidates can try to book same slot simultaneously
- Database transactions with locking prevent overbooking
- If slot fills up during booking attempt, show error message
- Allow retry with different slot

### 6. Link Formats

**Interview Link** (stored in database, used for data extraction):
```
https://app.fabrichq.ai/jobs/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>
```

**Slot Booking Link** (sent to candidates):
```
https://slot-booking.fabrichq.ai/book?candidate_id=<CANDIDATE_UUID>&job_id=<JOB_UUID>
```

### 7. Data Export
- Download all bookings as Excel (.xlsx) or CSV (.csv)
- Each record = one confirmed booking with job information
- Interview link includes start/end time parameters when exporting

## Technical Architecture

### Tech Stack
- **Backend**: Flask 3.0.0 (Python)
- **Database**: SQLite with WAL mode for concurrent writes
- **Frontend**: HTML + Jinja2 templates + Vanilla JavaScript + Bootstrap 5
- **Security**: Flask-WTF (CSRF protection), Session-based tokens, 9-layer validation
- **Data Processing**: Pandas, OpenPyXL

### Security Features

The application implements 9 layers of security validation:

#### Booking Confirmation Security Checks:
1. **Required fields validation** - All fields present (candidate_id, job_id, slot_id, booking_token)
2. **Token validation** - Token matches session token
3. **Token usage validation** - Token not already used
4. **Candidate ID validation** - Matches session candidate_id
5. **Job ID validation** - Matches session job_id
6. **Candidate existence** - Candidate exists in database
7. **Candidate status** - Status is 'clicked' (not 'pending')
8. **Duplicate booking check** - Candidate hasn't already booked for this job
9. **Job booking status** - Booking enabled for this job

**Security Violations Return HTTP 403 (Forbidden)**

### Database Schema

#### job_configs table
```sql
id                      INTEGER PRIMARY KEY AUTOINCREMENT
job_id                  TEXT UNIQUE NOT NULL           -- Job UUID
job_name                TEXT NOT NULL
slot_start_time         TEXT NOT NULL                  -- HH:MM format
slot_end_time           TEXT NOT NULL                  -- HH:MM format
slot_duration_minutes   INTEGER NOT NULL               -- 15, 30, 45, 60, 90, 120
capacity_per_slot       INTEGER NOT NULL               -- Max candidates per slot
booking_enabled         INTEGER DEFAULT 1              -- 0 or 1
created_at              DATETIME
updated_at              DATETIME
```

#### job_dates table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
job_id            TEXT NOT NULL                 -- FK to job_configs.job_id
date              TEXT NOT NULL                 -- dd-MM-yyyy format
day_of_week       TEXT NOT NULL                 -- e.g., 'Monday'
created_at        DATETIME
UNIQUE(job_id, date)
```

#### candidates table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
candidate_id      TEXT NOT NULL                 -- UUID from interview link
job_id            TEXT NOT NULL                 -- FK to job_configs.job_id
name              TEXT NOT NULL
email             TEXT NOT NULL
interview_link    TEXT                          -- Original interview link
status            TEXT DEFAULT 'pending'        -- pending/clicked/booked
created_at        DATETIME
updated_at        DATETIME
UNIQUE(candidate_id, job_id)                    -- Same person can apply to different jobs
```

#### slots table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
job_id            TEXT NOT NULL                 -- FK to job_configs.job_id
date              TEXT NOT NULL                 -- dd-MM-yyyy format
day_of_week       TEXT NOT NULL
start_time        TEXT NOT NULL                 -- HH:MM format
booked_count      INTEGER DEFAULT 0             -- Current bookings
created_at        DATETIME
UNIQUE(job_id, date, start_time)                -- One slot per job per date per time
```

#### bookings table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
candidate_id      TEXT NOT NULL
job_id            TEXT NOT NULL                 -- FK to job_configs.job_id
slot_id           INTEGER NOT NULL              -- FK to slots.id
booked_at         DATETIME
UNIQUE(candidate_id, job_id)                    -- One booking per candidate per job
```

#### settings table
```sql
key               TEXT PRIMARY KEY
value             TEXT NOT NULL
updated_at        DATETIME
```

### Project Structure
```
fabric-interview-slot-booking-app/
├── claude.md                       # This file - documentation
├── app.py                          # Main Flask application (848 lines)
├── database.py                     # Database functions (876 lines)
├── config.py                       # Job configurations
├── requirements.txt                # Python dependencies
├── templates/
│   ├── base.html                   # Base template with Bootstrap
│   ├── admin_login.html            # Admin login
│   ├── admin_dashboard.html        # Multi-job dashboard with per-job stats
│   ├── admin_upload.html           # Upload candidates per job
│   ├── admin_job_config.html       # Configure job settings
│   ├── admin_job_dates.html        # Manage interview dates per job
│   ├── admin_init_slots.html       # Initialize/clear slots per job
│   ├── admin_candidates.html       # View all candidates
│   ├── admin_bookings.html         # View all bookings
│   ├── booking_form.html           # Two-step booking form
│   ├── already_booked.html         # Already booked message
│   ├── booking_closed.html         # Booking closed message
│   └── invalid_link.html           # Invalid link message
├── static/
│   ├── css/
│   │   └── style.css               # Custom styles (date cards, etc.)
│   └── js/
│       └── booking.js              # Two-step booking logic (310 lines)
├── sample_data/
│   ├── candidates_sde.csv          # Sample for SDE position
│   ├── candidates_data_scientist.csv
│   └── candidates_business_mgmt.csv
└── instance/
    └── slots.db                    # SQLite database
```

## Application Routes

### Admin Routes

**Authentication:**
- `GET/POST /admin/login` - Admin login
- `GET /admin/logout` - Admin logout

**Dashboard:**
- `GET /admin/dashboard` - Multi-job dashboard
  - Overall statistics (total candidates, total bookings)
  - Per-job statistics (candidates, bookings, status breakdown)
  - Per-job pause/resume booking controls

**Candidate Upload:**
- `GET/POST /admin/upload` - Upload candidates CSV/Excel
  - Select job from dropdown
  - Upload file with columns: `name`, `email`, `interview_link`
  - **Validation Rules:**
    - `name`: Required, 1-100 characters
    - `email`: Valid email format
    - `interview_link`: Must be valid URL with format `https://app.fabrichq.ai/jobs/<JOB_UUID>/?candidate_id=<UUID>`
    - Both job_id and candidate_id must be valid UUIDs
    - job_id in URL must match selected job
  - Shows first 50 validation errors with row numbers
  - Creates candidate records with status='pending'

**Job Configuration:**
- `GET/POST /admin/job-config` - Configure job settings
  - Set start time, end time, slot duration, capacity per job
  - Warning: Changing config doesn't affect already initialized slots

**Date Management:**
- `GET/POST /admin/job-dates` - Manage interview dates
  - Add/delete dates per job
  - Deleting a date removes all associated slots and bookings

**Slot Management:**
- `GET/POST /admin/init-slots` - Initialize slots
  - Creates time slots based on job config and dates
  - Per-job initialization
- `POST /admin/clear-slots` - Clear all slots and bookings for a job

**Job Booking Control:**
- `POST /admin/toggle-job-booking/<job_id>` - Enable/disable booking per job

**Data Viewing:**
- `GET /admin/candidates` - View all candidates (with job filter)
- `GET /admin/bookings` - View all bookings (with job filter)

**Export:**
- `GET /admin/export` - Download bookings
  - Format: Excel (.xlsx) or CSV (.csv) via `?format=xlsx|csv` parameter
  - Includes: candidate_id, name, email, job_name, date, day_of_week, start_time, end_time, booked_at

### Candidate Routes

- `GET /book?candidate_id=<uuid>&job_id=<uuid>` - Booking form
  - Validates candidate_id and job_id
  - If status='booked' → show already_booked.html
  - If status='pending' → update to 'clicked'
  - Pre-fill name & email (read-only)
  - Two-step flow: date selection → slot selection

- `POST /book/confirm` - Confirm slot booking
  - 9-layer security validation
  - Transaction-safe booking with SQLite locking
  - Creates booking record
  - Updates candidate status to 'booked'
  - Returns JSON: {success: true, ...} or {error: "message"}

### API Routes

- `GET /api/job-dates?job_id=<uuid>` - Get available dates for a job
  - Returns: `[{date: '20-11-2025', day_of_week: 'Thursday'}, ...]`

- `GET /api/slots?job_id=<uuid>&date=<dd-mm-yyyy>` - Get available slots
  - Returns slots for specific job and date
  - Format: `[{id: 1, start_time: '10:00', booked_count: 5, capacity: 10, available: 5}, ...]`

## Key Implementation Details

### 1. Job Configuration (config.py)
```python
JOBS = {
    'e34e8e92-95ff-47f5-8e2f-86baa397c2a0': 'Software Development Engineer I',
    'd770069d-de27-4489-bdcc-0122ebf68a05': 'Data Scientist – I',
    '62566b89-8826-4140-8427-5413e4fa3ec7': 'Senior Associate – Business Management'
}

def is_valid_job_id(job_id):
    return job_id in JOBS

def get_job_name(job_id):
    return JOBS.get(job_id, 'Unknown Job')
```

### 2. Interview Link Parsing (app.py)
```python
def extract_candidate_id_and_job_from_url(interview_link):
    """
    Extract candidate_id and job_id from interview link URL
    Format: https://app.fabrichq.ai/jobs/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>
    Returns: (candidate_id, job_id, error_message) tuple
    """
    # Extract job_id from URL path: /jobs/<JOB_UUID>/
    job_path_match = re.search(r'/jobs/([a-f0-9\-]+)/?', url_str, re.IGNORECASE)
    job_id = job_path_match.group(1).strip()

    # Extract candidate_id from query parameter
    candidate_match = re.search(r'[?&]candidate_id=([^&]+)', url_str)
    candidate_id = candidate_match.group(1).strip()

    # Validate both are valid UUIDs
    # Validate job_id exists in system
```

### 3. Concurrent Booking Protection (database.py)
```python
# Enable SQLite WAL mode
conn.execute('PRAGMA journal_mode=WAL')

def book_slot(candidate_id, job_id, slot_id):
    """Transaction-safe slot booking"""
    conn = get_db_connection()
    conn.execute('BEGIN IMMEDIATE')  # Exclusive lock

    try:
        # Check if already booked for this job
        existing = get_booking_by_candidate_and_job(candidate_id, job_id)
        if existing:
            return {'error': 'Already booked for this job'}

        # Get slot with lock
        slot = get_slot(slot_id)
        config = get_job_config(job_id)

        # Check capacity
        if slot['booked_count'] >= config['capacity_per_slot']:
            conn.rollback()
            return {'error': 'Slot is full'}

        # Increment count, create booking, update status
        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
```

### 4. Dynamic Slot Generation (database.py)
```python
def generate_slot_times(start_time, end_time, duration_minutes):
    """Generate slot times based on configuration"""
    slots = []
    current = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')

    # Handle midnight crossing (e.g., 08:00 to 00:00 = full day)
    if end <= current:
        end += timedelta(days=1)

    while current < end:
        slots.append(current.strftime('%H:%M'))
        current += timedelta(minutes=duration_minutes)

    return slots

def initialize_slots_for_job(job_id):
    """Create slots for all dates configured for this job"""
    config = get_job_config(job_id)
    dates = get_job_dates(job_id)
    slot_times = generate_slot_times(
        config['slot_start_time'],
        config['slot_end_time'],
        config['slot_duration_minutes']
    )

    for date_info in dates:
        for start_time in slot_times:
            # Create slot record
            insert_slot(job_id, date_info['date'], date_info['day_of_week'], start_time)
```

### 5. Two-Step Booking Flow (booking.js)
```javascript
// Step 1: Load and display dates
function loadDates() {
    fetch(`/api/job-dates?job_id=${jobId}`)
        .then(response => response.json())
        .then(dates => displayDates(dates));
}

// Step 2: When date selected, load slots
function selectDate(date, dayOfWeek) {
    selectedDate = date;
    dateSelectionContainer.classList.add('d-none');
    loadSlots(jobId, date);
}

// Load slots for selected date
function loadSlots(jobId, date) {
    fetch(`/api/slots?job_id=${jobId}&date=${date}`)
        .then(response => response.json())
        .then(slots => displaySlots(slots));
}

// Back to dates button
backToDatesBtn.addEventListener('click', function() {
    // Reset selections, show date selection again
    dateSelectionContainer.classList.remove('d-none');
    slotContainer.classList.add('d-none');
});
```

## User Flow Examples

### Admin Flow
1. Login to admin dashboard
2. Upload candidates for each job position (CSV with name, email, interview_link)
3. Configure job settings (time range, duration, capacity)
4. Add interview dates for each job
5. Initialize slots for each job
6. Monitor per-job statistics on dashboard
7. Pause/resume booking per job as needed
8. Export booking data

### Candidate Flow
1. Receives slot booking link: `https://slot-booking.fabrichq.ai/book?candidate_id=<UUID>&job_id=<UUID>`
2. Opens link, status updates: 'pending' → 'clicked'
3. Sees pre-filled name and email (read-only)
4. **Step 1:** Selects interview date (e.g., "Thursday, 20-11-2025")
   - Can click "Back to Dates" to change selection
5. **Step 2:** Selects time slot (e.g., "10:00 AM - 11:00 AM")
   - Green = Available
   - Yellow = Almost Full
   - Gray = Full (disabled)
6. Clicks "Confirm Booking"
7. Success message displays booking details
8. Status updates: 'clicked' → 'booked'
9. Cannot book again for this job (can book for other jobs with different links)

### Concurrent Booking Scenario
- **10:00:00** - Candidate A views "10:30" slot (19/20 booked)
- **10:00:01** - Candidate B views "10:30" slot (19/20 booked)
- **10:00:02** - Candidate A clicks "Confirm" → **Success** (20/20)
- **10:00:03** - Candidate B clicks "Confirm" → **Error**: "Slot is full"
- **10:00:05** - Candidate B selects "11:00" → **Success**

## Sample Data

Three sample CSV files provided in `sample_data/`:

**candidates_sde.csv** - Software Development Engineer I
```csv
name,email,interview_link
Rajesh Kumar,rajesh.kumar@example.com,https://app.fabrichq.ai/jobs/e34e8e92-95ff-47f5-8e2f-86baa397c2a0/?candidate_id=a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d
```

**candidates_data_scientist.csv** - Data Scientist – I

**candidates_business_mgmt.csv** - Senior Associate – Business Management

## Dependencies
```
Flask==3.0.0
Flask-WTF==1.2.1
pandas==2.1.4
openpyxl==3.1.2
Werkzeug==3.0.1
```

## Setup and Deployment

### Initial Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Initialize database: `python database.py`
3. Run application: `python app.py`
4. Access admin at: `http://localhost:5000/admin/login`
   - Default credentials: `admin@fabrichq.ai` / `fabrichqai`

### Database Initialization
The database is automatically seeded with:
- 3 job configurations (SDE, Data Scientist, Business Management)
- Default settings (booking enabled)
- No dates or slots (must be configured by admin)

### Configuration
**Admin Credentials** (config.py):
```python
ADMIN_USERNAME = 'admin@fabrichq.ai'
ADMIN_PASSWORD = 'fabrichqai'  # Change in production
```

**Database Path** (config.py):
```python
DATABASE_PATH = 'instance/slots.db'
```

## Important Notes

### Multi-Job Architecture
- Each job is completely independent
- Different configurations don't affect each other
- Candidates can book slots for multiple jobs
- One booking per candidate per job (enforced at database level)

### Security
- CSRF tokens required on all admin forms
- Session-based booking tokens (single-use)
- 9-layer validation on booking confirmation
- Foreign key constraints ensure data integrity
- WAL mode prevents concurrent booking conflicts

### Link Format Distinction
- **Interview Link**: Stored in database, parsed for candidate/job IDs
- **Slot Booking Link**: Sent to candidates, uses query parameters

### Database Schema Fix
- Removed invalid foreign key constraint: `FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)`
- Reason: `candidate_id` is not unique in candidates table (part of composite key)
- Integrity maintained by: `UNIQUE(candidate_id, job_id)` constraints in both candidates and bookings tables

### CSRF Protection
All POST forms include CSRF token:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

## Testing Checklist
- [ ] Upload candidates for each job
- [ ] Configure job settings (time, duration, capacity)
- [ ] Add interview dates for each job
- [ ] Initialize slots for each job
- [ ] Test booking flow (date selection → slot selection)
- [ ] Test "Back to Dates" functionality
- [ ] Test concurrent booking for same slot
- [ ] Verify one candidate cannot book same job twice
- [ ] Verify candidate can book different jobs
- [ ] Test pause/resume booking per job
- [ ] Test data export (Excel and CSV)
- [ ] Verify all CSRF tokens working

## Admin Dashboard Features

### Overall Statistics
- Total candidates (across all jobs)
- Total bookings (across all jobs)

### Per-Job Cards
- Job name with active/paused status badge
- Candidates count
- Bookings count
- Pending count
- Status breakdown (progress bar showing pending/clicked/booked)
- Pause/Resume booking button

### Quick Actions
- Upload Candidates
- Job Configuration
- Manage Dates
- Initialize Slots
- View Candidates
- View Bookings
- Export Data (Excel/CSV)

## Future Enhancements
- Email notifications for booking confirmations
- Candidate rescheduling (within same job)
- Bulk operations (pause all jobs, export per job)
- Admin analytics (booking trends, peak times)
- WhatsApp integration for booking links
