from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

import duckdb

from etl.common import dump_json

from .common import ROOT, TEMPORAL_ROOT


def validate_sources(
    dataset: str,
    tables: Iterable[Dict[str, object]],
    joins: Iterable[Dict[str, str]],
    output_name: str,
    root: Path = ROOT,
) -> dict:
    connection = duckdb.connect()
    connection.execute("PRAGMA threads=4")
    reports: List[dict] = []
    for table in tables:
        relative = str(table["path"])
        path = root / relative
        if not path.exists():
            reports.append({"name": table["name"], "path": relative, "exists": False})
            continue
        expression = _reader(path)
        description = connection.execute(f"DESCRIBE SELECT * FROM {expression}").fetchall()
        columns = [row[0] for row in description]
        time_fields = [field for field in table.get("time_fields", []) if field in columns]
        metrics = ["count(*) AS row_count"]
        metrics.extend(
            f"round(100.0 * count_if({field} IS NULL) / greatest(count(*),1), 3) AS {field}_null_pct"
            for field in time_fields
        )
        values = connection.execute(f"SELECT {','.join(metrics)} FROM {expression}").fetchone()
        reports.append(
            {
                "name": table["name"],
                "path": relative,
                "exists": True,
                "schema": columns,
                "row_count": values[0],
                "time_null_pct": dict(zip(time_fields, values[1:])),
            }
        )
    join_reports = []
    for join in joins:
        left_path = root / join["left_path"]
        right_path = root / join["right_path"]
        left = _reader(left_path)
        right = _reader(right_path)
        left_key = join["left_key"]
        right_key = join.get("right_key", left_key)
        row = connection.execute(
            f"""SELECT count(*) AS total_count,
                       count(*) FILTER (WHERE r.{right_key} IS NOT NULL) AS matched_count
                FROM {left} l LEFT JOIN
                     (SELECT DISTINCT {right_key} FROM {right}) r
                  ON l.{left_key}=r.{right_key}"""
        ).fetchone()
        join_reports.append(
            {
                "name": join["name"],
                "total": row[0],
                "matched": row[1],
                "coverage": round(row[1] / max(1, row[0]), 6),
            }
        )
    payload = {
        "schema_version": "clincforestbench.source-validation.v2",
        "dataset": dataset,
        "all_required_files_present": all(item.get("exists") for item in reports),
        "tables": reports,
        "id_join_coverage": join_reports,
    }
    dump_json(TEMPORAL_ROOT / "source_validation" / output_name, payload)
    return payload


def validate_mcmed(root: Path = ROOT) -> dict:
    base = "dataset/restricted/mc-med-v1.0.1"
    return validate_sources(
        "MC-MED v1.0.1",
        [
            {"name": "visits", "path": f"{base}/visits.csv", "time_fields": ["Arrival_time", "Roomed_time", "Dispo_time"]},
            {"name": "orders", "path": f"{base}/orders.csv", "time_fields": ["Order_time", "First_admin_time", "Result_time"]},
            {"name": "labs", "path": f"{base}/labs.csv", "time_fields": ["Order_time", "Result_time"]},
            {"name": "rads", "path": f"{base}/rads.csv", "time_fields": ["Order_time", "Result_time"]},
            {"name": "pmh", "path": f"{base}/pmh.csv", "time_fields": ["Noted_date"]},
            {"name": "meds", "path": f"{base}/meds.csv", "time_fields": ["Start_date", "End_date"]},
        ],
        [
            {"name": "labs_to_visits_by_CSN", "left_path": f"{base}/labs.csv", "right_path": f"{base}/visits.csv", "left_key": "CSN"},
            {"name": "rads_to_visits_by_CSN", "left_path": f"{base}/rads.csv", "right_path": f"{base}/visits.csv", "left_key": "CSN"},
        ],
        "mcmed.json",
        root,
    )


def validate_mimic(root: Path = ROOT) -> dict:
    main = "dataset/restricted/mimiciv/3.1"
    note = "dataset/restricted/mimic-iv-note/2.2"
    ecg = "dataset/restricted/mimic-iv-ecg"
    ed = "dataset/restricted/mimic-iv-ed-v2.2"
    return validate_sources(
        "MIMIC-IV multimodal",
        [
            {"name": "admissions", "path": f"{main}/hosp/admissions.csv.gz", "time_fields": ["admittime", "dischtime"]},
            {"name": "labevents", "path": f"{main}/hosp/labevents.csv.gz", "time_fields": ["charttime", "storetime"]},
            {"name": "poe", "path": f"{main}/hosp/poe.csv.gz", "time_fields": ["ordertime"]},
            {"name": "discharge_notes", "path": f"{note}/note/discharge.csv.gz", "time_fields": ["charttime", "storetime"]},
            {"name": "radiology_notes", "path": f"{note}/note/radiology.csv.gz", "time_fields": ["charttime", "storetime"]},
            {"name": "ecg_records", "path": f"{ecg}/record_list.csv", "time_fields": ["ecg_time"]},
            {"name": "ecg_measurements", "path": f"{ecg}/machine_measurements.csv", "time_fields": ["ecg_time"]},
            {"name": "edstays", "path": f"{ed}/ed/edstays.csv.gz", "time_fields": ["intime", "outtime"]},
        ],
        [
            {"name": "discharge_to_admissions_by_hadm_id", "left_path": f"{note}/note/discharge.csv.gz", "right_path": f"{main}/hosp/admissions.csv.gz", "left_key": "hadm_id"},
            {"name": "radiology_to_admissions_by_hadm_id", "left_path": f"{note}/note/radiology.csv.gz", "right_path": f"{main}/hosp/admissions.csv.gz", "left_key": "hadm_id"},
            {"name": "ecg_to_patients_by_subject_id", "left_path": f"{ecg}/record_list.csv", "right_path": f"{main}/hosp/patients.csv.gz", "left_key": "subject_id"},
        ],
        "mimic.json",
        root,
    )


def validate_eicu(root: Path = ROOT) -> dict:
    base = "dataset/restricted/eicu-crd-v2.0"
    return validate_sources(
        "eICU-CRD v2.0",
        [
            {"name": "patient", "path": f"{base}/patient.csv.gz", "time_fields": ["hospitaladmitoffset", "unitdischargeoffset"]},
            {"name": "lab", "path": f"{base}/lab.csv.gz", "time_fields": ["labresultoffset", "labresultrevisedoffset"]},
            {"name": "diagnosis", "path": f"{base}/diagnosis.csv.gz", "time_fields": ["diagnosisoffset"]},
            {"name": "treatment", "path": f"{base}/treatment.csv.gz", "time_fields": ["treatmentoffset"]},
            {"name": "vitalPeriodic", "path": f"{base}/vitalPeriodic.csv.gz", "time_fields": ["observationoffset"]},
            {"name": "pastHistory", "path": f"{base}/pastHistory.csv.gz", "time_fields": ["pasthistoryoffset", "pasthistoryenteredoffset"]},
            {"name": "physicalExam", "path": f"{base}/physicalExam.csv.gz", "time_fields": ["physicalexamoffset"]},
        ],
        [
            {"name": "lab_to_patient_by_stay", "left_path": f"{base}/lab.csv.gz", "right_path": f"{base}/patient.csv.gz", "left_key": "patientunitstayid"},
            {"name": "diagnosis_to_patient_by_stay", "left_path": f"{base}/diagnosis.csv.gz", "right_path": f"{base}/patient.csv.gz", "left_key": "patientunitstayid"},
        ],
        "eicu.json",
        root,
    )


def _reader(path: Path) -> str:
    escaped = str(path).replace("'", "''")
    # The local labevents export has a small number of rows with an absent
    # trailing empty field.  Scope padding to that structured table: enabling
    # it for multiline clinical notes can change quoted-text parsing.
    if path.name == "labevents.csv.gz":
        return (
            f"read_csv_auto('{escaped}',header=true,strict_mode=false,"
            "null_padding=true,parallel=false)"
        )
    return f"read_csv_auto('{escaped}',header=true,strict_mode=false)"
