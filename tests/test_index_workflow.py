import tempfile
import unittest
from pathlib import Path

from creator_curriculum.cli import parser, run
from creator_curriculum.core import ContractError, digest, read_json, write_json
from creator_curriculum.index import build_index
from creator_curriculum.index_workflow import (initialize_index, prepare_index,
                                               resolve_index_plan_identity)
from creator_curriculum.scenarios import scenario_data


class DefaultIndexWorkflowTests(unittest.TestCase):
    def test_handoff_preserves_unknowns_and_does_not_overwrite_a_plan(self):
        corpus, learner, plan, _ = scenario_data('concept')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'index'
            plan['package_id'] = initialize_index(root, corpus, learner)['package_id']
            write_json(root / 'index-plan.json', plan)
            self.assertEqual(prepare_index(root)['existing_plan']['status'], 'current')
            before = (root / 'index-plan.json').read_bytes()
            learner.update(level=None, minutes_per_session=None)
            write_json(root / 'learner.json', learner)
            self.assertEqual(prepare_index(root)['existing_plan']['status'], 'needs_revision')
            handoff = read_json(root / 'planning-input.json')
            self.assertIsNone(handoff['learner']['level'])
            self.assertIsNone(handoff['learner']['minutes_per_session'])
            self.assertEqual((root / 'index-plan.json').read_bytes(), before)
            with self.assertRaises(ContractError):
                initialize_index(root, corpus, learner)

    def test_cli_default_handoff_and_build_require_current_learner(self):
        corpus, learner, plan, _ = scenario_data('concept')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / 'input.json', corpus)
            result = run(parser().parse_args(['init-index', '--corpus', str(root / 'input.json'),
                                             '--out', str(root / 'new'), '--goal', '比较两个概念']))
            actual = read_json(Path(result['workspace']) / 'learner.json')
            self.assertIsNone(actual['level'])
            self.assertIsNone(actual['minutes_per_session'])
            write_json(root / 'plan.json', plan)
            write_json(root / 'learner.json', learner)
            args = ['build-index', '--corpus', str(root / 'input.json'), '--plan', str(root / 'plan.json'),
                    '--out', str(root / 'output')]
            with self.assertRaisesRegex(ContractError, 'learner'):
                run(parser().parse_args(args))

    def test_exports_share_step_identity_and_required_material_evidence(self):
        corpus, learner, plan, materials = scenario_data('project')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, content in materials.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8')
            build_index(corpus, plan, root, learner=learner)
            data = read_json(root / 'index.json')
            design = read_json(root / 'learning-design.json')
            self.assertEqual(data['learning_paths'], design['paths'])
            self.assertEqual(data['learner'], learner)
            self.assertTrue(all(topic['task'] is None for topic in data['topics']))
            markdown = (root / 'README.md').read_text()
            activities = {a['id']: a for a in data['activities']}
            for path in data['learning_paths']:
                for step in path['steps']:
                    activity = activities[step['activity_id']]
                    self.assertIn(f'id="study-{path["id"]}-{step["id"]}"', markdown)
                    self.assertIn(activity['output'], markdown)
                    self.assertTrue(activity['sources'])
                    self.assertTrue(all('evidence' in source for source in activity['sources']))
            self.assertIn('learning_design', (root / 'index.html').read_text())

    def test_workspace_identity_isolated_stable_and_bound_to_feedback(self):
        corpus, learner, plan, _ = scenario_data('concept')
        plan.pop('package_id')
        with tempfile.TemporaryDirectory() as temporary:
            roots = [Path(temporary) / name for name in ('a', 'b')]
            identities = [initialize_index(root, corpus, learner)['package_id'] for root in roots]
            self.assertNotEqual(*identities)
            for root, identity in zip(roots, identities):
                build_index(corpus, plan, root, learner=learner)
                data = read_json(root / 'index.json')
                self.assertEqual(data['package_id'], identity)
                self.assertEqual(data['feedback_context']['package_id'], identity)
                self.assertEqual(read_json(root / 'index-plan.json')['package_id'], identity)
                learner['minutes_per_session'] = 7
                write_json(root / 'learner.json', learner)
                self.assertEqual(prepare_index(root)['package_id'], identity)
                plan['learner_hash'] = digest(learner)
                build_index(corpus, plan, root, learner=learner)
                self.assertEqual(read_json(root / 'index.json')['package_id'], identity)

    def test_external_build_allocates_identity_and_migrates_existing_output(self):
        corpus, learner, plan, _ = scenario_data('concept')
        plan.pop('package_id')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = []
            for name in ('a', 'b'):
                build_index(corpus, plan, root / name, learner=learner)
                packages.append(read_json(root / name / 'index.json')['package_id'])
            self.assertNotEqual(*packages)
            old = root / 'legacy-v2'
            write_json(old / 'index.json', {'package_id': 'creator-previous'})
            build_index(corpus, plan, old, learner=learner)
            self.assertEqual(read_json(old / 'index.json')['package_id'], 'creator-previous')
            build_index(corpus, plan, old, learner=learner)
            self.assertEqual(read_json(old / 'index-plan.json')['package_id'], 'creator-previous')

    def test_identity_conflict_and_invalid_metadata_do_not_change_workspace(self):
        corpus, learner, plan, _ = scenario_data('concept')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = initialize_index(root, corpus, learner)['package_id']
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaisesRegex(ContractError, 'package_id conflicts'):
                build_index(corpus, plan, root, learner=learner)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            self.assertEqual(resolve_index_plan_identity(root, {'schema_version': 2}, corpus)['package_id'], identity)
            write_json(root / 'index-workspace.json', {'schema_version': 2, 'package_id': identity})
            with self.assertRaisesRegex(ContractError, 'workspace identity'):
                prepare_index(root)

    def test_empty_discovery_hands_off_source_recovery_before_planning(self):
        corpus, learner, _, _ = scenario_data('concept')
        for video in corpus['videos']:
            video.update(status='excluded', segments=[], reason='Not part of this creator snapshot')
        for videos in ([], corpus['videos']):
            with self.subTest(excluded_count=len(videos)), tempfile.TemporaryDirectory() as temporary:
                inventory = {**corpus, 'videos': videos,
                             'discovery': {**corpus['discovery'], 'status': 'partial', 'expected_count': None}}
                result = initialize_index(temporary, inventory, learner)
                handoff = read_json(Path(temporary) / 'planning-input.json')
                self.assertEqual(result['intake']['status'], 'needs_sources')
                self.assertEqual(len(handoff['inventory']), len(videos))
                self.assertIsNone(handoff['discovery']['expected_count'])
                self.assertIn('do not invent', handoff['intake']['next_action'])
                self.assertFalse((Path(temporary) / 'index-plan.json').exists())


if __name__ == '__main__':
    unittest.main()
