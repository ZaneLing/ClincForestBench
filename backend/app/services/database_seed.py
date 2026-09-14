from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from backend.app.db import models as db
from backend.app.services.case_service import CaseService


def _hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def seed_benchmark(engine: Engine, cases: CaseService) -> None:
    """Idempotently add every loaded dataset, manifest and case.

    Existing local physician accounts and Arena sessions are preserved.  This
    is intentionally an additive seed so upgrading an older DDXPlus-only
    SQLite file makes the new tracks available without deleting history.
    """

    source_uris = {
        "DDXPlus": "dataset/ddxplus",
        "Synthea": "dataset/synthea",
        "MedAgentBench": "dataset/medagentbench",
    }
    with Session(engine) as database:
        for manifest_version, document in cases.manifest_documents.items():
            bundles = [
                bundle
                for bundle in cases.cases.values()
                if bundle.dataset.case_manifest_version == manifest_version
            ]
            if not bundles:
                continue
            first = bundles[0]
            if not database.get(db.DatasetVersion, first.dataset.dataset_version):
                database.add(
                    db.DatasetVersion(
                        version_id=first.dataset.dataset_version,
                        name=first.dataset.name,
                        source_uri=source_uris.get(first.dataset.name, "dataset"),
                        content_hash=_hash(document),
                        created_at=datetime.now(timezone.utc),
                    )
                )
            stored_manifest = database.get(db.CaseManifest, manifest_version)
            if not stored_manifest:
                database.add(
                    db.CaseManifest(
                        manifest_version=manifest_version,
                        dataset_version=first.dataset.dataset_version,
                        config=document,
                    )
                )
            else:
                stored_manifest.config = document

        for evidence in cases.all_evidence_catalog.values():
            if database.get(db.EvidenceCatalog, evidence.evidence_id):
                continue
            database.add(
                db.EvidenceCatalog(
                    evidence_id=evidence.evidence_id,
                    question_en=evidence.question_en,
                    data_type=evidence.data_type.value,
                    is_antecedent=evidence.is_antecedent,
                    semantic_role=evidence.semantic_role,
                    exposure_tier=evidence.exposure_tier,
                    definition=evidence.model_dump(mode="json"),
                )
            )
        database.flush()

        existing_children = set(
            database.scalars(select(db.EvidenceHierarchy.child_evidence_id)).all()
        )
        for evidence in cases.all_evidence_catalog.values():
            if evidence.parent_evidence_id and evidence.evidence_id not in existing_children:
                database.add(
                    db.EvidenceHierarchy(
                        parent_evidence_id=evidence.parent_evidence_id,
                        child_evidence_id=evidence.evidence_id,
                        activation_condition="PRESENT_OR_VALUE",
                    )
                )

        for condition_id, value in cases.all_condition_catalog.items():
            if database.get(db.ConditionCatalog, condition_id):
                continue
            database.add(
                db.ConditionCatalog(
                    condition_id=condition_id,
                    name=value.get("condition_name", condition_id),
                    severity=int(value.get("severity", 1)),
                    definition=value,
                )
            )
        database.flush()

        for bundle in cases.cases.values():
            stored_case = database.get(db.Case, bundle.case_id)
            replacing = bool(
                stored_case and stored_case.case_hash != bundle.case_hash
            )
            if replacing:
                session_count = database.scalar(
                    select(func.count(db.ArenaSession.session_id)).where(
                        db.ArenaSession.case_id == bundle.case_id
                    )
                )
                if session_count:
                    raise RuntimeError(
                        f"Case artifact changed after play history was recorded: {bundle.case_id}; bump the manifest version"
                    )
                database.execute(
                    delete(db.CaseEvidenceTruth).where(
                        db.CaseEvidenceTruth.case_id == bundle.case_id
                    )
                )
                database.execute(
                    delete(db.CaseOracleDifferential).where(
                        db.CaseOracleDifferential.case_id == bundle.case_id
                    )
                )
                stored_case.case_hash = bundle.case_hash
                stored_case.demographics = bundle.demographics.model_dump(mode="json")
                stored_case.initial_evidence_id = bundle.initial_evidence.evidence_id
                stored_case.metadata_json = {
                    **bundle.metadata.model_dump(mode="json"),
                    "dataset_name": bundle.dataset.name,
                    "case_type": bundle.case_type,
                    "generation_mode": bundle.generation_mode,
                }
            elif stored_case:
                continue
            else:
                database.add(db.Case(
                    case_id=bundle.case_id,
                    manifest_version=bundle.dataset.case_manifest_version,
                    case_hash=bundle.case_hash,
                    demographics=bundle.demographics.model_dump(mode="json"),
                    initial_evidence_id=bundle.initial_evidence.evidence_id,
                    metadata_json={
                        **bundle.metadata.model_dump(mode="json"),
                        "dataset_name": bundle.dataset.name,
                        "case_type": bundle.case_type,
                        "generation_mode": bundle.generation_mode,
                    },
                ))
            database.flush()
            for truth in bundle.truth:
                database.add(
                    db.CaseEvidenceTruth(
                        case_id=bundle.case_id,
                        evidence_id=truth.evidence_id,
                        status=truth.status.value,
                        response=truth.model_dump(mode="json"),
                    )
                )
            for rank, differential in enumerate(bundle.oracle.differential, start=1):
                database.add(
                    db.CaseOracleDifferential(
                        case_id=bundle.case_id,
                        condition_id=differential.condition,
                        rank=rank,
                        probability=differential.probability,
                        is_pathology=differential.condition == bundle.oracle.pathology,
                    )
                )
        database.commit()
