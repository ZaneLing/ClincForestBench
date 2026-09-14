"""PostgreSQL operational schema. Raw DDXPlus patients remain in Parquet."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    version_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceCatalog(Base):
    __tablename__ = "evidence_catalog"
    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    question_en: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(String, nullable=False)
    is_antecedent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    semantic_role: Mapped[str] = mapped_column(String, nullable=False)
    exposure_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)


class EvidenceHierarchy(Base):
    __tablename__ = "evidence_hierarchy"
    hierarchy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_catalog.evidence_id"))
    child_evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_catalog.evidence_id"), unique=True)
    activation_condition: Mapped[str] = mapped_column(String, default="PRESENT")


class ConditionCatalog(Base):
    __tablename__ = "condition_catalog"
    condition_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)


class CaseManifest(Base):
    __tablename__ = "case_manifests"
    manifest_version: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)


class Case(Base):
    __tablename__ = "cases"
    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    manifest_version: Mapped[str] = mapped_column(ForeignKey("case_manifests.manifest_version"))
    case_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    demographics: Mapped[dict] = mapped_column(JSON, nullable=False)
    initial_evidence_id: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)


class CaseEvidenceTruth(Base):
    __tablename__ = "case_evidence_truth"
    truth_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_catalog.evidence_id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("case_id", "evidence_id"),)


class CaseOracleDifferential(Base):
    __tablename__ = "case_oracle_differential"
    oracle_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    condition_id: Mapped[str] = mapped_column(ForeignKey("condition_catalog.condition_id"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    is_pathology: Mapped[bool] = mapped_column(Boolean, default=False)


class Player(Base):
    __tablename__ = "players"
    player_id: Mapped[str] = mapped_column(String, primary_key=True)
    player_type: Mapped[str] = mapped_column(String, nullable=False)
    specialty: Mapped[Optional[str]] = mapped_column(String)
    training_level: Mapped[Optional[str]] = mapped_column(String)
    years_experience: Mapped[Optional[float]] = mapped_column(Float)
    site: Mapped[Optional[str]] = mapped_column(String)
    country: Mapped[Optional[str]] = mapped_column(String)
    model_metadata: Mapped[Optional[dict]] = mapped_column(JSON)


class PhysicianAccount(Base):
    __tablename__ = "physician_accounts"
    username: Mapped[str] = mapped_column(String, primary_key=True)
    password_plaintext: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(
        ForeignKey("physician_accounts.username"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArenaSession(Base):
    __tablename__ = "sessions"
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    case_hash: Mapped[str] = mapped_column(String, nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    arena_mode: Mapped[str] = mapped_column(String, nullable=False)
    belief_capture_mode: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dataset_version: Mapped[str] = mapped_column(String, nullable=False)
    case_version: Mapped[str] = mapped_column(String, nullable=False)
    arena_version: Mapped[str] = mapped_column(String, nullable=False)
    ui_version: Mapped[str] = mapped_column(String, nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    final_state_hash: Mapped[Optional[str]] = mapped_column(String)


class SessionEvent(Base):
    __tablename__ = "session_events"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    client_event_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[dict] = mapped_column(JSON, nullable=False)
    observation: Mapped[Optional[dict]] = mapped_column(JSON)
    state_before_hash: Mapped[str] = mapped_column(String, nullable=False)
    state_after_hash: Mapped[str] = mapped_column(String, nullable=False)
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    result_type: Mapped[Optional[str]] = mapped_column(String)
    __table_args__ = (
        UniqueConstraint("session_id", "sequence"),
        UniqueConstraint("session_id", "client_event_id"),
    )


class StateSnapshot(Base):
    __tablename__ = "state_snapshots"
    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    state_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)
    revealed_evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    revealed_evidence_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BeliefSnapshot(Base):
    __tablename__ = "belief_snapshots"
    belief_row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    belief_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    state_hash: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelArenaRun(Base):
    __tablename__ = "model_arena_runs"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.session_id"), unique=True, index=True
    )
    model_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String, index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    dataset_name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    forced_final: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ModelInteraction(Base):
    __tablename__ = "model_interactions"
    interaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("model_arena_runs.run_id"), index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    assistant_content: Mapped[Optional[str]] = mapped_column(Text)
    parsed_decision: Mapped[Optional[dict]] = mapped_column(JSON)
    application_result: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "step"),)


class CaseGraphNode(Base):
    __tablename__ = "case_graph_nodes"
    node_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    state_hash: Mapped[str] = mapped_column(String, index=True)
    support: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint("case_id", "state_hash"),)


class CaseGraphEdge(Base):
    __tablename__ = "case_graph_edges"
    edge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), index=True)
    source_hash: Mapped[str] = mapped_column(String, nullable=False)
    target_hash: Mapped[str] = mapped_column(String, nullable=False)
    action_evidence_id: Mapped[str] = mapped_column(String, nullable=False)
    support: Mapped[int] = mapped_column(Integer, nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    subgroup_counts: Mapped[dict] = mapped_column(JSON, nullable=False)


class ExperimentConfig(Base):
    __tablename__ = "experiment_configs"
    config_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)


class AnalysisVersion(Base):
    __tablename__ = "analysis_versions"
    analysis_version: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False)
