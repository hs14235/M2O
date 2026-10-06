from datetime import date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Kind = Literal["action", "decision", "blocker", "follow_up", "risk"]
Role = Literal["owner", "reviewer", "editor", "viewer"]
Department = Literal["engineering", "hr", "finance"]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
RecordId = Annotated[str, Field(pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class DemoLoadInput(Contract):
    fixture_id: Literal["engineering", "hr", "finance", "no-outcomes"]


LifecycleEmail = Annotated[
    str, StringConstraints(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
]
LifecycleToken = Annotated[str, StringConstraints(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
LifecyclePassword = Annotated[str, StringConstraints(strip_whitespace=False, min_length=12, max_length=256)]


class InvitationInput(Contract):
    email: LifecycleEmail
    role: Role = "editor"


class InvitationTokenInput(Contract):
    token: LifecycleToken


class InvitationAcceptInput(InvitationTokenInput):
    email: LifecycleEmail
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: LifecyclePassword | None = None


class RecoveryInput(InvitationTokenInput):
    email: LifecycleEmail
    password: LifecyclePassword


class RecoveryRequestInput(Contract):
    email: LifecycleEmail


class ReauthenticationInput(Contract):
    password: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=256)]


class WorkspaceErasureInput(ReauthenticationInput):
    confirmation_name: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(strict=True, ge=1)


class AccountErasureInput(ReauthenticationInput):
    confirmation: Literal["DELETE MY ACCOUNT"]


class JiraDestinationInput(Contract):
    resource_id: RecordId
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$")
    expected_version: int = Field(strict=True, ge=1)


class SlackDestinationInput(Contract):
    channel_id: str = Field(pattern=r"^C[A-Z0-9]{7,63}$")
    expected_version: int = Field(strict=True, ge=1)


class SlackPreviewInput(Contract):
    action: Literal["create", "update"] = "create"
    expected_revision: int = Field(strict=True, ge=1)
    versions: dict[RecordId, Annotated[int, Field(strict=True, ge=1)]] = Field(min_length=1, max_length=10)
    expected_destination_version: int = Field(strict=True, ge=1)
    include_evidence: bool = Field(default=False, strict=True)
    confirm_restricted_share: bool = Field(default=False, strict=True)
    target_operation_id: RecordId | None = None


class SlackReconcileInput(Contract):
    message_ts: str = Field(pattern=r"^[0-9]{10,20}\.[0-9]{6}$")


class JiraPreviewInput(Contract):
    item_id: RecordId
    expected_item_version: int = Field(strict=True, ge=1)
    expected_destination_version: int = Field(strict=True, ge=1)
    issue_type_id: str = Field(pattern=r"^[0-9]{1,20}$")
    action: Literal["create", "update"] = "create"
    issue_key: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,39}-[1-9][0-9]{0,19}$")
    include_evidence: bool = False
    fields: dict[
        str,
        Annotated[str, Field(strict=True, max_length=16000)]
        | Annotated[int, Field(strict=True)]
        | Annotated[float, Field(strict=True)]
        | list[Annotated[str, Field(strict=True, max_length=255)]],
    ] = Field(default_factory=dict, max_length=50)


class LoginInput(Contract):
    email: str = Field(min_length=3, max_length=254)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=256)


class PlanInput(Contract):
    expected_item_version: int = Field(strict=True, ge=1)
    planned_on: date
    priority: int = Field(default=2, strict=True, ge=1, le=3)


class PlanPatch(PlanInput):
    expected_version: int = Field(strict=True, ge=1)
    state: Literal["planned", "in_progress", "blocked", "done"]


class WorkspaceInput(Contract):
    name: str = Field(min_length=1, max_length=120)
    department: Department = "engineering"


class MemberInput(Contract):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=120)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=12, max_length=256)
    role: Role = "editor"


class ParticipantInput(Contract):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=160)
    aliases: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )
    github_login: str | None = Field(default=None, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
    linkedin_url: str | None = Field(default=None, max_length=250)
    linked_user_id: RecordId | None = None

    @field_validator("linkedin_url")
    @classmethod
    def linkedin_profile_url(cls, value):
        if value is None:
            return None
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"www.linkedin.com", "linkedin.com"}
            or not parsed.path.startswith("/in/")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use an HTTPS LinkedIn /in/ profile URL without query parameters")
        return value


class IndexInput(Contract):
    meeting_id: Identifier
    title: str = Field(default="", max_length=200)
    transcript: str = Field(min_length=1, max_length=1_000_000)
    visibility: Literal["workspace", "restricted"] = "workspace"
    occurred_on: date | None = None
    timezone: str = Field(default="UTC", max_length=60)
    expected_version: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use an IANA timezone") from exc
        return value


class MeetingPatch(Contract):
    expected_version: int = Field(ge=1, strict=True)
    title: str = Field(min_length=1, max_length=200)


class ItemCandidate(Contract):
    kind: Kind
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4000)
    labels: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list, max_length=10
    )
    assignee_hint: str | None = Field(default=None, max_length=120)
    due_hint: str | None = Field(default=None, max_length=120)
    source_ids: list[RecordId] = Field(min_length=1, max_length=8)
    confidence: float = Field(default=0.6, ge=0, le=1)


class ModelOutput(Contract):
    tasks: list[ItemCandidate] = Field(max_length=40)


class ItemPatch(Contract):
    expected_version: int = Field(ge=1, strict=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=4000)
    kind: Kind | None = None
    labels: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = Field(
        default=None, max_length=10
    )
    status: Literal["draft", "approved", "done", "dismissed"] | None = None
    owner_id: RecordId | None = None
    due_date: date | None = None
    due_hint: str | None = Field(default=None, max_length=120)


class MentionConfirmation(Contract):
    participant_id: RecordId


class PreviewInput(Contract):
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=180)
    task_ids: list[RecordId] = Field(min_length=1, max_length=30)
    include_evidence: bool = False
    expected_versions: dict[RecordId, Annotated[int, Field(strict=True, ge=1)]] | None = Field(
        default=None, max_length=30
    )
    expected_destination_version: int | None = Field(default=None, strict=True, ge=1)
    external_disclosure_confirmed: bool = Field(default=False, strict=True)


class ApprovalInput(Contract):
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class JiraApprovalInput(ApprovalInput):
    retry_rejected: bool = Field(default=False, strict=True)


class SlackApprovalInput(ApprovalInput):
    retry_rejected: bool = Field(default=False, strict=True)


class GitHubBindingInput(Contract):
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=180)
    expected_version: int = Field(strict=True, ge=0)


class LinkedInDraftInput(Contract):
    kind: Literal["post", "outreach"]
    text: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=3000)
    versions: dict[RecordId, Annotated[int, Field(strict=True, ge=1)]] = Field(min_length=1, max_length=30)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Draft text must contain readable content")
        return value


class LinkedInDraftPatch(LinkedInDraftInput):
    expected_version: int = Field(strict=True, ge=1)


class LinkedInPreviewInput(Contract):
    draft_id: RecordId
    expected_draft_version: int = Field(strict=True, ge=1)
    disclosure_confirmed: bool = Field(default=False, strict=True)


class SlackLinkInput(Contract):
    connection_id: RecordId


class SlackLinkConfirmation(Contract):
    challenge_id: RecordId
    slack_user_id: str = Field(pattern=r"^[UW][A-Z0-9]{7,63}$")


class ExportInput(Contract):
    format: Literal["json", "markdown"]
    expected_revision: int = Field(ge=1, strict=True)
    versions: dict[RecordId, Annotated[int, Field(ge=1, strict=True)]] = Field(min_length=1, max_length=30)
    include_evidence: bool = False


class SearchInput(Contract):
    q: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20, strict=True)


class RoleInput(Contract):
    role: Role
