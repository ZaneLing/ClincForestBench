from enum import Enum


class EvidenceDataType(str, Enum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    MULTI_CHOICE = "multi_choice"


class TruthStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    VALUE = "VALUE"
    DEFAULT = "DEFAULT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ActionType(str, Enum):
    ASK_EVIDENCE = "ASK_EVIDENCE"
    SUBMIT_BELIEF = "SUBMIT_BELIEF"
    FINAL_DIAGNOSIS = "FINAL_DIAGNOSIS"
    STOP = "STOP"


class ActionResultType(str, Enum):
    OBSERVATION = "OBSERVATION"
    INVALID_ACTION = "INVALID_ACTION"
    REPEATED_QUERY = "REPEATED_QUERY"
    DEPENDENCY_NOT_MET = "DEPENDENCY_NOT_MET"


class SessionStatus(str, Enum):
    READY = "READY"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class ArenaMode(str, Enum):
    FREE_EXPLORATION = "FREE_EXPLORATION"
    LAYERED_EXPOSURE = "LAYERED_EXPOSURE"
    ANCHOR_STATE = "ANCHOR_STATE"


class BeliefCaptureMode(str, Enum):
    EVERY_STEP = "EVERY_STEP"
    CHECKPOINT = "CHECKPOINT"
    ON_CHANGE = "ON_CHANGE"
    TIER_BASED = "TIER_BASED"


class PlayerType(str, Enum):
    RESEARCHER = "RESEARCHER"
    PHYSICIAN = "PHYSICIAN"
    MODEL = "MODEL"
