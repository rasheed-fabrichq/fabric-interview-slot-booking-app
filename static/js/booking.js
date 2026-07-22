// Multi-Job Interview Slot Booking - Frontend JavaScript

let selectedDate = null;
let selectedSlotId = null;
let selectedSlotTime = null;
// Chosen in step 1 -- the link no longer carries a job.
let jobId = null;
let jobName = null;

// Get DOM elements
const datesGrid = document.getElementById('dates-grid');
const dateSelectionContainer = document.getElementById('date-selection-container');
const selectedDateInfo = document.getElementById('selected-date-info');
const selectedDateDisplay = document.getElementById('selected-date-display');
const slotContainer = document.getElementById('slot-container');
const slotsGrid = document.getElementById('slots-grid');
const loadingSpinner = document.getElementById('loading-spinner');
const selectedSlotInfo = document.getElementById('selected-slot-info');
const selectedSlotTimeSpan = document.getElementById('selected-slot-time');
const confirmBookingBtn = document.getElementById('confirm-booking-btn');
const changeDateBtn = document.getElementById('change-date-btn');
const backToDatesBtn = document.getElementById('back-to-dates-btn');
const jobSelectionContainer = document.getElementById('job-selection-container');
const jobSelect = document.getElementById('job-select');
const jobContinueBtn = document.getElementById('job-continue-btn');
const jobSelectFullName = document.getElementById('job-select-full-name');
const selectedJobInfo = document.getElementById('selected-job-info');
const selectedJobDisplay = document.getElementById('selected-job-display');
const changeJobBtn = document.getElementById('change-job-btn');
const candidateId = document.getElementById('candidate-id').value;
const bookingToken = document.getElementById('booking-token').value;

// Step 1 is choosing a position; dates load once a job is picked.
document.addEventListener('DOMContentLoaded', function() {
    // Continue stays disabled until a real position is chosen
    jobSelect.addEventListener('change', function () {
        jobContinueBtn.disabled = !this.value;
        showFullJobName();
    });

    // Restore state if the browser repopulated the select on a back/refresh
    showFullJobName();

    jobContinueBtn.addEventListener('click', function () {
        if (!jobSelect.value) return;
        const option = jobSelect.options[jobSelect.selectedIndex];
        selectJob(jobSelect.value, option.textContent.trim());
    });
});

// A long position name is truncated inside the select control, and native
// dropdowns ignore per-option tooltips in most browsers. So mirror the
// current selection in full underneath, and put it on the control's own
// title for hover.
function showFullJobName() {
    const name = jobSelect.value
        ? jobSelect.options[jobSelect.selectedIndex].textContent.trim()
        : '';

    jobSelect.title = name;

    if (name) {
        jobSelectFullName.textContent = name;
        jobSelectFullName.classList.remove('d-none');
    } else {
        jobSelectFullName.textContent = '';
        jobSelectFullName.classList.add('d-none');
    }
}

// Function to select a job and move on to dates
function selectJob(id, name) {
    jobId = id;
    jobName = name;

    selectedJobDisplay.textContent = name;
    selectedJobInfo.classList.remove('d-none');
    jobSelectionContainer.classList.add('d-none');
    dateSelectionContainer.classList.remove('d-none');

    loadDates();
}

// Go back to the position list, resetting everything downstream
function backToJobSelection() {
    jobId = null;
    jobName = null;
    selectedDate = null;
    selectedSlotId = null;
    selectedSlotTime = null;

    selectedJobInfo.classList.add('d-none');
    dateSelectionContainer.classList.add('d-none');
    selectedDateInfo.classList.add('d-none');
    slotContainer.classList.add('d-none');
    selectedSlotInfo.style.display = 'none';
    datesGrid.innerHTML = '';
    slotsGrid.innerHTML = '';

    // Re-arm the picker with the previous choice still shown
    jobContinueBtn.disabled = !jobSelect.value;
    showFullJobName();
    jobSelectionContainer.classList.remove('d-none');
}

// Function to load available dates for the job
function loadDates() {
    // Show loading spinner
    loadingSpinner.classList.remove('d-none');
    datesGrid.innerHTML = '';

    // Fetch dates from API
    fetch(`/api/job-dates?job_id=${jobId}`)
        .then(response => {
            if (!response.ok) throw new Error('Failed to load dates');
            return response.json();
        })
        .then(dates => {
            loadingSpinner.classList.add('d-none');
            displayDates(dates);
        })
        .catch(error => {
            loadingSpinner.classList.add('d-none');
            showError('Error loading dates. Please try again.');
            console.error('Error:', error);
        });
}

// Function to display available dates
function displayDates(dates) {
    datesGrid.innerHTML = '';

    if (dates.length === 0) {
        datesGrid.innerHTML = '<div class="col-12"><div class="alert alert-warning">No interview dates available.</div></div>';
        return;
    }

    dates.forEach(dateInfo => {
        const dateCard = createDateCard(dateInfo);
        datesGrid.appendChild(dateCard);
    });
}

// Function to create a date card
function createDateCard(dateInfo) {
    const col = document.createElement('div');
    // Two per row on phones as well -- dates are short enough to pair up.
    col.className = 'col-6 col-md-6';

    const card = document.createElement('div');
    card.className = 'card date-card';
    card.style.cursor = 'pointer';
    card.onclick = () => selectDate(dateInfo.date, dateInfo.day_of_week);

    card.innerHTML = `
        <div class="card-body text-center p-3">
            <h5 class="mb-1">${dateInfo.day_of_week}</h5>
            <p class="mb-0 text-muted">${dateInfo.date}</p>
        </div>
    `;

    col.appendChild(card);
    return col;
}

// Function to select a date
function selectDate(date, dayOfWeek) {
    selectedDate = date;

    // Hide date selection, show selected date info
    dateSelectionContainer.classList.add('d-none');
    selectedDateDisplay.textContent = `${date} (${dayOfWeek})`;
    selectedDateInfo.classList.remove('d-none');

    // Load slots for selected date
    loadSlots(jobId, date);
}

// Event listener for change date button
// Function to go back to date selection
function backToDateSelection() {
    // Reset date selection
    selectedDate = null;
    selectedSlotId = null;
    selectedSlotTime = null;

    // Hide slot container and selected date info
    slotContainer.classList.add('d-none');
    selectedDateInfo.classList.add('d-none');
    selectedSlotInfo.style.display = 'none';

    // Show date selection again
    dateSelectionContainer.classList.remove('d-none');

    // Clear slots grid
    slotsGrid.innerHTML = '';
}

// Event listener for "Change Date" button (shown after slot selection)
changeDateBtn.addEventListener('click', backToDateSelection);

// Event listener for "Back to Dates" button (shown in slot selection screen)
backToDatesBtn.addEventListener('click', backToDateSelection);

// Change position -- resets date and slot selection too
changeJobBtn.addEventListener('click', backToJobSelection);

// Function to load available slots for a specific date
function loadSlots(jobId, date) {
    // Show loading spinner
    loadingSpinner.classList.remove('d-none');
    slotContainer.classList.add('d-none');
    slotsGrid.innerHTML = '';

    // Fetch slots from API
    fetch(`/api/slots?job_id=${jobId}&date=${date}`)
        .then(response => {
            if (!response.ok) throw new Error('Failed to load slots');
            return response.json();
        })
        .then(slots => {
            loadingSpinner.classList.add('d-none');
            displaySlots(slots);
        })
        .catch(error => {
            loadingSpinner.classList.add('d-none');
            showError('Error loading slots. Please try again.');
            console.error('Error:', error);
        });
}

// Function to display slots
function displaySlots(slots) {
    slotsGrid.innerHTML = '';

    if (slots.length === 0) {
        slotContainer.classList.remove('d-none');
        slotsGrid.innerHTML = '<div class="col-12"><div class="alert alert-warning">No slots available for this date.</div></div>';
        return;
    }

    slots.forEach(slot => {
        const available = slot.available;
        const slotCard = createSlotCard(slot, available);
        slotsGrid.appendChild(slotCard);
    });

    slotContainer.classList.remove('d-none');
}

// Function to create a slot card
function createSlotCard(slot, available) {
    const col = document.createElement('div');
    col.className = 'col-6 col-md-3 col-lg-2';

    const card = document.createElement('div');
    card.className = 'card slot-card';

    // Determine slot status and styling
    let statusClass = '';
    let statusText = '';
    let isClickable = true;

    if (available === 0) {
        statusClass = 'slot-full';
        statusText = 'Full';
        isClickable = false;
    } else if (available <= 3) {
        statusClass = 'slot-almost-full';
        statusText = `${available} left`;
    } else {
        statusClass = 'slot-available';
        statusText = `${available} available`;
    }

    card.classList.add(statusClass);

    // Make card clickable if available
    if (isClickable) {
        card.style.cursor = 'pointer';
        card.onclick = () => selectSlot(slot.id, slot.start_time, card);
    }

    // Format time display (convert 24h to 12h format)
    const timeDisplay = formatTime(slot.start_time);

    card.innerHTML = `
        <div class="card-body text-center p-2">
            <h6 class="mb-1">${timeDisplay}</h6>
            <small class="text-muted">${statusText}</small>
        </div>
    `;

    col.appendChild(card);
    return col;
}

// Function to format time (24h to 12h)
function formatTime(time24) {
    const [hours, minutes] = time24.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const hour12 = hour % 12 || 12;
    return `${hour12}:${minutes} ${ampm}`;
}

// Function to select a slot
function selectSlot(slotId, slotTime, cardEl) {
    // Remove previous selection
    document.querySelectorAll('.slot-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Mark new selection
    if (cardEl) cardEl.classList.add('selected');

    // Store selected slot
    selectedSlotId = slotId;
    selectedSlotTime = slotTime;

    // Show selected slot info
    selectedSlotTimeSpan.textContent = formatTime(slotTime);
    selectedSlotInfo.style.display = 'block';

    // Scroll to confirm button
    selectedSlotInfo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Event listener for confirm booking button
confirmBookingBtn.addEventListener('click', function() {
    if (!jobId) {
        showError('Please select a position.');
        return;
    }

    if (!selectedSlotId) {
        showError('Please select a time slot.');
        return;
    }

    if (!selectedDate) {
        showError('Please select a date.');
        return;
    }

    // Disable button to prevent double-click
    confirmBookingBtn.disabled = true;
    confirmBookingBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Booking...';

    // Send booking request with security token
    fetch('/book/confirm', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            candidate_id: candidateId,
            job_id: jobId,
            slot_id: selectedSlotId,
            booking_token: bookingToken
        })
    })
    .then(response => {
        // Parse JSON regardless of status code
        return response.json().then(data => ({
            status: response.status,
            data: data
        }));
    })
    .then(result => {
        if (result.data.success) {
            showSuccess(result.data.message, result.data.start_time, result.data.end_time, result.data.job_name);
        } else {
            // Show specific error message from server
            showError(result.data.error || 'Booking failed. Please try again.');
            // Re-enable button to allow retry with different slot
            confirmBookingBtn.disabled = false;
            confirmBookingBtn.innerHTML = 'Confirm Booking';
        }
    })
    .catch(error => {
        // Network error or JSON parse error
        showError('A network error occurred. Please check your connection and try again.');
        console.error('Error:', error);
        // Re-enable button
        confirmBookingBtn.disabled = false;
        confirmBookingBtn.innerHTML = 'Confirm Booking';
    });
});

// Function to show success modal
function showSuccess(message, startTime, endTime, jobName) {
    document.getElementById('success-message').textContent = message;
    document.getElementById('modal-job-name').textContent = jobName;
    document.getElementById('modal-start-time').textContent = startTime;
    document.getElementById('modal-end-time').textContent = endTime;

    const successModal = new bootstrap.Modal(document.getElementById('successModal'));
    successModal.show();
}

// Function to show error modal
function showError(message) {
    document.getElementById('error-message').textContent = message;

    const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
    errorModal.show();
}
