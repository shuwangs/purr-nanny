"""Shared event-specific validation and discoverable JSON schemas."""
from typing import Literal
from pydantic import ConfigDict, Field, StrictBool, StrictStr, create_model
from typing import Annotated

Positive = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Text = Annotated[StrictStr, Field(max_length=500)]
FIELDS = {
    'vomiting': dict(blood=StrictBool, lethargy=StrictBool, after_meal=StrictBool),
    'appetite': dict(eating=Literal['normal', 'less', 'nothing'], duration_hours=Nonnegative),
    'litter': dict(straining=StrictBool, urine_output=Literal['normal', 'little', 'none']),
    'energy': dict(level=Literal['normal', 'reduced', 'severely_reduced']),
    'weight': dict(weight_kg=Positive),
    'feeding': dict(food=Text, amount=Text, meal_id=Annotated[StrictStr, Field(min_length=1, max_length=80)]),
    'water': dict(amount=Text),
    'litter_cleaning': dict(notes=Text),
    'medication': dict(name=Text, dose=Text),
    'food_change': dict(food=Text, previous_food=Text),
}
DETAIL_MODELS = {name: create_model(name.title()+'Details', __config__=ConfigDict(extra='forbid'),
    **{key: (value | None, None) for key, value in fields.items()}) for name, fields in FIELDS.items()}


def validate(event_type, details):
    if event_type not in DETAIL_MODELS:
        raise ValueError('Unknown event type')
    DETAIL_MODELS[event_type].model_validate(details)
