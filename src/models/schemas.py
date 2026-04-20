from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import AnalysisMode, TaskStatus


# ── Requests ──

class TelegramAuthRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    init_data: str | None = None


class ApiClientCreateRequest(BaseModel):
    name: str
    rate_limit_daily: int = 1000


class ApiClientCreatedResponse(BaseModel):
    api_key: str
    user_id: uuid.UUID
    client_id: uuid.UUID


# ── Task ──

class TaskResponse(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus
    mode: AnalysisMode
    created_at: datetime
    completed_at: datetime | None = None
    result: dict | None = None
    share_card_url: str | None = None
    error_message: str | None = None


class TaskCreated(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus = TaskStatus.PENDING
    estimated_seconds: int = 15


class TaskHistoryItem(BaseModel):
    task_id: uuid.UUID
    mode: str
    style: str = ""
    completed_at: datetime | None = None
    input_image_url: str = ""
    generated_image_url: str = ""
    score_before: float | None = None
    score_after: float | None = None
    perception_scores: dict | None = None
    purged: bool = False


class TaskHistoryResponse(BaseModel):
    items: list[TaskHistoryItem]
    total_count: int


# ── Perception Scores (unified across all modes) ──

class PerceptionScores(BaseModel):
    warmth: float = Field(ge=0, le=10)
    presence: float = Field(ge=0, le=10)
    appeal: float = Field(ge=0, le=10)
    authenticity: float = Field(ge=0, le=10, default=9.0)


class PerceptionInsight(BaseModel):
    parameter: str
    current_level: str
    suggestion: str
    controllable_by: str


# ── Rating Result ──

class PerceptionData(BaseModel):
    trust: float = Field(ge=0, le=10)
    attractiveness: float = Field(ge=0, le=10)
    emotional_expression: str


class RatingResult(BaseModel):
    score: float = Field(ge=0, le=10)
    perception: PerceptionData
    perception_scores: PerceptionScores | None = None
    perception_insights: list[PerceptionInsight] = Field(default_factory=list)
    insights: list[str]
    recommendations: list[str]


# ── Shared ──

class Variant(BaseModel):
    type: str
    image_url: str | None = None
    explanation: str


# ── Dating Result ──

class DatingResult(BaseModel):
    first_impression: str
    dating_score: float = Field(ge=0, le=10)
    strengths: list[str]
    weaknesses: list[str] = Field(default_factory=list)
    enhancement_opportunities: list[str] = Field(default_factory=list)
    variants: list[Variant] = []
    perception_scores: PerceptionScores | None = None
    perception_insights: list[PerceptionInsight] = Field(default_factory=list)


# ── CV Result ──

class CVResult(BaseModel):
    profession: str
    trust: float = Field(ge=0, le=10)
    competence: float = Field(ge=0, le=10)
    hireability: float = Field(ge=0, le=10)
    analysis: str
    image_url: str | None = None
    perception_scores: PerceptionScores | None = None
    perception_insights: list[PerceptionInsight] = Field(default_factory=list)


# ── Social Result ──

class SocialResult(BaseModel):
    first_impression: str
    social_score: float = Field(ge=0, le=10)
    strengths: list[str]
    weaknesses: list[str] = Field(default_factory=list)
    enhancement_opportunities: list[str] = Field(default_factory=list)
    variants: list[Variant] = []
    perception_scores: PerceptionScores | None = None
    perception_insights: list[PerceptionInsight] = Field(default_factory=list)


# ── Share ──

class ShareResponse(BaseModel):
    image_url: str
    caption: str
    deep_link: str


# ── User ──

class UserUsage(BaseModel):
    daily_limit: int
    used: int
    remaining: int
    is_premium: bool


class UserResponse(BaseModel):
    user_id: uuid.UUID
    telegram_id: int | None = None
    username: str | None = None
    usage: UserUsage


# ── Multi-channel Auth ──

class ChannelAuthResponse(BaseModel):
    """Returned by all /auth/* endpoints for non-Telegram channels."""
    session_token: str
    user_id: uuid.UUID
    usage: UserUsage


class OKAuthRequest(BaseModel):
    logged_user_id: str
    session_key: str
    auth_sig: str
    application_key: str = ""


class VKAuthRequest(BaseModel):
    launch_params: str


class WebAuthRequest(BaseModel):
    device_id: str


class OAuthInitRequest(BaseModel):
    device_id: str = ""
    link_code: str = ""


class OAuthInitResponse(BaseModel):
    authorize_url: str


# ── Identity Linking ──

class LinkedIdentity(BaseModel):
    provider: str
    external_id: str
    profile_data: dict | None = None
    created_at: datetime | None = None

class UserIdentitiesResponse(BaseModel):
    user_id: uuid.UUID
    identities: list[LinkedIdentity] = Field(default_factory=list)


# ── Universal Link Token ──

class LinkTokenResponse(BaseModel):
    code: str
    ttl: int
    link_url: str

class ClaimLinkRequest(BaseModel):
    code: str
    provider: str
    external_id: str
    profile_data: dict | None = None

class ClaimLinkResponse(BaseModel):
    session_token: str
    user_id: uuid.UUID
    usage: UserUsage
    identities: list[LinkedIdentity] = Field(default_factory=list)


# ── Phone Auth (OTP) ──

class PhoneOTPRequestBody(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)

class PhoneOTPVerifyBody(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    code: str = Field(..., min_length=4, max_length=6)
    link_code: str = ""


# ── Pre-Analysis ──

class InputQualityIssuePublic(BaseModel):
    code: str
    severity: str
    message: str
    suggestion: str


class InputQualityPublic(BaseModel):
    can_generate: bool
    soft_warnings: list[InputQualityIssuePublic] = Field(default_factory=list)
    blocking_issues: list[InputQualityIssuePublic] = Field(default_factory=list)


class PreAnalysisResponse(BaseModel):
    pre_analysis_id: str
    mode: AnalysisMode
    first_impression: str = ""
    score: float
    perception_scores: dict
    perception_insights: list[dict] = Field(default_factory=list)
    enhancement_opportunities: list[str] = Field(default_factory=list)
    input_quality: InputQualityPublic | None = None
