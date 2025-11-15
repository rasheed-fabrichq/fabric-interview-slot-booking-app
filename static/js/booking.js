// Interview Slot Booking - Frontend JavaScript

let selectedSlotId = null;
let selectedSlotTime = null;

// Get DOM elements
const collegeInput = document.getElementById('college');
const interviewDayInfo = document.getElementById('interview-day-info');
const interviewDaySpan = document.getElementById('interview-day');
const slotContainer = document.getElementById('slot-container');
const slotsGrid = document.getElementById('slots-grid');
const loadingSpinner = document.getElementById('loading-spinner');
const selectedSlotInfo = document.getElementById('selected-slot-info');
const selectedSlotTimeSpan = document.getElementById('selected-slot-time');
const confirmBookingBtn = document.getElementById('confirm-booking-btn');
const candidateId = document.getElementById('candidate-id').value;
const bookingToken = document.getElementById('booking-token').value;

// Auto-load slots on page load based on candidate's college
document.addEventListener('DOMContentLoaded', function() {
    const candidateCollege = collegeInput.value;

    if (candidateCollege && COLLEGE_DAY_MAPPING) {
        // Get the interview day for candidate's college
        const day = COLLEGE_DAY_MAPPING[candidateCollege];

        if (day) {
            // Show interview day
            interviewDaySpan.textContent = day;
            interviewDayInfo.classList.remove('d-none');

            // Load slots for this day
            loadSlots(day);
        }
    }
});

// Function to load available slots
function loadSlots(day) {
    // Show loading spinner
    loadingSpinner.classList.remove('d-none');
    slotContainer.classList.add('d-none');
    slotsGrid.innerHTML = '';

    // Fetch slots from API
    fetch(`/api/slots?day=${day}`)
        .then(response => response.json())
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
        slotsGrid.innerHTML = '<div class="col-12"><div class="alert alert-warning">No slots available.</div></div>';
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
        card.onclick = () => selectSlot(slot.id, slot.start_time);
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
function selectSlot(slotId, slotTime) {
    // Remove previous selection
    document.querySelectorAll('.slot-card').forEach(card => {
        card.classList.remove('selected');
    });

    // Mark new selection
    event.currentTarget.classList.add('selected');

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
    if (!selectedSlotId) {
        showError('Please select a time slot.');
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
            showSuccess(result.data.message, result.data.start_time, result.data.end_time);
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
function showSuccess(message, startTime, endTime) {
    document.getElementById('success-message').textContent = message;
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
