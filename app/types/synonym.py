from pydantic import BaseModel


class Synonym(BaseModel):
    id: str
    name: str | None = None
