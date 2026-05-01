# -*- coding: utf-8 -*-
"""Test the model combobox (cbModelIds) behavior in the LLM preferences tab.

Behavior requirements:
- If models() returns a non-empty list (server fetch succeeded), the combobox
  should be read-only (not editable) and only show items from the server list.
- If the previously saved model ID is not in the server list, auto-select the
  first item instead of preserving the invalid entry.
- If models() returns an empty list (not yet fetched or no models available),
  the combobox should remain editable to allow manual entry.
"""

import uuid

from qgitc.llm import AiModelBase
from qgitc.preferences import Preferences
from tests.base import TestBase


class _FakeModel(AiModelBase):
    """A fake model for testing _onModelChanged directly."""

    def __init__(self, model=None, providerConfig=None, parent=None):
        super().__init__("http://test.local/v1", model, parent)
        self._fake_models = []

    @property
    def name(self):
        return "Fake Model"

    def isLocal(self):
        return True

    def models(self):
        return self._fake_models


class TestPreferencesModelCombobox(TestBase):

    def setUp(self):
        super().setUp()
        self.preferences = Preferences(self.app.settings())
        self._provider_id = str(uuid.uuid4())

        # Configure a local provider
        self.app.settings().setLocalLlmProviders([{
            "id": self._provider_id,
            "name": "Test Provider",
            "url": "http://test.local/v1",
            "headers": {},
        }])

        # Create the fake model used for all tests
        self.fake_model = _FakeModel(parent=self.preferences)
        # AiModelFactory.modelKey returns the class name for AiModelBase instances
        self.fake_model_key = self.fake_model.__class__.__name__

        # Switch to LLM tab so cbModels is populated
        self.preferences.ui.tabWidget.setCurrentWidget(
            self.preferences.ui.tabLLM)
        self._process_events()

    def tearDown(self):
        self.preferences.deleteLater()
        super().tearDown()

    def _process_events(self, count=5):
        for _ in range(count):
            self.app.sendPostedEvents()
            self.app.processEvents()

    def _set_current_model_on_combobox(self):
        """Set our fake model as the current data in cbModels,
        then call _onModelChanged to trigger cbModelIds update."""
        cbModels = self.preferences.ui.cbModels
        index = cbModels.count()
        cbModels.addItem(self.fake_model.name, self.fake_model)
        cbModels.setCurrentIndex(index)
        self._process_events()
        return self.preferences.ui.cbModelIds

    def _call_on_model_changed(self):
        """Trigger _onModelChanged directly on the LLM tab."""
        self.preferences._onModelChanged(
            self.preferences.ui.cbModels.currentIndex())
        self._process_events()

    # --- Tests ---

    def test_combobox_is_editable_when_no_models(self):
        """When models() returns empty, the combobox should be editable."""
        self.fake_model._fake_models = []
        cbModelIds = self._set_current_model_on_combobox()
        self._call_on_model_changed()
        self.assertTrue(
            cbModelIds.isEditable(),
            "Combobox should be editable when models list is empty")

    def test_combobox_is_readonly_when_models_available(self):
        """When models() returns a non-empty list, combobox should be read-only."""
        self.fake_model._fake_models = [
            ("gpt-4", "GPT-4"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
        ]
        cbModelIds = self._set_current_model_on_combobox()
        self._call_on_model_changed()
        self.assertFalse(
            cbModelIds.isEditable(),
            "Combobox should be read-only when models list is non-empty")

    def test_invalid_saved_model_auto_selects_first_item(self):
        """When the saved model ID is not in the server list, auto-select first item."""
        self.app.settings().setDefaultLlmModelId(
            self.fake_model_key, "non-existent-model")
        self.fake_model._fake_models = [
            ("gpt-4", "GPT-4"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
        ]
        cbModelIds = self._set_current_model_on_combobox()
        self._call_on_model_changed()

        self.assertEqual(cbModelIds.count(), 2)
        # Should auto-select the first item
        self.assertEqual(
            cbModelIds.currentData(), "gpt-4",
            "Should auto-select the first model when saved model is not in list")
        # Should be read-only
        self.assertFalse(
            cbModelIds.isEditable(),
            "Combobox should be read-only when models are available")

    def test_valid_saved_model_is_preserved_when_in_list(self):
        """When the saved model ID is in the server list, it should be selected."""
        self.app.settings().setDefaultLlmModelId(
            self.fake_model_key, "gpt-3.5-turbo")
        self.fake_model._fake_models = [
            ("gpt-4", "GPT-4"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
        ]
        cbModelIds = self._set_current_model_on_combobox()
        self._call_on_model_changed()

        self.assertEqual(cbModelIds.count(), 2)
        self.assertEqual(
            cbModelIds.currentData(), "gpt-3.5-turbo",
            "Should select the saved model when it is in the list")
        # Should be read-only
        self.assertFalse(
            cbModelIds.isEditable(),
            "Combobox should be read-only when models are available")

    def test_old_invalid_value_not_kept_when_models_fetched(self):
        """Regression: old user-added model name should NOT be kept when server
        returns a list.  The combobox switches to read-only and selects first item."""
        self.app.settings().setDefaultLlmModelId(
            self.fake_model_key, "my-custom-model")
        self.fake_model._fake_models = [
            ("gpt-4", "GPT-4"),
        ]
        cbModelIds = self._set_current_model_on_combobox()
        self._call_on_model_changed()

        self.assertEqual(cbModelIds.count(), 1)
        self.assertEqual(
            cbModelIds.currentData(), "gpt-4",
            "Should auto-select first item, not preserve invalid custom model")
        self.assertFalse(
            cbModelIds.isEditable(),
            "Combobox should be read-only when server models are available")
