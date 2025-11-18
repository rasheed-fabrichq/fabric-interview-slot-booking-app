# Comprehensive Testing Guide - Interview Slot Booking Application

## Table of Contents
1. [Admin Scenarios](#admin-scenarios)
2. [Candidate Scenarios](#candidate-scenarios)
3. [Security & Edge Cases](#security--edge-cases)
4. [Concurrent Booking Scenarios](#concurrent-booking-scenarios)
5. [Data Integrity Tests](#data-integrity-tests)

---

## Admin Scenarios

### A1: Admin Login
**Test Cases:**
- [ ] Login with correct credentials (admin/admin123)
- [ ] Login with wrong username
- [ ] Login with wrong password
- [ ] Login with empty fields
- [ ] Check if redirected to dashboard after successful login
- [ ] Try accessing admin routes without login (should redirect to login)

**Expected Results:**
- ✓ Successful login redirects to dashboard
- ✓ Wrong credentials show error message
- ✓ Protected routes redirect to login if not authenticated

---

### A2: Upload Candidates

#### A2.1: Valid Upload
**Test Case:**
- [ ] Upload sample_candidates.csv (provided file)
- [ ] Upload with Excel (.xlsx) format
- [ ] Verify success message shows count

**Expected Results:**
- ✓ All candidates uploaded successfully
- ✓ Success message shows "X candidates uploaded successfully"

#### A2.2: Invalid File Format
**Test Cases:**
- [ ] Upload .txt file
- [ ] Upload .pdf file
- [ ] Upload image file
- [ ] Upload without selecting file

**Expected Results:**
- ✓ Error: "Invalid file format. Use CSV or Excel."

#### A2.3: Missing Columns
**Test Case:**
- [ ] Create CSV with only `name` and `email` (missing `candidate_id`)
- [ ] Upload file

**Expected Results:**
- ✓ Error: "Missing required columns: ['candidate_id', 'name', 'email']"

#### A2.4: Duplicate candidate_id
**Test Case:**
- [ ] Upload candidates
- [ ] Upload same file again

**Expected Results:**
- ✓ Error messages for duplicate candidate_ids
- ✓ Shows "X errors occurred"

#### A2.5: Invalid Data
**Test Cases:**
- [ ] Empty candidate_id
- [ ] Invalid email format
- [ ] Special characters in name
- [ ] Very long names (1000+ characters)

**Expected Results:**
- ✓ System handles gracefully
- ✓ Shows appropriate error messages

---

### A3: Initialize Slots

#### A3.1: First Time Initialization
**Test Case:**
- [ ] Click "Initialize Slots" button
- [ ] Verify success message

**Expected Results:**
- ✓ Success: "96 slots initialized successfully!" (48 per day × 2 days)
- ✓ Can view slots by checking database or making test booking

#### A3.2: Re-initialization Attempt
**Test Case:**
- [ ] Initialize slots
- [ ] Try to initialize again

**Expected Results:**
- ✓ Error: "Slots already initialized. Clear existing slots first."

#### A3.3: Clear and Re-initialize
**Test Case:**
- [ ] Initialize slots
- [ ] Make 2-3 test bookings
- [ ] Click "Clear All Slots" (confirm prompt)
- [ ] Verify bookings deleted
- [ ] Verify candidate statuses reset to 'pending'
- [ ] Initialize slots again

**Expected Results:**
- ✓ All bookings deleted
- ✓ All slots deleted
- ✓ Candidates reset to 'pending'
- ✓ Can re-initialize successfully

---

### A4: View Dashboard

**Test Cases:**
- [ ] View dashboard with 0 candidates
- [ ] View after uploading candidates
- [ ] View after some bookings made
- [ ] Check statistics accuracy:
  - [ ] Total candidates count
  - [ ] Total bookings count
  - [ ] Pending count
  - [ ] Clicked count
  - [ ] Booked count
  - [ ] Slot utilization percentages

**Expected Results:**
- ✓ All statistics are accurate
- ✓ Percentages calculated correctly
- ✓ No JavaScript errors in console

---

### A5: View Bookings

**Test Cases:**
- [ ] View with no bookings (shows "No bookings found")
- [ ] View with multiple bookings
- [ ] Verify all columns display correctly
- [ ] Check sorting by date/time
- [ ] Verify time shows with AM/PM format

**Expected Results:**
- ✓ All booking data displays correctly
- ✓ Times in 12-hour format with AM/PM
- ✓ Data sorted by date and time

---

### A6: Export Data

#### A6.1: Export Excel
**Test Cases:**
- [ ] Export with no bookings (should show error)
- [ ] Export with bookings
- [ ] Verify file downloads
- [ ] Open file and verify:
  - [ ] All columns present (Candidate ID, Name, Email, College, Start Time, End Time, Booked At)
  - [ ] Data matches bookings page
  - [ ] Times formatted correctly
  - [ ] No missing data

**Expected Results:**
- ✓ File downloads with timestamp name (bookings_YYYYMMDD_HHMMSS.xlsx)
- ✓ All data accurate and complete

#### A6.2: Export CSV
**Test Cases:**
- [ ] Export CSV format
- [ ] Open in Excel/Google Sheets
- [ ] Open in text editor
- [ ] Verify all data present
- [ ] Check for proper CSV formatting (quotes, commas)

**Expected Results:**
- ✓ Valid CSV file downloads
- ✓ Can be imported into other systems
- ✓ Data integrity maintained

---

### A7: Admin Logout
**Test Cases:**
- [ ] Logout from dashboard
- [ ] Try to access admin routes after logout (should redirect)
- [ ] Login again (should work)

**Expected Results:**
- ✓ Successfully logged out
- ✓ Session cleared
- ✓ Cannot access admin routes

---

## Candidate Scenarios

### C1: Invalid/Missing Link

#### C1.1: No candidate_id in URL
**Test Case:**
- [ ] Access: `http://localhost:5000/book/software-development-engineer-i` (no c_id parameter)

**Expected Results:**
- ✓ Shows "Invalid Link" page
- ✓ Message: "Missing candidate ID in the link."

#### C1.2: Invalid candidate_id
**Test Case:**
- [ ] Access: `http://localhost:5000/book/software-development-engineer-i?c_id=invalid-uuid-123`

**Expected Results:**
- ✓ Shows "Invalid Link" page
- ✓ Message: "Invalid booking link. Please check your email for the correct link."

#### C1.3: Invalid job slug
**Test Cases:**
- [ ] Access: `http://localhost:5000/book/invalid-job-slug?c_id=<valid-uuid>`
- [ ] Access: `http://localhost:5000/book/fake-position?c_id=<valid-uuid>`

**Expected Results:**
- ✓ Shows "Invalid Link" page
- ✓ Message: "Invalid job in the link."

#### C1.4: Malformed UUID
**Test Cases:**
- [ ] `?c_id=abc123`
- [ ] `?c_id=`
- [ ] `?c_id=<script>alert('xss')</script>`

**Expected Results:**
- ✓ Shows "Invalid Link" page
- ✓ No XSS or security vulnerabilities

---

### C2: Valid First-Time Access

**Test Case:**
- [ ] Upload candidate via admin
- [ ] Access: `http://localhost:5000/book/software-development-engineer-i?c_id=<valid-uuid>`
- [ ] Verify page loads
- [ ] Check status changed to 'clicked' in database

**Expected Results:**
- ✓ Booking form loads successfully
- ✓ Name and email fields pre-filled and disabled
- ✓ Candidate status changed from 'pending' to 'clicked'
- ✓ College dropdown shows all 9 IITs
- ✓ Booking token generated in session

**UI Checks:**
- [ ] Name field is disabled (read-only)
- [ ] Email field is disabled (read-only)
- [ ] College dropdown is enabled
- [ ] Instructions visible
- [ ] No slots visible yet (until college selected)

---

### C3: College Selection & Slot Loading

#### C3.1: Select Saturday College
**Test Cases:**
- [ ] Select "IIT Bombay"
- [ ] Verify "Interview Day: Saturday" appears
- [ ] Verify slots start loading (spinner shows)
- [ ] Verify 48 slots display (00:00 to 23:30)
- [ ] Check console for errors

**Expected Results:**
- ✓ Day info shows "Saturday"
- ✓ 48 slots load successfully
- ✓ Slots show availability (e.g., "10 available")
- ✓ No JavaScript errors

#### C3.2: Select Sunday College
**Test Cases:**
- [ ] Select "IIT Guwahati"
- [ ] Verify "Interview Day: Sunday" appears
- [ ] Verify correct slots load

**Expected Results:**
- ✓ Day info shows "Sunday"
- ✓ Different slots than Saturday

#### C3.3: Switch Between Colleges
**Test Cases:**
- [ ] Select "IIT Bombay" (Saturday)
- [ ] Wait for slots to load
- [ ] Select "IIT Delhi" (Saturday) - should show same slots
- [ ] Select "IIT Guwahati" (Sunday) - should show different slots

**Expected Results:**
- ✓ Slots update correctly
- ✓ No previous selection persists
- ✓ Smooth transition

---

### C4: Slot Selection

#### C4.1: Select Available Slot
**Test Case:**
- [ ] Select college
- [ ] Click on a green (available) slot
- [ ] Verify slot highlights
- [ ] Verify "Selected Slot" info appears
- [ ] Verify "Confirm Booking" button appears

**Expected Results:**
- ✓ Slot card gets 'selected' class (blue border)
- ✓ Shows selected time in 12-hour format
- ✓ Confirm button appears and is enabled
- ✓ Page scrolls to confirm button

#### C4.2: Change Slot Selection
**Test Case:**
- [ ] Select one slot
- [ ] Select another slot
- [ ] Verify only one slot is highlighted

**Expected Results:**
- ✓ Previous selection removed
- ✓ New slot highlighted
- ✓ Selected time updates

#### C4.3: Try to Select Full Slot
**Test Case:**
- [ ] Book a slot until it's full (10 bookings)
- [ ] Try to click the full slot

**Expected Results:**
- ✓ Slot is grayed out
- ✓ Cursor shows "not-allowed"
- ✓ Click has no effect

---

### C5: Booking Confirmation

#### C5.1: Successful Booking
**Test Case:**
- [ ] Select college
- [ ] Select available slot
- [ ] Click "Confirm Booking"
- [ ] Wait for response

**Expected Results:**
- ✓ Button shows "Booking..." with spinner
- ✓ Button disabled during request
- ✓ Success modal appears
- ✓ Modal shows:
  - Success message
  - Start time (with AM/PM)
  - End time (with AM/PM)
  - Note about email confirmation
- ✓ Candidate status changed to 'booked' in database

#### C5.2: Booking Without Selecting College
**Test Case:**
- [ ] Don't select college
- [ ] Try to click confirm (should not be visible)

**Expected Results:**
- ✓ Confirm button not visible without college selection

#### C5.3: Booking Without Selecting Slot
**Test Case:**
- [ ] Select college
- [ ] Don't select slot
- [ ] Try to click confirm (should not be visible)

**Expected Results:**
- ✓ Confirm button not visible without slot selection

---

### C6: Already Booked Scenario

#### C6.1: Access Link After Booking
**Test Case:**
- [ ] Complete a booking
- [ ] Close browser
- [ ] Access the same booking link again

**Expected Results:**
- ✓ Shows "Booking Already Confirmed" page
- ✓ Displays candidate details
- ✓ Shows booked slot details:
  - College
  - Interview Day
  - Date
  - Time (in AM/PM format with range)
  - Duration
- ✓ Shows note: "You cannot make changes"

#### C6.2: Verify All Details Correct
**Test Case:**
- [ ] Check displayed time matches booking
- [ ] Verify AM/PM format (e.g., "10:00 AM - 10:30 AM")
- [ ] Verify date format
- [ ] Verify college name

**Expected Results:**
- ✓ All details accurate
- ✓ Time in user-friendly format

---

### C7: Slot Full Scenario

#### C7.1: Slot Fills While Viewing
**Test Case:**
- [ ] Open booking form in Browser A
- [ ] Open same slot booking in Browsers B, C, D... (10 total)
- [ ] Complete booking from Browsers B-J (9 bookings)
- [ ] In Browser A, try to book the same slot

**Expected Results:**
- ✓ Browser A shows error modal
- ✓ Error: "This slot has just been booked by other candidates. Please choose another available slot."
- ✓ Modal can be closed
- ✓ Can select different slot
- ✓ Confirm button re-enabled

#### C7.2: Retry After Slot Full
**Test Case:**
- [ ] Get "slot full" error
- [ ] Close error modal
- [ ] Select different slot
- [ ] Book successfully

**Expected Results:**
- ✓ Can book different slot
- ✓ Booking succeeds
- ✓ Token still valid for retry

---

### C8: Session Expiry & Refresh

#### C8.1: Refresh Page After Loading
**Test Case:**
- [ ] Load booking form
- [ ] Select college and slot
- [ ] Refresh browser (F5)
- [ ] Try to book

**Expected Results:**
- ✓ New booking token generated
- ✓ Must re-select college and slot
- ✓ Booking works with new token

#### C8.2: Browser Back Button
**Test Case:**
- [ ] Complete booking
- [ ] Click browser back button

**Expected Results:**
- ✓ Shows "Already Booked" page (not booking form)
- ✓ Cannot book again

---

## Security & Edge Cases

### S1: Direct API Attacks

#### S1.1: Book Without Loading Form
**Test Case:**
```bash
curl -X POST http://localhost:5000/book/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "550e8400-e29b-41d4-a716-446655440001",
    "slot_id": 1,
    "college_name": "IIT Bombay",
    "booking_token": "fake-token"
  }'
```

**Expected Results:**
- ✓ HTTP 403 Forbidden
- ✓ Error: "Invalid or expired booking session"

#### S1.2: Book with Status 'pending'
**Test Case:**
- [ ] Upload candidate (status = 'pending')
- [ ] Try direct API call without opening form first

**Expected Results:**
- ✓ HTTP 403 Forbidden
- ✓ Error: "Access denied. You must access the booking form through the provided link first."

#### S1.3: Reuse Booking Token
**Test Case:**
- [ ] Load booking form (capture token from network tab)
- [ ] Complete booking
- [ ] Try to use same token again in API call

**Expected Results:**
- ✓ HTTP 403 Forbidden
- ✓ Error: "This booking session has already been used"

#### S1.4: Book for Different Candidate
**Test Case:**
- [ ] Open booking form for Candidate A
- [ ] Capture booking token
- [ ] Try to book using Candidate B's ID with Candidate A's token

**Expected Results:**
- ✓ HTTP 403 Forbidden
- ✓ Error: "Candidate ID mismatch. Security violation detected."

#### S1.5: SQL Injection Attempts
**Test Cases:**
```bash
# Try in candidate_id
?candidate_id='; DROP TABLE candidates; --

# Try in college name
"college_name": "IIT Bombay'; DROP TABLE slots; --"
```

**Expected Results:**
- ✓ No SQL injection (parameterized queries protect)
- ✓ Invalid candidate ID error

#### S1.6: XSS Attempts
**Test Cases:**
```bash
# In name field (via CSV upload)
name: "<script>alert('XSS')</script>"

# In URL
?candidate_id=<script>alert('XSS')</script>
```

**Expected Results:**
- ✓ Scripts not executed
- ✓ Content escaped properly
- ✓ No alerts or JavaScript execution

---

### S2: CSRF Protection

**Test Case:**
- [ ] Try to submit admin forms without CSRF token
- [ ] Check if admin forms have hidden csrf_token field

**Expected Results:**
- ✓ Forms contain CSRF tokens
- ✓ Submissions without token rejected

---

### S3: Session Hijacking

**Test Case:**
- [ ] Login as admin
- [ ] Copy session cookie
- [ ] Open incognito window
- [ ] Try to access admin routes with copied cookie

**Expected Results:**
- ✓ Cookie-based session works (expected behavior)
- ✓ Use HTTPS in production to prevent cookie theft

---

## Concurrent Booking Scenarios

### CB1: Race Condition Test

**Test Case:**
- [ ] Open booking form in 15 different browsers/tabs
- [ ] All select same college
- [ ] All select same slot (e.g., 10:00 AM)
- [ ] All click "Confirm" within 1-2 seconds
- [ ] Count successful bookings

**Expected Results:**
- ✓ Exactly 10 bookings succeed
- ✓ 5 bookings fail with "slot full" error
- ✓ Slot booked_count = 10 in database
- ✓ No overbooking (critical!)

**Verification:**
```sql
SELECT booked_count FROM slots WHERE id = 1;
-- Should be exactly 10

SELECT COUNT(*) FROM bookings WHERE slot_id = 1;
-- Should be exactly 10
```

---

### CB2: Different Slots Same Time

**Test Case:**
- [ ] 20 browsers simultaneously book different slots
- [ ] Verify all succeed
- [ ] No conflicts between different slots

**Expected Results:**
- ✓ All bookings succeed
- ✓ No race conditions between different slots

---

### CB3: Same Candidate Multiple Tabs

**Test Case:**
- [ ] Open same booking link in 5 tabs
- [ ] Try to book from all tabs simultaneously

**Expected Results:**
- ✓ Only first booking succeeds
- ✓ Others show: "You have already booked a slot"
- ✓ Database has exactly 1 booking for candidate

---

## Data Integrity Tests

### D1: Database Consistency

**Test Cases:**
- [ ] Upload 20 candidates
- [ ] Make 15 bookings
- [ ] Check database:

```sql
-- All bookings have valid candidate_ids
SELECT * FROM bookings WHERE candidate_id NOT IN (SELECT candidate_id FROM candidates);
-- Should return 0 rows

-- All bookings have valid slot_ids
SELECT * FROM bookings WHERE slot_id NOT IN (SELECT id FROM slots);
-- Should return 0 rows

-- Booked count matches actual bookings
SELECT s.id, s.booked_count, COUNT(b.id) as actual_count
FROM slots s
LEFT JOIN bookings b ON s.id = b.slot_id
GROUP BY s.id
HAVING s.booked_count != COUNT(b.id);
-- Should return 0 rows

-- All booked candidates have status='booked'
SELECT c.* FROM candidates c
JOIN bookings b ON c.candidate_id = b.candidate_id
WHERE c.status != 'booked';
-- Should return 0 rows
```

**Expected Results:**
- ✓ All foreign keys valid
- ✓ Counts accurate
- ✓ Statuses correct

---

### D2: Export Data Integrity

**Test Case:**
- [ ] Make 10 bookings
- [ ] Export to Excel
- [ ] Export to CSV
- [ ] Compare both files
- [ ] Compare with database

**Expected Results:**
- ✓ Both exports have same data
- ✓ Row count matches bookings count
- ✓ All candidate IDs present
- ✓ All times formatted correctly

---

## Performance Tests

### P1: Large Data Set

**Test Case:**
- [ ] Upload 700 candidates (use provided sample_candidates.csv + more)
- [ ] Initialize slots
- [ ] Make 100+ bookings
- [ ] Check dashboard load time
- [ ] Check bookings page load time
- [ ] Check export time

**Expected Results:**
- ✓ Pages load within 2-3 seconds
- ✓ No performance degradation
- ✓ Export completes within 5 seconds

---

### P2: Slot Loading Speed

**Test Case:**
- [ ] Open booking form
- [ ] Select college
- [ ] Measure time to load 48 slots

**Expected Results:**
- ✓ Slots load within 1 second
- ✓ No lag or freezing

---

## Browser Compatibility

**Test on:**
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (if on Mac)
- [ ] Edge (latest)
- [ ] Mobile Chrome (Android)
- [ ] Mobile Safari (iOS)

**Check:**
- [ ] All features work
- [ ] Layout responsive
- [ ] Modals display correctly
- [ ] No console errors

---

## Mobile Responsiveness

**Test Cases:**
- [ ] Open on mobile device
- [ ] Verify slot grid is scrollable
- [ ] Tap slots easily (not too small)
- [ ] Forms usable on small screen
- [ ] Modals fit screen
- [ ] Navigation works

---

## Error Handling

### E1: Network Errors

**Test Cases:**
- [ ] Disconnect internet before confirming booking
- [ ] Check error message shown
- [ ] Reconnect and retry

**Expected Results:**
- ✓ Shows error: "An error occurred. Please try again."
- ✓ Button re-enabled
- ✓ Can retry after reconnect

---

### E2: Server Errors

**Test Case:**
- [ ] Stop Flask server
- [ ] Try to load booking form
- [ ] Try to book slot

**Expected Results:**
- ✓ Graceful error handling
- ✓ User-friendly error messages

---

## Time Format Validation

**Test Cases:**
- [ ] Check all times show AM/PM format:
  - [ ] Already Booked page
  - [ ] Success modal after booking
  - [ ] Bookings list page
  - [ ] Export files

**Expected Results:**
- ✓ All times in 12-hour format (e.g., "02:00 PM" not "14:00")
- ✓ Consistent formatting everywhere

---

## Critical Path Testing

### CP1: Complete Happy Path
**Test Case:**
1. [ ] Admin login
2. [ ] Upload candidates
3. [ ] Initialize slots
4. [ ] Candidate opens link
5. [ ] Selects college
6. [ ] Selects slot
7. [ ] Confirms booking
8. [ ] Sees success message
9. [ ] Admin checks booking in dashboard
10. [ ] Admin exports data

**Expected Results:**
- ✓ All steps complete without errors
- ✓ Data accurate throughout

---

## Testing Tools & Commands

### Database Inspection
```bash
sqlite3 instance/slots.db

# Check tables
.tables

# View candidates
SELECT * FROM candidates;

# View slots with bookings
SELECT s.id, s.day, s.start_time, s.booked_count, COUNT(b.id) as actual
FROM slots s
LEFT JOIN bookings b ON s.id = b.slot_id
GROUP BY s.id;

# View all bookings
SELECT c.name, c.email, b.college_name, s.date, s.start_time
FROM bookings b
JOIN candidates c ON b.candidate_id = c.candidate_id
JOIN slots s ON b.slot_id = s.id;
```

### Browser DevTools
- **Console**: Check for JavaScript errors
- **Network**: Monitor API calls, check status codes
- **Application > Storage**: View session data

---

## Test Execution Checklist

### Priority 1 - Critical (Must Pass)
- [ ] C2: Valid first-time access
- [ ] C5.1: Successful booking
- [ ] C6.1: Already booked scenario
- [ ] C7.1: Slot full handling
- [ ] CB1: Race condition (no overbooking)
- [ ] S1.1-S1.4: All security tests
- [ ] D1: Database consistency

### Priority 2 - Important
- [ ] All Admin scenarios (A1-A7)
- [ ] C3: College selection
- [ ] C4: Slot selection
- [ ] S1.5-S1.6: Injection attacks
- [ ] D2: Export integrity

### Priority 3 - Nice to Have
- [ ] P1-P2: Performance tests
- [ ] Browser compatibility
- [ ] Mobile responsiveness

---

## Bug Tracking Template

When you find bugs, document them like this:

**Bug ID:** B001
**Severity:** Critical/High/Medium/Low
**Area:** Admin/Candidate/Security
**Description:** [What happened]
**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]

**Expected Result:** [What should happen]
**Actual Result:** [What actually happened]
**Screenshot/Logs:** [If applicable]
**Status:** Open/Fixed/Wontfix

---

## Final Verification Checklist

Before going to production:
- [ ] All Priority 1 tests pass
- [ ] All Priority 2 tests pass
- [ ] No critical or high severity bugs
- [ ] Security tests all pass
- [ ] Race condition test passes (no overbooking)
- [ ] Data export verified
- [ ] Mobile responsiveness checked
- [ ] Production config updated (SECRET_KEY, ADMIN_PASSWORD)
- [ ] Database backed up
- [ ] HTTPS enabled in production

---

## Notes

- Test in a clean environment (fresh database)
- Document all bugs found
- Re-test after fixes
- Use multiple test accounts for concurrent scenarios
- Keep sample data for testing
