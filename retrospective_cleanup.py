import sqlite3
from datetime import datetime

def cleanup():
    conn = sqlite3.connect("devlog.db")
    cur = conn.cursor()

    print("--- Starting Retroactive Cleanup ---")

    # 1. Remove exact/near duplicates (sessions for same project starting within 1 second of each other)
    print("Deleting duplicate sessions...")
    cur.execute("""
        DELETE FROM sessions 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM sessions 
            GROUP BY project, SUBSTR(start_time, 1, 19), duration
        )
    """)
    removed_dupes = cur.rowcount
    print(f"Removed {removed_dupes} duplicate entries.")

    # 2. Fix missing categories
    print("Fixing missing categories...")
    cur.execute("UPDATE sessions SET category = 'default' WHERE category IS NULL OR category = 'None'")
    updated_cats = cur.rowcount
    print(f"Updated {updated_cats} records with default category.")

    # 3. Correct project names for legacy records (e.g., 'Root' to 'Global')
    cur.execute("UPDATE sessions SET project = 'Global' WHERE project = 'Root'")
    updated_names = cur.rowcount
    print(f"Renamed {updated_names} 'Root' projects to 'Global'.")

    conn.commit()
    conn.close()
    print("--- Cleanup Complete ---")

if __name__ == "__main__":
    cleanup()
