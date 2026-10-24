from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Text = Annotated[str, Field(min_length=1, max_length=2000)]


class AgentPersona(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    role_in_group: Text
    vibe_and_style: Text
    expertise: Annotated[list[Annotated[str, Field(min_length=1, max_length=150)]], Field(min_length=1, max_length=12)]
    stance_on_topic: Text
    talkativeness: Annotated[float, Field(ge=0, le=1)]
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class GeneratePersonasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: Annotated[str, Field(min_length=1, max_length=4000)]
    num_agents: Annotated[int, Field(ge=2, le=6, strict=True)]


class PersonaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    personas: list[AgentPersona]


class StartRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: Annotated[str, Field(min_length=1, max_length=4000)]
    max_messages: Annotated[int, Field(ge=1, le=80, strict=True)]
    personas: Annotated[list[AgentPersona], Field(min_length=2, max_length=6)]

    @model_validator(mode="after")
    def unique_personas(self):
        if len({p.id for p in self.personas}) != len(self.personas):
            raise ValueError("Persona IDs must be unique")
        return self


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ReflexDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["NONE", "CASUAL", "EXPERTISE", "DIRECT_QUESTION", "ROASTED_OR_CALLED_OUT"]
    mode: Literal["CASUAL_CHIME", "BANTER", "DEEP_DIVE", "DEFENSIVE_ROAST", "SIGN_OFF"]
    relevance: Annotated[float, Field(ge=0, le=1)]
    reply_to: str | None
