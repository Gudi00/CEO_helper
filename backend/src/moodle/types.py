from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal["single_choice", "multiple_choice"]


class Option(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    value: str
    text: str = Field(min_length=1)


class QuestionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=0)
    attempt_id: str
    cmid: str
    has_images: bool


class NormalizedQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    type: QuestionType
    text: str = Field(min_length=1)
    options: list[Option] = Field(min_length=2)
    metadata: QuestionMetadata
