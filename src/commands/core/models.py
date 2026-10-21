from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, computed_field


class Latency(BaseModel):
    model_config = ConfigDict(frozen=True)

    seconds: float

    @computed_field
    @property
    def measured(self) -> bool:
        return math.isfinite(self.seconds)

    @computed_field
    @property
    def milliseconds(self) -> int | None:
        return round(self.seconds * 1000) if self.measured else None
