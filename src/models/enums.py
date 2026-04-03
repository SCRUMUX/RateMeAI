import enum


class AnalysisMode(str, enum.Enum):
    RATING = "rating"
    DATING = "dating"
    CV = "cv"
    EMOJI = "emoji"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
