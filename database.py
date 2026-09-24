"""
Database initialization and operations for Multi-Job Interview Slot Booking Application
"""
import sqlite3
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import DATABASE_PATH, BOOKING_CUTOFF_MINUTES, now_local


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

            -- The ID in candidates' links (/jobs/<ID>/ or /interviews/<ID>/)
            -- and in the booking link's job_id. Equal to job_id for a
            -- normal job; a batch shares its parent's link_id and has a
            -- generated job_id of its own.
            link_id TEXT NOT NULL,
            parent_job_id TEXT,                 -- set on batches only

            slot_start_time TEXT NOT NULL,
            slot_end_time TEXT NOT NULL,
            slot_duration_minutes INTEGER NOT NULL,
            capacity_per_slot INTEGER NOT NULL,
            booking_enabled INTEGER DEFAULT 1,

            -- Branding. Blank values fall back to the .env defaults, so
            -- a job only needs the fields that differ for its client.
            company_name TEXT,
            email_reply_to TEXT,
            email_cc TEXT,                      -- comma-separated, confirmation only
            support_email TEXT,
            faq_link TEXT,

            -- Reminder email
            reminder_email_enabled INTEGER NOT NULL DEFAULT 1,
            reminder_lead_minutes INTEGER,      -- NULL: REMINDER_LEAD_MINUTES

            -- Reminder call. call_enabled NULL follows CALLS_ENABLED.
            call_enabled INTEGER,
            call_lead_minutes INTEGER,
            call_assistant_id TEXT,
            call_agent_type TEXT,
            call_agent_name TEXT,
            call_company_name TEXT,             -- spoken; defaults to company_name
            call_role_name TEXT,                -- spoken; defaults to job_name
            call_disqualification_rate TEXT,
            call_api_base_url TEXT,

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_job_configs_link
        ON job_configs(link_id)
    ''')

    # Per-job email templates, one row per job per kind. A job with no
    # row for a kind is sent the default template from email_templates/.
    # kind: 'confirmation' | 'reminder' | 'followup'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_email_templates (
            job_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (job_id, kind),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    # Create job_dates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            date TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            slot_start_time TEXT,
            slot_end_time TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, date),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    # Add columns to existing job_dates table if they don't exist (for migration)
    cursor.execute("PRAGMA table_info(job_dates)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'slot_start_time' not in columns:
        cursor.execute('ALTER TABLE job_dates ADD COLUMN slot_start_time TEXT')
    if 'slot_end_time' not in columns:
        cursor.execute('ALTER TABLE job_dates ADD COLUMN slot_end_time TEXT')

    # Create candidates table (with job_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            interview_link TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, job_id),
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    # Phone is stored normalised to E.164 for the reminder call. Added
    # after the fact, so an existing database needs the column too.
    cursor.execute("PRAGMA table_info(candidates)")
    candidate_columns = [col[1] for col in cursor.fetchall()]
    if 'phone' not in candidate_columns:
        cursor.execute('ALTER TABLE candidates ADD COLUMN phone TEXT')

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
    # Outbound reminders, one row per booking per channel per kind.
    #
    # The UNIQUE constraint is what makes reminders safe: the worker
    # claims a reminder by INSERTing this row, so two workers racing on
    # the same booking cannot both win, and a crashed-and-restarted
    # worker will not re-send anything already claimed. Rows are created
    # by the worker at send time rather than at booking time, so a
    # rescheduled or released booking simply never gets claimed.
    #
    # channel: 'email' | 'call'   kind: 'reminder_15m'
    # status:  'pending' | 'sent' | 'failed' | 'skipped'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            slot_date TEXT,
            slot_start_time TEXT,
            scheduled_for DATETIME,
            attempts INTEGER NOT NULL DEFAULT 0,
            provider_ref TEXT,
            error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, job_id, channel, kind)
        )
    ''')

    # One row per reminder call placed, tracking it from queued through
    # to its outcome.
    #
    # Separate from notifications: that table owns the *claim* (one call
    # per booking, never twice), this one owns the *outcome*. Keeping
    # them apart means the dozen call-specific columns do not bloat the
    # table the email channel also uses.
    #
    # status: queued | in_progress | completed | failed | cancelled
    # request_payload holds exactly what was sent, including the phone
    # number and every spoken variable, so a call can be explained after
    # the fact without guessing what the agent was told.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            execution_id TEXT UNIQUE,
            phone TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            call_successful INTEGER,
            hangup_reason TEXT,
            duration_seconds REAL,
            cost REAL,
            transcript TEXT,
            recording_available INTEGER DEFAULT 0,
            slot_date TEXT,
            slot_start_time TEXT,
            request_payload TEXT,
            raw_response TEXT,
            error TEXT,
            poll_attempts INTEGER NOT NULL DEFAULT 0,
            placed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_polled_at DATETIME,
            completed_at DATETIME
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_call_logs_status
        ON call_logs(status)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_call_logs_candidate
        ON call_logs(candidate_id, job_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_notifications_lookup
        ON notifications(candidate_id, job_id, channel, kind)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_notifications_status
        ON notifications(status, channel)
    ''')

    # Follow-up emails asking candidates who have not booked to pick a
    # slot. One run per "send" click, one row per candidate emailed.
    # Kept apart from notifications, which is the reminder worker's
    # claim table and is keyed one-row-per-booking.
    # audience: 'not_booked' | 'pending' | 'clicked'
    # status:   'running' | 'completed'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS followup_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            audience TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            sent INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'running',
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME,
            FOREIGN KEY (job_id) REFERENCES job_configs(job_id)
        )
    ''')

    # status: 'sent' | 'failed' | 'skipped'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS followup_sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            job_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            email TEXT,
            status TEXT NOT NULL,
            error TEXT,
            provider_ref TEXT,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES followup_runs(id)
        )
    ''')

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

    # No jobs are seeded: every job is created from Admin > Jobs.

    conn.commit()
    conn.close()

    print("Database initialized successfully!")


# ==================== JOB CONFIGURATION FUNCTIONS ====================

def get_all_jobs():
    """Get all jobs as a dictionary {job_id: job_name}"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT job_id, job_name FROM job_configs ORDER BY created_at')
    jobs = {row['job_id']: row['job_name'] for row in cursor.fetchall()}
    conn.close()

    return jobs


def create_job(job_id, job_name, start_time='08:00', end_time='00:00', duration=60, capacity=15,
               company_name=None):
    """Create a new job configuration"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Only a batch's link_id differs from its job_id; a job created
        # here is addressed in links by its own ID.
        cursor.execute('''
            INSERT INTO job_configs
            (job_id, job_name, link_id, company_name, slot_start_time,
             slot_end_time, slot_duration_minutes, capacity_per_slot,
             booking_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (job_id, job_name, job_id, company_name, start_time, end_time,
              duration, capacity))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'Job with this ID already exists'}


def create_batch(parent_job_id, batch_name):
    """Create a batch of an existing job.

    A batch is a job of its own -- its own dates, slots, capacity and
    candidates -- that shares the parent's link_id, so candidates of
    every batch arrive with the same /book?job_id=<link_id> link and are
    routed to their batch by which one they were uploaded into.

    Copies the parent's slot settings, communication settings and email
    templates. Dates are not copied: different dates are the usual
    reason for a batch.

    Returns {'success': True, 'job_id': ...} or {'error': ...}.
    """
    import uuid

    parent = get_job_config(parent_job_id)
    if not parent:
        return {'error': 'Parent job not found'}

    # Batches of a batch hang off the original job, so every batch in a
    # group points at the same parent.
    root_job_id = parent['parent_job_id'] or parent['job_id']
    new_job_id = str(uuid.uuid4())

    copied = ('slot_start_time', 'slot_end_time', 'slot_duration_minutes',
              'capacity_per_slot') + COMMUNICATION_FIELDS
    columns = ('job_id', 'job_name', 'link_id', 'parent_job_id',
               'booking_enabled') + copied
    values = (new_job_id, batch_name, parent['link_id'], root_job_id, 1,
              *(parent[c] for c in copied))

    with get_db_transaction() as conn:
        conn.execute(
            f'INSERT INTO job_configs ({", ".join(columns)}) '
            f'VALUES ({", ".join("?" for _ in columns)})', values)
        conn.execute('''
            INSERT INTO job_email_templates (job_id, kind, subject, body, updated_at)
            SELECT ?, kind, subject, body, ?
            FROM job_email_templates WHERE job_id = ?
        ''', (new_job_id, datetime.now(), parent_job_id))

    return {'success': True, 'job_id': new_job_id}


def link_id_exists(link_id):
    """Whether any job is addressed by this link ID."""
    conn = get_db_connection()
    row = conn.execute('SELECT 1 FROM job_configs WHERE link_id = ? LIMIT 1',
                       (link_id,)).fetchone()
    conn.close()
    return row is not None


def find_candidate_by_link(candidate_id, link_id):
    """Resolve a booking link to the candidate's own batch.

    Looks for the candidate in every job sharing link_id. A job without
    batches has link_id equal to its job_id, so this finds the same row
    get_candidate would. Upload keeps a candidate in at most one batch
    per link_id, so there is at most one match.

    A batch's internal job_id is accepted too, so a link built with it
    still works.
    """
    conn = get_db_connection()
    row = conn.execute('''
        SELECT c.* FROM candidates c
        JOIN job_configs jc ON c.job_id = jc.job_id
        WHERE c.candidate_id = ? AND (jc.link_id = ? OR jc.job_id = ?)
        ORDER BY jc.link_id = ? DESC
        LIMIT 1
    ''', (candidate_id, link_id, link_id, link_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def find_candidate_other_batch(candidate_id, link_id, job_id):
    """Name of another job with this link_id the candidate is already in.

    Used on upload: a candidate in two batches of the same job would
    have one booking link that could mean either, so it is refused.
    """
    conn = get_db_connection()
    row = conn.execute('''
        SELECT jc.job_name FROM candidates c
        JOIN job_configs jc ON c.job_id = jc.job_id
        WHERE c.candidate_id = ? AND jc.link_id = ? AND c.job_id != ?
        LIMIT 1
    ''', (candidate_id, link_id, job_id)).fetchone()
    conn.close()
    return row['job_name'] if row else None


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


# ==================== JOB COMMUNICATION SETTINGS ====================

# job_configs columns an admin can set from the Communications page.
# Anything else passed to update_job_communication is ignored, so a
# stray form field cannot write to scheduling columns.
COMMUNICATION_FIELDS = (
    'company_name', 'email_reply_to', 'email_cc', 'support_email',
    'faq_link',
    'reminder_email_enabled', 'reminder_lead_minutes',
    'call_enabled', 'call_lead_minutes', 'call_assistant_id',
    'call_agent_type', 'call_agent_name', 'call_company_name',
    'call_role_name', 'call_disqualification_rate', 'call_api_base_url',
)

EMAIL_TEMPLATE_KINDS = ('confirmation', 'reminder', 'followup')


def get_job_communication(job_id):
    """A job's communication settings, or None if the job does not exist.

    Returns the COMMUNICATION_FIELDS columns plus job_name and link_id. Values are
    as stored: NULL means "use the default", resolved by the caller.
    """
    conn = get_db_connection()
    row = conn.execute(
        f'SELECT job_id, job_name, link_id, {", ".join(COMMUNICATION_FIELDS)} '
        f'FROM job_configs WHERE job_id = ?', (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_job_communications():
    """Every job's communication settings, keyed by job_id."""
    conn = get_db_connection()
    rows = conn.execute(
        f'SELECT job_id, job_name, link_id, {", ".join(COMMUNICATION_FIELDS)} '
        f'FROM job_configs').fetchall()
    conn.close()
    return {row['job_id']: dict(row) for row in rows}


def update_job_communication(job_id, **fields):
    """Set communication fields for a job. Pass None to clear one."""
    updates = {k: v for k, v in fields.items() if k in COMMUNICATION_FIELDS}
    if not updates:
        return {'error': 'No valid fields provided'}

    assignments = ', '.join(f'{k} = ?' for k in updates)
    conn = get_db_connection()
    cursor = conn.execute(
        f'UPDATE job_configs SET {assignments}, updated_at = ? '
        f'WHERE job_id = ?',
        (*updates.values(), datetime.now(), job_id))
    conn.commit()
    updated = cursor.rowcount
    conn.close()

    if not updated:
        return {'error': 'Job not found'}
    return {'success': True}


def get_job_email_template(job_id, kind):
    """The job's own template for this kind, or None to use the default."""
    conn = get_db_connection()
    row = conn.execute(
        'SELECT subject, body, updated_at FROM job_email_templates '
        'WHERE job_id = ? AND kind = ?', (job_id, kind)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_job_email_template(job_id, kind, subject, body):
    """Create or replace a job's template for one kind."""
    if kind not in EMAIL_TEMPLATE_KINDS:
        return {'error': f'Unknown template kind: {kind}'}

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO job_email_templates (job_id, kind, subject, body, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(job_id, kind) DO UPDATE SET
            subject = excluded.subject,
            body = excluded.body,
            updated_at = excluded.updated_at
    ''', (job_id, kind, subject, body, datetime.now()))
    conn.commit()
    conn.close()
    return {'success': True}


def delete_job_email_template(job_id, kind):
    """Drop a job's template so it falls back to the default."""
    conn = get_db_connection()
    cursor = conn.execute(
        'DELETE FROM job_email_templates WHERE job_id = ? AND kind = ?',
        (job_id, kind))
    conn.commit()
    removed = cursor.rowcount
    conn.close()
    return removed > 0


def copy_job_communication(source_job_id, target_job_id):
    """Copy settings and templates from one job to another.

    Replaces everything on the target, including clearing templates the
    source does not have, so the two end up identical.
    """
    source = get_job_communication(source_job_id)
    if not source:
        return {'error': 'Source job not found'}

    if not get_job_communication(target_job_id):
        return {'error': 'Target job not found'}

    with get_db_transaction() as conn:
        assignments = ', '.join(f'{k} = ?' for k in COMMUNICATION_FIELDS)
        conn.execute(
            f'UPDATE job_configs SET {assignments}, updated_at = ? '
            f'WHERE job_id = ?',
            (*(source[k] for k in COMMUNICATION_FIELDS), datetime.now(),
             target_job_id))

        conn.execute('DELETE FROM job_email_templates WHERE job_id = ?',
                     (target_job_id,))
        conn.execute('''
            INSERT INTO job_email_templates (job_id, kind, subject, body, updated_at)
            SELECT ?, kind, subject, body, ?
            FROM job_email_templates WHERE job_id = ?
        ''', (target_job_id, datetime.now(), source_job_id))

    return {'success': True}


# ==================== DELETION ====================

# Every table holding per-job rows, in the order they are cleared: rows
# that point at others go first.
JOB_OWNED_TABLES = ('bookings', 'notifications', 'call_logs',
                    'followup_sends', 'followup_runs', 'candidates', 'slots',
                    'job_dates', 'job_email_templates')


def get_job_usage():
    """What deleting each job would remove, keyed by job_id."""
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT jc.job_id,
            (SELECT COUNT(*) FROM candidates c WHERE c.job_id = jc.job_id) AS candidates,
            (SELECT COUNT(*) FROM bookings b WHERE b.job_id = jc.job_id) AS bookings,
            (SELECT COUNT(*) FROM slots s WHERE s.job_id = jc.job_id) AS slots,
            (SELECT COUNT(*) FROM job_dates d WHERE d.job_id = jc.job_id) AS dates,
            (SELECT COUNT(*) FROM job_configs b2 WHERE b2.parent_job_id = jc.job_id) AS batches
        FROM job_configs jc
    ''').fetchall()
    conn.close()
    return {r['job_id']: dict(r) for r in rows}


def delete_job(job_id):
    """Delete a job and everything belonging to it, in one transaction.

    Removes its bookings, candidates, slots, dates, templates and
    reminder/follow-up history. Candidates are not notified.

    If the job has batches they are kept: the oldest batch becomes the
    parent of the rest, so the group still hangs together. They keep the
    shared link_id, so their candidates' links keep working.

    Returns {'success': True, 'counts': {...}} or {'error': ...}.
    """
    usage = get_job_usage().get(job_id)
    if usage is None:
        return {'error': 'Job not found'}

    with get_db_transaction() as conn:
        batches = [r['job_id'] for r in conn.execute('''
            SELECT job_id FROM job_configs WHERE parent_job_id = ?
            ORDER BY created_at, id
        ''', (job_id,)).fetchall()]
        if batches:
            new_parent = batches[0]
            conn.execute('UPDATE job_configs SET parent_job_id = NULL '
                         'WHERE job_id = ?', (new_parent,))
            conn.execute('UPDATE job_configs SET parent_job_id = ? '
                         'WHERE parent_job_id = ?', (new_parent, job_id))

        for table in JOB_OWNED_TABLES:
            conn.execute(f'DELETE FROM {table} WHERE job_id = ?', (job_id,))
        conn.execute('DELETE FROM job_configs WHERE job_id = ?', (job_id,))

    return {'success': True, 'counts': usage}


def delete_candidates(candidate_keys):
    """Delete candidates, freeing any slot they had booked.

    candidate_keys is an iterable of (candidate_id, job_id). Each booked
    candidate's seat is returned to its slot, so someone else can take
    it. Their reminder claims go too, so nothing is sent for a booking
    that no longer exists. Candidates are not notified.

    Returns {'deleted': n, 'bookings_freed': m}.
    """
    deleted = freed = 0
    with get_db_transaction() as conn:
        for candidate_id, job_id in candidate_keys:
            booking = conn.execute('''
                SELECT slot_id FROM bookings
                WHERE candidate_id = ? AND job_id = ?
            ''', (candidate_id, job_id)).fetchone()
            if booking:
                conn.execute('''
                    UPDATE slots SET booked_count = MAX(0, booked_count - 1)
                    WHERE id = ?
                ''', (booking['slot_id'],))
                conn.execute('DELETE FROM bookings WHERE candidate_id = ? '
                             'AND job_id = ?', (candidate_id, job_id))
                freed += 1

            conn.execute('DELETE FROM notifications WHERE candidate_id = ? '
                         'AND job_id = ?', (candidate_id, job_id))
            cursor = conn.execute('DELETE FROM candidates WHERE '
                                  'candidate_id = ? AND job_id = ?',
                                  (candidate_id, job_id))
            deleted += cursor.rowcount

    return {'deleted': deleted, 'bookings_freed': freed}


# ==================== FOLLOW-UP EMAILS ====================

FOLLOWUP_AUDIENCES = {
    'not_booked': ('pending', 'clicked'),
    'pending': ('pending',),
    'clicked': ('clicked',),
}


def get_followup_recipients(job_id, audience):
    """Candidates of a job who have not booked, filtered by status.

    Includes link_id so the caller can build each booking link.
    """
    statuses = FOLLOWUP_AUDIENCES[audience]
    conn = get_db_connection()
    rows = conn.execute(f'''
        SELECT c.candidate_id, c.job_id, c.name, c.email, c.status,
               jc.job_name, jc.link_id
        FROM candidates c
        JOIN job_configs jc ON c.job_id = jc.job_id
        WHERE c.job_id = ?
          AND c.status IN ({", ".join("?" for _ in statuses)})
          AND NOT EXISTS (SELECT 1 FROM bookings b
                          WHERE b.candidate_id = c.candidate_id
                            AND b.job_id = c.job_id)
        ORDER BY c.created_at
    ''', (job_id, *statuses)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_followup_audience_counts(job_id):
    """How many candidates each audience would reach."""
    return {audience: len(get_followup_recipients(job_id, audience))
            for audience in FOLLOWUP_AUDIENCES}


def create_followup_run(job_id, audience, total):
    """Start a follow-up run, unless one for this job is already going.

    Returns the run id, or None if a run started in the last 30 minutes
    is still marked running -- the guard against a double-clicked Send
    emailing everyone twice. An older 'running' row is treated as dead
    (the process sending it was restarted) and does not block.
    """
    with get_db_transaction() as conn:
        busy = conn.execute('''
            SELECT 1 FROM followup_runs
            WHERE job_id = ? AND status = 'running'
              AND started_at > datetime('now', '-30 minutes')
        ''', (job_id,)).fetchone()
        if busy:
            return None
        cursor = conn.execute('''
            INSERT INTO followup_runs (job_id, audience, total)
            VALUES (?, ?, ?)
        ''', (job_id, audience, total))
        return cursor.lastrowid


def record_followup_send(run_id, job_id, candidate_id, email, status,
                         error=None, provider_ref=None):
    """Log one candidate's follow-up and bump the run's counters."""
    if status not in ('sent', 'failed', 'skipped'):
        raise ValueError(f'Unknown follow-up status: {status}')
    with get_db_transaction() as conn:
        conn.execute('''
            INSERT INTO followup_sends
            (run_id, job_id, candidate_id, email, status, error, provider_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (run_id, job_id, candidate_id, email, status, error,
              provider_ref))
        conn.execute(f'UPDATE followup_runs SET {status} = {status} + 1 '
                     f'WHERE id = ?', (run_id,))


def finish_followup_run(run_id):
    conn = get_db_connection()
    conn.execute('''
        UPDATE followup_runs SET status = 'completed',
            finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (run_id,))
    conn.commit()
    conn.close()


def get_followup_runs(job_id, limit=10):
    """Recent follow-up runs for a job, newest first, with failures."""
    conn = get_db_connection()
    runs = [dict(r) for r in conn.execute('''
        SELECT * FROM followup_runs WHERE job_id = ?
        ORDER BY id DESC LIMIT ?
    ''', (job_id, limit)).fetchall()]
    for run in runs:
        run['failures'] = [dict(r) for r in conn.execute('''
            SELECT fs.email, fs.error, c.name
            FROM followup_sends fs
            LEFT JOIN candidates c
              ON c.candidate_id = fs.candidate_id AND c.job_id = fs.job_id
            WHERE fs.run_id = ? AND fs.status = 'failed'
            ORDER BY fs.id
        ''', (run['id'],)).fetchall()]
    conn.close()
    return runs


# ==================== JOB DATES FUNCTIONS ====================

def get_job_dates(job_id, only_bookable=False):
    """Get all dates for a specific job with optional time overrides.

    only_bookable drops dates that have no slots left in the future, so a
    candidate is never offered a day they cannot actually book.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # dates are dd-mm-yyyy strings, so sort by year/month/day rather than
    # lexically -- otherwise 01-08-2026 would sort before 30-07-2026.
    cursor.execute('''
        SELECT date, day_of_week, slot_start_time, slot_end_time FROM job_dates
        WHERE job_id = ?
        ORDER BY substr(date, 7, 4), substr(date, 4, 2), substr(date, 1, 2)
    ''', (job_id,))

    dates = [dict(row) for row in cursor.fetchall()]

    if only_bookable:
        now = now_local()
        bookable = []
        for d in dates:
            cursor.execute(
                'SELECT start_time FROM slots WHERE job_id = ? AND date = ?',
                (job_id, d['date']))
            times = [r['start_time'] for r in cursor.fetchall()]
            if any(not is_slot_in_past(d['date'], t, now) for t in times):
                bookable.append(d)
        dates = bookable

    conn.close()

    return dates


def add_job_date(job_id, date, day_of_week, start_time=None, end_time=None):
    """Add a new interview date for a job with optional custom time range"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO job_dates (job_id, date, day_of_week, slot_start_time, slot_end_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (job_id, date, day_of_week, start_time, end_time))
        conn.commit()
        conn.close()
        return {'success': True}
    except sqlite3.IntegrityError:
        conn.close()
        return {'error': 'This date already exists for this job'}


def update_job_date_times(job_id, date, start_time, end_time):
    """Update time range for a specific date"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE job_dates
        SET slot_start_time = ?, slot_end_time = ?
        WHERE job_id = ? AND date = ?
    ''', (start_time, end_time, job_id, date))

    conn.commit()
    conn.close()

    return {'success': True}


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

def add_candidate(candidate_id, job_id, name, email, interview_link=None,
                  phone=None):
    """Add a new candidate to the database.

    phone should already be normalised to E.164 by phone_utils; it is
    stored as-is and dialled verbatim by the reminder call.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO candidates (candidate_id, job_id, name, email, phone, interview_link, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''', (candidate_id, job_id, name, email, phone, interview_link))
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
                c.phone,
                c.interview_link,
                c.status,
                c.created_at,
                c.updated_at,
                jc.job_name,
                jc.link_id
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
                c.phone,
                c.interview_link,
                c.status,
                c.created_at,
                c.updated_at,
                jc.job_name,
                jc.link_id
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
    """Initialize all time slots for a specific job (supports per-date time ranges)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get job configuration (default times and duration)
    cursor.execute('''
        SELECT slot_start_time, slot_end_time, slot_duration_minutes
        FROM job_configs WHERE job_id = ?
    ''', (job_id,))

    config = cursor.fetchone()
    if not config:
        conn.close()
        return {'error': 'Job configuration not found'}

    # Get all dates for this job (with optional time overrides)
    cursor.execute('''
        SELECT date, day_of_week, slot_start_time, slot_end_time FROM job_dates WHERE job_id = ?
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

    # Insert slots for each date
    slots_inserted = 0
    for date_row in dates:
        date = date_row['date']
        day_of_week = date_row['day_of_week']

        # Use date-specific times if available, otherwise fall back to job config
        date_start_time = date_row['slot_start_time'] or config['slot_start_time']
        date_end_time = date_row['slot_end_time'] or config['slot_end_time']

        # Generate slot times for this specific date
        slot_times = generate_slot_times(
            date_start_time,
            date_end_time,
            config['slot_duration_minutes']
        )

        for start_time in slot_times:
            cursor.execute('''
                INSERT INTO slots (job_id, date, day_of_week, start_time, booked_count)
                VALUES (?, ?, ?, ?, 0)
            ''', (job_id, date, day_of_week, start_time))
            slots_inserted += 1

    conn.commit()
    conn.close()

    return {'success': True, 'slots_created': slots_inserted}


def is_slot_in_past(date, start_time, now=None):
    """Has this slot's start time already passed (or is too close)?

    date is dd-mm-yyyy and start_time is HH:MM, both in the interview
    timezone.
    """
    now = now or now_local()
    try:
        slot_dt = datetime.strptime(f'{date} {start_time}', '%d-%m-%Y %H:%M')
    except ValueError:
        return False  # malformed rows are left visible rather than hidden

    # Strictly less-than: a slot starting exactly now is still bookable,
    # so someone arriving at 12:00 can take the 12:00 slot.
    return slot_dt < now + timedelta(minutes=BOOKING_CUTOFF_MINUTES)


def get_slots_by_job_and_date(job_id, date, include_past=False):
    """Get all slots for a specific job and date with availability.

    Slots whose start time has already passed are excluded by default, so
    a candidate arriving mid-day only sees times they can still attend.
    """
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

    if not include_past:
        now = now_local()
        slots = [s for s in slots
                 if not is_slot_in_past(s['date'], s['start_time'], now)]

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

            # Re-check here, not just when listing slots: a page left open
            # since the morning would otherwise still post a slot whose
            # time has since passed.
            if is_slot_in_past(slot['date'], slot['start_time']):
                return {'error': 'That time slot has already passed. '
                                 'Please choose a later one.'}

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
                jc.link_id,
                s.date,
                s.day_of_week,
                s.start_time,
                jc.slot_duration_minutes,
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
                jc.link_id,
                s.date,
                s.day_of_week,
                s.start_time,
                jc.slot_duration_minutes,
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


def release_booking(candidate_id, job_id):
    """Cancel a candidate's booking so they can book again.

    Frees the seat back into the slot and resets the candidate to
    'clicked', so their original booking link works again and they may
    choose a different date and time. Does not notify the candidate.
    """
    try:
        with get_db_transaction() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT b.slot_id, s.date, s.start_time
                FROM bookings b
                JOIN slots s ON b.slot_id = s.id
                WHERE b.candidate_id = ? AND b.job_id = ?
            ''', (candidate_id, job_id))
            booking = cursor.fetchone()

            if not booking:
                return {'error': 'No booking found for this candidate.'}

            # Give the seat back. Guard against going negative in case the
            # count was ever adjusted by hand (see block_slots.py).
            cursor.execute('''
                UPDATE slots
                SET booked_count = MAX(0, booked_count - 1)
                WHERE id = ?
            ''', (booking['slot_id'],))

            cursor.execute('''
                DELETE FROM bookings
                WHERE candidate_id = ? AND job_id = ?
            ''', (candidate_id, job_id))

            cursor.execute('''
                UPDATE candidates
                SET status = 'clicked', updated_at = ?
                WHERE candidate_id = ? AND job_id = ?
            ''', (datetime.now(), candidate_id, job_id))

            # Clear any reminder claim for the old slot. Without this a
            # candidate who rebooks keeps the row from their previous
            # booking, and the reminder for the new time is never sent.
            cursor.execute('''
                DELETE FROM notifications
                WHERE candidate_id = ? AND job_id = ?
            ''', (candidate_id, job_id))

            return {
                'success': True,
                'freed_date': booking['date'],
                'freed_time': booking['start_time'],
            }

    except Exception as e:
        return {'error': f'An error occurred: {str(e)}'}


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
            jc.slot_duration_minutes,
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


# ==================== REMINDER NOTIFICATIONS ====================

def get_bookings_due_for_reminder(lead_minutes, channel, kind='reminder_15m',
                                  now=None, window_minutes=None):
    """Bookings whose slot starts within the reminder window.

    Returns bookings starting between now and now + lead_minutes that do
    not already have a notification row for this channel/kind.

    window_minutes bounds how far back a missed reminder is still worth
    sending: if the worker was down, a booking whose slot already began
    should not get a "starts in 15 minutes" email. None means the window
    is exactly [now, now + lead_minutes] -- nothing already started.

    Note the past-slot filtering happens in Python, not SQL, because
    dates are stored as dd-mm-yyyy strings which do not compare
    chronologically.
    """
    now = now or now_local()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            c.candidate_id, c.name, c.email, c.phone, c.interview_link,
            jc.job_name, b.job_id,
            s.date, s.day_of_week, s.start_time,
            jc.slot_duration_minutes
        FROM bookings b
        JOIN candidates c
          ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
        JOIN slots s ON b.slot_id = s.id
        JOIN job_configs jc ON b.job_id = jc.job_id
        WHERE NOT EXISTS (
            SELECT 1 FROM notifications n
            WHERE n.candidate_id = b.candidate_id
              AND n.job_id = b.job_id
              AND n.channel = ?
              AND n.kind = ?
        )
    ''', (channel, kind))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    horizon = now + timedelta(minutes=lead_minutes)
    earliest = (now - timedelta(minutes=window_minutes)
                if window_minutes else now)

    due = []
    for row in rows:
        try:
            slot_dt = datetime.strptime(
                f"{row['date']} {row['start_time']}", '%d-%m-%Y %H:%M')
        except ValueError:
            continue
        if earliest <= slot_dt <= horizon:
            row['slot_datetime'] = slot_dt
            due.append(row)

    due.sort(key=lambda r: r['slot_datetime'])
    return due


def claim_notification(candidate_id, job_id, channel, kind, slot_date,
                       slot_start_time, scheduled_for=None):
    """Atomically claim the right to send one reminder.

    Returns True if this caller won the claim and should send, False if
    a row already existed -- meaning another worker (or an earlier run)
    already has it. This is the single guard against double-sending, so
    it must be called before doing any sending work, never after.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO notifications
            (candidate_id, job_id, channel, kind, status, slot_date,
             slot_start_time, scheduled_for, attempts)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, 1)
        ''', (candidate_id, job_id, channel, kind, slot_date,
              slot_start_time, scheduled_for or now_local()))
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def mark_notification(candidate_id, job_id, channel, kind, status,
                      error=None, provider_ref=None):
    """Record the outcome of a claimed reminder."""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE notifications
            SET status = ?, error = ?, provider_ref = ?, updated_at = ?
            WHERE candidate_id = ? AND job_id = ? AND channel = ? AND kind = ?
        ''', (status, error, provider_ref, now_local(),
              candidate_id, job_id, channel, kind))
        conn.commit()
    finally:
        conn.close()


def release_notification(candidate_id, job_id, channel=None, kind=None):
    """Delete notification rows so the reminder can be claimed again.

    Used when a booking is reset, and by the admin retry action for a
    reminder that failed.
    """
    conn = get_db_connection()
    try:
        query = ('DELETE FROM notifications '
                 'WHERE candidate_id = ? AND job_id = ?')
        params = [candidate_id, job_id]
        if channel:
            query += ' AND channel = ?'
            params.append(channel)
        if kind:
            query += ' AND kind = ?'
            params.append(kind)
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ==================== CALL LOGS ====================

def create_call_log(candidate_id, job_id, execution_id, phone,
                    slot_date, slot_start_time, request_payload,
                    status='queued'):
    """Record a call the moment it is accepted by the calling system."""
    import json as _json
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO call_logs
            (candidate_id, job_id, execution_id, phone, status,
             slot_date, slot_start_time, request_payload, placed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (candidate_id, job_id, execution_id, phone, status,
              slot_date, slot_start_time,
              _json.dumps(request_payload) if request_payload else None,
              now_local()))
        conn.commit()
        return {'success': True}
    finally:
        conn.close()


def get_pollable_call_logs(batch_size=20, max_attempts=60):
    """Calls that have not reached a terminal state yet.

    Bounded by max_attempts so a call the provider never closes out
    cannot be polled forever. Oldest first, so nothing starves.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM call_logs
        WHERE status IN ('queued', 'in_progress')
          AND execution_id IS NOT NULL
          AND poll_attempts < ?
        ORDER BY placed_at
        LIMIT ?
    ''', (max_attempts, batch_size))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def update_call_log(execution_id, **fields):
    """Update one call log by its execution id."""
    allowed = ('status', 'call_successful', 'hangup_reason',
               'duration_seconds', 'cost', 'transcript',
               'recording_available', 'raw_response', 'error',
               'poll_attempts', 'last_polled_at', 'completed_at')
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return {'error': 'No valid fields provided'}

    assignments = ', '.join(f'{k} = ?' for k in updates)
    conn = get_db_connection()
    try:
        conn.execute(f'UPDATE call_logs SET {assignments} '
                     f'WHERE execution_id = ?',
                     (*updates.values(), execution_id))
        conn.commit()
        return {'success': True}
    finally:
        conn.close()


def bump_call_poll_attempt(execution_id):
    """Count a poll, so a stuck call eventually stops being polled."""
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE call_logs
            SET poll_attempts = poll_attempts + 1, last_polled_at = ?
            WHERE execution_id = ?
        ''', (now_local(), execution_id))
        conn.commit()
    finally:
        conn.close()


def get_call_logs(job_id=None, status=None, outcome=None):
    """Every call placed, newest first, with candidate details."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
        SELECT
            cl.*,
            c.name, c.email,
            jc.job_name
        FROM call_logs cl
        LEFT JOIN candidates c
          ON cl.candidate_id = c.candidate_id AND cl.job_id = c.job_id
        LEFT JOIN job_configs jc ON cl.job_id = jc.job_id
        WHERE 1 = 1
    '''
    params = []
    if job_id:
        query += ' AND cl.job_id = ?'
        params.append(job_id)
    if status:
        query += ' AND cl.status = ?'
        params.append(status)
    if outcome == 'answered':
        query += ' AND cl.call_successful = 1'
    elif outcome == 'not_answered':
        query += ' AND cl.call_successful = 0'
    query += ' ORDER BY cl.placed_at DESC, cl.id DESC'

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_call_log(execution_id):
    """One call log with candidate details, or None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cl.*, c.name, c.email, jc.job_name
        FROM call_logs cl
        LEFT JOIN candidates c
          ON cl.candidate_id = c.candidate_id AND cl.job_id = c.job_id
        LEFT JOIN job_configs jc ON cl.job_id = jc.job_id
        WHERE cl.execution_id = ?
    ''', (execution_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_call_stats(job_id=None):
    """Counts for the dashboard summary cards."""
    conn = get_db_connection()
    cursor = conn.cursor()
    where = ' WHERE job_id = ?' if job_id else ''
    params = (job_id,) if job_id else ()

    cursor.execute(f'SELECT COUNT(*) AS n FROM call_logs{where}', params)
    total = cursor.fetchone()['n']

    cursor.execute(f'''SELECT COUNT(*) AS n FROM call_logs{where}
                       {"AND" if where else "WHERE"} status IN
                       ('queued', 'in_progress')''', params)
    in_progress = cursor.fetchone()['n']

    cursor.execute(f'''SELECT COUNT(*) AS n FROM call_logs{where}
                       {"AND" if where else "WHERE"}
                       call_successful = 1''', params)
    answered = cursor.fetchone()['n']

    cursor.execute(f'''SELECT COUNT(*) AS n FROM call_logs{where}
                       {"AND" if where else "WHERE"}
                       call_successful = 0''', params)
    not_answered = cursor.fetchone()['n']

    conn.close()
    return {'total': total, 'in_progress': in_progress,
            'answered': answered, 'not_answered': not_answered}


def get_notification_log(job_id=None, status=None, channel=None):
    """Every reminder attempt, newest first, with candidate details.

    Left joins the candidate so a row still shows if the candidate was
    later removed, rather than vanishing from the audit trail.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
        SELECT
            n.candidate_id, n.job_id, n.channel, n.kind, n.status,
            n.slot_date, n.slot_start_time, n.attempts, n.provider_ref,
            n.error, n.created_at, n.updated_at,
            c.name, c.email, c.phone,
            jc.job_name
        FROM notifications n
        LEFT JOIN candidates c
          ON n.candidate_id = c.candidate_id AND n.job_id = c.job_id
        LEFT JOIN job_configs jc ON n.job_id = jc.job_id
        WHERE 1 = 1
    '''
    params = []
    if job_id:
        query += ' AND n.job_id = ?'
        params.append(job_id)
    if status:
        query += ' AND n.status = ?'
        params.append(status)
    if channel:
        query += ' AND n.channel = ?'
        params.append(channel)
    query += ' ORDER BY n.updated_at DESC, n.id DESC'

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_notification_stats(job_id=None):
    """Counts per status, for the summary cards on the log page."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if job_id:
        cursor.execute('''SELECT status, COUNT(*) AS n FROM notifications
                          WHERE job_id = ? GROUP BY status''', (job_id,))
    else:
        cursor.execute('SELECT status, COUNT(*) AS n FROM notifications '
                       'GROUP BY status')
    counts = {r['status']: r['n'] for r in cursor.fetchall()}
    conn.close()
    counts['total'] = sum(counts.values())
    return counts


def get_notifications_for_bookings(channel=None):
    """All notification rows, keyed by (candidate_id, job_id, channel).

    Used by the admin bookings page to show reminder status without
    running one query per row.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if channel:
        cursor.execute('SELECT * FROM notifications WHERE channel = ?',
                       (channel,))
    else:
        cursor.execute('SELECT * FROM notifications')
    result = {}
    for row in cursor.fetchall():
        row = dict(row)
        result[(row['candidate_id'], row['job_id'], row['channel'])] = row
    conn.close()
    return result


if __name__ == '__main__':
    # Initialize database when run directly
    init_database()
    print(f"Database created at: {DATABASE_PATH}")
