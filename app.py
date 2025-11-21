"""
Main Flask application for Multi-Job Interview Slot Booking System
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session, Response
import io
from flask_wtf.csrf import CSRFProtect
from werkzeug.utils import secure_filename
import pandas as pd
import os
import secrets
import re
from uuid import UUID
from datetime import datetime, timedelta
from functools import wraps

# Import from local modules
from database import (
    init_database, add_candidate, get_candidate, update_candidate_status,
    get_slots_by_job_and_date, book_slot, get_all_bookings,
    initialize_slots_for_job, get_dashboard_stats,
    get_booking_by_candidate_and_job, clear_slots_for_job,
    is_booking_enabled, set_booking_enabled, get_all_candidates,
    get_job_config, get_all_job_configs, update_job_config,
    get_job_dates, add_job_date, delete_job_date,
    is_booking_enabled_for_job, set_job_booking_enabled,
    get_candidate_booking_for_job, get_all_slots_for_job
)
from config import (
    JOBS, is_valid_job_id, get_job_name,
    ADMIN_USERNAME, ADMIN_PASSWORD
)

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


def extract_candidate_id_and_job_from_url(interview_link):
    """
    Extract candidate_id and job_id from interview link URL
    Expected format: https://app.fabrichq.ai/interview/<JOB_UUID>/?candidate_id=<CANDIDATE_UUID>
    Returns: (candidate_id, job_id, error_message) tuple
    """
    if not interview_link or pd.isna(interview_link):
        return None, None, "Interview link is empty"

    try:
        url_str = str(interview_link).strip()

        # Check if it's a valid URL format
        if not url_str.startswith('http://') and not url_str.startswith('https://'):
            return None, None, "Invalid URL format - must start with http:// or https://"

        # Extract job_id from URL path pattern: /interview/<JOB_UUID>/
        job_path_match = re.search(r'/interview/([a-f0-9\-]+)/?', url_str, re.IGNORECASE)
        if not job_path_match:
            return None, None, "job_id not found in URL path - expected format: /interview/<JOB_UUID>/"

        job_id = job_path_match.group(1).strip()

        # Validate job_id is a valid UUID
        if not is_valid_uuid(job_id):
            return None, None, f"Extracted job_id '{job_id}' is not a valid UUID"

        # Validate job_id exists in our system
        if not is_valid_job_id(job_id):
            return None, None, f"Extracted job_id '{job_id}' is not configured in the system"

        # Extract candidate_id from query parameter
        candidate_match = re.search(r'[?&]candidate_id=([^&]+)', url_str)
        if not candidate_match:
            return None, None, "candidate_id parameter not found in URL"

        candidate_id = candidate_match.group(1).strip()

        # Validate the extracted candidate_id is a valid UUID
        if not is_valid_uuid(candidate_id):
            return None, None, f"Extracted candidate_id '{candidate_id}' is not a valid UUID"

        return candidate_id, job_id, None

    except Exception as e:
        return None, None, f"Error parsing URL: {str(e)}"


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
    """Main booking form for candidates"""
    # Check if booking is globally enabled
    if not is_booking_enabled():
        return render_template('booking_closed.html')

    candidate_id = request.args.get('candidate_id')
    job_id = request.args.get('job_id')

    if not candidate_id:
        return render_template('invalid_link.html',
                             message='Missing candidate ID in the link.')

    if not job_id:
        return render_template('invalid_link.html',
                             message='Missing job ID in the link.')

    # Validate job_id
    if not is_valid_job_id(job_id):
        return render_template('invalid_link.html',
                             message='Invalid job ID in the link.')

    # Check if booking is enabled for this specific job
    if not is_booking_enabled_for_job(job_id):
        return render_template('booking_closed.html',
                             message=f'Booking for {get_job_name(job_id)} is currently closed.')

    # Get candidate details
    candidate = get_candidate(candidate_id, job_id)

    if not candidate:
        return render_template('invalid_link.html',
                             message='Invalid booking link. Please check your email for the correct link.')

    # Check if already booked for THIS JOB
    if candidate['status'] == 'booked':
        booking = get_booking_by_candidate_and_job(candidate_id, job_id)

        # Get job config for duration
        job_config = get_job_config(job_id)
        slot_duration = job_config['slot_duration_minutes'] if job_config else 30

        # Format time to 12-hour format with AM/PM
        if booking and booking.get('start_time'):
            time_24h = booking['start_time']
            time_obj = datetime.strptime(time_24h, '%H:%M')
            booking['start_time_formatted'] = time_obj.strftime('%I:%M %p')

            # Calculate end time
            start_datetime = datetime.strptime(f"{booking['date']} {time_24h}", "%d-%m-%Y %H:%M")
            end_datetime = start_datetime + timedelta(minutes=slot_duration)
            booking['end_time_formatted'] = end_datetime.strftime('%I:%M %p')

        return render_template('already_booked.html',
                             candidate=candidate,
                             booking=booking)

    # Update status to 'clicked' if it was 'pending'
    if candidate['status'] == 'pending':
        update_candidate_status(candidate_id, job_id, 'clicked')

    # Generate unique booking token for this session
    booking_token = secrets.token_urlsafe(32)
    session['booking_token'] = booking_token
    session['booking_candidate_id'] = candidate_id
    session['booking_job_id'] = job_id
    session['booking_token_used'] = False

    return render_template('booking_form.html',
                         candidate=candidate,
                         booking_token=booking_token,
                         job_id=job_id,
                         job_name=get_job_name(job_id))


@app.route('/api/job-dates')
def get_job_dates_api():
    """API endpoint to get available dates for a specific job"""
    job_id = request.args.get('job_id')

    if not job_id:
        return jsonify({'error': 'Missing job_id parameter'}), 400

    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job_id'}), 400

    dates = get_job_dates(job_id)
    return jsonify(dates)


@app.route('/api/slots')
def get_slots_api():
    """API endpoint to get available slots for a specific job and date"""
    job_id = request.args.get('job_id')
    date = request.args.get('date')

    if not job_id:
        return jsonify({'error': 'Missing job_id parameter'}), 400

    if not date:
        return jsonify({'error': 'Missing date parameter'}), 400

    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job_id'}), 400

    slots = get_slots_by_job_and_date(job_id, date)
    return jsonify(slots)


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
    session_job_id = session.get('booking_job_id')
    token_used = session.get('booking_token_used', True)

    if not session_token or booking_token != session_token:
        return jsonify({'error': 'Invalid or expired booking session. Please reload the booking page.'}), 403

    # Security Check 3: Token not already used
    if token_used:
        return jsonify({'error': 'This booking session has already been used. Please reload the page.'}), 403

    # Security Check 4: Validate candidate_id matches session
    if candidate_id != session_candidate_id:
        return jsonify({'error': 'Candidate ID mismatch. Security violation detected.'}), 403

    # Security Check 5: Validate job_id matches session
    if job_id != session_job_id:
        return jsonify({'error': 'Job ID mismatch. Security violation detected.'}), 403

    # Security Check 6: Validate candidate exists for this job
    candidate = get_candidate(candidate_id, job_id)
    if not candidate:
        return jsonify({'error': 'Invalid candidate ID or job ID'}), 400

    # Security Check 7: Candidate status must be 'clicked' (not 'pending')
    if candidate['status'] == 'pending':
        return jsonify({'error': 'Access denied. You must access the booking form through the provided link first.'}), 403

    if candidate['status'] == 'booked':
        return jsonify({'error': 'You have already booked a slot for this job.'}), 400

    # Security Check 8: Validate job_id exists
    if not is_valid_job_id(job_id):
        return jsonify({'error': 'Invalid job ID.'}), 400

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
    session.pop('booking_job_id', None)
    session.pop('booking_token_used', None)

    # Get job config for duration
    job_config = get_job_config(job_id)
    slot_duration = job_config['slot_duration_minutes'] if job_config else 30

    # Calculate end time
    slot_date = result['slot_date']
    slot_time = result['slot_time']
    start_datetime = datetime.strptime(f"{slot_date} {slot_time}", "%d-%m-%Y %H:%M")
    end_datetime = start_datetime + timedelta(minutes=slot_duration)

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
        # Get selected job_id from form
        job_id = request.form.get('job_id')

        if not job_id or not is_valid_job_id(job_id):
            return render_template('admin_upload.html',
                                 error='Please select a valid job',
                                 jobs=JOBS)

        if 'file' not in request.files:
            return render_template('admin_upload.html',
                                 error='No file uploaded',
                                 jobs=JOBS)

        file = request.files['file']

        if file.filename == '':
            return render_template('admin_upload.html',
                                 error='No file selected',
                                 jobs=JOBS)

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
                                         jobs=JOBS)

                # Validate columns (removed college_name, kept interview_link optional)
                required_columns = ['name', 'email', 'interview_link']
                if not all(col in df.columns for col in required_columns):
                    return render_template('admin_upload.html',
                                         error=f'Missing required columns: {required_columns}',
                                         jobs=JOBS)

                # Add candidates with validation
                success_count = 0
                error_count = 0
                errors = []

                for index, row in df.iterrows():
                    row_num = index + 2  # Excel row number (header is row 1)

                    # Get values
                    name = row.get('name')
                    email = row.get('email')
                    interview_link = row.get('interview_link')

                    # Prepare row display for error messages
                    row_display = f"name='{name}', email='{email}', interview_link='{interview_link}'"

                    # Validation 1: Check for missing fields
                    if pd.isna(name) or pd.isna(email) or pd.isna(interview_link):
                        error_count += 1
                        missing_fields = []
                        if pd.isna(name):
                            missing_fields.append('name')
                        if pd.isna(email):
                            missing_fields.append('email')
                        if pd.isna(interview_link):
                            missing_fields.append('interview_link')
                        errors.append(f"Row {row_num}: Missing required fields: {', '.join(missing_fields)} | Row data: {row_display}")
                        continue

                    # Validation 2: Validate interview_link and extract candidate_id and job_id
                    extracted_candidate_id, extracted_job_id, link_error = extract_candidate_id_and_job_from_url(interview_link)
                    if link_error:
                        error_count += 1
                        errors.append(f"Row {row_num}: {link_error} | Row data: {row_display}")
                        continue

                    # Validation 3: Verify job_id matches selected job
                    if extracted_job_id != job_id:
                        error_count += 1
                        errors.append(f"Row {row_num}: job_id mismatch - Interview link has '{extracted_job_id}' but you selected '{job_id}' | Row data: {row_display}")
                        continue

                    # Validation 4: Validate UUID
                    if not is_valid_uuid(extracted_candidate_id):
                        error_count += 1
                        errors.append(f"Row {row_num}: Invalid UUID format for candidate_id | Row data: {row_display}")
                        continue

                    # Validation 5: Validate name
                    if not is_valid_name(name):
                        error_count += 1
                        if pd.isna(name) or str(name).strip() == '':
                            errors.append(f"Row {row_num}: Name cannot be empty | Row data: {row_display}")
                        else:
                            errors.append(f"Row {row_num}: Name exceeds 100 character limit (current: {len(str(name))}) | Row data: {row_display}")
                        continue

                    # Validation 6: Validate email
                    if not is_valid_email(email):
                        error_count += 1
                        errors.append(f"Row {row_num}: Invalid email format | Row data: {row_display}")
                        continue

                    # All validations passed, try to add candidate
                    result = add_candidate(
                        extracted_candidate_id,
                        job_id,
                        str(name).strip(),
                        str(email).strip(),
                        str(interview_link).strip()
                    )

                    if 'success' in result:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(f"Row {row_num}: {result.get('error')} | Row data: {row_display}")

                # Clean up uploaded file
                os.remove(filepath)

                return render_template('admin_upload.html',
                                     success=f'{success_count} candidates uploaded successfully for {get_job_name(job_id)}.',
                                     error=f'{error_count} errors occurred.' if error_count > 0 else None,
                                     errors=errors[:50],  # Show first 50 errors
                                     jobs=JOBS)

            except Exception as e:
                return render_template('admin_upload.html',
                                     error=f'Error processing file: {str(e)}',
                                     jobs=JOBS)

    return render_template('admin_upload.html', jobs=JOBS)


@app.route('/admin/job-config', methods=['GET', 'POST'])
@admin_required
def admin_job_config():
    """Configure job settings (time range, duration, capacity)"""
    if request.method == 'POST':
        job_id = request.form.get('job_id')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        duration = request.form.get('duration')
        capacity = request.form.get('capacity')

        if not all([job_id, start_time, end_time, duration, capacity]):
            return render_template('admin_job_config.html',
                                 error='All fields are required',
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

        if not is_valid_job_id(job_id):
            return render_template('admin_job_config.html',
                                 error='Invalid job ID',
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

        try:
            duration_int = int(duration)
            capacity_int = int(capacity)

            if duration_int <= 0 or capacity_int <= 0:
                raise ValueError("Duration and capacity must be positive")

            update_job_config(job_id, start_time, end_time, duration_int, capacity_int)

            return render_template('admin_job_config.html',
                                 success=f'Configuration updated for {get_job_name(job_id)}',
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

        except ValueError as e:
            return render_template('admin_job_config.html',
                                 error=f'Invalid input: {str(e)}',
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

    return render_template('admin_job_config.html',
                         jobs=JOBS,
                         configs=get_all_job_configs())


@app.route('/admin/job-dates', methods=['GET', 'POST'])
@admin_required
def admin_job_dates():
    """Manage interview dates for each job"""
    if request.method == 'POST':
        action = request.form.get('action')
        job_id = request.form.get('job_id')

        if not is_valid_job_id(job_id):
            return render_template('admin_job_dates.html',
                                 error='Invalid job ID',
                                 jobs=JOBS,
                                 all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

        if action == 'add':
            date_str = request.form.get('date')  # Format: yyyy-mm-dd from date input

            if not date_str:
                return render_template('admin_job_dates.html',
                                     error='Date is required',
                                     jobs=JOBS,
                                     all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

            try:
                # Convert yyyy-mm-dd to dd-mm-yyyy and get day of week
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d-%m-%Y')
                day_of_week = date_obj.strftime('%A')

                result = add_job_date(job_id, formatted_date, day_of_week)

                if 'error' in result:
                    return render_template('admin_job_dates.html',
                                         error=result['error'],
                                         jobs=JOBS,
                                         all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

                return render_template('admin_job_dates.html',
                                     success=f'Date {formatted_date} ({day_of_week}) added to {get_job_name(job_id)}',
                                     jobs=JOBS,
                                     all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

            except ValueError:
                return render_template('admin_job_dates.html',
                                     error='Invalid date format',
                                     jobs=JOBS,
                                     all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

        elif action == 'delete':
            date = request.form.get('date')  # Format: dd-mm-yyyy

            delete_job_date(job_id, date)

            return render_template('admin_job_dates.html',
                                 success=f'Date {date} removed from {get_job_name(job_id)}',
                                 jobs=JOBS,
                                 all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})

    return render_template('admin_job_dates.html',
                         jobs=JOBS,
                         all_dates={jid: get_job_dates(jid) for jid in JOBS.keys()})


@app.route('/admin/init-slots', methods=['GET', 'POST'])
@admin_required
def admin_init_slots():
    """Initialize slots for a specific job"""
    if request.method == 'POST':
        job_id = request.form.get('job_id')

        if not is_valid_job_id(job_id):
            return render_template('admin_init_slots.html',
                                 error='Invalid job ID',
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

        result = initialize_slots_for_job(job_id)

        if 'error' in result:
            return render_template('admin_init_slots.html',
                                 error=result['error'],
                                 jobs=JOBS,
                                 configs=get_all_job_configs())

        return render_template('admin_init_slots.html',
                             success=f"{result['slots_created']} slots initialized successfully for {get_job_name(job_id)}!",
                             jobs=JOBS,
                             configs=get_all_job_configs())

    return render_template('admin_init_slots.html',
                         jobs=JOBS,
                         configs=get_all_job_configs())


@app.route('/admin/clear-slots', methods=['POST'])
@admin_required
def admin_clear_slots():
    """Clear all slots for a specific job (for testing/reset)"""
    job_id = request.form.get('job_id')

    if not is_valid_job_id(job_id):
        return redirect(url_for('admin_init_slots'))

    clear_slots_for_job(job_id)
    return redirect(url_for('admin_init_slots'))


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
    export_data = []
    for booking in bookings:
        # Get job config for duration
        job_config = get_job_config(booking['job_id'])
        slot_duration = job_config['slot_duration_minutes'] if job_config else 30

        # Parse start time
        start_datetime = datetime.strptime(
            f"{booking['date']} {booking['start_time']}",
            "%d-%m-%Y %H:%M"
        )
        end_datetime = start_datetime + timedelta(minutes=slot_duration)

        # Get interview link and create expiry link
        interview_link = booking.get('interview_link', '')
        interview_link_with_expiry = add_expiry_to_interview_link(
            interview_link,
            start_datetime,
            end_datetime
        ) if interview_link else ''

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
                         jobs=JOBS,
                         selected_job=job_id)


@app.route('/admin/candidates')
@admin_required
def admin_candidates():
    """View all candidates"""
    job_id = request.args.get('job_id')  # Optional job filter
    candidates = get_all_candidates(job_id if job_id and is_valid_job_id(job_id) else None)

    return render_template('admin_candidates.html',
                         candidates=candidates,
                         jobs=JOBS,
                         selected_job=job_id)


@app.route('/admin/export-pending')
@admin_required
def admin_export_pending():
    """Export pending and clicked candidates (non-booked) to CSV"""
    job_id = request.args.get('job_id')
    status_filter = request.args.get('status', 'all')  # 'pending', 'clicked', or 'all'

    candidates = get_all_candidates(job_id if job_id and is_valid_job_id(job_id) else None)

    # Filter for non-booked candidates (pending or clicked)
    if status_filter == 'pending':
        filtered = [c for c in candidates if c['status'] == 'pending']
    elif status_filter == 'clicked':
        filtered = [c for c in candidates if c['status'] == 'clicked']
    else:
        filtered = [c for c in candidates if c['status'] in ('pending', 'clicked')]

    if not filtered:
        return "No candidates to export", 400

    # Prepare CSV data
    export_data = []
    for c in filtered:
        export_data.append({
            'Name': c['name'],
            'Email': c['email'],
            'Interview Link': c.get('interview_link', '')
        })

    df = pd.DataFrame(export_data)

    # Generate CSV
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    # Create filename
    job_suffix = f"_{job_id}" if job_id else "_all_jobs"
    status_suffix = f"_{status_filter}" if status_filter != 'all' else "_pending_clicked"
    filename = f"candidates{job_suffix}{status_suffix}.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/admin/slots')
@admin_required
def admin_slots():
    """View all slots with booking statistics for a specific job"""
    job_id = request.args.get('job_id')  # Required job filter

    if not job_id or not is_valid_job_id(job_id):
        # If no valid job selected, redirect to dashboard
        return redirect(url_for('admin_dashboard'))

    # Get all slots for the selected job
    all_slots = get_all_slots_for_job(job_id)

    # Group slots by date for better display
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

    # Convert to sorted list
    dates_data = sorted(slots_by_date.values(), key=lambda x: x['date'])

    return render_template('admin_slots.html',
                         dates_data=dates_data,
                         jobs=JOBS,
                         selected_job=job_id,
                         job_name=get_job_name(job_id))


# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5005)
