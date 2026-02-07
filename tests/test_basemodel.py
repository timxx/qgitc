# -*- coding: utf-8 -*-

import unittest
from typing import List, Optional

from qgitc.basemodel import BaseModel, Field, ValidationError


class TestField(unittest.TestCase):
    """Test Field descriptor."""

    def test_field_default(self):
        """Test field with default value."""
        field = Field(default=42, description="Test field")
        self.assertEqual(field.default, 42)
        self.assertEqual(field.description, "Test field")
        self.assertFalse(field.required)

    def test_field_required(self):
        """Test required field (default is ...)."""
        field = Field(default=..., description="Required field")
        self.assertTrue(field.required)

    def test_field_constraints(self):
        """Test field constraints."""
        field = Field(default=10, ge=1, le=100,
                      description="Constrained field")
        self.assertEqual(field.ge, 1)
        self.assertEqual(field.le, 100)

    def test_field_list_constraints(self):
        """Test field list length constraints."""
        field = Field(default=[], min_length=1, max_length=10)
        self.assertEqual(field.min_length, 1)
        self.assertEqual(field.max_length, 10)


class TestBaseModelBasics(unittest.TestCase):
    """Test basic BaseModel functionality."""

    def test_simple_model(self):
        """Test model with simple types."""
        class SimpleModel(BaseModel):
            name: str = Field(..., description="Name field")
            age: int = Field(..., description="Age field")
            active: bool = Field(True, description="Active flag")

        model = SimpleModel(name="Alice", age=30)
        self.assertEqual(model.name, "Alice")
        self.assertEqual(model.age, 30)
        self.assertTrue(model.active)

    def test_optional_fields(self):
        """Test model with Optional fields."""
        class OptionalModel(BaseModel):
            name: str = Field(..., description="Required name")
            nickname: Optional[str] = Field(
                None, description="Optional nickname")
            age: Optional[int] = Field(None, description="Optional age")

        model = OptionalModel(name="Bob")
        self.assertEqual(model.name, "Bob")
        self.assertIsNone(model.nickname)
        self.assertIsNone(model.age)

    def test_default_values(self):
        """Test that default values are used and not re-validated."""
        class DefaultModel(BaseModel):
            count: int = Field(10, ge=1, le=100)
            enabled: bool = Field(True)
            tags: List[str] = Field([])

        model = DefaultModel()
        self.assertEqual(model.count, 10)
        self.assertTrue(model.enabled)
        self.assertEqual(model.tags, [])

    def test_required_field_missing(self):
        """Test that missing required field raises ValidationError."""
        class RequiredModel(BaseModel):
            name: str = Field(..., description="Required name")

        with self.assertRaises(ValidationError) as ctx:
            RequiredModel()
        self.assertIn("required", str(ctx.exception).lower())


class TestBaseModelValidation(unittest.TestCase):
    """Test BaseModel validation."""

    def test_int_from_string(self):
        """Test that string numbers are converted to int (LLM often sends strings)."""
        class IntModel(BaseModel):
            count: int = Field(..., description="Count")
            optional_count: Optional[int] = Field(
                None, description="Optional count")

        # String to int conversion
        model = IntModel(count="42", optional_count="10")
        self.assertEqual(model.count, 42)
        self.assertIsInstance(model.count, int)
        self.assertEqual(model.optional_count, 10)
        self.assertIsInstance(model.optional_count, int)

    def test_int_constraints(self):
        """Test integer constraint validation."""
        class ConstrainedModel(BaseModel):
            value: int = Field(..., ge=1, le=100,
                               description="Value between 1 and 100")

        # Valid value
        model = ConstrainedModel(value=50)
        self.assertEqual(model.value, 50)

        # Value too small
        with self.assertRaises(ValidationError) as ctx:
            ConstrainedModel(value=0)
        self.assertIn(">=", str(ctx.exception))

        # Value too large
        with self.assertRaises(ValidationError) as ctx:
            ConstrainedModel(value=101)
        self.assertIn("<=", str(ctx.exception))

    def test_bool_validation(self):
        """Test boolean validation."""
        class BoolModel(BaseModel):
            enabled: bool = Field(True, description="Enabled flag")

        model = BoolModel(enabled=False)
        self.assertFalse(model.enabled)

        # Invalid bool type
        with self.assertRaises(ValidationError) as ctx:
            BoolModel(enabled="not a bool")
        self.assertIn("boolean", str(ctx.exception).lower())

    def test_string_validation(self):
        """Test string validation."""
        class StringModel(BaseModel):
            name: str = Field(..., description="Name")

        model = StringModel(name="Alice")
        self.assertEqual(model.name, "Alice")

        # Invalid string type
        with self.assertRaises(ValidationError) as ctx:
            StringModel(name=123)
        self.assertIn("string", str(ctx.exception).lower())

    def test_list_validation(self):
        """Test list validation."""
        class ListModel(BaseModel):
            tags: List[str] = Field(..., min_length=1,
                                    max_length=5, description="Tags")

        # Valid list
        model = ListModel(tags=["tag1", "tag2"])
        self.assertEqual(model.tags, ["tag1", "tag2"])

        # Empty list when min_length=1
        with self.assertRaises(ValidationError) as ctx:
            ListModel(tags=[])
        self.assertIn("at least", str(ctx.exception).lower())

        # Too many items
        with self.assertRaises(ValidationError) as ctx:
            ListModel(tags=["a", "b", "c", "d", "e", "f"])
        self.assertIn("at most", str(ctx.exception).lower())

    def test_list_item_conversion(self):
        """Test that list items are converted to correct types."""
        class ListIntModel(BaseModel):
            numbers: List[int] = Field(..., description="List of numbers")

        # String numbers converted to int
        model = ListIntModel(numbers=["1", "2", "3"])
        self.assertEqual(model.numbers, [1, 2, 3])
        self.assertTrue(all(isinstance(n, int) for n in model.numbers))

    def test_optional_int_union_handling(self):
        """Test that Optional[int] (Union[int, None]) is handled correctly.
        
        This tests the bug fix where Optional[int] is actually Union[int, None],
        and get_origin() returns typing.Union, not type(Optional).
        """
        class OptionalIntModel(BaseModel):
            nth: Optional[int] = Field(
                None, ge=1, le=10000, description="Nth item")

        # String to int conversion with Optional
        model = OptionalIntModel(nth="2")
        self.assertEqual(model.nth, 2)
        self.assertIsInstance(model.nth, int)

        # None is valid for Optional
        model = OptionalIntModel(nth=None)
        self.assertIsNone(model.nth)

        # No value provided, uses default
        model = OptionalIntModel()
        self.assertIsNone(model.nth)

        # Constraints still apply
        with self.assertRaises(ValidationError):
            OptionalIntModel(nth=0)


class TestBaseModelJSONSchema(unittest.TestCase):
    """Test JSON Schema generation."""

    def test_simple_schema(self):
        """Test schema generation for simple types."""
        class SimpleModel(BaseModel):
            name: str = Field(..., description="Name field")
            age: int = Field(..., ge=0, le=150, description="Age field")
            active: bool = Field(True, description="Active flag")

        schema = SimpleModel.model_json_schema()

        self.assertEqual(schema["type"], "object")
        self.assertIn("name", schema["properties"])
        self.assertIn("age", schema["properties"])
        self.assertIn("active", schema["properties"])

        # Check types
        self.assertEqual(schema["properties"]["name"]["type"], "string")
        self.assertEqual(schema["properties"]["age"]["type"], "integer")
        self.assertEqual(schema["properties"]["age"]["minimum"], 0)
        self.assertEqual(schema["properties"]["age"]["maximum"], 150)
        self.assertEqual(schema["properties"]["active"]["type"], "boolean")

        # Check descriptions
        self.assertEqual(schema["properties"]["name"]
                         ["description"], "Name field")
        self.assertEqual(schema["properties"]["age"]
                         ["description"], "Age field")

        # Check required fields
        self.assertIn("name", schema["required"])
        self.assertIn("age", schema["required"])
        self.assertNotIn("active", schema["required"])

    def test_optional_schema(self):
        """Test schema generation with Optional fields."""
        class OptionalModel(BaseModel):
            name: str = Field(..., description="Required name")
            nickname: Optional[str] = Field(
                None, description="Optional nickname")

        schema = OptionalModel.model_json_schema()

        # Both fields should be in properties
        self.assertIn("name", schema["properties"])
        self.assertIn("nickname", schema["properties"])

        # Only name should be required
        self.assertEqual(schema["required"], ["name"])

    def test_list_schema(self):
        """Test schema generation for List fields."""
        class ListModel(BaseModel):
            tags: List[str] = Field(..., min_length=1,
                                    max_length=10, description="Tags")
            numbers: List[int] = Field([], description="Numbers")

        schema = ListModel.model_json_schema()

        # Check tags array schema
        tags_schema = schema["properties"]["tags"]
        self.assertEqual(tags_schema["type"], "array")
        self.assertEqual(tags_schema["items"]["type"], "string")
        self.assertEqual(tags_schema["minItems"], 1)
        self.assertEqual(tags_schema["maxItems"], 10)

        # Check numbers array schema
        numbers_schema = schema["properties"]["numbers"]
        self.assertEqual(numbers_schema["type"], "array")
        self.assertEqual(numbers_schema["items"]["type"], "integer")


class TestRealWorldScenarios(unittest.TestCase):
    """Test real-world scenarios from git tools."""

    def test_git_log_params(self):
        """Test GitLogParams-like model."""
        class GitLogParams(BaseModel):
            repo_dir: Optional[str] = None
            nth: Optional[int] = Field(
                None, ge=1, le=10000, description="Nth commit")
            max_count: Optional[int] = Field(
                20, ge=1, le=200, description="Max commits")

        # LLM sends string for nth
        params = GitLogParams(nth="5", max_count="10")
        self.assertEqual(params.nth, 5)
        self.assertEqual(params.max_count, 10)
        self.assertIsNone(params.repo_dir)

        # Default values work
        params = GitLogParams()
        self.assertIsNone(params.nth)
        self.assertEqual(params.max_count, 20)

    def test_git_add_params(self):
        """Test GitAddParams-like model."""
        class GitAddParams(BaseModel):
            repo_dir: Optional[str] = None
            files: List[str] = Field(..., min_length=1,
                                     description="Files to stage")

        # Valid params
        params = GitAddParams(files=["file1.py", "file2.py"])
        self.assertEqual(params.files, ["file1.py", "file2.py"])

        # Empty list should fail
        with self.assertRaises(ValidationError):
            GitAddParams(files=[])

        # Missing required field
        with self.assertRaises(ValidationError):
            GitAddParams()

    def test_run_command_params(self):
        """Test RunCommandParams-like model."""
        class RunCommandParams(BaseModel):
            command: str = Field(..., description="Command to execute")
            working_dir: Optional[str] = Field(
                None, description="Working directory")
            timeout: int = Field(
                60, ge=1, le=300, description="Timeout in seconds")

        # Valid params with string timeout from LLM
        params = RunCommandParams(command="git status", timeout="120")
        self.assertEqual(params.command, "git status")
        self.assertEqual(params.timeout, 120)
        self.assertIsNone(params.working_dir)

        # Default timeout
        params = RunCommandParams(command="ls")
        self.assertEqual(params.timeout, 60)

        # Timeout out of range
        with self.assertRaises(ValidationError):
            RunCommandParams(command="test", timeout=400)
