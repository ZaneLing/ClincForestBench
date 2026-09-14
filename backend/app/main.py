from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.schemas import (
    BeliefRequest,
    AccountCredentials,
    CreateSessionRequest,
    CreateModelRunRequest,
    EvidenceActionRequest,
    ExportRequest,
    FinalizeRequest,
)
from backend.app.config import Settings
from backend.app.domain.session import Player
from backend.app.domain.evidence import human_readable_response
from backend.app.repositories.memory import InMemoryArenaRepository
from backend.app.services.arena_service import ArenaService
from backend.app.services.auth_service import AuthService
from backend.app.services.case_service import CaseService
from backend.app.services.case_tree_service import CaseTreeService
from backend.app.services.export_service import ExportService
from backend.app.services.forest_analytics_service import ForestAnalyticsService
from backend.app.services.graph_builder import build_case_graph
from backend.app.services.model_arena_service import ModelArenaService
from backend.app.services.review_service import ReviewService
from backend.app.services.state_reducer import replay_session


class AppContainer:
    def __init__(self, case_service: Optional[CaseService] = None) -> None:
        self.settings = Settings()
        self.cases = case_service or CaseService()
        self.case_trees = CaseTreeService(self.cases.root)
        if self.settings.arena_repository in {"postgresql", "sqlite"}:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from backend.app.db.base import Base
            from backend.app.repositories.sqlalchemy import SqlAlchemyArenaRepository
            from backend.app.services.database_seed import seed_benchmark

            engine_options = {"pool_pre_ping": True}
            if self.settings.arena_repository == "sqlite":
                engine_options["connect_args"] = {"check_same_thread": False}
            engine = create_engine(self.settings.database_url, **engine_options)
            Base.metadata.create_all(engine)
            seed_benchmark(engine, self.cases)
            self.repository = SqlAlchemyArenaRepository(
                sessionmaker(bind=engine, expire_on_commit=False)
            )
        else:
            self.repository = InMemoryArenaRepository()
        self.arena = ArenaService(self.cases, self.repository)
        self.auth = AuthService(self.repository)
        self.reviews = ReviewService(self.cases, self.repository)
        self.forest = ForestAnalyticsService(
            self.cases, self.repository, self.case_trees
        )
        self.model_arena = ModelArenaService(
            self.settings,
            self.cases,
            self.arena,
            self.repository,
            self.reviews,
            self.forest,
            self.case_trees,
        )
        self.exports = ExportService(
            self.cases, self.repository, Path(self.settings.export_dir)
        )


def create_app(case_service: Optional[CaseService] = None) -> FastAPI:
    container = AppContainer(case_service)
    application = FastAPI(
        title=container.settings.app_name,
        version="0.1.0",
        description=(
            "Deterministic clinical-decision benchmark. Active-session routes "
            "are intentionally oracle-free; ground-truth comparison unlocks "
            "only after finalization, with unrestricted oracle data confined "
            "to /research."
        ),
    )
    application.state.container = container
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def research_access(x_research_key: str = Header(default="")) -> None:
        if not secrets.compare_digest(
            x_research_key, container.settings.research_api_key
        ):
            raise HTTPException(status_code=403, detail="Research access required")

    def bearer_token(authorization: str = Header(default="")) -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        return token

    def current_username(token: str = Depends(bearer_token)) -> str:
        try:
            return container.auth.account_for_token(token).username
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def assert_session_owner(session_id: str, username: str) -> None:
        try:
            session = container.arena.get_session(session_id)
        except KeyError as exc:
            raise translate_error(exc)
        if session.player.player_id != username:
            raise HTTPException(status_code=403, detail="Session belongs to another account")

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail=str(exc))
        return HTTPException(status_code=409, detail=str(exc))

    @application.get("/health")
    def health():
        return {
            "status": "ok",
            "case_count": len(container.cases.cases),
            "environments": [
                "DDXPlusEnvironment",
                "SyntheaClinicalEnvironment",
                "FHIRClinicalEnvironment",
            ],
        }

    @application.post("/auth/register", status_code=201)
    def register(request: AccountCredentials):
        try:
            account, auth_session = container.auth.register(
                request.username, request.password
            )
            return {
                "account": {"username": account.username},
                "token": auth_session.token,
            }
        except ValueError as exc:
            raise translate_error(exc)

    @application.post("/auth/login")
    def login(request: AccountCredentials):
        try:
            account, auth_session = container.auth.login(
                request.username, request.password
            )
            return {
                "account": {"username": account.username},
                "token": auth_session.token,
            }
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @application.get("/auth/me")
    def auth_me(username: str = Depends(current_username)):
        return {"username": username}

    @application.post("/auth/logout", status_code=204)
    def logout(token: str = Depends(bearer_token)):
        container.auth.logout(token)
        return None

    @application.get("/cases")
    def list_cases():
        # Safe inventory: no pathology, quality score, differential or truth.
        return {
            "case_ids": container.cases.case_ids(),
            "cases": container.cases.case_summaries(),
        }

    @application.get("/cases/{case_id}/catalog")
    def case_catalog(case_id: str):
        # Case-local closed answer vocabulary and action metadata contain no
        # truth values or reference outcome for the selected case.
        try:
            bundle = container.cases.get(case_id)
            return {
                "case": next(
                    item
                    for item in container.cases.case_summaries()
                    if item["case_id"] == case_id
                ),
                "conditions": container.cases.safe_condition_catalog(case_id),
                "action_domains": sorted(
                    {
                        item.clinical_domain
                        for item in container.cases.catalog_for_case(case_id).values()
                        if item.evidence_id != bundle.initial_evidence.evidence_id
                    }
                ),
            }
        except KeyError as exc:
            raise translate_error(exc)

    @application.get("/catalog/conditions")
    def conditions():
        # A closed answer vocabulary is required for structured beliefs and is
        # not a case-specific oracle.
        return {"conditions": container.cases.safe_condition_catalog()}

    @application.get("/catalog/evidences")
    def evidences():
        # Evidence definitions explain public dataset codes and contain no
        # case-specific truth, diagnosis, or oracle probabilities.
        return {
            "evidences": [
                definition.model_dump(mode="json")
                for _, definition in sorted(
                    container.cases.evidence_catalog.items(),
                    key=lambda item: int(item[0].split("_")[1]),
                )
            ]
        }

    @application.post("/sessions", status_code=201)
    def create_session(
        request: CreateSessionRequest,
        username: str = Depends(current_username),
    ):
        case_id = request.case_id or container.cases.case_ids()[0]
        try:
            session = container.arena.create_session(
                case_id=case_id,
                player=Player(
                    player_id=username,
                    player_type="PHYSICIAN",
                    specialty=request.specialty,
                    training_level=request.training_level,
                    years_experience=request.years_experience,
                    site=request.site,
                    country=request.country,
                ),
                arena_mode=request.arena_mode,
                belief_capture_mode=request.belief_capture_mode,
                random_seed=request.random_seed,
            )
            return {
                "session": session.model_dump(mode="json"),
                "state": container.arena.state(session.session_id).public_payload(),
            }
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get("/sessions/{session_id}")
    def get_session(session_id: str, username: str = Depends(current_username)):
        assert_session_owner(session_id, username)
        try:
            return container.arena.get_session(session_id).model_dump(mode="json")
        except KeyError as exc:
            raise translate_error(exc)

    @application.get("/sessions/{session_id}/state")
    def get_state(session_id: str, username: str = Depends(current_username)):
        assert_session_owner(session_id, username)
        try:
            return container.arena.state(session_id).public_payload()
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get("/sessions/{session_id}/available-evidences")
    def available_evidences(
        session_id: str, username: str = Depends(current_username)
    ):
        assert_session_owner(session_id, username)
        try:
            return container.arena.available_actions(session_id).model_dump(mode="json")
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.post("/sessions/{session_id}/actions/evidence")
    def ask_evidence(
        session_id: str,
        request: EvidenceActionRequest,
        username: str = Depends(current_username),
    ):
        assert_session_owner(session_id, username)
        try:
            session = container.arena.get_session(session_id)
            definition = container.cases.catalog_for_case(session.case_id)[
                request.evidence_id
            ]
            result = container.arena.ask_evidence(
                session_id=session_id,
                evidence_id=request.evidence_id,
                client_event_id=request.client_event_id,
                client_timestamp=request.client_timestamp,
                latency_ms=request.latency_ms,
            )
            return {
                "result_type": result.result_type.value,
                "observation": result.observation.model_dump(mode="json") if result.observation else None,
                "answer_text": human_readable_response(
                    result.observation,
                    definition,
                ) if result.observation else None,
                "state_before_hash": result.state_before_hash,
                "state_after_hash": result.state_after_hash,
                "state": result.state.public_payload(),
                "message": result.message,
            }
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.post("/sessions/{session_id}/beliefs", status_code=201)
    def submit_belief(
        session_id: str,
        request: BeliefRequest,
        username: str = Depends(current_username),
    ):
        assert_session_owner(session_id, username)
        try:
            return container.arena.submit_belief(
                session_id, request.belief, request.client_event_id,
                request.client_timestamp,
            ).model_dump(mode="json")
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.post("/sessions/{session_id}/finalize")
    def finalize(
        session_id: str,
        request: FinalizeRequest,
        username: str = Depends(current_username),
    ):
        assert_session_owner(session_id, username)
        try:
            return container.arena.finalize(
                session_id, request.belief, request.client_event_id
            ).model_dump(mode="json")
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get("/sessions/{session_id}/review")
    def completed_review(
        session_id: str, username: str = Depends(current_username)
    ):
        assert_session_owner(session_id, username)
        try:
            review = container.reviews.completed_session_review(session_id)
            review["ground_truth_tree"] = container.case_trees.get(
                review["case_id"]
            )["processed_tree"]
            review["community_final_diagnoses"] = container.forest.case_detail(
                review["case_id"]
            )["final_diagnoses"]
            return review
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get("/sessions/{session_id}/artifact")
    def completed_artifact(
        session_id: str, username: str = Depends(current_username)
    ):
        assert_session_owner(session_id, username)
        try:
            return container.reviews.completed_session_artifact(session_id)
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get("/me/history")
    def personal_history(username: str = Depends(current_username)):
        sessions = [
            item
            for item in container.repository.all_sessions()
            if item.player.player_id == username
            and item.status.value == "COMPLETED"
        ]
        result = []
        for session in sorted(
            sessions, key=lambda item: item.completed_at or item.started_at, reverse=True
        ):
            review = container.reviews.completed_session_review(session.session_id)
            result.append(
                {
                    "session_id": session.session_id,
                    "case_id": session.case_id,
                    "dataset_name": review["dataset_name"],
                    "case_type": review["case_type"],
                    "terminology": review["terminology"],
                    "started_at": session.started_at.isoformat(),
                    "completed_at": session.completed_at.isoformat()
                    if session.completed_at
                    else None,
                    "questions_asked": review["comparison"]["questions_asked"],
                    "predicted_diagnosis": review["comparison"][
                        "predicted_diagnosis"
                    ],
                    "ground_truth_diagnosis": review["comparison"][
                        "ground_truth_diagnosis"
                    ],
                    "predicted_label": review["comparison"]["predicted_label"],
                    "ground_truth_label": review["comparison"][
                        "ground_truth_label"
                    ],
                    "is_correct": review["comparison"]["is_correct"],
                }
            )
        return {"username": username, "sessions": result}

    @application.get("/me/history/{session_id}")
    def personal_history_detail(
        session_id: str,
        username: str = Depends(current_username),
    ):
        assert_session_owner(session_id, username)
        session = container.arena.get_session(session_id)
        try:
            artifact = container.reviews.completed_session_artifact(session_id)
            tree_audit = container.case_trees.get(session.case_id)
            return {
                "session_id": session_id,
                "case_id": session.case_id,
                "ground_truth_tree": tree_audit["processed_tree"],
                "decision_json": artifact,
                "belief_rounds": artifact["belief_history"],
            }
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get(
        "/research/forest/cases", dependencies=[Depends(research_access)]
    )
    def forest_cases():
        return container.forest.case_index()

    @application.get(
        "/research/forest/cases/{case_id}",
        dependencies=[Depends(research_access)],
    )
    def forest_case(case_id: str):
        try:
            return container.forest.case_detail(case_id)
        except KeyError as exc:
            raise translate_error(exc)

    @application.get(
        "/model-arena/status", dependencies=[Depends(research_access)]
    )
    def model_arena_status():
        return container.model_arena.status()

    @application.get(
        "/model-arena/models", dependencies=[Depends(research_access)]
    )
    def model_arena_models():
        try:
            return container.model_arena.models()
        except (ValueError, OSError) as exc:
            raise translate_error(exc)

    @application.get(
        "/model-arena/runs", dependencies=[Depends(research_access)]
    )
    def model_arena_runs(case_id: Optional[str] = None):
        try:
            return container.model_arena.list_runs(case_id)
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.post(
        "/model-arena/runs",
        status_code=201,
        dependencies=[Depends(research_access)],
    )
    def create_model_arena_run(request: CreateModelRunRequest):
        try:
            return container.model_arena.create_run(
                request.model_id, request.case_id, request.max_questions
            )
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get(
        "/model-arena/runs/{run_id}",
        dependencies=[Depends(research_access)],
    )
    def model_arena_run(run_id: str):
        try:
            return container.model_arena.detail(run_id)
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.post(
        "/model-arena/runs/{run_id}/step",
        dependencies=[Depends(research_access)],
    )
    def step_model_arena_run(run_id: str):
        try:
            return container.model_arena.step(run_id)
        except (KeyError, ValueError) as exc:
            raise translate_error(exc)

    @application.get(
        "/admin/accounts", dependencies=[Depends(research_access)]
    )
    def admin_accounts():
        sessions = container.repository.all_sessions()
        return {
            "storage_warning": "Passwords are stored and returned as plaintext for this local prototype only.",
            "accounts": [
                {
                    **account.model_dump(mode="json"),
                    "session_count": sum(
                        item.player.player_id == account.username for item in sessions
                    ),
                    "completed_session_count": sum(
                        item.player.player_id == account.username
                        and item.status.value == "COMPLETED"
                        for item in sessions
                    ),
                }
                for account in container.repository.all_accounts()
            ],
        }

    @application.delete(
        "/admin/accounts/{username}",
        status_code=204,
        dependencies=[Depends(research_access)],
    )
    def delete_unused_account(username: str):
        try:
            container.repository.delete_account(username)
            return None
        except ValueError as exc:
            raise translate_error(exc)

    @application.get(
        "/research/cases/{case_id}", dependencies=[Depends(research_access)]
    )
    def research_case(case_id: str):
        try:
            return container.cases.get(case_id).model_dump(mode="json")
        except KeyError as exc:
            raise translate_error(exc)

    @application.get(
        "/research/case-trees", dependencies=[Depends(research_access)]
    )
    def research_case_tree_manifest():
        return container.case_trees.manifest()

    @application.get(
        "/research/cases/{case_id}/tree-audit",
        dependencies=[Depends(research_access)],
    )
    def research_case_tree(case_id: str):
        try:
            return container.case_trees.get(case_id)
        except KeyError as exc:
            raise translate_error(exc)

    @application.get(
        "/research/cases/{case_id}/graph", dependencies=[Depends(research_access)]
    )
    def research_graph(case_id: str):
        try:
            container.cases.get(case_id)
            sessions = container.repository.all_sessions()
            return build_case_graph(
                case_id,
                sessions,
                {s.session_id: container.repository.events(s.session_id) for s in sessions},
                {s.session_id: container.repository.states(s.session_id) for s in sessions},
            ).model_dump(mode="json")
        except KeyError as exc:
            raise translate_error(exc)

    @application.get(
        "/research/sessions/{session_id}", dependencies=[Depends(research_access)]
    )
    def research_session(session_id: str):
        try:
            session = container.repository.get_session(session_id)
            return {
                "session": session.model_dump(mode="json"),
                "case": container.cases.get(session.case_id).model_dump(mode="json"),
                "events": [e.model_dump(mode="json") for e in container.repository.events(session_id)],
                "states": [s.model_dump(mode="json") for s in container.repository.states(session_id)],
                "beliefs": [b.model_dump(mode="json") for b in container.repository.beliefs(session_id)],
                "replay_final_state": replay_session(session_id, container.cases, container.repository).model_dump(mode="json"),
            }
        except (KeyError, AssertionError) as exc:
            raise translate_error(exc)

    @application.post("/exports", dependencies=[Depends(research_access)])
    def create_export(request: ExportRequest):
        try:
            path = container.exports.export(request.session_id)
            return {"status": "created", "path": str(path)}
        except (KeyError, FileExistsError) as exc:
            raise translate_error(exc)

    return application


app = create_app()
