from pydantic import BaseModel


class Synonym(BaseModel):
    name: str
    id: str
