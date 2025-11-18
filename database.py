"""
Database initialization and operations for Multi-Job Interview Slot Booking Application
"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH


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

    # Create job_configs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            job_name TEXT NOT NULL,
            slot_start_time TEXT NOT NULL,
            slot_end_time TEXT NOT NULL,
            slot_duration_minutes INTEGER NOT NULL,
            capacity_per_slot INTEGER NOT NULL,
            booking_enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create job_dates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, date),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
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

    # Create slots table (with job_id and date)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            booked_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, date, start_time),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_job_id_slots
        ON slots(job_id)
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
            UNIQUE(candidate_id, job_id),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id),
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        )
    ''')

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

    # Initialize default settings
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('booking_enabled', 'true')
    ''')

    # Seed initial job configurations
    seed_job_configs(cursor)

    conn.commit()
    conn.close()

    print("Database initialized successfully!")


def seed_job_configs(cursor):
    """Seed initial job configurations"""
    jobs = [
        {
            'job_id': 'fc4c9c14-208c-427a-be2e-4d0080f286d6',
            'job_name': 'Software Development Engineer I',
            'start_time': '08:00',
            'end_time': '00:00',
            'duration': 60,
            'capacity': 20,
            'dates': []  # Dates will be added by admin
        },
        {
            'job_id': 'b4f5ea74-a44a-4c93-a0f2-08abfaa337ed',
            'job_name': 'Data Scientist – I',
            'start_time': '08:00',
            'end_time': '00:00',
            'duration': 60,
            'capacity': 15,
            'dates': []  # Dates will be added by admin
        },
        {
            'job_id': 'a6c802c5-4861-4003-98c2-451069dff950',
            'job_name': 'Senior Associate – Business Management',
            'start_time': '08:00',
            'end_time': '00:00',
            'duration': 30,
            'capacity': 15,
            'dates': []  # Dates will be added by admin
        }
    ]

    for job in jobs:
        # Insert job config (ignore if already exists)
        cursor.execute('''
            INSERT OR IGNORE INTO job_configs
            (job_id, job_name, slot_start_time, slot_end_time,
             slot_duration_minutes, capacity_per_slot, booking_enabled)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (job['job_id'], job['job_name'], job['start_time'],
              job['end_time'], job['duration'], job['capacity']))

        # Add dates for each job
        for date, day in job['dates']:
            cursor.execute('''
                INSERT OR IGNORE INTO job_dates (job_id, date, day_of_week)
                VALUES (?, ?, ?)
            ''', (job['job_id'], date, day))


# ==================== JOB CONFIGURATION FUNCTIONS ====================

def get_job_config(job_id):
    """Get job configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    conn.close()

    if config:
        return dict(config)
    return None


def update_job_config(job_id, start_time, end_time, duration, capacity):
    """Update job configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE job_configs
        SET slot_start_time = ?,
            slot_end_time = ?,
            slot_duration_minutes = ?,
            capacity_per_slot = ?,
            updated_at = ?
        WHERE job_id = ?
    ''', (start_time, end_time, duration, capacity, datetime.now(), job_id))

    conn.commit()
    conn.close()

    return {'success': True}


def get_all_job_configs():
    """Get all job configurations"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM job_configs ORDER BY created_at')
    configs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return configs


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

def get_job_dates(job_id):
    """Get all dates for a specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT date, day_of_week FROM job_dates
        WHERE job_id = ?
        ORDER BY date
    ''', (job_id,))

    dates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return dates


def add_job_date(job_id, date, day_of_week):
    """Add a new interview date for a job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO job_dates (job_id, date, day_of_week)
            VALUES (?, ?, ?)
        ''', (job_id, date, day_of_week))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'This date already exists for this job'}


def delete_job_date(job_id, date):
    """Delete an interview date for a job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # First delete any slots for this date
    cursor.execute('''
        DELETE FROM slots WHERE job_id = ? AND date = ?
    ''', (job_id, date))

    # Then delete the date
    cursor.execute('''
        DELETE FROM job_dates WHERE job_id = ? AND date = ?
    ''', (job_id, date))

    conn.commit()
    conn.close()

    return {'success': True}


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


def initialize_slots_for_job(job_id):
    """Initialize all time slots for a specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get job configuration
    cursor.execute('''
        SELECT slot_start_time, slot_end_time, slot_duration_minutes
        FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    if not config:
        conn.close()
        return {'error': 'Job configuration not found'}

    # Get all dates for this job
    cursor.execute('''
        SELECT date, day_of_week FROM job_dates WHERE job_id = ?
    ''', (job_id,))

    dates = cursor.fetchall()
    if not dates:
        conn.close()
        return {'error': 'No dates configured for this job'}

    # Check if slots already exist for this job
    cursor.execute('SELECT COUNT(*) as count FROM slots WHERE job_id = ?', (job_id,))
    count = cursor.fetchone()['count']

    if count > 0:
        conn.close()
        return {'error': f'Slots already initialized for this job. Clear existing slots first.'}

    # Generate slot times
    slot_times = generate_slot_times(
        config['slot_start_time'],
        config['slot_end_time'],
        config['slot_duration_minutes']
    )

    # Insert slots for each date
    slots_inserted = 0
    for date_row in dates:
        date = date_row['date']
        day_of_week = date_row['day_of_week']

        for start_time in slot_times:
            cursor.execute('''
                INSERT INTO slots (job_id, date, day_of_week, start_time, booked_count)
                VALUES (?, ?, ?, ?, 0)
            ''', (job_id, date, day_of_week, start_time))
            slots_inserted += 1

    conn.commit()
    conn.close()

    return {'success': True, 'slots_created': slots_inserted}


def get_slots_by_job_and_date(job_id, date):
    """Get all slots for a specific job and date with availability"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get job capacity
    cursor.execute('''
        SELECT capacity_per_slot FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    if not config:
        conn.close()
        return []

    max_capacity = config['capacity_per_slot']

    cursor.execute('''
        SELECT id, job_id, date, day_of_week, start_time, booked_count,
               ? as max_capacity,
               (? - booked_count) as available
        FROM slots
        WHERE job_id = ? AND date = ?
        ORDER BY start_time
    ''', (max_capacity, max_capacity, job_id, date))

    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return slots


def get_all_slots_for_job(job_id):
    """Get all slots for a specific job grouped by date with booking statistics"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get job capacity
    cursor.execute('''
        SELECT capacity_per_slot, slot_duration_minutes FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    if not config:
        conn.close()
        return []

    max_capacity = config['capacity_per_slot']
    slot_duration = config['slot_duration_minutes']

    # Get all slots for this job
    cursor.execute('''
        SELECT id, job_id, date, day_of_week, start_time, booked_count,
               ? as max_capacity,
               (? - booked_count) as available,
               ? as slot_duration_minutes
        FROM slots
        WHERE job_id = ?
        ORDER BY date, start_time
    ''', (max_capacity, max_capacity, slot_duration, job_id))

    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return slots


def clear_slots_for_job(job_id):
    """Clear all slots for a specific job"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete bookings for this job first
    cursor.execute('DELETE FROM bookings WHERE job_id = ?', (job_id,))

    # Delete slots
    cursor.execute('DELETE FROM slots WHERE job_id = ?', (job_id,))

    # Reset candidate statuses for this job
    cursor.execute('''
        UPDATE candidates
        SET status = 'pending', updated_at = ?
        WHERE job_id = ? AND status != 'pending'
    ''', (datetime.now(), job_id))

    conn.commit()
    conn.close()

    return {'success': True, 'message': f'All slots and bookings cleared for job {job_id}'}


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
                SELECT id, booked_count, start_time, date, job_id
                FROM slots
                WHERE id = ?
            ''', (slot_id,))

            slot = cursor.fetchone()

            if not slot:
                return {'error': 'Invalid slot selected.'}

            # Verify slot belongs to the correct job
            if slot['job_id'] != job_id:
                return {'error': 'Invalid slot for this job.'}

            # Get job capacity
            cursor.execute('''
                SELECT capacity_per_slot FROM job_configs WHERE job_id = ?
            ''', (job_id,))

            config = cursor.fetchone()
            max_capacity = config['capacity_per_slot']

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
                jc.slot_duration_minutes,
                b.booked_at
            FROM bookings b
            JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
            JOIN slots s ON b.slot_id = s.id
            JOIN job_configs jc ON b.job_id = jc.job_id
            WHERE b.job_id = ?
            ORDER BY s.date, s.start_time
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
                jc.slot_duration_minutes,
                b.booked_at
            FROM bookings b
            JOIN candidates c ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
            JOIN slots s ON b.slot_id = s.id
            JOIN job_configs jc ON b.job_id = jc.job_id
            ORDER BY s.date, s.start_time
        ''')

    bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return bookings


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
