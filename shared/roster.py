import csv
import io

COLUMNS = ("student_id", "name", "email")


def parse_roster(text):
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    missing = [c for c in COLUMNS if c not in fields]
    if missing:
        raise ValueError(f"The roster needs these columns: {', '.join(COLUMNS)}. Missing: {', '.join(missing)}.")
    students = []
    for line, row in enumerate(reader, start=2):
        student = {c: (row[fields[c]] or "").strip() for c in COLUMNS}
        if not any(student.values()):
            continue
        if not all(student.values()):
            raise ValueError(f"Row {line} is missing a student ID, name or email.")
        student["email"] = student["email"].lower()
        students.append(student)
    return students
