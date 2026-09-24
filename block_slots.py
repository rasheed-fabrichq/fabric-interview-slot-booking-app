"""
Script to artificially block slots by increasing their booked_count
This prevents candidates from booking these slots without actually adding bookings.

Usage:
    python block_slots.py

How it works:
- You provide a list of slot IDs and the number to add to their booked_count
- The script updates the booked_count directly in the slots table
- No bookings or candidate entries are created
- This makes the slots appear full when candidates try to book

IMPORTANT: This does NOT affect existing bookings or any other functionality
"""

import sqlite3
from config import DATABASE_PATH


def block_slots_by_ids(slot_ids, increment_count):
    """
    Block specific slots by increasing their booked_count

    Args:
        slot_ids: List of slot IDs to block
        increment_count: Number to add to the booked_count for each slot

    Returns:
        Dictionary with success status and details
    """
    if not slot_ids:
        return {'error': 'No slot IDs provided'}

    if increment_count <= 0:
        return {'error': 'Increment count must be positive'}

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        updated_slots = []
        errors = []

        for slot_id in slot_ids:
            # Get current slot details
            cursor.execute('''
                SELECT id, job_id, date, start_time, booked_count
                FROM slots
                WHERE id = ?
            ''', (slot_id,))

            slot = cursor.fetchone()

            if not slot:
                errors.append(f"Slot ID {slot_id}: Not found")
                continue

            # Get job capacity to check if we're exceeding it
            cursor.execute('''
                SELECT capacity_per_slot, job_name
                FROM job_configs
                WHERE job_id = ?
            ''', (slot['job_id'],))

            job_config = cursor.fetchone()

            if not job_config:
                errors.append(f"Slot ID {slot_id}: Job config not found")
                continue

            old_booked_count = slot['booked_count']
            new_booked_count = old_booked_count + increment_count
            max_capacity = job_config['capacity_per_slot']

            # Check if new count exceeds capacity
            if new_booked_count > max_capacity:
                errors.append(
                    f"Slot ID {slot_id}: Would exceed capacity "
                    f"({new_booked_count} > {max_capacity}). "
                    f"Current: {old_booked_count}, Trying to add: {increment_count}"
                )
                continue

            # Update the booked_count
            cursor.execute('''
                UPDATE slots
                SET booked_count = booked_count + ?
                WHERE id = ?
            ''', (increment_count, slot_id))

            updated_slots.append({
                'slot_id': slot_id,
                'job_name': job_config['job_name'],
                'date': slot['date'],
                'start_time': slot['start_time'],
                'old_booked_count': old_booked_count,
                'new_booked_count': new_booked_count,
                'max_capacity': max_capacity,
                'remaining': max_capacity - new_booked_count
            })

        conn.commit()
        conn.close()

        return {
            'success': True,
            'updated_count': len(updated_slots),
            'updated_slots': updated_slots,
            'errors': errors
        }

    except Exception as e:
        conn.rollback()
        conn.close()
        return {'error': f'Database error: {str(e)}'}


def unblock_slots_by_ids(slot_ids, decrement_count):
    """
    Unblock specific slots by decreasing their booked_count
    Use this to reverse the blocking operation

    Args:
        slot_ids: List of slot IDs to unblock
        decrement_count: Number to subtract from the booked_count for each slot

    Returns:
        Dictionary with success status and details
    """
    if not slot_ids:
        return {'error': 'No slot IDs provided'}

    if decrement_count <= 0:
        return {'error': 'Decrement count must be positive'}

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        updated_slots = []
        errors = []

        for slot_id in slot_ids:
            # Get current slot details
            cursor.execute('''
                SELECT id, job_id, date, start_time, booked_count
                FROM slots
                WHERE id = ?
            ''', (slot_id,))

            slot = cursor.fetchone()

            if not slot:
                errors.append(f"Slot ID {slot_id}: Not found")
                continue

            # Get job info
            cursor.execute('''
                SELECT job_name FROM job_configs WHERE job_id = ?
            ''', (slot['job_id'],))

            job_config = cursor.fetchone()

            old_booked_count = slot['booked_count']
            new_booked_count = max(0, old_booked_count - decrement_count)  # Don't go below 0

            # Update the booked_count
            cursor.execute('''
                UPDATE slots
                SET booked_count = ?
                WHERE id = ?
            ''', (new_booked_count, slot_id))

            updated_slots.append({
                'slot_id': slot_id,
                'job_name': job_config['job_name'] if job_config else 'Unknown',
                'date': slot['date'],
                'start_time': slot['start_time'],
                'old_booked_count': old_booked_count,
                'new_booked_count': new_booked_count
            })

        conn.commit()
        conn.close()

        return {
            'success': True,
            'updated_count': len(updated_slots),
            'updated_slots': updated_slots,
            'errors': errors
        }

    except Exception as e:
        conn.rollback()
        conn.close()
        return {'error': f'Database error: {str(e)}'}


def view_slot_details(slot_ids):
    """
    View details of specific slots before blocking/unblocking

    Args:
        slot_ids: List of slot IDs to view

    Returns:
        List of slot details
    """
    if not slot_ids:
        return []

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    slots_info = []

    for slot_id in slot_ids:
        cursor.execute('''
            SELECT
                s.id,
                s.job_id,
                s.date,
                s.day_of_week,
                s.start_time,
                s.booked_count,
                jc.job_name,
                jc.capacity_per_slot,
                jc.slot_duration_minutes,
                (jc.capacity_per_slot - s.booked_count) as available
            FROM slots s
            JOIN job_configs jc ON s.job_id = jc.job_id
            WHERE s.id = ?
        ''', (slot_id,))

        slot = cursor.fetchone()

        if slot:
            slots_info.append({
                'slot_id': slot['id'],
                'job_name': slot['job_name'],
                'date': slot['date'],
                'day_of_week': slot['day_of_week'],
                'start_time': slot['start_time'],
                'duration': slot['slot_duration_minutes'],
                'booked_count': slot['booked_count'],
                'max_capacity': slot['capacity_per_slot'],
                'available': slot['available']
            })

    conn.close()
    return slots_info


if __name__ == '__main__':
    print("=" * 70)
    print("SLOT BLOCKING/UNBLOCKING SCRIPT")
    print("=" * 70)
    print()
    print("This script allows you to artificially block or unblock slots")
    print("by modifying their booked_count without adding actual bookings.")
    print()

    # ==============================================================
    # CONFIGURATION: Edit these values for your use case
    # ==============================================================

    # OPERATION MODE: Choose 'block' or 'unblock'
    OPERATION = 'unblock'  # Options: 'block' or 'unblock'

    # List the slot IDs you want to block/unblock
    SLOT_IDS = [1, 2, 3, 4, 5]  # Replace with your slot IDs

    # How many "phantom bookings" to add (block) or remove (unblock)
    # For example:
    #   - To block: Set to 3 to reduce availability by 3 slots
    #   - To unblock: Set to 3 to restore availability of 3 slots
    COUNT = 3

    # ==============================================================
    #
    # EXAMPLES:
    #
    # Example 1: Block slots from 8 PM to 12 AM to reduce concurrency
    #   OPERATION = 'block'
    #   SLOT_IDS = [101, 102, 103, 104, 105, 106, 107, 108]
    #   COUNT = 3  # Block 3 slots from each time interval
    #
    # Example 2: Unblock previously blocked slots
    #   OPERATION = 'unblock'
    #   SLOT_IDS = [101, 102, 103, 104, 105, 106, 107, 108]
    #   COUNT = 3  # Restore 3 slots to each time interval
    #
    # ==============================================================

    print("CONFIGURATION:")
    print(f"  Operation: {OPERATION.upper()}")
    print(f"  Slot IDs: {SLOT_IDS}")
    print(f"  Count: {COUNT}")
    print()

    # Validate operation mode
    if OPERATION not in ['block', 'unblock']:
        print(f"ERROR: Invalid operation '{OPERATION}'. Must be 'block' or 'unblock'")
        exit(1)

    # View current slot details
    print("Current slot details:")
    print("-" * 70)
    current_slots = view_slot_details(SLOT_IDS)

    if not current_slots:
        print("ERROR: None of the provided slot IDs were found!")
        print()
        print("Tips:")
        print("  1. Check the slot IDs in the admin panel at /admin/slots")
        print("  2. Make sure slots have been initialized for the job")
        print("  3. Verify the database path in config.py")
        exit(1)

    for slot in current_slots:
        print(f"\nSlot ID: {slot['slot_id']}")
        print(f"  Job: {slot['job_name']}")
        print(f"  Date: {slot['date']} ({slot['day_of_week']})")
        print(f"  Time: {slot['start_time']} ({slot['duration']} mins)")
        print(f"  Current: {slot['booked_count']}/{slot['max_capacity']} booked")
        print(f"  Available: {slot['available']} slots")

        if OPERATION == 'block':
            print(f"  After blocking: {slot['booked_count'] + COUNT}/{slot['max_capacity']} booked")
            print(f"  New available: {max(0, slot['available'] - COUNT)} slots")
        else:
            new_booked = max(0, slot['booked_count'] - COUNT)
            print(f"  After unblocking: {new_booked}/{slot['max_capacity']} booked")
            print(f"  New available: {slot['max_capacity'] - new_booked} slots")

    print()
    print("=" * 70)

    # Ask for confirmation
    action_verb = "blocking" if OPERATION == 'block' else "unblocking"
    response = input(f"\nDo you want to proceed with {action_verb} these slots? (yes/no): ").lower().strip()

    if response == 'yes':
        print(f"\n{action_verb.capitalize()} slots...")

        if OPERATION == 'block':
            result = block_slots_by_ids(SLOT_IDS, COUNT)
        else:
            result = unblock_slots_by_ids(SLOT_IDS, COUNT)

        if 'error' in result:
            print(f"\nERROR: {result['error']}")
        else:
            print(f"\nSUCCESS! Updated {result['updated_count']} slots")
            print()

            for slot in result['updated_slots']:
                print(f"Slot ID {slot['slot_id']} ({slot['job_name']} - {slot['date']} {slot['start_time']}):")
                print(f"  {slot['old_booked_count']} → {slot['new_booked_count']} / {slot['max_capacity']}")
                print(f"  Remaining available: {slot['remaining']}")
                print()

            if result['errors']:
                print("ERRORS encountered:")
                for error in result['errors']:
                    print(f"  - {error}")
                print()

        print("=" * 70)
        print("DONE!")
        print()
        print("Notes:")
        if OPERATION == 'block':
            print("  - No bookings or candidate entries were created")
            print("  - Candidates will see these slots as having less availability")
            print("  - You can reverse this by setting OPERATION='unblock' and running again")
            print("  - Check the admin panel at /admin/slots to verify")
        else:
            print("  - No bookings or candidate entries were removed")
            print("  - Candidates will see these slots as having more availability")
            print("  - You can block again by setting OPERATION='block' and running again")
            print("  - Check the admin panel at /admin/slots to verify")
    else:
        print(f"\nOperation cancelled. No {action_verb} was performed.")

    print()
    print("=" * 70)
