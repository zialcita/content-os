"""Regression checks for final M0 API/database alignment review."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator

SCHEMAS = json.loads((Path(__file__).with_name('target-v6.openapi.json')).read_text())['components']['schemas']

class BindingTests(unittest.TestCase):
    def test_manual_script_can_omit_production_plan_but_paid_regeneration_cannot(self):
        for name in ('AssetWrite', 'AssetVersion'):
            Draft202012Validator(SCHEMAS[name]['properties']['plan_version_id']).validate(None)
            self.assertIn('plan_version_id', SCHEMAS[name]['required'])
        paid = SCHEMAS['RegenerateRequest']
        self.assertIn('approved_plan_version_id', paid['required'])
        self.assertFalse(Draft202012Validator(paid['properties']['approved_plan_version_id']).is_valid(None))

    def test_invitation_includes_revision_for_optimistic_revocation(self):
        self.assertIn('revision', SCHEMAS['Invitation']['required'])
        self.assertEqual(SCHEMAS['Invitation']['properties']['revision']['minimum'], 1)

    def test_clip_work_pins_exact_final_cut_file(self):
        for name in ('ClipCandidatesRequest', 'ClipCandidate', 'ClipSelectionWrite', 'ClipSelectionVersion'):
            self.assertIn('final_cut_rendition_id', SCHEMAS[name]['required'])
            self.assertEqual(SCHEMAS[name]['properties']['final_cut_rendition_id']['format'], 'uuid')

if __name__ == '__main__':
    unittest.main()
