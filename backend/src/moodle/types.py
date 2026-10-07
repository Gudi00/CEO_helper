from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal["single_choice", "multiple_choice"]


class Option(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    value: str = Field(max_length=256)
    text: str = Field(min_length=1, max_length=2000)


class QuestionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=0)
    attempt_id: str = Field(max_length=64)
    cmid: str = Field(max_length=64)
    has_images: bool


class QuestionImage(BaseModel):
    """A picture from the question, fetched by the extension from the quiz
    page. Raster formats only — SVG can carry scripts and text payloads.
    """

    model_config = ConfigDict(frozen=True)

    mime: Literal["image/png", "image/jpeg", "image/webp"]
    # ~1 MB of binary data as base64.
    data: str = Field(min_length=1, max_length=1_400_000, pattern=r"^[A-Za-z0-9+/]+=*$")


class NormalizedQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(max_length=128)
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    type: QuestionType
    text: str = Field(min_length=1, max_length=8000)
    options: list[Option] = Field(min_length=2, max_length=20)
    metadata: QuestionMetadata
    # Not part of the hash: answers to questions with images are never cached.
    images: list[QuestionImage] = Field(default_factory=list, max_length=4)
