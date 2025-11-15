"""
Load Test Data Generator
Generates 1000 candidates and assigns slots to all of them for testing
"""
import uuid
import random
import sys
from datetime import datetime

# Import from local modules
from database import add_candidate, book_slot, get_slots_by_day
from config import COLLEGES, COLLEGE_DAY_MAPPING


def generate_candidates(count=1000):
    """Generate realistic candidate data"""
    print(f"\n{'='*60}")
    print(f"GENERATING {count} TEST CANDIDATES")
    print(f"{'='*60}\n")

    # Common first names and last names for generating realistic names
    first_names = [
        'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Krishna', 'Shaurya',
        'Atharv', 'Advik', 'Pranav', 'Arnav', 'Dhruv', 'Kabir', 'Rudra', 'Reyansh',
        'Aadhya', 'Ananya', 'Diya', 'Isha', 'Navya', 'Saanvi', 'Sara', 'Anika',
        'Pari', 'Myra', 'Kiara', 'Shanaya', 'Kavya', 'Riya', 'Anvi', 'Prisha',
        'Rohan', 'Ayaan', 'Rishi', 'Karthik', 'Nikhil', 'Aakash', 'Varun', 'Aryan',
        'Priya', 'Neha', 'Pooja', 'Sneha', 'Anjali', 'Shreya', 'Divya', 'Meera'
    ]

    last_names = [
        'Sharma', 'Verma', 'Gupta', 'Kumar', 'Singh', 'Patel', 'Reddy', 'Rao',
        'Nair', 'Iyer', 'Pillai', 'Menon', 'Desai', 'Joshi', 'Shah', 'Mehta',
        'Agarwal', 'Bansal', 'Jain', 'Arora', 'Malhotra', 'Khanna', 'Chopra', 'Kapoor',
        'Sinha', 'Das', 'Roy', 'Ghosh', 'Chatterjee', 'Mukherjee', 'Bose', 'Sen',
        'Khan', 'Ahmed', 'Ali', 'Hussain', 'Rahman', 'Ansari', 'Siddiqui', 'Qureshi'
    ]

    email_domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'iitb.ac.in', 'iitd.ac.in']

    candidates = []

    for i in range(count):
        candidate_id = str(uuid.uuid4())
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        name = f"{first_name} {last_name}"

        # Generate email
        email_prefix = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}"
        email = f"{email_prefix}@{random.choice(email_domains)}"

        candidates.append({
            'candidate_id': candidate_id,
            'name': name,
            'email': email
        })

        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{count} candidates...")

    print(f"\n✓ Successfully generated {count} candidates\n")
    return candidates


def add_candidates_to_db(candidates):
    """Add candidates to database"""
    print(f"{'='*60}")
    print(f"ADDING CANDIDATES TO DATABASE")
    print(f"{'='*60}\n")

    success_count = 0
    error_count = 0
    errors = []

    for i, candidate in enumerate(candidates):
        result = add_candidate(
            candidate['candidate_id'],
            candidate['name'],
            candidate['email']
        )

        if 'success' in result:
            success_count += 1
        else:
            error_count += 1
            errors.append(f"Candidate {i+1}: {result.get('error')}")

        if (i + 1) % 100 == 0:
            print(f"  Added {i + 1}/{len(candidates)} candidates...")

    print(f"\n✓ Successfully added: {success_count}")
    if error_count > 0:
        print(f"✗ Errors: {error_count}")
        if errors:
            print("\nFirst 10 errors:")
            for error in errors[:10]:
                print(f"  - {error}")

    print()
    return success_count


def assign_slots_to_candidates(candidates):
    """Assign slots to all candidates"""
    print(f"{'='*60}")
    print(f"ASSIGNING SLOTS TO CANDIDATES")
    print(f"{'='*60}\n")

    # Get all available slots for both days
    saturday_slots = get_slots_by_day('Saturday')
    sunday_slots = get_slots_by_day('Sunday')

    print(f"Available Saturday slots: {len(saturday_slots)}")
    print(f"Available Sunday slots: {len(sunday_slots)}")
    print()

    success_count = 0
    error_count = 0
    errors = []

    for i, candidate in enumerate(candidates):
        # Pick a random college
        college = random.choice(COLLEGES)

        # Get the day for that college
        day = COLLEGE_DAY_MAPPING[college]

        # Get slots for that day
        slots = saturday_slots if day == 'Saturday' else sunday_slots

        # Filter available slots (slots with capacity left)
        available_slots = [s for s in slots if s['available'] > 0]

        if not available_slots:
            error_count += 1
            errors.append(f"Candidate {i+1} ({candidate['name']}): No available slots for {day}")
            continue

        # Pick a random available slot
        slot = random.choice(available_slots)

        # Book the slot
        result = book_slot(
            candidate['candidate_id'],
            slot['id'],
            college
        )

        if 'success' in result:
            success_count += 1
            # Update local slot availability
            slot['booked_count'] += 1
            slot['available'] -= 1
        else:
            error_count += 1
            errors.append(f"Candidate {i+1} ({candidate['name']}): {result.get('error')}")

        if (i + 1) % 100 == 0:
            print(f"  Assigned slots for {i + 1}/{len(candidates)} candidates...")

    print(f"\n✓ Successfully booked: {success_count}")
    if error_count > 0:
        print(f"✗ Errors: {error_count}")
        if errors:
            print("\nFirst 10 errors:")
            for error in errors[:10]:
                print(f"  - {error}")

    print()
    return success_count


def print_summary():
    """Print database statistics summary"""
    from database import get_dashboard_stats

    print(f"\n{'='*60}")
    print(f"DATABASE STATISTICS SUMMARY")
    print(f"{'='*60}\n")

    stats = get_dashboard_stats()

    print(f"Total Candidates: {stats['total_candidates']}")
    print(f"Total Bookings: {stats['total_bookings']}")
    print()

    print("Candidates by Status:")
    for status, count in stats['status_counts'].items():
        print(f"  - {status}: {count}")
    print()

    print("Slot Utilization by Day:")
    for day_stat in stats['day_stats']:
        utilization = (day_stat['total_booked'] / day_stat['total_capacity']) * 100
        print(f"  - {day_stat['day']}:")
        print(f"    Booked: {day_stat['total_booked']} / {day_stat['total_capacity']} ({utilization:.1f}%)")

    print(f"\n{'='*60}\n")


def main():
    """Main function to run the load test"""
    print(f"\n{'#'*60}")
    print(f"# LOAD TEST DATA GENERATOR")
    print(f"# Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    # Ask for confirmation
    print("\n⚠️  WARNING: This will add 1000 candidates and assign slots to them.")
    response = input("Do you want to continue? (yes/no): ").strip().lower()

    if response != 'yes':
        print("\n❌ Operation cancelled.\n")
        sys.exit(0)

    # Step 1: Generate candidates
    candidates = generate_candidates(1000)

    # Step 2: Add to database
    added_count = add_candidates_to_db(candidates)

    if added_count == 0:
        print("\n❌ No candidates were added. Exiting.\n")
        sys.exit(1)

    # Step 3: Assign slots
    booked_count = assign_slots_to_candidates(candidates)

    # Step 4: Print summary
    print_summary()

    print("✅ Load test data generation completed!")
    print(f"   - {added_count} candidates added")
    print(f"   - {booked_count} slots booked\n")


if __name__ == '__main__':
    main()
