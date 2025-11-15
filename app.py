"""
Main Flask application for Interview Slot Booking
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
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
    get_slots_by_day, book_slot, get_all_bookings, initialize_slots,
    get_dashboard_stats, get_booking_by_candidate, clear_all_slots,
    is_booking_enabled, set_booking_enabled, get_all_candidates
)
from config import (
    COLLEGES, COLLEGE_DAY_MAPPING, INTERVIEW_DATES,
    ADMIN_USERNAME, ADMIN_PASSWORD, SLOT_DURATION_MINUTES
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


def extract_candidate_id_from_url(interview_link):
    """
    Extract candidate_id from interview link URL
    Expected format: https://app.fabrichq.ai/interview/<job_id>?candidate_id=<candidate_id>
    Returns: (candidate_id, error_message) tuple
    """
    if not interview_link or pd.isna(interview_link):
        return None, "Interview link is empty"

    try:
        url_str = str(interview_link).strip()

        # Check if it's a valid URL format
        if not url_str.startswith('http://') and not url_str.startswith('https://'):
            return None, "Invalid URL format - must start with http:// or https://"

        # Extract candidate_id from query parameter
        # Use regex to find candidate_id parameter
        match = re.search(r'[?&]candidate_id=([^&]+)', url_str)

        if not match:
            return None, "candidate_id parameter not found in URL"

        candidate_id = match.group(1).strip()

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
    """Main booking form for candidates"""
    # Check if booking is enabled
    if not is_booking_enabled():
        return render_template('booking_closed.html')

    candidate_id = request.args.get('candidate_id')

    if not candidate_id:
        return render_template('invalid_link.html',
                             message='Missing candidate ID in the link.')

    # Get candidate details
    candidate = get_candidate(candidate_id)

    if not candidate:
        return render_template('invalid_link.html',
                             message='Invalid booking link. Please check your email for the correct link.')

    # Check if already booked
    if candidate['status'] == 'booked':
        booking = get_booking_by_candidate(candidate_id)

        # Format time to 12-hour format with AM/PM
        if booking and booking.get('start_time'):
            time_24h = booking['start_time']
            time_obj = datetime.strptime(time_24h, '%H:%M')
            booking['start_time_formatted'] = time_obj.strftime('%I:%M %p')

            # Calculate end time
            start_datetime = datetime.strptime(f"{booking['date']} {time_24h}", "%d-%m-%Y %H:%M")
            end_datetime = start_datetime + timedelta(minutes=SLOT_DURATION_MINUTES)
            booking['end_time_formatted'] = end_datetime.strftime('%I:%M %p')

        return render_template('already_booked.html',
                             candidate=candidate,
                             booking=booking)

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
                         college_day_mapping=COLLEGE_DAY_MAPPING)


@app.route('/api/slots')
def get_slots_api():
    """API endpoint to get available slots for a specific day"""
    day = request.args.get('day')

    if not day or day not in ['Saturday', 'Sunday']:
        return jsonify({'error': 'Invalid day parameter'}), 400

    slots = get_slots_by_day(day)
    return jsonify(slots)


@app.route('/book/confirm', methods=['POST'])
@csrf.exempt  # Using custom booking token instead of CSRF
def confirm_booking():
    """Confirm slot booking with enhanced security"""
    data = request.json

    candidate_id = data.get('candidate_id')
    slot_id = data.get('slot_id')
    booking_token = data.get('booking_token')

    # Security Check 1: Validate all required fields
    if not all([candidate_id, slot_id, booking_token]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Security Check 2: Validate booking token
    session_token = session.get('booking_token')
    session_candidate_id = session.get('booking_candidate_id')
    token_used = session.get('booking_token_used', True)

    if not session_token or booking_token != session_token:
        return jsonify({'error': 'Invalid or expired booking session. Please reload the booking page.'}), 403

    if token_used:
        return jsonify({'error': 'This booking session has already been used. Please reload the page.'}), 403

    # Security Check 3: Validate candidate_id matches session
    if candidate_id != session_candidate_id:
        return jsonify({'error': 'Candidate ID mismatch. Security violation detected.'}), 403

    # Security Check 4: Validate candidate exists and status
    candidate = get_candidate(candidate_id)
    if not candidate:
        return jsonify({'error': 'Invalid candidate ID'}), 400

    # Security Check 5: Candidate status must be 'clicked' (not 'pending')
    if candidate['status'] == 'pending':
        return jsonify({'error': 'Access denied. You must access the booking form through the provided link first.'}), 403

    if candidate['status'] == 'booked':
        return jsonify({'error': 'You have already booked a slot.'}), 400

    # Get college_name from candidate record
    college_name = candidate['college_name']

    # Security Check 6: Validate college (defensive check)
    if college_name not in COLLEGES:
        return jsonify({'error': 'Invalid college in candidate record. Please contact admin.'}), 400

    # Security Check 7: Check if booking is currently enabled
    if not is_booking_enabled():
        return jsonify({'error': 'Booking has been closed by the administrator.'}), 403

    # Mark token as used to prevent reuse
    session['booking_token_used'] = True

    # Book the slot (with transaction safety)
    result = book_slot(candidate_id, slot_id, college_name)

    if 'error' in result:
        # If booking failed, allow retry by resetting token
        session['booking_token_used'] = False
        return jsonify(result), 400

    # Clear session data after successful booking
    session.pop('booking_token', None)
    session.pop('booking_candidate_id', None)
    session.pop('booking_token_used', None)

    # Calculate end time
    slot_date = result['slot_date']
    slot_time = result['slot_time']
    start_datetime = datetime.strptime(f"{slot_date} {slot_time}", "%d-%m-%Y %H:%M")
    end_datetime = start_datetime + timedelta(minutes=SLOT_DURATION_MINUTES)

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
        'end_time': f"{end_date_formatted} {end_time_12h}"
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
    booking_status = is_booking_enabled()
    return render_template('admin_dashboard.html', stats=stats, booking_enabled=booking_status)


@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():
    """Upload candidates from CSV/Excel"""
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('admin_upload.html',
                                 error='No file uploaded')

        file = request.files['file']

        if file.filename == '':
            return render_template('admin_upload.html',
                                 error='No file selected')

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
                                         error='Invalid file format. Use CSV or Excel.')

                # Validate columns
                required_columns = ['candidate_id', 'name', 'email', 'college_name', 'interview_link']
                if not all(col in df.columns for col in required_columns):
                    return render_template('admin_upload.html',
                                         error=f'Missing required columns: {required_columns}')

                # Add candidates with validation
                success_count = 0
                error_count = 0
                errors = []

                for index, row in df.iterrows():
                    row_num = index + 2  # Excel row number (header is row 1)

                    # Get values
                    candidate_id = row.get('candidate_id')
                    name = row.get('name')
                    email = row.get('email')
                    college_name = row.get('college_name')
                    interview_link = row.get('interview_link')

                    # Prepare row display for error messages
                    row_display = f"candidate_id='{candidate_id}', name='{name}', email='{email}', college_name='{college_name}', interview_link='{interview_link}'"

                    # Validation 1: Check for missing fields
                    if pd.isna(candidate_id) or pd.isna(name) or pd.isna(email) or pd.isna(college_name) or pd.isna(interview_link):
                        error_count += 1
                        missing_fields = []
                        if pd.isna(candidate_id):
                            missing_fields.append('candidate_id')
                        if pd.isna(name):
                            missing_fields.append('name')
                        if pd.isna(email):
                            missing_fields.append('email')
                        if pd.isna(college_name):
                            missing_fields.append('college_name')
                        if pd.isna(interview_link):
                            missing_fields.append('interview_link')
                        errors.append(f"Row {row_num}: Missing required fields: {', '.join(missing_fields)} | Row data: {row_display}")
                        continue

                    # Validation 2: Validate interview_link and extract candidate_id
                    extracted_id, link_error = extract_candidate_id_from_url(interview_link)
                    if link_error:
                        error_count += 1
                        errors.append(f"Row {row_num}: {link_error} | Row data: {row_display}")
                        continue

                    # Validation 3: Validate UUID
                    if not is_valid_uuid(candidate_id):
                        error_count += 1
                        errors.append(f"Row {row_num}: Invalid UUID format for candidate_id | Row data: {row_display}")
                        continue

                    # Validation 4: Verify that extracted candidate_id matches provided candidate_id
                    if extracted_id != str(candidate_id).strip():
                        error_count += 1
                        errors.append(f"Row {row_num}: candidate_id mismatch - CSV has '{str(candidate_id).strip()}' but URL has '{extracted_id}' | Row data: {row_display}")
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

                    # Validation 7: Validate college_name
                    college_name_str = str(college_name).strip()
                    if college_name_str not in COLLEGES:
                        error_count += 1
                        errors.append(f"Row {row_num}: Invalid college name '{college_name_str}'. Must be one of: {', '.join(COLLEGES)} | Row data: {row_display}")
                        continue

                    # All validations passed, try to add candidate
                    result = add_candidate(
                        str(candidate_id).strip(),
                        str(name).strip(),
                        str(email).strip(),
                        college_name_str,
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
                                     success=f'{success_count} candidates uploaded successfully.',
                                     error=f'{error_count} errors occurred.' if error_count > 0 else None,
                                     errors=errors[:50])  # Show first 50 errors

            except Exception as e:
                return render_template('admin_upload.html',
                                     error=f'Error processing file: {str(e)}')

    return render_template('admin_upload.html')


@app.route('/admin/init-slots', methods=['GET', 'POST'])
@admin_required
def admin_init_slots():
    """Initialize slots for both days"""
    if request.method == 'POST':
        result = initialize_slots()

        if 'error' in result:
            return render_template('admin_init_slots.html',
                                 error=result['error'],
                                 interview_dates=INTERVIEW_DATES)

        return render_template('admin_init_slots.html',
                             success=f"{result['slots_created']} slots initialized successfully!",
                             interview_dates=INTERVIEW_DATES)

    return render_template('admin_init_slots.html',
                         interview_dates=INTERVIEW_DATES)


@app.route('/admin/clear-slots', methods=['POST'])
@admin_required
def admin_clear_slots():
    """Clear all slots (for testing/reset)"""
    result = clear_all_slots()
    return redirect(url_for('admin_init_slots'))


@app.route('/admin/toggle-booking', methods=['POST'])
@admin_required
def admin_toggle_booking():
    """Toggle booking enabled/disabled status"""
    action = request.form.get('action')  # 'enable' or 'disable'

    if action == 'enable':
        set_booking_enabled(True)
    elif action == 'disable':
        set_booking_enabled(False)

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/export')
@admin_required
def admin_export():
    """Export all bookings to Excel or CSV"""
    # Get export format from query parameter (default: xlsx)
    export_format = request.args.get('format', 'xlsx').lower()

    bookings = get_all_bookings()

    if not bookings:
        return "No bookings to export", 400

    # Prepare data for export
    export_data = []
    for booking in bookings:
        # Parse start time
        start_datetime = datetime.strptime(
            f"{booking['date']} {booking['start_time']}",
            "%d-%m-%Y %H:%M"
        )
        end_datetime = start_datetime + timedelta(minutes=SLOT_DURATION_MINUTES)

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
            'College': booking['college_name'],
            'Start Time': start_datetime.strftime("%d-%m-%Y %H:%M"),
            'End Time': end_datetime.strftime("%d-%m-%Y %H:%M"),
            'Interview Link': interview_link,
            'Interview Link with Expiry': interview_link_with_expiry,
            'Booked At': booking['booked_at']
        })

    # Create DataFrame
    df = pd.DataFrame(export_data)

    # Export based on format
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if export_format == 'csv':
        # Save to CSV
        export_filename = f"bookings_{timestamp}.csv"
        export_path = os.path.join(app.config['UPLOAD_FOLDER'], export_filename)
        df.to_csv(export_path, index=False)

        return send_file(export_path,
                        as_attachment=True,
                        download_name=export_filename,
                        mimetype='text/csv')
    else:
        # Save to Excel (default)
        export_filename = f"bookings_{timestamp}.xlsx"
        export_path = os.path.join(app.config['UPLOAD_FOLDER'], export_filename)
        df.to_excel(export_path, index=False)

        return send_file(export_path,
                        as_attachment=True,
                        download_name=export_filename,
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    """View all bookings"""
    bookings = get_all_bookings()

    # Add end time to each booking
    for booking in bookings:
        start_datetime = datetime.strptime(
            f"{booking['date']} {booking['start_time']}",
            "%d-%m-%Y %H:%M"
        )
        end_datetime = start_datetime + timedelta(minutes=SLOT_DURATION_MINUTES)
        booking['end_time'] = end_datetime.strftime("%H:%M")

    return render_template('admin_bookings.html', bookings=bookings)


@app.route('/admin/candidates')
@admin_required
def admin_candidates():
    """View all candidates"""
    candidates = get_all_candidates()
    return render_template('admin_candidates.html', candidates=candidates)


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
