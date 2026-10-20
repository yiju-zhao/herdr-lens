"""A real source file for checking line-number navigation."""


def build_report(values):
    total = sum(values)
    count = len(values)
    average = total / count if count else 0
    return {"total": total, "count": count, "average": average}
