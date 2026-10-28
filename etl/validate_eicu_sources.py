from etl.source_adapters.validation import validate_eicu


if __name__ == "__main__":
    report = validate_eicu()
    print(f"eICU: {len(report['tables'])} tables validated")
