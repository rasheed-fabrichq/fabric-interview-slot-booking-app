"""
Database initialization and operations for Interview Slot Booking Application
"""
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH, SLOT_TIMES, INTERVIEW_DATES, SLOT_CAPACITY


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

    # Create candidates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            college_name TEXT NOT NULL,
            interview_link TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: Add interview_link column if it doesn't exist
    cursor.execute("PRAGMA table_info(candidates)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'interview_link' not in columns:
        cursor.execute('ALTER TABLE candidates ADD COLUMN interview_link TEXT')

    # Create index on candidate_id for faster lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_candidate_id
        ON candidates(candidate_id)
    ''')

    # Create slots table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            start_time TEXT NOT NULL,
            date TEXT NOT NULL,
            booked_count INTEGER DEFAULT 0,
            max_capacity INTEGER DEFAULT 10,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(day, start_time)
        )
    ''')

    # Create bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            slot_id INTEGER NOT NULL,
            college_name TEXT NOT NULL,
            booked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id),
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        )
    ''')

    # Create index on candidate_id for faster lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_booking_candidate
        ON bookings(candidate_id)
    ''')

    # Create settings table for application configuration
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

    conn.commit()
    conn.close()

    print("Database initialized successfully!")


def initialize_slots():
    """Initialize all time slots for both days"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if slots already exist
    cursor.execute('SELECT COUNT(*) as count FROM slots')
    count = cursor.fetchone()['count']

    if count > 0:
        conn.close()
        return {'error': 'Slots already initialized. Clear existing slots first.'}

    # Insert slots for both days
    slots_inserted = 0
    for day, date in INTERVIEW_DATES.items():
        for start_time in SLOT_TIMES:
            cursor.execute('''
                INSERT INTO slots (day, start_time, date, booked_count, max_capacity)
                VALUES (?, ?, ?, 0, ?)
            ''', (day, start_time, date, SLOT_CAPACITY))
            slots_inserted += 1

    conn.commit()
    conn.close()

    return {'success': True, 'slots_created': slots_inserted}


def add_candidate(candidate_id, name, email, college_name, interview_link=None):
    """Add a new candidate to the database"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO candidates (candidate_id, name, email, college_name, interview_link, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (candidate_id, name, email, college_name, interview_link))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'Candidate ID already exists'}


def get_candidate(candidate_id):
    """Get candidate details by candidate_id"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM candidates WHERE candidate_id = ?
    ''', (candidate_id,))

    candidate = cursor.fetchone()
    conn.close()

    if candidate:
        return dict(candidate)
    return None


def update_candidate_status(candidate_id, status):
    """Update candidate status"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE candidates
        SET status = ?, updated_at = ?
        WHERE candidate_id = ?
    ''', (status, datetime.now(), candidate_id))

    conn.commit()
    conn.close()


def get_slots_by_day(day):
    """Get all slots for a specific day with availability"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, day, start_time, date, booked_count, max_capacity,
               (max_capacity - booked_count) as available
        FROM slots
        WHERE day = ?
        ORDER BY start_time
    ''', (day,))

    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return slots


def book_slot(candidate_id, slot_id, college_name):
    """
    Book a slot for a candidate with transaction safety
    Returns: {'success': True} or {'error': 'message'}
    """
    try:
        with get_db_transaction() as conn:
            cursor = conn.cursor()

            # Check if candidate already has a booking
            cursor.execute('''
                SELECT COUNT(*) as count FROM bookings
                WHERE candidate_id = ?
            ''', (candidate_id,))

            if cursor.fetchone()['count'] > 0:
                return {'error': 'You have already booked a slot.'}

            # Get slot details with lock
            cursor.execute('''
                SELECT id, booked_count, max_capacity, start_time, date
                FROM slots
                WHERE id = ?
            ''', (slot_id,))

            slot = cursor.fetchone()

            if not slot:
                return {'error': 'Invalid slot selected.'}

            # Check availability
            if slot['booked_count'] >= slot['max_capacity']:
                return {'error': 'This slot has just been booked by other candidates. Please choose another available slot.'}

            # Increment booked count
            cursor.execute('''
                UPDATE slots
                SET booked_count = booked_count + 1
                WHERE id = ?
            ''', (slot_id,))

            # Create booking
            cursor.execute('''
                INSERT INTO bookings (candidate_id, slot_id, college_name, booked_at)
                VALUES (?, ?, ?, ?)
            ''', (candidate_id, slot_id, college_name, datetime.now()))

            # Update candidate status to 'booked'
            cursor.execute('''
                UPDATE candidates
                SET status = 'booked', updated_at = ?
                WHERE candidate_id = ?
            ''', (datetime.now(), candidate_id))

            return {
                'success': True,
                'slot_time': slot['start_time'],
                'slot_date': slot['date']
            }

    except Exception as e:
        return {'error': f'An error occurred: {str(e)}'}


def get_all_bookings():
    """Get all bookings with candidate and slot details"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.candidate_id,
            c.name,
            c.email,
            c.interview_link,
            b.college_name,
            s.date,
            s.start_time,
            b.booked_at
        FROM bookings b
        JOIN candidates c ON b.candidate_id = c.candidate_id
        JOIN slots s ON b.slot_id = s.id
        ORDER BY s.date, s.start_time
    ''')

    bookings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return bookings


def get_booking_by_candidate(candidate_id):
    """Get booking details for a specific candidate"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.name,
            c.email,
            b.college_name,
            s.date,
            s.start_time,
            s.day,
            b.booked_at
        FROM bookings b
        JOIN candidates c ON b.candidate_id = c.candidate_id
        JOIN slots s ON b.slot_id = s.id
        WHERE b.candidate_id = ?
    ''', (candidate_id,))

    booking = cursor.fetchone()
    conn.close()

    if booking:
        return dict(booking)
    return None


def get_dashboard_stats():
    """Get statistics for admin dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total candidates
    cursor.execute('SELECT COUNT(*) as total FROM candidates')
    total_candidates = cursor.fetchone()['total']

    # Total bookings
    cursor.execute('SELECT COUNT(*) as total FROM bookings')
    total_bookings = cursor.fetchone()['total']

    # Candidates by status
    cursor.execute('''
        SELECT status, COUNT(*) as count
        FROM candidates
        GROUP BY status
    ''')
    status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

    # Slot utilization by day
    cursor.execute('''
        SELECT day,
               SUM(booked_count) as total_booked,
               COUNT(*) * max_capacity as total_capacity
        FROM slots
        GROUP BY day
    ''')
    day_stats = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        'total_candidates': total_candidates,
        'total_bookings': total_bookings,
        'status_counts': status_counts,
        'day_stats': day_stats
    }


def clear_all_slots():
    """Clear all slot data and bookings (for testing/reset)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Delete bookings first (due to foreign key constraints)
    cursor.execute('DELETE FROM bookings')

    # Then delete slots
    cursor.execute('DELETE FROM slots')

    # Reset candidate statuses to 'pending'
    cursor.execute("UPDATE candidates SET status = 'pending', updated_at = ? WHERE status != 'pending'",
                   (datetime.now(),))

    conn.commit()
    conn.close()

    return {'success': True, 'message': 'All slots and bookings cleared. Candidate statuses reset.'}


def is_booking_enabled():
    """Check if booking is currently enabled"""
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
    """Enable or disable booking"""
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


def get_all_candidates():
    """Get all candidates with their details"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.candidate_id,
            c.name,
            c.email,
            c.college_name,
            c.interview_link,
            c.status,
            c.created_at,
            c.updated_at
        FROM candidates c
        ORDER BY c.created_at DESC
    ''')

    candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return candidates


if __name__ == '__main__':
    # Initialize database when run directly
    init_database()
    print(f"Database created at: {DATABASE_PATH}")
