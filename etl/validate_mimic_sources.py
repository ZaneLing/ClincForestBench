from etl.source_adapters.validation import validate_mimic


if __name__ == "__main__":
    report = validate_mimic()
    print(f"MIMIC: {len(report['tables'])} tables validated")
