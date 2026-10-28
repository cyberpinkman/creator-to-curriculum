"""Cross-mode checks use authored cases, not real creator content or model output."""
import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from creator_curriculum.core import ContractError, index_learning_design, validate_index_plan
from creator_curriculum.scenarios import build_scenario, scenario_data, scenario_names


class LearningScenarioTests(unittest.TestCase):
    def test_modes_build_through_the_same_default_contract(self):
        expected = {'concept': ('understand', 'ready'), 'practice': ('practice', 'ready'),
                    'project': ('create', 'ready'), 'comparison': ('compare', 'partial'),
                    'lookup': ('lookup', 'partial')}
        self.assertEqual(set(scenario_names()), set(expected))
        with tempfile.TemporaryDirectory() as temporary:
            for name, (kind, status) in expected.items():
                with self.subTest(name=name):
                    corpus, learner, plan, _ = scenario_data(name)
                    validate_index_plan(plan, corpus, learner)
                    self.assertTrue(all(v['transcript_source'] == 'synthetic' for v in corpus['videos']))
                    self.assertEqual(plan['activities'][0]['kind'], kind)
                    output = build_scenario(name, Path(temporary) / name)
                    payload = json.loads((output / 'index.json').read_text())
                    self.assertEqual(payload['learner'], learner)
                    self.assertEqual(payload['learning_design']['status'], status)
                    self.assertTrue((output / 'index.html').is_file())
                    for activity in plan['activities']:
                        self.assertIn(activity['output'], (output / 'README.md').read_text())

    def test_changed_goal_or_constraints_cannot_reuse_an_old_plan(self):
        corpus, learner, plan, _ = scenario_data('concept')
        # The sources are identical: the planning input, not acquisition, changed.
        for change in ({'goal': '只检查一次距离计算错误。'},
                       {'minutes_per_session': 2},
                       {'prior_knowledge': ['已能解释比例尺，只需检查单位。']}):
            with self.subTest(change=change):
                altered = {**copy.deepcopy(learner), **change}
                with self.assertRaises(ContractError):
                    validate_index_plan(plan, corpus, altered)

    def test_project_preserves_two_stages_of_one_topic_and_an_alternate_activity(self):
        corpus, learner, plan, _ = scenario_data('project')
        design = index_learning_design(plan, corpus, learner)
        paths = {p['id']: p for p in design['paths']}
        steps = paths['start']['steps']
        self.assertEqual([s['topic_id'] for s in steps], ['poster', 'poster'])
        self.assertEqual([s['id'] for s in steps], ['brief', 'layout'])
        self.assertEqual([s['activity_id'] for s in steps], ['draft-brief', 'make-poster'])
        self.assertEqual(paths['revise']['steps'][0]['activity_id'], 'revise-poster')
        self.assertEqual(paths['revise']['steps'][0]['topic_id'], 'poster')
        activities = {a['id']: a for a in plan['activities']}
        self.assertNotEqual(activities['make-poster']['output'], activities['revise-poster']['output'])
        self.assertEqual(paths['start']['topic_ids'], ['poster'])

    def test_missing_foundation_and_material_stay_visible_without_fabricated_sources(self):
        corpus, learner, plan, files = scenario_data('lookup')
        self.assertIsNone(learner['level'])
        self.assertEqual(files, {})
        gap = next(c for c in plan['capabilities'] if c['id'] == 'file-basics')
        self.assertEqual(gap['coverage']['status'], 'missing')
        self.assertEqual(gap['coverage']['sources'], [])
        self.assertFalse(any(v['id'] == 'file-basics' for v in corpus['videos']))
        design = index_learning_design(plan, corpus, learner)
        steps = design['paths'][0]['steps']
        self.assertEqual(steps[0]['readiness']['status'], 'ready')
        self.assertEqual(steps[1]['readiness']['status'], 'blocked')
        self.assertTrue(steps[1]['readiness']['issues'])
        self.assertEqual(plan['materials'][0]['availability'], 'unavailable')
        self.assertNotIn('local_path', plan['materials'][0])

    def test_opposing_claims_remain_distinct_and_do_not_become_a_ready_prescription(self):
        corpus, learner, plan, _ = scenario_data('comparison')
        capability = plan['capabilities'][0]
        self.assertEqual(capability['coverage']['status'], 'conflicting')
        self.assertEqual(len(capability['coverage']['sources']), 2)
        self.assertEqual({s['video_id'] for s in plan['activities'][0]['sources']},
                         {'single-list', 'separate-boards'})
        self.assertIsNone(learner['minutes_per_session'])
        design = index_learning_design(plan, corpus, learner)
        self.assertEqual(design['paths'][0]['steps'][0]['readiness']['status'], 'needs_review')
        for video in corpus['videos']:
            self.assertEqual(plan['reviews'][video['id']]['evidence'][0]['quote'], video['segments'][0]['text'])

    def test_practice_contains_real_differences_to_observe_and_keeps_filled_materials(self):
        _, _, plan, files = scenario_data('practice')
        rows = list(csv.DictReader(io.StringIO(files['materials/sample-table.csv'])))
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r['id'] for r in rows}), 3)
        self.assertTrue(any(r['name'] != r['name'].strip() for r in rows))
        self.assertGreater(len({r['id'] for r in rows if r['name'].strip() == '小林'}), 1)
        self.assertEqual(plan['activities'][1]['capability_ids'], ['clean-and-check'])
        with tempfile.TemporaryDirectory() as temporary:
            output = build_scenario('practice', temporary)
            material = output / 'materials/sample-table.csv'
            filled = material.read_text() + '\n# learner note: 核对中\n'
            material.write_text(filled)
            build_scenario('practice', temporary)
            self.assertEqual(material.read_text(), filled)


if __name__ == '__main__':
    unittest.main()
