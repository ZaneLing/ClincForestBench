from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.services.encounter_catalog import EncounterCatalog, bilingual
from backend.app.services.encounter_service import EncounterService


class EventRequest(BaseModel):
    client_event_id: str = Field(min_length=1, max_length=128)


class VisitRequest(EventRequest):
    case_id: str = Field(min_length=1, max_length=128)
    is_simulation: bool = False


class ActionRequest(EventRequest):
    item_id: str = Field(min_length=1, max_length=256)
    reason_id: str = Field(min_length=1, max_length=64)
    reason_text: str = Field(default="", max_length=2000)
    hypothesis: str = Field(default="", max_length=1000)


class DiagnosisRequest(EventRequest):
    diagnoses: list[str] = Field(min_length=1, max_length=30)


class PrescriptionRequest(EventRequest):
    text: str = Field(min_length=1, max_length=10000)


def register_encounter_routes(app, container, current_username, research_access):
    @lru_cache(maxsize=1)
    def service():
        database = ":memory:" if container.settings.arena_repository == "memory" else container.cases.root / "data/encounters.db"
        return EncounterService(EncounterCatalog(container.cases), database)

    def invoke(call):
        try:
            return call()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/encounters/catalog")
    def catalog(username: str = Depends(current_username)):
        svc = service()
        conditions = {key: value.get("condition_name", key) for key, value in container.cases.all_condition_catalog.items()
                      if value.get("kind", "DIAGNOSIS") == "DIAGNOSIS"}
        return {"items": list(svc.catalog.items.values()),
                "cases": [{"case_id": v["case_id"], "dataset": v["dataset"], "track_type": v["track_type"]} for v in svc.catalog.visits.values()],
                "conditions": [{"id": key, "label": bilingual(value)} for key, value in conditions.items()]}

    @app.get("/encounters/reasons/{item_id}")
    def reasons(item_id: str, username: str = Depends(current_username)):
        return invoke(lambda: service().catalog.reasons(item_id))

    @app.post("/encounters", status_code=201)
    def create(request: VisitRequest, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().create(request.case_id, username, request.client_event_id, is_simulation=request.is_simulation), lang))

    @app.get("/encounters/history")
    def history(username: str = Depends(current_username)):
        return service().history(username)

    @app.get("/encounters/{encounter_id}")
    def detail(encounter_id: str, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().get(encounter_id, username), lang))

    @app.get("/encounters/{encounter_id}/export")
    def export(encounter_id: str, username: str = Depends(current_username)):
        return invoke(lambda: service().get(encounter_id, username))

    @app.post("/encounters/{encounter_id}/actions")
    def act(encounter_id: str, request: ActionRequest, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().act(encounter_id, username, request), lang))

    @app.post("/encounters/{encounter_id}/diagnoses")
    def diagnose(encounter_id: str, request: DiagnosisRequest, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().diagnose(encounter_id, username, request), lang))

    @app.post("/encounters/{encounter_id}/prescription")
    def prescribe(encounter_id: str, request: PrescriptionRequest, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().prescribe(encounter_id, username, request), lang))

    @app.post("/encounters/{encounter_id}/finish")
    def finish(encounter_id: str, request: EventRequest, lang: str = "en", username: str = Depends(current_username)):
        return invoke(lambda: service().view(service().finish(encounter_id, username, request), lang))

    @app.get("/research/encounter-mapping", dependencies=[Depends(research_access)])
    def mapping():
        return service().catalog.report()

    @app.get("/research/encounter-cases", dependencies=[Depends(research_access)])
    def inspection_catalog():
        catalog = service().catalog
        return {"items": list(catalog.items.values()),
                "cases": [{"case_id": cid, "dataset": visit["dataset"],
                           "source": "evidence"}
                          for cid, visit in catalog.visits.items()]}

    @app.get("/research/encounter-cases/{case_id}", dependencies=[Depends(research_access)])
    def inspect_case(case_id: str, lang: str = "en"):
        return invoke(lambda: service().catalog.inspection(case_id, lang))

    @app.get("/research/classic-simulation-forest/cases")
    def classic_simulation_index():
        return invoke(lambda: service().classic_simulation_index())

    @app.get("/research/classic-simulation-forest/cases/{case_id}")
    def classic_simulation_case(case_id: str, lang: str = "en"):
        # Only source-derived labels/observations are localized. Authored demo
        # diagnoses stay in their original form in the read-only projection.
        return invoke(lambda: service().classic_simulation_detail(case_id, lang))

    # Read-only aggregate forest is intentionally viewable without a research key.
    # Individual visits/exports and source inspection remain protected.
    @app.get("/research/encounter-forest")
    def forest(case_id: str = "", simulation: bool = False, lang: str = "en"):
        return invoke(lambda: service().forest(case_id or None, simulation=simulation, locale=lang))
