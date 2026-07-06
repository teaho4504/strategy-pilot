from pydantic import BaseModel


class WatchTicker(BaseModel):
    code: str
    name: str
    price: int
    changePct: float
