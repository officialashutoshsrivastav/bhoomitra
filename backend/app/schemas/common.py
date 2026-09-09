from typing import Annotated, Any, Dict, Generic, List, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: List[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = max(1, (total + page_size - 1) // page_size) if page_size else 1
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class PageParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
        page_size: Annotated[int, Query(ge=1, le=200, description="Items per page")] = 20,
        sort: Annotated[Optional[str], Query(description="Sort field, prefix with '-' for descending")] = None,
    ):
        self.page = page
        self.page_size = page_size
        self.sort = sort

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def sort_field(self) -> tuple[Optional[str], bool]:
        if not self.sort:
            return None, True
        if self.sort.startswith("-"):
            return self.sort[1:], True
        return self.sort, False


class Message(BaseModel):
    message: str
    detail: Optional[Dict[str, Any]] = None


class IDResponse(BaseModel):
    id: str


class DemoLabel(BaseModel):
    is_demo: bool = Field(False, description="True when the record is Demo / Synthetic Data, not an official statistic")


DEMO_NOTICE = "Demo / Synthetic Data — not an official government statistic"
