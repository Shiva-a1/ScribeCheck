import sys

from api.auth import invite
from shared import db

if len(sys.argv) != 3:
    sys.exit('Usage: python -m scripts.add_teacher teacher@ufl.edu "Teacher Name"')

email, name = sys.argv[1].strip().lower(), sys.argv[2].strip()
with db.connection() as conn:
    conn.execute(
        "INSERT INTO users (email, name, role) VALUES (%s, %s, 'teacher') "
        "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, role = 'teacher'",
        (email, name),
    )
invite(email)
print(f"{email} can now sign in as a teacher.")
