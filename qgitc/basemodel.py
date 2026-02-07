# -*- coding: utf-8 -*-

from typing import (
    Any,
    Dict,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

# ==================== Lightweight BaseModel Implementation ====================
# A minimal implementation inspired by Pydantic for parameter validation
# and JSON schema generation.


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class Field:
    """Field descriptor for parameter definition."""

    def __init__(
        self,
        default=None,
        *,
        description: str = "",
        ge: Optional[int] = None,
        le: Optional[int] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ):
        self.default = default
        self.description = description
        self.ge = ge  # greater than or equal
        self.le = le  # less than or equal
        self.min_length = min_length
        self.max_length = max_length
        self.required = default is ...


class BaseModel:
    """Lightweight base model for parameter validation and schema generation."""

    def __init__(self, **kwargs):
        type_hints = get_type_hints(self.__class__)

        # Get field definitions from class attributes
        fields = {}
        for name, value in self.__class__.__dict__.items():
            if isinstance(value, Field):
                fields[name] = value

        # Validate and set attributes
        for name, field_type in type_hints.items():
            field_def: Field = fields.get(name, Field(None))
            value = kwargs.get(name)

            # Handle required fields
            if value is None:
                if field_def.required:
                    raise ValidationError(f"Field '{name}' is required")
                # Use default value - no need to validate, trust it's correct
                setattr(self, name, field_def.default)
                continue

            # Validate type and constraints only for provided values
            value = self._validate_field(name, value, field_type, field_def)
            setattr(self, name, value)

    def _validate_field(self, name: str, value: Any, field_type: Type, field_def: Field) -> Any:
        """Validate a field value."""
        origin = get_origin(field_type)

        # Handle Optional types (Optional[X] is actually Union[X, None])
        # get_origin returns typing.Union, not type(Optional)
        if origin is Union:
            args = get_args(field_type)
            # Filter out NoneType to get the actual type
            non_none_args = [arg for arg in args if arg is not type(None)]
            if non_none_args:
                field_type = non_none_args[0]
                origin = get_origin(field_type)
            # If value is None and Optional, return None (already handled above)
            if value is None:
                return None

        # Validate int
        if field_type == int or (origin is None and field_type is int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValidationError(f"Field '{name}' must be an integer")

            if field_def.ge is not None and value < field_def.ge:
                raise ValidationError(
                    f"Field '{name}' must be >= {field_def.ge}")
            if field_def.le is not None and value > field_def.le:
                raise ValidationError(
                    f"Field '{name}' must be <= {field_def.le}")

        # Validate str
        elif field_type == str or (origin is None and field_type is str):
            if not isinstance(value, str):
                raise ValidationError(f"Field '{name}' must be a string")

        # Validate bool
        elif field_type == bool or (origin is None and field_type is bool):
            if not isinstance(value, bool):
                raise ValidationError(f"Field '{name}' must be a boolean")

        # Validate List
        elif origin is list:
            if not isinstance(value, list):
                raise ValidationError(f"Field '{name}' must be a list")

            if field_def.min_length is not None and len(value) < field_def.min_length:
                raise ValidationError(
                    f"Field '{name}' must have at least {field_def.min_length} items")
            if field_def.max_length is not None and len(value) > field_def.max_length:
                raise ValidationError(
                    f"Field '{name}' must have at most {field_def.max_length} items")

            # Validate list items
            args = get_args(field_type)
            if args:
                item_type = args[0]
                value = [self._validate_simple_type(
                    f"{name}[{i}]", item, item_type) for i, item in enumerate(value)]

        return value

    def _validate_simple_type(self, name: str, value: Any, expected_type: Type) -> Any:
        """Validate simple types in lists."""
        if expected_type == str and not isinstance(value, str):
            raise ValidationError(f"Field '{name}' must be a string")
        elif expected_type == int:
            try:
                return int(value)
            except (TypeError, ValueError):
                raise ValidationError(f"Field '{name}' must be an integer")
        elif expected_type == bool and not isinstance(value, bool):
            raise ValidationError(f"Field '{name}' must be a boolean")
        return value

    @classmethod
    def model_json_schema(cls) -> Dict[str, Any]:
        """Generate JSON Schema for the model."""
        type_hints = get_type_hints(cls)
        properties = {}
        required = []

        # Get field definitions
        fields = {}
        for name, value in cls.__dict__.items():
            if isinstance(value, Field):
                fields[name] = value

        for name, field_type in type_hints.items():
            field_def: Field = fields.get(name, Field(None))
            prop = BaseModel._type_to_json_schema(field_type, field_def)

            if field_def.description:
                prop["description"] = field_def.description

            properties[name] = prop

            if field_def.required:
                required.append(name)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    @staticmethod
    def _type_to_json_schema(field_type: Type, field_def: Field) -> Dict[str, Any]:
        """Convert Python type to JSON Schema type."""
        origin = get_origin(field_type)

        # Handle Optional (Union[X, None])
        if origin is Union:
            args = get_args(field_type)
            # Filter out NoneType to get the actual type
            non_none_args = [arg for arg in args if arg is not type(None)]
            if non_none_args:
                field_type = non_none_args[0]
                origin = get_origin(field_type)

        # Basic types
        if field_type == str or (origin is None and field_type is str):
            return {"type": "string"}

        elif field_type == int or (origin is None and field_type is int):
            schema = {"type": "integer"}
            if field_def.ge is not None:
                schema["minimum"] = field_def.ge
            if field_def.le is not None:
                schema["maximum"] = field_def.le
            return schema

        elif field_type == bool or (origin is None and field_type is bool):
            return {"type": "boolean"}

        elif origin is list:
            args = get_args(field_type)
            item_schema = {"type": "string"}  # default
            if args:
                item_type = args[0]
                if item_type == str:
                    item_schema = {"type": "string"}
                elif item_type == int:
                    item_schema = {"type": "integer"}
                elif item_type == bool:
                    item_schema = {"type": "boolean"}

            schema = {"type": "array", "items": item_schema}
            if field_def.min_length is not None:
                schema["minItems"] = field_def.min_length
            if field_def.max_length is not None:
                schema["maxItems"] = field_def.max_length
            return schema

        return {"type": "string"}  # fallback
