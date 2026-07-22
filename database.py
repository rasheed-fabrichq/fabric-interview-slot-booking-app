"""
Database initialization and operations for Multi-Job Interview Slot Booking Application
"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from config import (
    DATABASE_PATH, DEFAULT_SLOT_CAPACITY, DEFAULT_SLOT_START_TIME,
    DEFAULT_SLOT_END_TIME, DEFAULT_SLOT_DURATION_MINUTES
)


def get_db_connection():
    """Get database connection with WAL mode enabled for concurrent writes"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    conn.execute('PRAGMA journal_mode=WAL')  # Enable Write-Ahead Logging
    conn.execute('PRAGMA foreign_keys=ON')  # Enable foreign key constraints
    return conn


@contextmanager
def get_db_transaction():
    """Context manager for database transactions with proper locking"""
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')  # Acquire write lock immediately
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_database():
    """Initialize database with required tables"""
    # Ensure instance directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Create job_configs table.
    # NOTE: scheduling (window, duration, capacity, dates) is NO LONGER
    # per-job -- it lives in the settings table and interview_dates,
    # because all jobs share one slot pool. A job row now only carries
    # its identity and its own booking on/off switch.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            job_name TEXT NOT NULL,
            booking_enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create interview_dates table.
    # NOTE: dates are SHARED ACROSS ALL JOBS, same as slots. One row per
    # date. slot_start_time/slot_end_time optionally override the global
    # window for that particular day.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            day_of_week TEXT NOT NULL,
            slot_start_time TEXT,
            slot_end_time TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create candidates table (with job_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            interview_link TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, job_id),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    # Create index on candidate_id for faster lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_candidate_id
        ON candidates(candidate_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_job_id_candidates
        ON candidates(job_id)
    ''')

    # Create slots table.
    # NOTE: slots are SHARED ACROSS ALL JOBS. There is exactly one row per
    # (date, start_time) and its booked_count is the total number of
    # interviews booked in that window regardless of which job the
    # candidate applied for. Capacity is the global 'slot_capacity'
    # setting, not job_configs.capacity_per_slot.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            booked_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, start_time)
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_date_slots
        ON slots(date)
    ''')

    # Create bookings table (with job_id, UNIQUE constraint per job)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            slot_id INTEGER NOT NULL,
            booked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            email_status TEXT DEFAULT NULL,
            email_sent_at DATETIME DEFAULT NULL,
            email_error TEXT DEFAULT NULL,
            UNIQUE(candidate_id, job_id),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id),
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        )
    ''')

    # Migrate existing bookings table to add email columns if missing
    cursor.execute("PRAGMA table_info(bookings)")
    booking_columns = [col[1] for col in cursor.fetchall()]
    if 'email_status' not in booking_columns:
        cursor.execute(
            'ALTER TABLE bookings ADD COLUMN email_status TEXT DEFAULT NULL')
    if 'email_sent_at' not in booking_columns:
        cursor.execute(
            'ALTER TABLE bookings ADD COLUMN email_sent_at DATETIME DEFAULT NULL')
    if 'email_error' not in booking_columns:
        cursor.execute(
            'ALTER TABLE bookings ADD COLUMN email_error TEXT DEFAULT NULL')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_booking_candidate
        ON bookings(candidate_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_booking_job
        ON bookings(job_id)
    ''')

    # Create settings table for global application configuration
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Initialize default settings.
    # slot_capacity / slot_start_time / slot_end_time / slot_duration_minutes
    # are GLOBAL: they apply to every job, because all jobs share one pool
    # of interview slots.
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('booking_enabled', 'true')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('slot_capacity', ?)
    ''', (str(DEFAULT_SLOT_CAPACITY),))

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('slot_start_time', ?)
    ''', (DEFAULT_SLOT_START_TIME,))

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('slot_end_time', ?)
    ''', (DEFAULT_SLOT_END_TIME,))

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value) VALUES ('slot_duration_minutes', ?)
    ''', (str(DEFAULT_SLOT_DURATION_MINUTES),))

    conn.commit()
    conn.close()

    print("Database initialized successfully!")


# ==================== GLOBAL SLOT CONFIGURATION ====================
#
# All jobs share one pool of interview slots, so the interview window,
# slot length and per-slot capacity are single global values rather than
# per-job settings.

def get_setting(key, default=None):
    """Read a single value from the settings table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()

    return row['value'] if row else default


def set_setting(key, value):
    """Write a single value to the settings table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, str(value), datetime.now()))

    conn.commit()
    conn.close()

    return {'success': True}


def get_slot_capacity():
    """Number of concurrent interviews allowed per slot, across ALL jobs."""
    return int(get_setting('slot_capacity', DEFAULT_SLOT_CAPACITY))


def get_slot_config():
    """Get the global slot configuration shared by every job."""
    return {
        'slot_start_time': get_setting('slot_start_time', DEFAULT_SLOT_START_TIME),
        'slot_end_time': get_setting('slot_end_time', DEFAULT_SLOT_END_TIME),
        'slot_duration_minutes': int(get_setting(
            'slot_duration_minutes', DEFAULT_SLOT_DURATION_MINUTES)),
        'capacity_per_slot': get_slot_capacity(),
    }


def update_slot_config(start_time, end_time, duration, capacity):
    """Update the global slot configuration.

    Does not touch slots that have already been initialized -- clear and
    re-initialize for changes to take effect.
    """
    set_setting('slot_start_time', start_time)
    set_setting('slot_end_time', end_time)
    set_setting('slot_duration_minutes', duration)
    set_setting('slot_capacity', capacity)

    return {'success': True}


# ==================== JOB CONFIGURATION FUNCTIONS ====================

def get_all_jobs():
    """Get all jobs as a dictionary {job_id: job_name}"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT job_id, job_name FROM job_configs ORDER BY created_at')
    jobs = {row['job_id']: row['job_name'] for row in cursor.fetchall()}
    conn.close()

    return jobs


def create_job(job_id, job_name):
    """Create a new job.

    Scheduling is global (see get_slot_config), so a job carries no
    window/duration/capacity of its own.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO job_configs (job_id, job_name, booking_enabled)
            VALUES (?, ?, 1)
        ''', (job_id, job_name))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'Job with this ID already exists'}


def get_job_config(job_id):
    """Get a job's details, merged with the global slot configuration.

    The slot fields are included so existing callers that read
    slot_duration_minutes / capacity_per_slot keep working; they are the
    same for every job.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    conn.close()

    if config:
        return {**dict(config), **get_slot_config()}
    return None


def get_all_job_configs():
    """Get all jobs, each merged with the global slot configuration."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM job_configs ORDER BY created_at')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    slot_config = get_slot_config()
    return [{**row, **slot_config} for row in rows]


def is_booking_enabled_for_job(job_id):
    """Check if booking is enabled for a specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT booking_enabled FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    result = cursor.fetchone()
    conn.close()

    if result:
        return result['booking_enabled'] == 1
    return False


def set_job_booking_enabled(job_id, enabled):
    """Enable or disable booking for a specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    value = 1 if enabled else 0

    cursor.execute('''
        UPDATE job_configs
        SET booking_enabled = ?, updated_at = ?
        WHERE job_id = ?
    ''', (value, datetime.now(), job_id))

    conn.commit()
    conn.close()

    return {'success': True, 'booking_enabled': enabled}


# ==================== JOB DATES FUNCTIONS ====================

def get_interview_dates():
    """Get all interview dates (shared by every job), with optional
    per-date time overrides."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT date, day_of_week, slot_start_time, slot_end_time
        FROM interview_dates
        ORDER BY substr(date, 7, 4), substr(date, 4, 2), substr(date, 1, 2)
    ''')

    dates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return dates


def add_interview_date(date, day_of_week, start_time=None, end_time=None):
    """Add an interview date, optionally overriding the global window."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO interview_dates
            (date, day_of_week, slot_start_time, slot_end_time)
            VALUES (?, ?, ?, ?)
        ''', (date, day_of_week, start_time, end_time))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'This date has already been added'}


def update_interview_date_times(date, start_time, end_time):
    """Override the interview window for one date."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE interview_dates
        SET slot_start_time = ?, slot_end_time = ?
        WHERE date = ?
    ''', (start_time, end_time, date))

    conn.commit()
    conn.close()

    return {'success': True}


def count_bookings_on_date(date):
    """How many bookings exist on a date, across all jobs.

    Used to warn before destructive actions.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) as count
        FROM bookings b
        JOIN slots s ON b.slot_id = s.id
        WHERE s.date = ?
    ''', (date,))

    count = cursor.fetchone()['count']
    conn.close()

    return count


def delete_interview_date(date, force=False):
    """Delete an interview date and its slots.

    Slots are shared across all jobs, so this destroys bookings belonging
    to every job on that date. Refuses to run when bookings exist unless
    force=True.
    """
    existing_bookings = count_bookings_on_date(date)
    if existing_bookings > 0 and not force:
        return {
            'error': (
                f'{existing_bookings} booking(s) already exist on {date}, '
                f'across all jobs. Deleting this date would cancel them. '
                f'Confirm the deletion to proceed.'
            ),
            'booking_count': existing_bookings,
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    # Bookings reference slots, so clear them first.
    cursor.execute('''
        DELETE FROM bookings
        WHERE slot_id IN (SELECT id FROM slots WHERE date = ?)
    ''', (date,))

    cursor.execute('DELETE FROM slots WHERE date = ?', (date,))
    cursor.execute('DELETE FROM interview_dates WHERE date = ?', (date,))

    conn.commit()
    conn.close()

    return {'success': True, 'bookings_deleted': existing_bookings}


# ==================== CANDIDATE FUNCTIONS ====================

def add_candidate(candidate_id, job_id, name, email, interview_link=None):
    """Add a new candidate to the database"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO candidates (candidate_id, job_id, name, email, interview_link, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (candidate_id, job_id, name, email, interview_link))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'Candidate already exists for this job'}


def get_candidate(candidate_id, job_id):
    """Get candidate details by candidate_id and job_id"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM candidates WHERE candidate_id = ? AND job_id = ?
    ''', (candidate_id, job_id))

    candidate = cursor.fetchone()
    conn.close()

    if candidate:
        return dict(candidate)
    return None


def update_candidate_status(candidate_id, job_id, status):
    """Update candidate status"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE candidates
        SET status = ?, updated_at = ?
        WHERE candidate_id = ? AND job_id = ?
    ''', (status, datetime.now(), candidate_id, job_id))

    conn.commit()
    conn.close()


def get_all_candidates(job_id=None):
    """Get all candidates with their details, optionally filtered by job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if job_id:
        cursor.execute('''
            SELECT
                c.candidate_id,
                c.job_id,
                c.name,
                c.email,
                c.interview_link,
                c.status,
                c.created_at,
                c.updated_at,
                jc.job_name
            FROM candidates c
            LEFT JOIN job_configs jc ON c.job_id = jc.job_id
            WHERE c.job_id = ?
            ORDER BY c.created_at DESC
        ''', (job_id,))
    else:
        cursor.execute('''
            SELECT
                c.candidate_id,
                c.job_id,
                c.name,
                c.email,
                c.interview_link,
                c.status,
                c.created_at,
                c.updated_at,
                jc.job_name
            FROM candidates c
            LEFT JOIN job_configs jc ON c.job_id = jc.job_id
            ORDER BY c.created_at DESC
        ''')

    candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return candidates


# ==================== SLOT FUNCTIONS ====================

def generate_slot_times(start_time, end_time, duration_minutes):
    """Generate slot times based on start, end, and duration"""
    slots = []
    start_hour, start_min = map(int, start_time.split(':'))
    end_hour, end_min = map(int, end_time.split(':'))

    # Convert to minutes since midnight
    current_minutes = start_hour * 60 + start_min
    end_minutes = end_hour * 60 + end_min

    # Handle case where end time is midnight (00:00) - means end of day
    if end_minutes == 0:
        end_minutes = 24 * 60

    while current_minutes < end_minutes:
        hour = (current_minutes // 60) % 24
        minute = current_minutes % 60
        slots.append(f"{hour:02d}:{minute:02d}")
        current_minutes += duration_minutes

    return slots


def initialize_slots():
    """Create the shared slot pool for every configured interview date.

    Slots are shared across all jobs, so this runs once globally rather
    than per job. Only adds slots for dates that do not have them yet, so
    it is safe to re-run after adding a new date.
    """
    config = get_slot_config()
    dates = get_interview_dates()

    if not dates:
        return {'error': 'No interview dates configured. Add a date first.'}

    conn = get_db_connection()
    cursor = conn.cursor()

    slots_inserted = 0
    dates_skipped = []

    for date_row in dates:
        date = date_row['date']
        day_of_week = date_row['day_of_week']

        # Skip dates that already have slots so existing bookings and
        # their booked_count are never disturbed.
        cursor.execute('SELECT COUNT(*) as count FROM slots WHERE date = ?', (date,))
        if cursor.fetchone()['count'] > 0:
            dates_skipped.append(date)
            continue

        # Per-date overrides fall back to the global window.
        slot_times = generate_slot_times(
            date_row['slot_start_time'] or config['slot_start_time'],
            date_row['slot_end_time'] or config['slot_end_time'],
            config['slot_duration_minutes']
        )

        for start_time in slot_times:
            cursor.execute('''
                INSERT INTO slots (date, day_of_week, start_time, booked_count)
                VALUES (?, ?, ?, 0)
            ''', (date, day_of_week, start_time))
            slots_inserted += 1

    conn.commit()
    conn.close()

    if slots_inserted == 0 and dates_skipped:
        return {
            'error': (
                'All configured dates already have slots. Clear them first '
                'if you want to regenerate with a new configuration.'
            )
        }

    return {
        'success': True,
        'slots_created': slots_inserted,
        'dates_skipped': dates_skipped,
    }


def get_slots_by_date(date):
    """Get the shared slots for a date, with availability.

    booked_count covers bookings from every job.
    """
    max_capacity = get_slot_capacity()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, date, day_of_week, start_time, booked_count,
               ? as max_capacity,
               MAX(0, ? - booked_count) as available
        FROM slots
        WHERE date = ?
        ORDER BY start_time
    ''', (max_capacity, max_capacity, date))

    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return slots


def get_all_slots():
    """Get every slot in the shared pool with booking statistics."""
    config = get_slot_config()
    max_capacity = config['capacity_per_slot']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, date, day_of_week, start_time, booked_count,
               ? as max_capacity,
               MAX(0, ? - booked_count) as available,
               ? as slot_duration_minutes
        FROM slots
        ORDER BY substr(date, 7, 4), substr(date, 4, 2), substr(date, 1, 2),
                 start_time
    ''', (max_capacity, max_capacity, config['slot_duration_minutes']))

    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return slots


def count_all_bookings():
    """Total bookings across every job and date."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) as count FROM bookings')
    count = cursor.fetchone()['count']
    conn.close()

    return count


def clear_all_slots(force=False):
    """Delete the entire shared slot pool, all bookings, and reset
    candidate statuses.

    Slots are shared, so there is no per-job version of this -- it wipes
    scheduling for all 16 jobs at once. Refuses to run while bookings
    exist unless force=True.
    """
    existing_bookings = count_all_bookings()
    if existing_bookings > 0 and not force:
        return {
            'error': (
                f'{existing_bookings} booking(s) exist across all jobs. '
                f'Clearing slots cancels every one of them and resets those '
                f'candidates to pending. Confirm to proceed.'
            ),
            'booking_count': existing_bookings,
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM bookings')
    cursor.execute('DELETE FROM slots')
    cursor.execute('''
        UPDATE candidates
        SET status = 'pending', updated_at = ?
        WHERE status != 'pending'
    ''', (datetime.now(),))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'bookings_deleted': existing_bookings,
        'message': 'All slots and bookings cleared.',
    }


# ==================== BOOKING FUNCTIONS ====================

def get_candidate_booking_for_job(candidate_id, job_id):
    """Check if candidate already has a booking for this specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) as count FROM bookings
        WHERE candidate_id = ? AND job_id = ?
    ''', (candidate_id, job_id))

    result = cursor.fetchone()
    conn.close()

    return result['count'] > 0


def book_slot(candidate_id, job_id, slot_id):
    """
    Book a slot for a candidate with transaction safety
    Returns: {'success': True} or {'error': 'message'}
    """
    try:
        with get_db_transaction() as conn:
            cursor = conn.cursor()

            # Check if candidate already has a booking for THIS JOB
            cursor.execute('''
                SELECT COUNT(*) as count FROM bookings
                WHERE candidate_id = ? AND job_id = ?
            ''', (candidate_id, job_id))

            if cursor.fetchone()['count'] > 0:
                return {'error': 'You have already booked a slot for this job.'}

            # Get slot details with lock
            cursor.execute('''
                SELECT id, booked_count, start_time, date
                FROM slots
                WHERE id = ?
            ''', (slot_id,))

            slot = cursor.fetchone()

            if not slot:
                return {'error': 'Invalid slot selected.'}

            # Capacity is global: booked_count already counts bookings
            # made from every job, so this check enforces the shared
            # concurrency limit across all of them.
            cursor.execute(
                "SELECT value FROM settings WHERE key = 'slot_capacity'")
            capacity_row = cursor.fetchone()
            max_capacity = (int(capacity_row['value'])
                            if capacity_row else DEFAULT_SLOT_CAPACITY)

            # Check availability
            if slot['booked_count'] >= max_capacity:
                return {'error': 'This slot has just been booked by other candidates. Please choose another available slot.'}

            # Increment booked count
            cursor.execute('''
                UPDATE slots
                SET booked_count = booked_count + 1
                WHERE id = ?
            ''', (slot_id,))

            # Create booking
            cursor.execute('''
                INSERT INTO bookings (candidate_id, job_id, slot_id, booked_at)
                VALUES (?, ?, ?, ?)
            ''', (candidate_id, job_id, slot_id, datetime.now()))

            # Update candidate status to 'booked'
            cursor.execute('''
                UPDATE candidates
                SET status = 'booked', updated_at = ?
                WHERE candidate_id = ? AND job_id = ?
            ''', (datetime.now(), candidate_id, job_id))

            return {
                'success': True,
                'slot_time': slot['start_time'],
                'slot_date': slot['date']
            }

    except sqlite3.IntegrityError as e:
        # Handle UNIQUE constraint violation
        if 'UNIQUE constraint failed' in str(e):
            return {'error': 'You have already booked a slot for this job.'}
        return {'error': f'An error occurred: {str(e)}'}
    except Exception as e:
        return {'error': f'An error occurred: {str(e)}'}


def get_booking_by_candidate_and_job(candidate_id, job_id):
    """Get booking details for a specific candidate and job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.name,
            c.email,
            jc.job_name,
            s.date,
            s.day_of_week,
            s.start_time,
            b.booked_at
        FROM bookings b
        JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
        JOIN slots s ON b.slot_id = s.id
        JOIN job_configs jc ON b.job_id = jc.job_id
        WHERE b.candidate_id = ? AND b.job_id = ?
    ''', (candidate_id, job_id))

    booking = cursor.fetchone()
    conn.close()

    if booking:
        return dict(booking)
    return None


def get_all_bookings(job_id=None):
    """Get all bookings with candidate and slot details, optionally filtered by job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if job_id:
        cursor.execute('''
            SELECT
                c.candidate_id,
                c.name,
                c.email,
                c.interview_link,
                jc.job_name,
                b.job_id,
                s.date,
                s.day_of_week,
                s.start_time,
                b.booked_at,
                b.email_status,
                b.email_sent_at,
                b.email_error
            FROM bookings b
            JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
            JOIN slots s ON b.slot_id = s.id
            JOIN job_configs jc ON b.job_id = jc.job_id
            WHERE b.job_id = ?
            ORDER BY b.booked_at
        ''', (job_id,))
    else:
        cursor.execute('''
            SELECT
                c.candidate_id,
                c.name,
                c.email,
                c.interview_link,
                jc.job_name,
                b.job_id,
                s.date,
                s.day_of_week,
                s.start_time,
                b.booked_at,
                b.email_status,
                b.email_sent_at,
                b.email_error
            FROM bookings b
            JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
            JOIN slots s ON b.slot_id = s.id
            JOIN job_configs jc ON b.job_id = jc.job_id
            ORDER BY b.booked_at
        ''')

    bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return bookings


def update_booking_email_status(candidate_id, job_id, status, error=None):
    """Update the confirmation email send status for a booking.

    status: 'sent' | 'failed'
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE bookings
        SET email_status = ?, email_sent_at = ?, email_error = ?
        WHERE candidate_id = ? AND job_id = ?
    ''', (status, datetime.now(), error, candidate_id, job_id))

    conn.commit()
    conn.close()


def get_booking_with_details(candidate_id, job_id):
    """Get full booking details needed for sending confirmation email."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.candidate_id,
            c.name,
            c.email,
            c.interview_link,
            jc.job_name,
            b.job_id,
            s.date,
            s.day_of_week,
            s.start_time,
            b.booked_at,
            b.email_status,
            b.email_sent_at,
            b.email_error
        FROM bookings b
        JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
        JOIN slots s ON b.slot_id = s.id
        JOIN job_configs jc ON b.job_id = jc.job_id
        WHERE b.candidate_id = ? AND b.job_id = ?
    ''', (candidate_id, job_id))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ==================== DASHBOARD & STATS ====================

def get_dashboard_stats():
    """Get statistics for admin dashboard (per-job)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get stats per job - using subqueries to avoid JOIN issues
    cursor.execute('''
        SELECT
            jc.job_id,
            jc.job_name,
            jc.booking_enabled,
            (SELECT COUNT(*) FROM candidates WHERE job_id = jc.job_id) as total_candidates,
            (SELECT COUNT(*) FROM bookings WHERE job_id = jc.job_id) as total_bookings,
            (SELECT COUNT(*) FROM candidates WHERE job_id = jc.job_id AND status = 'pending') as pending_count,
            (SELECT COUNT(*) FROM candidates WHERE job_id = jc.job_id AND status = 'clicked') as clicked_count,
            (SELECT COUNT(*) FROM candidates WHERE job_id = jc.job_id AND status = 'booked') as booked_count
        FROM job_configs jc
        ORDER BY jc.created_at
    ''')

    job_stats = [dict(row) for row in cursor.fetchall()]

    # Get overall totals
    cursor.execute('SELECT COUNT(*) as total FROM candidates')
    total_candidates = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) as total FROM bookings')
    total_bookings = cursor.fetchone()['total']

    conn.close()

    return {
        'total_candidates': total_candidates,
        'total_bookings': total_bookings,
        'job_stats': job_stats
    }


# ==================== GLOBAL SETTINGS ====================

def is_booking_enabled():
    """Check if booking is globally enabled"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT value FROM settings WHERE key = 'booking_enabled'
    ''')

    result = cursor.fetchone()
    conn.close()

    if result:
        return result['value'].lower() == 'true'
    return True  # Default to enabled if setting not found


def set_booking_enabled(enabled):
    """Enable or disable booking globally"""
    conn = get_db_connection()
    cursor = conn.cursor()

    value = 'true' if enabled else 'false'

    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES ('booking_enabled', ?, ?)
    ''', (value, datetime.now()))

    conn.commit()
    conn.close()

    return {'success': True, 'booking_enabled': enabled}


if __name__ == '__main__':
    # Initialize database when run directly
    init_database()
    print(f"Database created at: {DATABASE_PATH}")
