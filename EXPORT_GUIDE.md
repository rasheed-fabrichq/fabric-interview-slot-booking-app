# Data Export Guide

## Export Formats

The application now supports exporting booking data in two formats:

### 1. Excel (.xlsx)
- Rich formatting support
- Good for presentations and reports
- URL: `/admin/export?format=xlsx` or `/admin/export` (default)

### 2. CSV (.csv)
- Plain text format
- Easy to import into other systems
- Good for data processing and scripts
- URL: `/admin/export?format=csv`

## Exported Data Fields

All exports include the following columns:

1. **Candidate ID** - The unique UUID for the candidate
2. **Name** - Candidate's full name
3. **Email** - Candidate's email address
4. **College** - Selected IIT
5. **Start Time** - Interview start time (dd-MM-yyyy HH:mm format)
6. **End Time** - Interview end time (dd-MM-yyyy HH:mm format)
7. **Booked At** - Timestamp when booking was made

## Example Export Data

```csv
Candidate ID,Name,Email,College,Start Time,End Time,Booked At
550e8400-e29b-41d4-a716-446655440001,Alice Johnson,alice@iitb.ac.in,IIT Bombay,15-11-2025 10:00,15-11-2025 10:30,2025-11-13 14:30:00
550e8400-e29b-41d4-a716-446655440002,Bob Smith,bob@iitd.ac.in,IIT Delhi,15-11-2025 10:30,15-11-2025 11:00,2025-11-13 14:35:00
```

## How to Export

### From Admin Dashboard
1. Login to admin panel
2. Click "Export Excel" for .xlsx format
3. Click "Export CSV" for .csv format

### From Bookings Page
1. Go to "View Bookings"
2. Use export buttons at the top right
3. Choose desired format

### Direct URLs
- Excel: `http://your-domain.com/admin/export?format=xlsx`
- CSV: `http://your-domain.com/admin/export?format=csv`

## File Naming

Exported files are automatically named with timestamps:
- Excel: `bookings_20251113_143000.xlsx`
- CSV: `bookings_20251113_143000.csv`

Format: `bookings_YYYYMMDD_HHMMSS.{xlsx|csv}`

## Use Cases

**Excel (.xlsx)**
- Viewing in Microsoft Excel or Google Sheets
- Creating formatted reports
- Sharing with non-technical staff
- Presentations

**CSV (.csv)**
- Importing into databases
- Processing with scripts (Python, R, etc.)
- Version control (Git-friendly)
- Email marketing systems
- CRM imports
