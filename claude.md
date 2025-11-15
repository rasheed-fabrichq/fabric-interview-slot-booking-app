# Interview Slot Booking Application - Requirements & Plan

## Project Overview
A Flask-based web application for managing interview slot bookings for campus drives across 9 IITs. Built for one-time use with quick deployment requirements.

## Core Requirements

### 1. Candidate Management
- Admin uploads candidate data: `candidate_id` (UUID), `name`, `email`
- Each candidate receives unique booking link with their `candidate_id`
- Candidate can book only once (enforced by status tracking)
- Name and email are pre-filled and read-only in booking form

### 2. Slot Booking Rules
- **10 candidates maximum per time slot ACROSS ALL COLLEGES** (shared capacity)
- Slots are 30-minute intervals
- **Full 24-hour availability**: Interviews are AI-conducted, so slots cover entire day (00:00 to 23:30)
- **48 slots per day** (00:00, 00:30, 01:00... 23:00, 23:30)
- Colleges divided by days:
  - **Saturday**: IIT Bombay, IIT Delhi, IIT Madras, IIT Roorkee
  - **Sunday**: IIT Guwahati, IIT Dhanbad, IIT Kharagpur (IIT KGP), IIT BHU, IIT Kanpur

### 3. Candidate Status Tracking
- `pending` → Initial state after upload
- `clicked` → When candidate opens booking link
- `booked` → After successful slot confirmation
- Once `booked`, candidate cannot access form again

### 4. Concurrent Booking Handling
- Multiple candidates can try to book same slot simultaneously
- Use database transactions with locking to prevent overbooking
- If slot fills up during booking attempt, show error: "This slot has just been booked by other candidates. Please choose another available slot."
- Allow retry with different slot

### 5. Data Storage Format
```
Booking record:
- Name: Rahul Sharma
- Email: rahul.sharma@iitb.ac.in
- College: IIT Bombay
- Start time: 14-11-2025 10:00
- End time: 14-11-2025 10:30
```

### 6. Data Export
- Download all bookings as Excel (.xlsx) or CSV (.csv)
- Each record = one confirmed booking

## Technical Architecture

### Tech Stack
- **Backend**: Flask (Python)
- **Database**: SQLite with WAL mode for concurrent writes
- **Frontend**: HTML + Jinja2 templates + Vanilla JavaScript + Bootstrap
- **Security**: Flask-WTF (CSRF protection), Session-based tokens, Status validation
- **No React** (simplicity for hosting)

### Security Features

The application implements multiple layers of security to prevent unauthorized bookings:

#### 1. Session-Based Booking Tokens
- **Unique token generated** when candidate accesses booking form
- Token stored in server-side session (not just in browser)
- Token must be included in booking confirmation request
- Token is single-use (marked as used after booking attempt)

#### 2. CSRF Protection
- Flask-WTF provides CSRF protection for all forms
- Prevents cross-site request forgery attacks

#### 3. Status-Based Access Control
- Candidates must have status 'clicked' to book (not 'pending')
- Direct API calls with 'pending' status are rejected
- Ensures candidate accessed the booking form legitimately

#### 4. Session Validation
- Candidate ID in request must match session
- Prevents booking on behalf of other candidates
- Session data cleared after successful booking

#### 5. Single-Use Token Enforcement
- Token can only be used once
- If booking fails (slot full), token is reset for retry
- Prevents replay attacks

#### 6. Comprehensive Validation Checks
1. All required fields present (candidate_id, slot_id, college_name, booking_token)
2. Token matches session token
3. Token not already used
4. Candidate ID matches session
5. Candidate exists in database
6. Candidate status is 'clicked' (not 'pending')
7. Candidate not already booked
8. College is valid

**Security Violations Return HTTP 403 (Forbidden)**

### Database Schema

#### candidates table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
candidate_id      TEXT UNIQUE NOT NULL        -- UUID from upload
name              TEXT NOT NULL
email             TEXT NOT NULL
status            TEXT DEFAULT 'pending'      -- pending/clicked/booked
created_at        DATETIME
updated_at        DATETIME
```

#### slots table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
day               TEXT NOT NULL               -- 'Saturday' or 'Sunday'
start_time        TEXT NOT NULL               -- 'HH:MM' format (e.g., '10:00')
date              TEXT NOT NULL               -- 'dd-MM-yyyy' format
booked_count      INTEGER DEFAULT 0           -- Current bookings (0-10)
max_capacity      INTEGER DEFAULT 10          -- Always 10
created_at        DATETIME
```

**IMPORTANT**: Each slot record represents ONE time slot shared across ALL colleges for that day. When any candidate from any college books this slot, `booked_count` increments.

#### bookings table
```sql
id                INTEGER PRIMARY KEY AUTOINCREMENT
candidate_id      TEXT NOT NULL               -- FK to candidates.candidate_id
slot_id           INTEGER NOT NULL            -- FK to slots.id
college_name      TEXT NOT NULL
booked_at         DATETIME
```

### Project Structure
```
interview-booking/
├── claude.md                 # This file - requirements & plan
├── app.py                    # Main Flask application
├── database.py               # Database initialization & models
├── config.py                 # Configuration (dates, colleges)
├── requirements.txt          # Python dependencies
├── templates/
│   ├── admin_upload.html     # Admin: Upload candidates
│   ├── admin_dashboard.html  # Admin: View statistics
│   ├── booking_form.html     # Candidate: Booking form
│   ├── already_booked.html   # Message: Already booked
│   ├── invalid_link.html     # Message: Invalid candidate_id
│   └── success.html          # Message: Booking confirmed
├── static/
│   ├── css/
│   │   └── style.css         # Custom styles
│   └── js/
│       └── booking.js        # Slot selection logic
└── instance/
    └── slots.db              # SQLite database (created at runtime)
```

## Application Routes

### Admin Routes
- `GET/POST /admin/upload` - Upload candidates CSV/Excel
  - Accepts file with columns: `candidate_id`, `name`, `email`
  - **Validation Rules:**
    - `candidate_id`: Must be a valid UUID (version 4)
    - `name`: Required, cannot be empty, max 100 characters
    - `email`: Must be valid email format (regex validated)
    - All three fields must be present in each row
  - Shows detailed error messages with row numbers and full row data for debugging
  - Shows first 50 validation errors
  - Creates candidate records with status='pending'

- `GET /admin/init-slots` - Initialize time slots for both days
  - Creates slot records based on SLOT_TIMES configuration
  - Run once before sending booking links

- `GET /admin/dashboard` - View booking statistics
  - Total candidates uploaded
  - Total bookings made
  - Slots utilization

- `GET /admin/export` - Download all bookings
  - Format: Excel (.xlsx) or CSV (.csv) - controlled by `?format=xlsx` or `?format=csv` query parameter
  - Includes: candidate_id, name, email, college, start_time, end_time, booked_at
  - Default format: Excel (.xlsx)

### Candidate Routes
- `GET /book?candidate_id=<uuid>` - Main booking form
  - Validates candidate_id exists
  - If status='booked' → redirect to already_booked.html
  - If status='pending' → update to 'clicked'
  - Pre-fill name & email (read-only fields)
  - Show college dropdown

- `POST /book/confirm` - Confirm slot booking
  - Receives: candidate_id, slot_id, college_name
  - Transaction-safe booking with SQLite locking
  - Validates slot availability
  - Creates booking record
  - Updates candidate status to 'booked'
  - Returns JSON: {success: true} or {error: "message"}

- `GET /api/slots?day=<Saturday|Sunday>` - Get available slots (JSON API)
  - Returns slots for specified day with availability
  - Format: `[{id: 1, start_time: '10:00', booked_count: 5, available: 5}, ...]`

## Key Implementation Details

### 1. College to Day Mapping
```python
COLLEGE_DAY_MAPPING = {
    'IIT Bombay': 'Saturday',
    'IIT Delhi': 'Saturday',
    'IIT Madras': 'Saturday',
    'IIT Roorkee': 'Saturday',
    'IIT Guwahati': 'Sunday',
    'IIT Dhanbad': 'Sunday',
    'IIT Kharagpur (IIT KGP)': 'Sunday',
    'IIT BHU': 'Sunday',
    'IIT Kanpur': 'Sunday'
}
```

### 2. Concurrent Booking Protection
```python
# Enable SQLite WAL mode for better concurrency
conn.execute('PRAGMA journal_mode=WAL')

# Use BEGIN IMMEDIATE for exclusive lock during booking
def book_slot(candidate_id, slot_id, college):
    conn.execute('BEGIN IMMEDIATE')
    try:
        # Get slot with lock
        slot = get_slot(slot_id)

        # Check availability
        if slot['booked_count'] >= 10:
            conn.rollback()
            return {'error': 'This slot has just been booked by other candidates. Please choose another available slot.'}

        # Increment booked count
        update_slot_count(slot_id)

        # Create booking
        create_booking(candidate_id, slot_id, college)

        # Update candidate status
        update_candidate_status(candidate_id, 'booked')

        conn.commit()
        return {'success': True}
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
```

### 3. Frontend Slot Display Logic (JavaScript)
```javascript
// On college selection
collegeDropdown.addEventListener('change', function() {
    const college = this.value;
    const day = COLLEGE_DAY_MAPPING[college];

    // Fetch slots for this day
    fetch(`/api/slots?day=${day}`)
        .then(response => response.json())
        .then(slots => {
            displaySlots(slots);
        });
});

// Display slots with visual indicators
function displaySlots(slots) {
    slots.forEach(slot => {
        const available = 10 - slot.booked_count;
        let cssClass = '';

        if (available === 0) {
            cssClass = 'slot-full';  // Gray, disabled
        } else if (available <= 3) {
            cssClass = 'slot-almost-full';  // Yellow/warning
        } else {
            cssClass = 'slot-available';  // Green
        }

        // Create slot card
        // Show: time, available count, clickable if not full
    });
}
```

### 4. Time Slot Configuration
```python
# Full 24-hour coverage with 30-minute intervals (48 slots per day)
# Generated programmatically: ['00:00', '00:30', '01:00', '01:30', ... '23:00', '23:30']
# Interviews are AI-conducted, so time is not a constraint
SLOT_TIMES = [f"{hour:02d}:{minute:02d}"
              for hour in range(24)
              for minute in [0, 30]]

# Interview dates
INTERVIEW_DATES = {
    'Saturday': '16-11-2025',
    'Sunday': '17-11-2025'
}
```

## User Flow Examples

### Admin Flow
1. Admin uploads CSV with candidates (candidate_id, name, email)
2. Admin initializes slots via `/admin/init-slots`
3. Admin sends emails with booking links: `https://domain.com/book?candidate_id=<UUID>`
4. Admin monitors dashboard for booking statistics
5. Admin exports bookings after 24 hours

### Candidate Flow
1. Candidate clicks link from email: `https://domain.com/book?candidate_id=abc123...`
2. Status updates: 'pending' → 'clicked'
3. Form loads with:
   - Name: **Riya Singh** (read-only)
   - Email: **riya.singh@iitd.ac.in** (read-only)
   - College: [Dropdown with 9 IITs]
4. Candidate selects "IIT Delhi" → System determines day = Saturday
5. Slots for Saturday display - all 48 slots from 00:00 to 23:30 (AI interview, 24-hour availability)
6. Candidate clicks "11:30" slot → clicks "Confirm"
7. Backend validates & books (if available)
8. Success message: "Your interview slot for 11:30 on Saturday has been confirmed."
9. Status updates: 'clicked' → 'booked'
10. Link becomes inactive for this candidate

### Concurrent Booking Scenario
- **10:00:00** - Candidate A views "10:30 AM" slot (9/10 booked)
- **10:00:01** - Candidate B views "10:30 AM" slot (9/10 booked)
- **10:00:02** - Candidate A clicks "Confirm" → **Success** (10/10)
- **10:00:03** - Candidate B clicks "Confirm" → **Error**: "This slot has just been booked by other candidates. Please choose another available slot."
- **10:00:05** - Candidate B selects "11:00 AM" → **Success**

## Dependencies
```
Flask==3.0.0
pandas==2.1.4
openpyxl==3.1.2
Werkzeug==3.0.1
```

## Deployment Options
1. **Railway** (Recommended) - Free tier, persistent storage, easy deployment
2. **Render** - Free tier available
3. **PythonAnywhere** - Free tier with limitations

## Development Checklist
- [ ] Create project structure
- [ ] Set up database with proper schema
- [ ] Implement admin upload (CSV/Excel)
- [ ] Implement slot initialization
- [ ] Implement booking form with validation
- [ ] Implement concurrent-safe slot booking
- [ ] Create all HTML templates
- [ ] Add JavaScript for dynamic slot selection
- [ ] Implement export functionality
- [ ] Style with Bootstrap
- [ ] Test concurrent booking scenarios
- [ ] Deploy to hosting platform

## Testing Scenarios
1. Upload 10 test candidates
2. Initialize slots
3. Open multiple booking links simultaneously
4. Try to book same slot from multiple browsers
5. Verify only 10 bookings allowed per slot
6. Verify error message when slot fills up
7. Verify candidate cannot book twice
8. Export data and validate format

## Important Notes
- **Slot capacity is SHARED across all colleges** - 10 total per time slot, not per college
- **SQLite WAL mode is critical** for handling concurrent writes
- **Transaction locking prevents race conditions** during booking
- **candidate_id is UUID** - secure, unpredictable
- **Status tracking prevents multiple bookings** by same candidate
- **One-time use application** - optimized for fast deployment, not long-term maintenance

## Configuration Before Deployment
1. Update `INTERVIEW_DATES` in config.py with actual dates
2. Change `ADMIN_PASSWORD` in config.py
3. Adjust `SLOT_TIMES` if different schedule needed
4. Verify college list and day assignments

## Post-Deployment Steps
1. Upload candidate list via admin panel
2. Initialize slots
3. Test booking flow with 2-3 test candidates
4. Send booking link emails to all candidates
5. Monitor dashboard during booking window
6. Export final data after 24 hours
