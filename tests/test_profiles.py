"""First-run profile onboarding and migration checks."""

import json
import tempfile
import unittest
from pathlib import Path

from slideshow.profiles import (DEFAULT_PROFILE_NAME, active_profile,
                                load_registry, save_registry, update_profile)


class ProfileOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.directory = Path(self.storage.name)

    def tearDown(self):
        self.storage.cleanup()

    def test_empty_workspace_requires_onboarding(self):
        registry = load_registry(self.directory, legacy_data=False)
        profile = active_profile(registry)
        self.assertEqual(profile["name"], DEFAULT_PROFILE_NAME)
        self.assertFalse(profile["onboarded"])

    def test_legacy_workspace_is_already_onboarded(self):
        registry = load_registry(self.directory, legacy_data=True)
        self.assertTrue(active_profile(registry)["onboarded"])

    def test_existing_named_profile_is_treated_as_onboarded(self):
        (self.directory / "profiles.json").write_text(json.dumps({
            "active_profile": "main",
            "profiles": [{
                "id": "main", "name": "Παρασκευή", "role": "",
                "color": "#e8bd79", "legacy": True,
                "created_at": "2026-01-01T00:00:00", "last_project": "",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        registry = load_registry(self.directory, legacy_data=False)
        self.assertTrue(active_profile(registry)["onboarded"])

    def test_completion_persists_name_and_flag(self):
        registry = load_registry(self.directory, legacy_data=False)
        profile = active_profile(registry)
        update_profile(registry, profile["id"], name="Γιώργος",
                       role="Φωτογράφος", color="#84c5a5", onboarded=True)
        save_registry(self.directory, registry)
        reloaded = load_registry(self.directory, legacy_data=False)
        saved = active_profile(reloaded)
        self.assertEqual(saved["name"], "Γιώργος")
        self.assertEqual(saved["role"], "Φωτογράφος")
        self.assertEqual(saved["color"], "#84c5a5")
        self.assertTrue(saved["onboarded"])


if __name__ == "__main__":
    unittest.main()
