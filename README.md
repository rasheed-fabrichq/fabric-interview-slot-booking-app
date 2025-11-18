# Interview Slot Booking Application

A Flask-based web application for managing AI interview slot bookings for campus drives across 9 IITs.

## Features

- **Candidate Management**: Upload candidate data with unique UUIDs
- **24/7 Slot Availability**: 48 slots per day (00:00 to 23:30, 30-minute intervals)
- **Shared Capacity**: 10 candidates maximum per slot across all colleges
- **Concurrent Booking Protection**: Transaction-safe booking system prevents overbooking
- **Status Tracking**: pending → clicked → booked
- **Enhanced Security**: Session tokens, CSRF protection, status validation
- **Admin Dashboard**: Statistics and booking management
- **Excel Export**: Download all bookings as Excel file

## Security Features

This application implements multiple layers of security to prevent unauthorized bookings:

1. **Session-Based Tokens**: Unique, single-use tokens generated for each booking session
2. **CSRF Protection**: Flask-WTF prevents cross-site request forgery attacks
3. **Status Validation**: Candidates must access the form legitimately (status 'clicked') before booking
4. **Session Validation**: Prevents booking on behalf of other candidates
5. **Token Expiry**: Tokens are single-use and session-bound
6. **Comprehensive Checks**: 8-layer validation on every booking request

**Direct API calls without proper session tokens will be rejected with HTTP 403 (Forbidden).**

## Tech Stack

- **Backend**: Flask (Python)
- **Database**: SQLite with WAL mode
- **Frontend**: HTML, Bootstrap 5, Vanilla JavaScript
- **Security**: Flask-WTF, Session management
- **Data Processing**: Pandas, OpenPyxl

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Setup Steps

1. **Clone or navigate to the project directory**:
   ```bash
   cd Interview-slot-booking-app
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - On Linux/Mac:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Before running the application, update the following in `config.py`:

1. **Interview Dates**:
   ```python
   INTERVIEW_DATES = {
       'Saturday': '16-11-2025',  # Update with actual date
       'Sunday': '17-11-2025'
   }
   ```

2. **Admin Credentials** (Important!):
   ```python
   ADMIN_USERNAME = 'admin'
   ADMIN_PASSWORD = 'admin123'  # Change this!
   ```

3. **Secret Key** in `app.py`:
   ```python
   app.secret_key = 'your-secret-key-change-in-production'
   ```

## Running the Application

1. **Initialize the database**:
   ```bash
   python database.py
   ```

2. **Start the Flask application**:
   ```bash
   python app.py
   ```

3. **Access the application**:
   - Open your browser and go to: `http://localhost:5000`
   - Admin panel: `http://localhost:5000/admin/login`

## Usage Guide

### For Admin

1. **Login to Admin Panel**:
   - Go to `/admin/login`
   - Enter admin credentials

2. **Upload Candidates**:
   - Navigate to "Upload Candidates"
   - Prepare a CSV/Excel file with columns: `candidate_id`, `name`, `email`
   - Upload the file
   - Example format:
     ```csv
     candidate_id,name,email
     7f3e9a2c-4b1d-4f8e-9c2a-1b3d4e5f6a7b,John Doe,john@iitb.ac.in
     8a4f0b3d-5c2e-5g9f-0d3b-2c4e6f8a9b0c,Jane Smith,jane@iitd.ac.in
     ```

3. **Initialize Slots**:
   - Navigate to "Initialize Slots"
   - Click "Initialize Slots" button
   - This creates 48 slots for each interview day

4. **Send Booking Links**:
   - Send emails to candidates with their unique booking links:
   - Format: `http://your-domain.com/book/<job-slug>?c_id=<their-uuid>`
   - Example: `http://your-domain.com/book/software-development-engineer-i?c_id=abc123...`

5. **Monitor Bookings**:
   - View dashboard for real-time statistics
   - View all bookings in "View Bookings"
   - Export data as Excel from "Export Data"

### For Candidates

1. **Click the unique link** received via email
2. **Select college** from dropdown
3. **Choose available time slot** (green = available, yellow = filling up, gray = full)
4. **Click "Confirm Booking"**
5. **Receive confirmation** with interview details

## Project Structure

```
interview-booking/
├── app.py                    # Main Flask application
├── database.py               # Database operations
├── config.py                 # Configuration
├── requirements.txt          # Python dependencies
├── claude.md                 # Complete requirements doc
├── README.md                 # This file
├── templates/                # HTML templates
│   ├── base.html
│   ├── booking_form.html
│   ├── already_booked.html
│   ├── invalid_link.html
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── admin_upload.html
│   ├── admin_init_slots.html
│   └── admin_bookings.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── booking.js
└── instance/
    └── slots.db              # SQLite database (auto-created)
```

## Database Schema

### candidates
- `id`: Primary key
- `candidate_id`: UUID (unique)
- `name`: Candidate name
- `email`: Email address
- `status`: pending/clicked/booked
- `created_at`, `updated_at`: Timestamps

### slots
- `id`: Primary key
- `day`: Saturday/Sunday
- `start_time`: Time in HH:MM format
- `date`: Date in dd-MM-yyyy format
- `booked_count`: Current bookings (0-10)
- `max_capacity`: Always 10
- `created_at`: Timestamp

### bookings
- `id`: Primary key
- `candidate_id`: Foreign key
- `slot_id`: Foreign key
- `college_name`: Selected college
- `booked_at`: Timestamp

## API Endpoints

### Public Routes
- `GET /` - Home page
- `GET /book/<job-slug>?c_id=<uuid>` - Booking form
- `POST /book/confirm` - Confirm booking
- `GET /api/slots?day=<Saturday|Sunday>` - Get available slots

### Admin Routes (requires authentication)
- `GET/POST /admin/login` - Admin login
- `GET /admin/dashboard` - Dashboard with statistics
- `GET/POST /admin/upload` - Upload candidates
- `GET/POST /admin/init-slots` - Initialize slots
- `GET /admin/bookings` - View all bookings
- `GET /admin/export` - Export bookings to Excel

## Testing

### Creating Test Candidates

Use the provided `sample_candidates.csv` file or create your own:

```csv
candidate_id,name,email
550e8400-e29b-41d4-a716-446655440001,Alice Johnson,alice@iitb.ac.in
550e8400-e29b-41d4-a716-446655440002,Bob Smith,bob@iitd.ac.in
550e8400-e29b-41d4-a716-446655440003,Carol Davis,carol@iitm.ac.in
```

### Testing Concurrent Bookings

1. Upload test candidates
2. Initialize slots
3. Open multiple browser windows/tabs
4. Access booking links simultaneously
5. Try booking the same slot from multiple browsers
6. Verify only 10 bookings succeed per slot

## Deployment

### Option 1: Railway

1. Create account on [Railway](https://railway.app)
2. Connect GitHub repository
3. Set environment variables
4. Deploy

### Option 2: Render

1. Create account on [Render](https://render.com)
2. Create new Web Service
3. Connect repository
4. Deploy

### Option 3: PythonAnywhere

1. Create account on [PythonAnywhere](https://www.pythonanywhere.com)
2. Upload files
3. Configure WSGI
4. Deploy

## Security Notes

1. **Change default admin password** before deployment
2. **Update Flask secret key** with a random string
3. **Use HTTPS** in production
4. **Backup database** regularly during booking window
5. **Keep candidate data confidential**

## Troubleshooting

### Database locked error
- Ensure WAL mode is enabled (handled automatically)
- Check file permissions on `instance/slots.db`

### Slots not loading
- Check browser console for JavaScript errors
- Verify `/api/slots` endpoint is accessible
- Ensure slots are initialized

### Upload failing
- Check CSV format matches required columns
- Verify file size is under 16MB
- Check file encoding (UTF-8 recommended)

## Support

For issues or questions:
1. Check `claude.md` for detailed requirements
2. Review application logs
3. Check browser console for frontend errors

## License

This project is created for campus recruitment purposes.

## Credits

Developed using Flask, Bootstrap, and modern web technologies.
