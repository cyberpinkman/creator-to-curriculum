"""Authored synthetic attempts exercise cross-mode feedback semantics, not grading."""

import copy
import tempfile
import unittest
from pathlib import Path

from creator_curriculum.core import (ContractError, digest, index_learning_feedback,
                                     read_json, validate_learning_feedback, write_json)
from creator_curriculum.feedback import feedback_context_for_workspace
from creator_curriculum.scenarios import build_feedback_scenario, build_scenario, scenario_data, scenario_names


class FeedbackScenarioTests(unittest.TestCase):
    def test_five_modes_have_bounded_next_actions_and_honest_synthetic_evidence(self):
        actions = {'concept': 'continue', 'practice': 'request_evidence',
                   'project': 'continue', 'comparison': 'finish', 'lookup': 'resolve_gap'}
        self.assertEqual(set(actions), set(scenario_names()))
        with tempfile.TemporaryDirectory() as temporary:
            for name, action in actions.items():
                with self.subTest(name=name):
                    output = build_feedback_scenario(name, Path(temporary) / name)
                    state = read_json(output / 'feedback-state.json')
                    payload = read_json(output / 'index.json')
                    context = feedback_context_for_workspace(output)
                    self.assertEqual(payload['feedback_context'], context)
                    projection = index_learning_feedback(context, state)
                    self.assertEqual(payload['learning_feedback'], projection)
                    self.assertEqual(projection['feedback'][-1]['next_action']['kind'], action)
                    self.assertTrue(projection['feedback'][-1]['actionable'])
                    attempts = {a['id']: a for a in state['attempts']}
                    for attempt in attempts.values():
                        self.assertIn('合成演示，非真实学习者记录', attempt['response'])
                        self.assertEqual(attempt['artifact_refs'], [])
                    for feedback in state['feedback']:
                        self.assertIn('合成演示，非真实学习者记录', feedback['summary'])
                        self.assertEqual(feedback['observations'], [])
                        attempt = attempts[feedback['attempt_id']]
                        for result in feedback['criteria']:
                            for evidence in result['evidence']:
                                self.assertIn(evidence['quote'], attempt['response'])
                    self.assertTrue((output / 'index.html').is_file())

    def test_concept_correction_preserves_bad_attempt_and_only_new_guidance_can_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('concept', temporary)
            state = read_json(output / 'feedback-state.json')
            context = feedback_context_for_workspace(output)
            before, after = state['attempts']
            self.assertIn('实际一万米', before['response'])
            self.assertIn('实际一万厘米', after['response'])
            self.assertNotEqual(before['id'], after['id'])
            self.assertEqual((before['path_id'], before['step_id'], before['activity_id']),
                             (after['path_id'], after['step_id'], after['activity_id']))
            self.assertEqual(before['criteria'], after['criteria'])
            old, current = index_learning_feedback(context, state)['feedback']
            self.assertEqual([c['result'] for c in old['criteria']], ['needs_work', 'needs_work'])
            self.assertEqual(old['status'], 'superseded')
            self.assertFalse(old['actionable'])
            self.assertEqual(current['status'], 'current')
            self.assertEqual([c['result'] for c in current['criteria']], ['met', 'met'])
            self.assertEqual(current['next_action']['target'], {'path_id': 'start', 'step_id': 'calculate'})
            # A superficially completed old answer cannot progress merely by changing the action.
            wrong = copy.deepcopy(state['feedback'][0])
            wrong['next_action'] = copy.deepcopy(current['next_action'])
            with self.assertRaises(ContractError):
                validate_learning_feedback(wrong, before, context)

    def test_missing_practice_product_and_reference_answer_are_not_performance(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('practice', temporary)
            state = read_json(output / 'feedback-state.json')
            context = feedback_context_for_workspace(output)
            self.assertIn('我看过教程，也试着清理了', state['attempts'][0]['response'])
            self.assertTrue(state['attempts'][0]['blocker'])
            for feedback in state['feedback']:
                self.assertEqual({c['result'] for c in feedback['criteria']}, {'not_observed'})
                self.assertEqual(feedback['next_action']['kind'], 'request_evidence')
                self.assertIsNone(feedback['next_action']['target'])
            reference = state['attempts'][1]
            self.assertEqual(reference['work_origin'], 'reference')
            wrong = copy.deepcopy(state['feedback'][1])
            wrong['criteria'][0].update(result='met', evidence=[{'field': 'response', 'quote': '应保留四行'}])
            with self.assertRaises(ContractError):
                validate_learning_feedback(wrong, reference, context)

    def test_project_unknown_fact_is_allowed_without_completing_the_next_same_topic_activity(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('project', temporary)
            state = read_json(output / 'feedback-state.json')
            context = feedback_context_for_workspace(output)
            feedback = state['feedback'][-1]
            self.assertIn('参加条件：待确认', state['attempts'][-1]['response'])
            self.assertEqual({c['result'] for c in feedback['criteria']}, {'met'})
            self.assertEqual(feedback['next_action']['target'], {'path_id': 'start', 'step_id': 'layout'})
            steps = {(s['path_id'], s['step_id']): s for s in context['steps']}
            self.assertEqual(steps['start', 'brief']['topic_id'], steps['start', 'layout']['topic_id'])
            self.assertNotEqual(steps['start', 'brief']['activity_id'], steps['start', 'layout']['activity_id'])
            self.assertEqual({a['activity_id'] for a in state['attempts']}, {'draft-brief'})
            self.assertFalse(any(a['step_id'] == 'layout' for a in state['attempts']))
            _, original_learner, original_plan, files = scenario_data('project')
            self.assertEqual(read_json(output / 'learner.json'), original_learner)
            self.assertEqual(read_json(output / 'index-plan.json'), original_plan)
            for relative, body in files.items():
                self.assertEqual((output / relative).read_text(), body)

    def test_comparison_finishes_a_bounded_task_without_erasing_source_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('comparison', temporary)
            state = read_json(output / 'feedback-state.json')
            self.assertEqual([f['next_action']['kind'] for f in state['feedback']], ['retry', 'finish'])
            self.assertIn('needs_work', [c['result'] for c in state['feedback'][0]['criteria']])
            self.assertIn('待核实条件', state['attempts'][-1]['response'])
            payload = read_json(output / 'index.json')
            self.assertEqual(payload['feedback_context']['steps'][0]['readiness']['status'], 'needs_review')
            plan = read_json(output / 'index-plan.json')
            self.assertEqual(plan['capabilities'][0]['coverage']['status'], 'conflicting')
            self.assertEqual(len(plan['capabilities'][0]['coverage']['sources']), 2)
            self.assertIsNone(state['feedback'][-1]['next_action']['target'])

    def test_lookup_keeps_unavailable_inputs_and_prerequisites_as_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('lookup', temporary)
            state = read_json(output / 'feedback-state.json')
            context = feedback_context_for_workspace(output)
            step = next(s for s in context['steps'] if s['step_id'] == 'naming')
            self.assertEqual(step['readiness']['status'], 'blocked')
            self.assertEqual({c['result'] for c in state['feedback'][0]['criteria']}, {'not_observed'})
            self.assertEqual(state['feedback'][0]['next_action']['kind'], 'resolve_gap')
            self.assertIsNone(state['feedback'][0]['next_action']['target'])
            plan = read_json(output / 'index-plan.json')
            self.assertEqual(plan['materials'][0]['availability'], 'unavailable')
            missing = next(c for c in plan['capabilities'] if c['id'] == 'file-basics')
            self.assertEqual(missing['coverage']['status'], 'missing')
            self.assertEqual(missing['coverage']['sources'], [])

    def test_feedback_is_opt_in_and_repeat_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_scenario('concept', temporary)
            self.assertFalse((output / 'feedback-state.json').exists())
            self.assertEqual(read_json(output / 'index.json')['learning_feedback']['attempts'], [])
            build_feedback_scenario('concept', output)
            original = (output / 'feedback-state.json').read_bytes()
            build_feedback_scenario('concept', output)
            self.assertEqual((output / 'feedback-state.json').read_bytes(), original)

    def test_material_change_retains_old_feedback_as_stale_and_never_overwrites_filled_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('project', temporary)
            before = read_json(output / 'feedback-state.json')
            material = output / 'materials/poster-brief.md'
            filled = material.read_text() + '\n使用者待确认记录：地点需要重新核对。\n'
            material.write_text(filled)
            build_feedback_scenario('project', output)
            after = read_json(output / 'feedback-state.json')
            self.assertEqual(after['attempts'][:len(before['attempts'])], before['attempts'])
            self.assertEqual(after['feedback'][:len(before['feedback'])], before['feedback'])
            self.assertEqual(len(after['attempts']), 2 * len(before['attempts']))
            self.assertEqual(material.read_text(), filled)
            projection = read_json(output / 'index.json')['learning_feedback']
            self.assertTrue(all(f['status'] == 'stale' and not f['actionable']
                                for f in projection['feedback'][:len(before['feedback'])]))
            self.assertEqual(projection['feedback'][-1]['status'], 'current')

    def test_demo_rejects_real_records_before_rebuilding_existing_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = build_feedback_scenario('concept', temporary)
            state = read_json(output / 'feedback-state.json')
            real = copy.deepcopy(state['attempts'][-1])
            real['id'] = 'learner-attempt-to-preserve'
            real['response'] = '这份实际记录不能被合成演示混用。'
            state['attempts'].append(real)
            write_json(output / 'feedback-state.json', state)
            # Valid customised input makes an accidental demo rebuild observable.
            learner = read_json(output / 'learner.json')
            learner['language'] = 'en'
            plan = read_json(output / 'index-plan.json')
            plan['learner_hash'] = digest(learner)
            write_json(output / 'learner.json', learner)
            write_json(output / 'index-plan.json', plan)
            protected = {name: (output / name).read_bytes()
                         for name in ('feedback-state.json', 'learner.json', 'index-plan.json', 'index.json')}
            with self.assertRaisesRegex(ContractError, 'non-demo records'):
                build_feedback_scenario('concept', output)
            self.assertEqual({name: (output / name).read_bytes() for name in protected}, protected)


if __name__ == '__main__':
    unittest.main()
