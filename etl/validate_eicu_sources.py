from etl.temporal_v2.validation import validate_eicu


if __name__ == "__main__":
    report = validate_eicu()
    print(f"eICU: {len(report['tables'])} tables validated")
