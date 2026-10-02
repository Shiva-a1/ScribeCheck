def scheme_problems(questions):
    problems = []
    if not questions:
        problems.append("Upload an answer key first.")
    for q in questions:
        label = f"Question {q['number']}"
        total = sum(float(p["marks"]) for p in q["points"])
        if float(q["max_marks"]) <= 0:
            problems.append(f"{label} needs its marks filled in.")
        elif not q["points"]:
            problems.append(f"{label} has no rubric points.")
        elif abs(total - float(q["max_marks"])) > 1e-9:
            problems.append(f"{label}: points add up to {total:g}, but the question is worth {float(q['max_marks']):g}.")
        if any(not p["description"].strip() for p in q["points"]):
            problems.append(f"{label} has a rubric point with no description.")
    return problems
