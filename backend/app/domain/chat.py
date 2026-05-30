"""Chat API request/response types."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def message_must_not_be_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return v


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
