from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import SystemConfig
from .registry import REGISTRY
from .services import clear_cache, get_config, public_config, sync_registry


class SystemConfigTests(TestCase):
    def setUp(self):
        clear_cache()

    def test_every_registry_key_is_seeded(self):
        keys = set(SystemConfig.objects.values_list("key", flat=True))
        self.assertTrue(set(REGISTRY).issubset(keys))

    def test_default_used_when_row_missing(self):
        SystemConfig.objects.filter(key="quiz.pass_score").delete()
        self.assertEqual(get_config("quiz.pass_score"), REGISTRY["quiz.pass_score"].default)

    def test_db_value_overrides_default_and_cache_is_cleared(self):
        self.assertEqual(get_config("quiz.pass_score"), 7)
        row = SystemConfig.objects.get(key="quiz.pass_score")
        row.value = "8"
        row.save()
        self.assertEqual(get_config("quiz.pass_score"), 8)

    def test_sync_does_not_overwrite_edits(self):
        SystemConfig.objects.filter(key="quiz.pass_score").update(value="9")
        self.assertEqual(sync_registry(), 0)
        self.assertEqual(SystemConfig.objects.get(key="quiz.pass_score").value, "9")

    def test_invalid_values_rejected(self):
        row = SystemConfig.objects.get(key="quiz.pass_score")
        row.value = "seven"
        with self.assertRaises(ValidationError):
            row.full_clean()
        row.value = "0"
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            get_config("does.not.exist")

    def test_public_endpoint_only_exposes_public_keys(self):
        response = self.client.get("/api/config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), public_config())
        self.assertIn("quiz.pass_score", response.json())
        self.assertNotIn("llm.model", response.json())
