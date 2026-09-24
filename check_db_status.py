"""
Quick script to check current database status
"""
from database import get_dashboard_stats, get_slots_by_day


def main():
    print("\n" + "="*60)
    print("CURRENT DATABASE STATUS")
    print("="*60 + "\n")

    # Get stats
    stats = get_dashboard_stats()

    print(f"Total Candidates: {stats['total_candidates']}")
    print(f"Total Bookings: {stats['total_bookings']}")
    print()

    print("Candidates by Status:")
    if stats['status_counts']:
        for status, count in stats['status_counts'].items():
            print(f"  - {status}: {count}")
    else:
        print("  (No candidates)")
    print()

    # Check slots
    saturday_slots = get_slots_by_day('Saturday')
    sunday_slots = get_slots_by_day('Sunday')

    print(f"Saturday Slots: {len(saturday_slots)}")
    if saturday_slots:
        total_capacity = sum(s['max_capacity'] for s in saturday_slots)
        total_booked = sum(s['booked_count'] for s in saturday_slots)
        available = total_capacity - total_booked
        print(f"  - Total Capacity: {total_capacity}")
        print(f"  - Booked: {total_booked}")
        print(f"  - Available: {available}")

    print()

    print(f"Sunday Slots: {len(sunday_slots)}")
    if sunday_slots:
        total_capacity = sum(s['max_capacity'] for s in sunday_slots)
        total_booked = sum(s['booked_count'] for s in sunday_slots)
        available = total_capacity - total_booked
        print(f"  - Total Capacity: {total_capacity}")
        print(f"  - Booked: {total_booked}")
        print(f"  - Available: {available}")

    print()

    # Check if ready for load test
    print("="*60)
    total_slots = len(saturday_slots) + len(sunday_slots)

    if total_slots == 0:
        print("⚠️  WARNING: No slots found! Please initialize slots first.")
        print("   Run: Initialize slots from admin dashboard")
    elif stats['total_candidates'] > 0:
        print("⚠️  WARNING: Database already contains candidates.")
        print(f"   Current candidates: {stats['total_candidates']}")
        print("   You may want to clear data before load testing.")
    else:
        total_capacity = sum(s['max_capacity'] for s in saturday_slots + sunday_slots)
        print("✓ Database is ready for load testing!")
        print(f"  - Total slot capacity: {total_capacity}")
        print(f"  - You can safely add 1000 candidates")

    print("="*60 + "\n")


if __name__ == '__main__':
    main()
