from etl.temporal_v2.validation import validate_mcmed


if __name__ == "__main__":
    report = validate_mcmed()
    print(f"MC-MED: {len(report['tables'])} tables validated")
