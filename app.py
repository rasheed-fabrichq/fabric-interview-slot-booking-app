"""
Main Flask application for Multi-Job Interview Slot Booking System
"""
# dotenv MUST be loaded first, before any module that reads os.environ
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session, Response
import io
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
import pandas as pd
import os
import secrets
import re
import threading
from uuid import UUID
from datetime import datetime, timedelta
from functools import wraps

# Import from local modules
from database import (
    init_database, add_candidate, get_candidate, update_candidate_status,
    get_slots_by_date, book_slot, get_all_bookings,
    initialize_slots, get_dashboard_stats,
    get_booking_by_candidate, clear_all_slots, release_booking,
    is_booking_enabled, set_booking_enabled, get_all_candidates,
    get_job_config, get_all_job_configs,
    get_interview_dates, add_interview_date, delete_interview_date,
    is_booking_enabled_for_job, set_job_booking_enabled,
    get_all_slots,
    create_job, update_interview_date_times,
    get_slot_config, update_slot_config,
    update_booking_email_status, get_booking_with_details
)
from config import (
    get_jobs, is_valid_job_id, get_job_name,
    build_interview_link,
    ADMIN_USERNAME, ADMIN_PASSWORD
)
from email_utils import send_booking_confirmation

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'  # Change this!
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# CSRF Protection Configuration
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit for booking forms
csrf = CSRFProtect(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database on startup
init_database()


def send_confirmation_email_async(candidate_id, job_id, slot_date, slot_time, slot_duration, delay_seconds=300):
    """Send booking confirmation email in a background thread, with optional delay."""
    import time
    print(f"[EMAIL] Thread started for candidate={candidate_id} job={job_id}. Waiting {delay_seconds}s before sending...")
    time.sleep(delay_seconds)
    print(f"[EMAIL] Delay done. Fetching booking details for candidate={candidate_id}")

    try:
        booking = get_booking_with_details(candidate_id)
        if not booking:
            print(f"[EMAIL] ERROR: No booking found for candidate={candidate_id}. Aborting.")
            return

        print(f"[EMAIL] Booking found: name={booking['name']} email={booking['email']} date={booking['date']} time={booking['start_time']}")

        start_dt = datetime.strptime(f"{slot_date} {slot_time}", "%d-%m-%Y %H:%M")
        end_dt = start_dt + timedelta(minutes=slot_duration)
        start_time_fmt = start_dt.strftime("%I:%M %p")
        end_time_fmt = end_dt.strftime("%I:%M %p")

        # The interview link is built from the job the candidate chose,
        # not stored at upload time.
        interview_link_with_expiry = add_expiry_to_interview_link(
            build_interview_link(booking['job_id'], candidate_id),
            start_dt,
            end_dt
        )
        print(f"[EMAIL] Interview link built: {interview_link_with_expiry[:80]}...")

        print(f"[EMAIL] Calling send_booking_confirmation for {booking['email']}...")
        success, error = send_booking_confirmation(
            candidate_name=booking['name'],
            candidate_email=booking['email'],
            job_name=booking['job_name'],
            slot_date=slot_date,
            day_of_week=booking['day_of_week'],
            start_time=start_time_fmt,
            end_time=end_time_fmt,
            interview_link_with_expiry=interview_link_with_expiry,
            duration_minutes=slot_duration,
        )

        if success:
            print(f"[EMAIL] SUCCESS: Confirmation email sent to {booking['email']}")
            update_booking_email_status(candidate_id, 'sent')
        else:
            print(f"[EMAIL] FAILED: Could not send to {booking['email']}. Error: {error}")
            update_booking_email_status(candidate_id, 'failed', error=error)

    except Exception as e:
        print(f"[EMAIL] EXCEPTION for candidate={candidate_id}: {e}")
        update_booking_email_status(candidate_id, 'failed', error=str(e))


# Admin authentication decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# Validation helper functions
def is_valid_email(email):
    """Validate email format"""
    if not email or pd.isna(email):
        return False
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, str(email).strip()) is not None


def is_valid_uuid(uuid_string):
    """Validate UUID format"""
    if not uuid_string or pd.isna(uuid_string):
        return False
    try:
        UUID(str(uuid_string).strip(), version=4)
        return True
    except (ValueError, AttributeError):
        return False


def is_valid_name(name):
    """Validate name - not empty and within character limit"""
    if not name or pd.isna(name):
        return False
    name_str = str(name).strip()
    return len(name_str) > 0 and len(name_str) <= 100


def extract_candidate_id_from_url(interview_link):
    """
    Extract candidate_id from an interview link.

    Candidates are not uploaded per job, so any job UUID in the link's
    path is ignored -- the candidate picks their job when booking, and the
    real interview link is built at that point.

    Returns: (candidate_id, error_message) tuple
    """
    if interview_link is None or (not isinstance(interview_link, str) and pd.isna(interview_link)):
        return None, "Interview link is empty"

    try:
        url_str = str(interview_link).strip()

        if not url_str:
            return None, "Interview link is empty"

        # Check if it's a valid URL format
        if not url_str.startswith('http://') and not url_str.startswith('https://'):
            return None, "Invalid URL format - must start with http:// or https://"

        # Extract candidate_id from query parameter
        candidate_match = re.search(r'[?&]candidate_id=([^&]+)', url_str)
        if not candidate_match:
            return None, "candidate_id parameter not found in URL"

        candidate_id = candidate_match.group(1).strip()

        # Validate the extracted candidate_id is a valid UUID
        if not is_valid_uuid(candidate_id):
            return None, f"Extracted candidate_id '{candidate_id}' is not a valid UUID"

        return candidate_id, None

    except Exception as e:
        return None, f"Error parsing URL: {str(e)}"


def add_expiry_to_interview_link(interview_link, start_datetime, end_datetime):
    """
    Add start_time and end_time parameters to interview link
    Format: &start_time=YYYY-MM-DDTHH:mm&end_time=YYYY-MM-DDTHH:mm
    Returns: Modified URL with expiry parameters
    """
    if not interview_link:
        return ""

    try:
        url_str = str(interview_link).strip()

        # Format datetime objects to required format: YYYY-MM-DDTHH:mm
        start_time_str = start_datetime.strftime("%Y-%m-%dT%H:%M")
        end_time_str = end_datetime.strftime("%Y-%m-%dT%H:%M")

        # Add parameters to URL
        # Check if URL already has query parameters
        separator = '&' if '?' in url_str else '?'
        expiry_link = f"{url_str}{separator}start_time={start_time_str}&end_time={end_time_str}"

        return expiry_link

    except Exception as e:
        return interview_link  # Return original link if there's an error


# ============= PUBLIC ROUTES =============

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/book')
def booking_form():
    """Booking form for candidates.

    The link carries only candidate_id -- the candidate picks which job to
    interview for as the first step of the flow.
    """
    # Check if booking is globally enabled
    if not is_booking_enabled():
        return render_template('booking_closed.html')

    candidate_id = request.args.get('candidate_id')

    if not candidate_id:
        return render_template('invalid_link.html',
                             message='Missing candidate ID in the link.')

    candidate = get_candidate(candidate_id)

    if not candidate:
        return render_template('invalid_link.html',
                             message='Invalid booking link. Please check your email for the correct link.')

    # One booking per person: if they have booked any job, they are done.
    if candidate['status'] == 'booked':
        booking = get_booking_by_candidate(candidate_id)
        slot_duration = get_slot_config()['slot_duration_minutes']

        if booking and booking.get('start_time'):
            time_24h = booking['start_time']
            time_obj = datetime.strptime(time_24h, '%H:%M')
            booking['start_time_formatted'] = time_obj.strftime('%I:%M %p')

            start_datetime = datetime.strptime(
                f"{booking['date']} {time_24h}", "%d-%m-%Y %H:%M")
            end_datetime = start_datetime + timedelta(minutes=slot_duration)
            booking['end_time_formatted'] = end_datetime.strftime('%I:%M %p')

        return render_template('already_booked.html',
                             candidate=candidate,
                             booking=booking)

    # Only jobs that are currently open for booking can be chosen
    open_jobs = [{'job_id': jid, 'job_name': jname}
                 for jid, jname in get_jobs().items()
                 if is_booking_enabled_for_job(jid)]

    if not open_jobs:
        return render_template('booking_closed.html',
                             message='No case studies are currently open for booking.')

    # Update status to 'clicked' if it was 'pending'
    if candidate['status'] == 'pending':
        update_candidate_status(candidate_id, 'clicked')

    # Generate unique booking token for this session
    booking_token = secrets.token_urlsafe(32)
    session['booking_token'] = booking_token
    session['booking_candidate_id'] = candidate_id
    session['booking_token_used'] = False

    return render_template('booking_form.html',
                         candidate=candidate,
                         booking_token=booking_token,
                         jobs=open_jobs)


@app.route('/api/job-dates')
def get_job_dates_api():
    """Available interview dates.

    Dates are shared by every job; job_id is still accepted and validated
    so existing booking links keep working.
    """
    job_id = request.args.get('job_id')

    if not job_id:
        return jsonify({'error': 'Missing job_id parameter'}), 400

    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job_id'}), 400

    # Candidate-facing: hide days with no slots left today or later.
    return jsonify(get_interview_dates(only_bookable=True))


@app.route('/api/slots')
def get_slots_api():
    """Available slots for a date.

    Slots are shared across all jobs, so availability already accounts
    for bookings made from every other job.
    """
    job_id = request.args.get('job_id')
    date = request.args.get('date')

    if not job_id:
        return jsonify({'error': 'Missing job_id parameter'}), 400

    if not date:
        return jsonify({'error': 'Missing date parameter'}), 400

    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job_id'}), 400

    # Candidate-facing: past slots are filtered out by default.
    return jsonify(get_slots_by_date(date))


@app.route('/book/confirm', methods=['POST'])
@csrf.exempt  # Using custom booking token instead of CSRF
def confirm_booking():
    """Confirm slot booking with enhanced security (9-layer validation)"""
    data = request.json

    candidate_id = data.get('candidate_id')
    job_id = data.get('job_id')
    slot_id = data.get('slot_id')
    booking_token = data.get('booking_token')

    # Security Check 1: Validate all required fields
    if not all([candidate_id, job_id, slot_id, booking_token]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Security Check 2: Validate booking token
    session_token = session.get('booking_token')
    session_candidate_id = session.get('booking_candidate_id')
    token_used = session.get('booking_token_used', True)

    if not session_token or booking_token != session_token:
        return jsonify({'error': 'Invalid or expired booking session. Please reload the booking page.'}), 403

    # Security Check 3: Token not already used
    if token_used:
        return jsonify({'error': 'This booking session has already been used. Please reload the page.'}), 403

    # Security Check 4: Validate candidate_id matches session
    if candidate_id != session_candidate_id:
        return jsonify({'error': 'Candidate ID mismatch. Security violation detected.'}), 403

    # Security Check 5: Validate the chosen job exists. The job is picked
    # in the form rather than fixed by the link, so it is validated here
    # rather than compared against the session.
    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job selected.'}), 400

    # Security Check 6: Validate candidate exists
    candidate = get_candidate(candidate_id)
    if not candidate:
        return jsonify({'error': 'Invalid candidate ID'}), 400

    # Security Check 7: Candidate status must be 'clicked' (not 'pending')
    if candidate['status'] == 'pending':
        return jsonify({'error': 'Access denied. You must access the booking form through the provided link first.'}), 403

    if candidate['status'] == 'booked':
        return jsonify({'error': 'You have already booked an interview slot.'}), 400

    # Security Check 9: Check if booking is enabled for this job
    if not is_booking_enabled_for_job(job_id):
        return jsonify({'error': f'Booking for {get_job_name(job_id)} has been closed by the administrator.'}), 403

    # Mark token as used to prevent reuse
    session['booking_token_used'] = True

    # Book the slot (with transaction safety)
    result = book_slot(candidate_id, job_id, slot_id)

    if 'error' in result:
        # If booking failed, allow retry by resetting token
        session['booking_token_used'] = False
        return jsonify(result), 400

    # Clear session data after successful booking
    session.pop('booking_token', None)
    session.pop('booking_candidate_id', None)
    session.pop('booking_token_used', None)

    slot_duration = get_slot_config()['slot_duration_minutes']

    # Calculate end time
    slot_date = result['slot_date']
    slot_time = result['slot_time']
    start_datetime = datetime.strptime(f"{slot_date} {slot_time}", "%d-%m-%Y %H:%M")
    end_datetime = start_datetime + timedelta(minutes=slot_duration)

    # Send confirmation email in background (non-blocking)
    email_thread = threading.Thread(
        target=send_confirmation_email_async,
        args=(candidate_id, job_id, slot_date, slot_time, slot_duration),
        daemon=True
    )
    email_thread.start()

    # Format times in 12-hour format with AM/PM
    start_time_12h = start_datetime.strftime("%I:%M %p")
    end_time_12h = end_datetime.strftime("%I:%M %p")

    # Format dates separately (end date might be next day)
    start_date_formatted = start_datetime.strftime("%d-%m-%Y")
    end_date_formatted = end_datetime.strftime("%d-%m-%Y")

    return jsonify({
        'success': True,
        'message': f'Your interview slot for {start_time_12h} on {start_date_formatted} has been confirmed.',
        'start_time': f"{start_date_formatted} {start_time_12h}",
        'end_time': f"{end_date_formatted} {end_time_12h}",
        'job_name': get_job_name(job_id)
    })


# ============= ADMIN ROUTES =============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html',
                                 error='Invalid credentials')

    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard with statistics"""
    stats = get_dashboard_stats()
    return render_template('admin_dashboard.html', stats=stats)


@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    """Upload candidates via CSV/Excel"""
    if request.method == 'POST':
        # Candidates are uploaded once for the whole drive, not per job --
        # they choose their job when booking.
        if 'file' not in request.files:
            return render_template('admin_upload.html',
                                 error='No file uploaded',
                                 jobs=get_jobs())

        file = request.files['file']

        if file.filename == '':
            return render_template('admin_upload.html',
                                 error='No file selected',
                                 jobs=get_jobs())

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                # Read file based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                elif filename.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(filepath)
                else:
                    return render_template('admin_upload.html',
                                         error='Invalid file format. Use CSV or Excel.',
                                         jobs=get_jobs())

                # Expected headers: Name, Email, AI Interview Link.
                # Matched case-insensitively with surrounding whitespace
                # trimmed, so 'name' / ' Name ' / 'NAME' all work.
                header_map = {
                    str(col).strip().lower(): col for col in df.columns
                }
                required_columns = ['Name', 'Email', 'AI Interview Link']
                missing_columns = [c for c in required_columns
                                   if c.lower() not in header_map]
                if missing_columns:
                    return render_template(
                        'admin_upload.html',
                        error=(f"Missing required column(s): "
                               f"{', '.join(missing_columns)}. "
                               f"Expected: {', '.join(required_columns)}. "
                               f"Found: {', '.join(str(c) for c in df.columns)}"),
                        jobs=get_jobs())

                name_col = header_map['name']
                email_col = header_map['email']
                link_col = header_map['ai interview link']

                # Add candidates with validation
                success_count = 0
                error_count = 0
                errors = []

                for index, row in df.iterrows():
                    row_num = index + 2  # Excel row number (header is row 1)

                    # Get values
                    name = row.get(name_col)
                    email = row.get(email_col)
                    interview_link = row.get(link_col)

                    # Prepare row display for error messages
                    row_display = (f"Name='{name}', Email='{email}', "
                                   f"AI Interview Link='{interview_link}'")

                    # Validation 1: Check for missing fields
                    if pd.isna(name) or pd.isna(email) or pd.isna(interview_link):
                        error_count += 1
                        missing_fields = []
                        if pd.isna(name):
                            missing_fields.append('Name')
                        if pd.isna(email):
                            missing_fields.append('Email')
                        if pd.isna(interview_link):
                            missing_fields.append('AI Interview Link')
                        errors.append(f"Row {row_num}: Missing required fields: {', '.join(missing_fields)} | Row data: {row_display}")
                        continue

                    # Validation 2: Extract candidate_id from the interview
                    # link. Any job in the link is ignored -- the candidate
                    # picks their job when booking.
                    extracted_candidate_id, link_error = extract_candidate_id_from_url(interview_link)
                    if link_error:
                        error_count += 1
                        errors.append(f"Row {row_num}: {link_error} | Row data: {row_display}")
                        continue

                    # Validation 3: Validate name
                    if not is_valid_name(name):
                        error_count += 1
                        if pd.isna(name) or str(name).strip() == '':
                            errors.append(f"Row {row_num}: Name cannot be empty | Row data: {row_display}")
                        else:
                            errors.append(f"Row {row_num}: Name exceeds 100 character limit (current: {len(str(name))}) | Row data: {row_display}")
                        continue

                    # Validation 4: Validate email
                    if not is_valid_email(email):
                        error_count += 1
                        errors.append(f"Row {row_num}: Invalid email format | Row data: {row_display}")
                        continue

                    # All validations passed, try to add candidate
                    result = add_candidate(
                        extracted_candidate_id,
                        str(name).strip(),
                        str(email).strip()
                    )

                    if 'success' in result:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(f"Row {row_num}: {result.get('error')} | Row data: {row_display}")

                # Clean up uploaded file
                os.remove(filepath)

                return render_template('admin_upload.html',
                                     success=f'{success_count} candidates uploaded successfully.',
                                     error=f'{error_count} errors occurred.' if error_count > 0 else None,
                                     errors=errors[:50],  # Show first 50 errors
                                     jobs=get_jobs())

            except Exception as e:
                return render_template('admin_upload.html',
                                     error=f'Error processing file: {str(e)}',
                                     jobs=get_jobs())

    return render_template('admin_upload.html', jobs=get_jobs())


@app.route('/admin/job-config', methods=['GET', 'POST'])
@admin_required
def admin_job_config():
    """Configure the global slot settings shared by every job.

    Window, duration and capacity apply to all jobs at once, because they
    all draw from one shared pool of interview slots.
    """
    if request.method == 'POST':
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        duration = request.form.get('duration')
        capacity = request.form.get('capacity')

        if not all([start_time, end_time, duration, capacity]):
            return render_template('admin_job_config.html',
                                 error='All fields are required',
                                 jobs=get_jobs(),
                                 config=get_slot_config())

        try:
            duration_int = int(duration)
            capacity_int = int(capacity)

            if duration_int <= 0 or capacity_int <= 0:
                raise ValueError("Duration and capacity must be positive")

            update_slot_config(start_time, end_time, duration_int, capacity_int)

            return render_template(
                'admin_job_config.html',
                success=('Slot configuration updated for all jobs. '
                         'Clear and re-initialize slots for changes to '
                         'affect already-generated slots.'),
                jobs=get_jobs(),
                config=get_slot_config())

        except ValueError as e:
            return render_template('admin_job_config.html',
                                 error=f'Invalid input: {str(e)}',
                                 jobs=get_jobs(),
                                 config=get_slot_config())

    return render_template('admin_job_config.html',
                         jobs=get_jobs(),
                         config=get_slot_config())


@app.route('/admin/job-dates', methods=['GET', 'POST'])
@admin_required
def admin_job_dates():
    """Manage interview dates. Dates are shared by every job."""

    def render(**kwargs):
        return render_template('admin_job_dates.html',
                               dates=get_interview_dates(),
                               config=get_slot_config(),
                               **kwargs)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            date_str = request.form.get('date')  # yyyy-mm-dd from date input
            start_time = request.form.get('start_time')  # optional override
            end_time = request.form.get('end_time')      # optional override

            if not date_str:
                return render(error='Date is required')

            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d-%m-%Y')
                day_of_week = date_obj.strftime('%A')
            except ValueError:
                return render(error='Invalid date format')

            # Only treat times as overrides when actually provided
            custom_start = start_time if start_time and start_time.strip() else None
            custom_end = end_time if end_time and end_time.strip() else None

            result = add_interview_date(formatted_date, day_of_week,
                                        custom_start, custom_end)

            if 'error' in result:
                return render(error=result['error'])

            time_info = ""
            if custom_start and custom_end:
                time_info = f" (Custom times: {custom_start} - {custom_end})"

            return render(
                success=(f'Date {formatted_date} ({day_of_week}){time_info} '
                         f'added. Initialize slots to generate its time slots.'))

        elif action == 'update_times':
            date = request.form.get('date')  # dd-mm-yyyy
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')

            if not all([date, start_time, end_time]):
                return render(
                    error='Date, start time, and end time are required')

            update_interview_date_times(date, start_time, end_time)

            return render(
                success=(f'Time range updated for {date}: {start_time} - '
                         f'{end_time}. Clear and re-initialize slots for this '
                         f'to take effect.'))

        elif action == 'delete':
            date = request.form.get('date')  # dd-mm-yyyy
            confirmed = request.form.get('confirm') == 'yes'

            # Slots are shared, so deleting a date cancels bookings across
            # every job. delete_interview_date refuses unless confirmed.
            result = delete_interview_date(date, force=confirmed)

            if 'error' in result:
                return render(error=result['error'],
                              confirm_delete_date=date,
                              confirm_delete_count=result.get('booking_count'))

            deleted = result.get('bookings_deleted', 0)
            note = (f' {deleted} booking(s) across all jobs were cancelled.'
                    if deleted else '')
            return render(success=f'Date {date} removed.{note}')

    return render()


@app.route('/admin/init-slots', methods=['GET', 'POST'])
@admin_required
def admin_init_slots():
    """Initialize the shared slot pool used by every job."""

    def render(**kwargs):
        return render_template('admin_init_slots.html',
                               dates=get_interview_dates(),
                               config=get_slot_config(),
                               slots=get_all_slots(),
                               **kwargs)

    if request.method == 'POST':
        result = initialize_slots()

        if 'error' in result:
            return render(error=result['error'])

        skipped = result.get('dates_skipped') or []
        note = (f" {len(skipped)} date(s) already had slots and were left "
                f"untouched." if skipped else "")
        return render(
            success=(f"{result['slots_created']} slots initialized, shared "
                     f"across all jobs.{note}"))

    return render()


@app.route('/admin/clear-slots', methods=['POST'])
@admin_required
def admin_clear_slots():
    """Clear the entire shared slot pool.

    Slots are shared, so this wipes scheduling for every job at once and
    cancels all bookings. Requires explicit confirmation when bookings
    exist.
    """
    confirmed = request.form.get('confirm') == 'yes'
    result = clear_all_slots(force=confirmed)

    if 'error' in result:
        return render_template('admin_init_slots.html',
                               error=result['error'],
                               confirm_clear=True,
                               confirm_clear_count=result.get('booking_count'),
                               dates=get_interview_dates(),
                               config=get_slot_config(),
                               slots=get_all_slots())

    deleted = result.get('bookings_deleted', 0)
    note = f' {deleted} booking(s) were cancelled.' if deleted else ''
    return render_template('admin_init_slots.html',
                           success=f'All slots cleared.{note}',
                           dates=get_interview_dates(),
                           config=get_slot_config(),
                           slots=get_all_slots())


@app.route('/admin/toggle-booking', methods=['POST'])
@admin_required
def admin_toggle_booking():
    """Toggle booking enabled/disabled status (global)"""
    action = request.form.get('action')  # 'enable' or 'disable'

    if action == 'enable':
        set_booking_enabled(True)
    elif action == 'disable':
        set_booking_enabled(False)

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/toggle-job-booking/<job_id>', methods=['POST'])
@admin_required
def admin_toggle_job_booking(job_id):
    """Toggle booking enabled/disabled for a specific job"""
    if not is_valid_job_id(job_id):
        return redirect(url_for('admin_dashboard'))

    action = request.form.get('action')  # 'enable' or 'disable'

    if action == 'enable':
        set_job_booking_enabled(job_id, True)
    elif action == 'disable':
        set_job_booking_enabled(job_id, False)

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/export')
@admin_required
def admin_export():
    """Export all bookings to Excel or CSV"""
    # Get export format from query parameter (default: xlsx)
    export_format = request.args.get('format', 'xlsx').lower()
    job_id = request.args.get('job_id')  # Optional job filter

    # Filter by job if specified
    bookings = get_all_bookings(job_id if job_id and is_valid_job_id(job_id) else None)

    if not bookings:
        return "No bookings to export", 400

    # Prepare data for export
    slot_duration = get_slot_config()['slot_duration_minutes']
    export_data = []
    for booking in bookings:
        # Parse start time
        start_datetime = datetime.strptime(
            f"{booking['date']} {booking['start_time']}",
            "%d-%m-%Y %H:%M"
        )
        end_datetime = start_datetime + timedelta(minutes=slot_duration)

        # Build the interview link for the job this candidate chose
        interview_link = build_interview_link(
            booking['job_id'], booking['candidate_id'])
        interview_link_with_expiry = add_expiry_to_interview_link(
            interview_link,
            start_datetime,
            end_datetime
        )

        export_data.append({
            'Candidate ID': booking['candidate_id'],
            'Name': booking['name'],
            'Email': booking['email'],
            'Job': booking['job_name'],
            'Job ID': booking['job_id'],
            'Date': booking['date'],
            'Day': booking['day_of_week'],
            'Start Time': start_datetime.strftime("%d-%m-%Y %H:%M"),
            'End Time': end_datetime.strftime("%d-%m-%Y %H:%M"),
            'Interview Link': interview_link,
            'Interview Link with Expiry': interview_link_with_expiry,
            'Booked At': booking['booked_at']
        })

    # Create DataFrame
    df = pd.DataFrame(export_data)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_suffix = f"_{job_id}" if job_id else "_all"
    filename = f"bookings{job_suffix}_{timestamp}"

    # Export based on format
    if export_format == 'csv':
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f'{filename}.csv')
        df.to_csv(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f'{filename}.csv')
    else:  # xlsx
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f'{filename}.xlsx')
        df.to_excel(filepath, index=False, engine='openpyxl')
        return send_file(filepath, as_attachment=True, download_name=f'{filename}.xlsx')


@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    """View all bookings"""
    job_id = request.args.get('job_id')  # Optional job filter
    bookings = get_all_bookings(job_id if job_id and is_valid_job_id(job_id) else None)

    for booking in bookings:
        slot_duration = booking.get('slot_duration_minutes')
        if slot_duration:
            start_time = datetime.strptime(booking['start_time'], "%H:%M")
            end_time = start_time + timedelta(minutes=slot_duration)
            booking['end_time'] = end_time.strftime("%H:%M")

    return render_template('admin_bookings.html',
                         bookings=bookings,
                         jobs=get_jobs(),
                         selected_job=job_id)


@app.route('/admin/candidates')
@admin_required
def admin_candidates():
    """View all candidates"""
    job_id = request.args.get('job_id')  # Optional job filter
    candidates = get_all_candidates(job_id if job_id and is_valid_job_id(job_id) else None)

    return render_template('admin_candidates.html',
                         candidates=candidates,
                         jobs=get_jobs(),
                         selected_job=job_id)


@app.route('/admin/export-pending')
@admin_required
def admin_export_pending():
    """Export candidates who have not booked yet, with their booking links.

    Non-booked candidates belong to no job, so this is not job-filtered.
    """
    status_filter = request.args.get('status', 'all')  # 'pending', 'clicked', or 'all'

    candidates = get_all_candidates()

    # Filter for non-booked candidates (pending or clicked)
    if status_filter == 'pending':
        filtered = [c for c in candidates if c['status'] == 'pending']
    elif status_filter == 'clicked':
        filtered = [c for c in candidates if c['status'] == 'clicked']
    else:
        filtered = [c for c in candidates if c['status'] in ('pending', 'clicked')]

    if not filtered:
        return "No candidates to export", 400

    # Prepare CSV data, including the slot-booking link to send them
    base = request.host_url.rstrip('/')
    export_data = []
    for c in filtered:
        export_data.append({
            'Name': c['name'],
            'Email': c['email'],
            'Candidate ID': c['candidate_id'],
            'Status': c['status'],
            'Slot Booking Link': f"{base}/book?candidate_id={c['candidate_id']}",
        })

    df = pd.DataFrame(export_data)

    # Generate CSV
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    status_suffix = f"_{status_filter}" if status_filter != 'all' else "_pending_clicked"
    filename = f"candidates{status_suffix}.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/admin/release-booking/<candidate_id>', methods=['POST'])
@admin_required
@csrf.exempt
def admin_release_booking(candidate_id):
    """Cancel a candidate's booking so they can book again.

    Frees the slot for everyone and lets the candidate re-use their
    original booking link to pick a different case study or time.
    """
    candidate = get_candidate(candidate_id)
    if not candidate:
        return jsonify({'error': 'Candidate not found'}), 404

    result = release_booking(candidate_id)

    if 'error' in result:
        return jsonify(result), 400

    print(f"[ADMIN] Released booking for candidate={candidate_id} "
          f"({result['freed_date']} {result['freed_time']})")

    booking_link = f"{request.host_url.rstrip('/')}/book?candidate_id={candidate_id}"
    return jsonify({
        'success': True,
        'message': (f"Booking released. {result['freed_date']} "
                    f"{result['freed_time']} is free again."),
        'booking_link': booking_link,
    })


@app.route('/admin/resend-email/<candidate_id>', methods=['POST'])
@admin_required
@csrf.exempt
def admin_resend_email(candidate_id):
    """Resend booking confirmation email for a specific candidate."""
    booking = get_booking_with_details(candidate_id)
    if not booking:
        return jsonify({'error': 'Booking not found'}), 404

    slot_duration = get_slot_config()['slot_duration_minutes']

    print(f"[EMAIL] Admin triggered resend for candidate={candidate_id}")
    email_thread = threading.Thread(
        target=send_confirmation_email_async,
        args=(candidate_id, booking['job_id'], booking['date'],
              booking['start_time'], slot_duration, 0),  # delay=0 for manual resend
        daemon=True
    )
    email_thread.start()

    return jsonify({'success': True, 'message': 'Email queued for sending'})


@app.route('/admin/slots')
@admin_required
def admin_slots():
    """View the shared slot pool with booking statistics.

    There is one pool for all jobs, so this is not filtered by job.
    """
    all_slots = get_all_slots()

    # Group slots by date for display
    slots_by_date = {}
    for slot in all_slots:
        date = slot['date']
        if date not in slots_by_date:
            slots_by_date[date] = {
                'date': date,
                'day_of_week': slot['day_of_week'],
                'slots': [],
                'total_capacity': 0,
                'total_booked': 0
            }
        slots_by_date[date]['slots'].append(slot)
        slots_by_date[date]['total_capacity'] += slot['max_capacity']
        slots_by_date[date]['total_booked'] += slot['booked_count']

    # get_all_slots already returns rows in date/time order
    dates_data = list(slots_by_date.values())

    return render_template('admin_slots.html',
                         dates_data=dates_data,
                         config=get_slot_config())


@app.route('/admin/jobs', methods=['GET', 'POST'])
@admin_required
def admin_jobs():
    """Manage jobs - create new jobs"""
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        job_name = request.form.get('job_name')

        if not all([job_id, job_name]):
            return render_template('admin_jobs.html',
                                 error='Job ID and Job Name are required',
                                 jobs=get_jobs(),
                                 config=get_slot_config())

        # Validate UUID format
        try:
            UUID(str(job_id).strip(), version=4)
        except (ValueError, AttributeError):
            return render_template('admin_jobs.html',
                                 error='Job ID must be a valid UUID (e.g., fc4c9c14-208c-427a-be2e-4d0080f286d6)',
                                 jobs=get_jobs(),
                                 config=get_slot_config())

        # Scheduling is global -- a new job automatically uses the shared
        # window, duration, capacity and dates.
        result = create_job(job_id.strip(), job_name.strip())

        if 'error' in result:
            return render_template('admin_jobs.html',
                                 error=result['error'],
                                 jobs=get_jobs(),
                                 config=get_slot_config())

        return render_template('admin_jobs.html',
                             success=f'Job "{job_name}" created successfully!',
                             jobs=get_jobs(),
                             config=get_slot_config())

    return render_template('admin_jobs.html', jobs=get_jobs(),
                           config=get_slot_config())


# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
