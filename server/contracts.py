from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MealSlot(Input):
    meal_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    time: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


class CatProfile(Input):
    name: str = Field(min_length=1, max_length=80)
    meals_per_day: int | None = Field(default=None, strict=True, ge=1, le=12)
    meal_schedule: list[MealSlot] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def consistent_plan(self):
        slots = self.meal_schedule or []
        if len({slot.meal_id for slot in slots}) != len(slots):
            raise ValueError("Meal IDs must be unique")
        if slots and self.meals_per_day is not None and len(slots) != self.meals_per_day:
            raise ValueError("meals_per_day must match the number of meal slots")
        return self


class AddCat(CatProfile):
    idempotency_key: str = Field(min_length=8, max_length=128)


class UpdateCat(Input):
    cat_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    meals_per_day: int | None = Field(default=None, strict=True, ge=1, le=12)
    meal_schedule: list[MealSlot] | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def has_changes(self):
        if self.name is None and self.meals_per_day is None and self.meal_schedule is None:
            raise ValueError("Supply a profile change")
        return self


def profile_changes(args, existing=None):
    from server.backend import DomainError
    values = {key: value for key, value in (existing or {}).items() if key != "cat_id"}
    values.update({key: args[key] for key in ("name", "meals_per_day", "meal_schedule") if key in args and args[key] is not None})
    try:
        return CatProfile.model_validate(values).model_dump(mode="json", exclude_none=True)
    except ValueError:
        raise DomainError("invalid_profile", "Profile or meal schedule is invalid") from None


class Event(Input):
    cat_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    event_id: str | None = None
    occurred_at: datetime | None = None
    reporter: str | None = Field(default=None, max_length=80)
    performed_by: str | None = Field(default=None, min_length=1, max_length=80)
    recorded_by: str | None = Field(default=None, min_length=1, max_length=80)
    details: dict = Field(default_factory=dict)
    source: Literal["user", "seed"] = "user"

    @field_validator("occurred_at", "event_id", mode="before")
    @classmethod
    def empty_optional_fields(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


    @model_validator(mode="after")
    def details_match_type(self):
        from server.event_details import validate
        validate(self.event_type, self.details)
        return self

    @classmethod
    def model_json_schema(cls, **kwargs):
        from server.event_details import DETAIL_MODELS
        schema = super().model_json_schema(**kwargs)
        schema['properties']['occurred_at']['anyOf'].append({'type': 'string', 'pattern': r'^\s*$'})
        schema['allOf'] = [
            {'if': {'properties': {'event_type': {'const': kind}}, 'required': ['event_type']},
             'then': {'properties': {'details': DETAIL_MODELS[kind].model_json_schema()}}}
            for kind in schema['properties']['event_type']['enum']]
        return schema


class HealthEvent(Event):
    event_type: Literal["vomiting", "appetite", "litter", "energy", "weight"]


class CareEvent(Event):
    event_type: Literal["feeding", "water", "litter_cleaning", "medication", "food_change"]


class Query(Input):
    cat_id: str = Field(min_length=1, max_length=128)


class WindowQuery(Query):
    days: int = Field(default=7, ge=1, le=90)


MODELS = dict(list_cats=Input, add_cat=AddCat, update_cat=UpdateCat, log_health_event=HealthEvent,
              log_care_event=CareEvent, get_today=Query, get_patterns=WindowQuery,
              get_vet_summary=WindowQuery)
DESCRIPTIONS = {
    "list_cats": "List cats in the authenticated household. Select by cat_id; ask which cat when names are ambiguous.",
    "add_cat": "Create a cat profile. Reuse the idempotency key on retries.",
    "update_cat": "Update a cat profile and optional feeding plan. Meal slots have unique meal_id, label, and optional household-local HH:MM time. meals_per_day alone does not identify meals.",
    "log_health_event": "Record a health observation, never a diagnosis. For follow-up answers pass the existing event_id and a new idempotency key. Unknown details must remain unknown. Read red_flags before ordinary follow_up questions.",
    "log_care_event": "Record care such as feeding or litter cleaning. For planned feeding supply details.meal_id from the cat profile. Multiple meals are normal; care_notes only asks to confirm another record for the same meal, and never blocks saving. Use event_id to supplement an existing record; reuse the idempotency key only for retries.",
    "get_today": "Read care and health records for today in the configured household timezone. Feeding summary reports every feeding with time, reporter, food and amount. A same-meal care note asks for confirmation; counts alone never establish overfeeding.",
    "get_patterns": "Read deterministic patterns with evidence and sample sizes. Never invent associations when data or the rules backend is unavailable.",
    "get_vet_summary": "Read a factual event timeline for a veterinarian; this does not provide a diagnosis.",
}


def envelope(**values):
    return {"schema_version": "1.0", "event_id": None, "logged": False,
            "follow_up": [], "red_flags": [], "patterns": [],
            "notification_status": {"state": "disabled"}, **values}
