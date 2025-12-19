from pydantic import BaseModel


class Localisation(BaseModel):
    statuses: dict[str, list[str]]
    states: dict[str, str]
    ui: dict[str, str]
    errors: dict[str, str]
    commands: dict[str, str | list[str]]

    def get(self, key: str, default: str | list[str]) -> str | list[str]:
        merged = {}

        for field in self.__pydantic_fields__:
            merged.update(getattr(self, field))

        return merged.get(key, default)