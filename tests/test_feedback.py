"""Evidence and navigation invariants for Agent feedback, without a grading model."""
import copy
import unittest

from creator_curriculum.core import (
    ContractError, digest, index_feedback_context, index_learning_feedback,
    validate_learning_attempt, validate_learning_feedback,
)
from creator_curriculum.scenarios import scenario_data


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.learner, self.plan, _ = scenario_data('project')
        self.material_hashes = {'poster-brief': 'a' * 64, 'poster-draft': 'b' * 64}
        self.context = index_feedback_context(self.plan, self.corpus, self.learner, self.material_hashes)

    def attempt(self, step=0, **changes):
        current = self.context['steps'][step]
        result = dict(schema_version=1, id='attempt-one', package_id=self.context['package_id'],
                      context_hash=self.context['context_hash'], path_id=current['path_id'],
                      step_id=current['step_id'], activity_id=current['activity_id'],
                      created_at='2026-10-27T10:00:00Z', work_origin='learner',
                      response='活动名称：换书。时间：待确认。地点：社区阅览室。参加条件：带一本书。',
                      artifact_refs=[], blocker='', criteria=copy.deepcopy(current['success_criteria']))
        result.update(changes)
        return result

    def feedback(self, attempt=None, *, kind='continue', target='next', result='met', **changes):
        attempt = attempt or self.attempt()
        if target == 'next':
            steps = [s for s in self.context['steps'] if s['path_id'] == attempt['path_id']]
            position = next(i for i, s in enumerate(steps) if s['step_id'] == attempt['step_id'])
            following = steps[position + 1] if position + 1 < len(steps) else steps[position]
            target = {key: following[key] for key in ('path_id', 'step_id')}
        feedback = dict(schema_version=1, id='feedback-one', attempt_id=attempt['id'],
                        attempt_hash=digest(attempt), context_hash=attempt['context_hash'],
                        created_at='2026-10-27T10:01:00Z', summary='只评价这一次提交的产物。', observations=[],
                        criteria=[dict(criterion_index=i, result=result,
                                       evidence=[] if result == 'not_observed' else [dict(field='response', quote='时间：待确认。')],
                                       reason='对照本次标准检查提交中的具体内容。') for i in range(len(attempt['criteria']))],
                        next_action=dict(kind=kind, reason='按这次产物选择下一项行动。', instructions=['保留原稿，完成所指任务。'],
                                         output='一份可复查的尝试记录。', stop_when='留下尝试结果后停下。', target=target))
        feedback.update(changes)
        return feedback

    def state(self, attempts=None, feedback=None):
        return dict(schema_version=1, package_id=self.context['package_id'],
                    attempts=attempts or [], feedback=feedback or [])

    def test_context_changes_with_plan_learner_source_or_material_bytes(self):
        before = copy.deepcopy((self.plan, self.corpus, self.learner))
        for change in ('activity', 'criterion', 'path', 'learner', 'source', 'material'):
            with self.subTest(change=change):
                plan, corpus, learner = copy.deepcopy((self.plan, self.corpus, self.learner))
                material_hashes = dict(self.material_hashes)
                if change == 'activity':
                    plan['activities'][0]['instructions'].append('保留一次改稿说明。')
                elif change == 'criterion':
                    plan['activities'][0]['success_criteria'].reverse()
                elif change == 'path':
                    plan['paths'][0]['steps'][0]['reason'] = '新的安排依据。'
                elif change == 'learner':
                    learner['minutes_per_session'] = 25
                    plan['learner_hash'] = digest(learner)
                elif change == 'source':
                    corpus['videos'][0]['title'] += '（修订）'
                    plan['source_hash'] = digest(corpus)
                else:
                    material_hashes['poster-brief'] = 'c' * 64
                self.assertNotEqual(index_feedback_context(plan, corpus, learner, material_hashes)['context_hash'],
                                    self.context['context_hash'])
        self.assertEqual(before, (self.plan, self.corpus, self.learner))

    def test_attempt_binding_keeps_same_topic_steps_and_criteria_distinct(self):
        first, second = self.attempt(), self.attempt(1, id='attempt-two')
        self.assertEqual(self.context['steps'][0]['topic_id'], self.context['steps'][1]['topic_id'])
        for attempt in (first, second):
            validate_learning_attempt(attempt, self.context)
        for changes in (dict(activity_id=second['activity_id']), dict(criteria=second['criteria']),
                        dict(step_id='absent'), dict(context_hash='0' * 64), dict(package_id='elsewhere')):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                validate_learning_attempt({**first, **changes}, self.context)
        # Old bindings remain structurally readable, but are not current.
        validate_learning_attempt({**first, 'context_hash': '0' * 64})

    def test_attempt_payload_and_provenance_are_explicit(self):
        validate_learning_attempt(self.attempt(response='', blocker='缺少输入素材'), self.context)
        validate_learning_attempt(self.attempt(response='', artifact_refs=['draft.png']), self.context)
        for changes in (dict(response='', blocker='', artifact_refs=[]), dict(work_origin='mastered'),
                        dict(artifact_refs=['a', 'a']), dict(created_at='not-a-date'),
                        dict(context_hash='short'), dict(watched=True), dict(criteria=[])):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                validate_learning_attempt({**self.attempt(), **changes}, self.context)

    def test_every_frozen_criterion_needs_valid_evidence_not_flags(self):
        attempt = self.attempt()
        validate_learning_feedback(self.feedback(attempt), attempt, self.context)
        mutations = [
            lambda f: f['criteria'].pop(),
            lambda f: f['criteria'][1].update(criterion_index=0),
            lambda f: f['criteria'][0].update(criterion_index=True),
            lambda f: f['criteria'][0].update(evidence=[]),
            lambda f: f['criteria'][0]['evidence'][0].update(quote='不存在的作业内容'),
            lambda f: f['criteria'][0]['evidence'][0].update(field='blocker'),
            lambda f: f['criteria'][0]['evidence'][0].update(field='practiced'),
            lambda f: f.update(score=100),
            lambda f: f.update(mastered=True),
            lambda f: f.update(attempt_hash='0' * 64),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                feedback = self.feedback(attempt)
                mutate(feedback)
                with self.assertRaises(ContractError):
                    validate_learning_feedback(feedback, attempt, self.context)

    def test_reference_and_unknown_work_can_only_receive_uncertain_performance_results(self):
        for origin in ('reference', 'unknown'):
            with self.subTest(origin=origin):
                attempt = self.attempt(work_origin=origin)
                for result in ('met', 'needs_work'):
                    with self.subTest(result=result), self.assertRaises(ContractError):
                        validate_learning_feedback(self.feedback(attempt, result=result), attempt, self.context)
                feedback = self.feedback(attempt, result='not_observed', kind='request_evidence', target=None)
                validate_learning_feedback(feedback, attempt, self.context)
        attempt = self.attempt(work_origin='assisted')
        validate_learning_feedback(self.feedback(attempt), attempt, self.context)

    def test_artifact_references_do_not_prove_inspection_without_observations(self):
        attempt = self.attempt(response='', artifact_refs=['draft.png'])
        feedback = self.feedback(attempt)
        for criterion in feedback['criteria']:
            criterion['evidence'] = [dict(observation_id='view-one')]
        with self.assertRaises(ContractError):
            validate_learning_feedback(feedback, attempt, self.context)
        observation = dict(id='view-one', artifact_ref='draft.png', method='view',
                           observation='图中列出四项活动信息，时间仍标为待确认。', limitations='只查看这一张图，未检查其他版本。')
        feedback['observations'] = [observation]
        validate_learning_feedback(feedback, attempt, self.context)
        for changes in (dict(artifact_ref='unsubmitted.png'), dict(method='guess'), dict(limitations='')):
            with self.subTest(changes=changes):
                feedback['observations'] = [{**observation, **changes}]
                with self.assertRaises(ContractError):
                    validate_learning_feedback(feedback, attempt, self.context)

    def test_navigation_actions_use_exact_current_path_and_step_boundaries(self):
        first, final = self.attempt(), self.attempt(1, id='final-attempt')
        here = dict(path_id=first['path_id'], step_id=first['step_id'])
        last = dict(path_id=final['path_id'], step_id=final['step_id'])
        alternative = dict(path_id='revise', step_id='revision')
        valid = [(first, 'continue', last), (first, 'retry', here), (final, 'revisit', here),
                 (first, 'switch_path', alternative), (first, 'resolve_gap', None),
                 (first, 'request_evidence', None), (final, 'finish', None)]
        for attempt, kind, target in valid:
            with self.subTest(kind=kind):
                validate_learning_feedback(self.feedback(attempt, kind=kind, target=target), attempt, self.context)
        invalid = [(first, 'continue', here), (final, 'continue', here), (first, 'retry', last),
                   (first, 'revisit', last), (final, 'switch_path', here),
                   (first, 'finish', None), (first, 'resolve_gap', last),
                   (first, 'request_evidence', here)]
        for attempt, kind, target in invalid:
            with self.subTest(invalid=kind, target=target), self.assertRaises(ContractError):
                validate_learning_feedback(self.feedback(attempt, kind=kind, target=target), attempt, self.context)
        for kind, attempt in [('continue', first), ('finish', final)]:
            with self.subTest(incomplete=kind), self.assertRaises(ContractError):
                validate_learning_feedback(self.feedback(attempt, kind=kind, target=None if kind == 'finish' else last,
                                                          result='not_observed'), attempt, self.context)

    def test_blocked_steps_do_not_advance_and_comparison_finish_does_not_resolve_coverage(self):
        for name in ('lookup', 'comparison'):
            corpus, learner, plan, _ = scenario_data(name)
            context = index_feedback_context(plan, corpus, learner)
            old_context = self.context
            self.context = context
            try:
                if name == 'lookup':
                    first, blocked = self.attempt(), self.attempt(1)
                    for attempt, kind, target in [(first, 'continue', 'next'), (blocked, 'retry', 'next'),
                                                   (blocked, 'finish', None)]:
                        with self.subTest(name=name, kind=kind), self.assertRaises(ContractError):
                            validate_learning_feedback(self.feedback(attempt, kind=kind, target=target), attempt, context)
                    validate_learning_feedback(self.feedback(blocked, kind='resolve_gap', target=None), blocked, context)
                else:
                    attempt = self.attempt()
                    before = copy.deepcopy(plan)
                    validate_learning_feedback(self.feedback(attempt, kind='finish', target=None), attempt, context)
                    self.assertEqual(plan, before)
                    self.assertEqual(plan['capabilities'][0]['coverage']['status'], 'conflicting')
            finally:
                self.context = old_context

    def test_history_is_immutable_and_repeated_import_is_idempotent(self):
        attempt = self.attempt()
        feedback = self.feedback(attempt)
        state = self.state([attempt, copy.deepcopy(attempt)], [feedback, copy.deepcopy(feedback)])
        before = copy.deepcopy(state)
        result = index_learning_feedback(self.context, state)
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(len(result['feedback']), 1)
        self.assertEqual(result['feedback'][0]['status'], 'current')
        self.assertTrue(result['feedback'][0]['actionable'])
        self.assertEqual(result['feedback'][0]['attempt'], attempt)
        self.assertEqual(before, state)
        for attempts, feedbacks in [([attempt, {**attempt, 'response': 'changed'}], [feedback]),
                                    ([attempt], [feedback, {**feedback, 'summary': 'changed'}])]:
            with self.subTest(attempts=attempts), self.assertRaises(ContractError):
                index_learning_feedback(self.context, self.state(attempts, feedbacks))

    def test_new_attempt_or_new_feedback_supersedes_older_guidance_by_append_order(self):
        first = self.attempt()
        newer = self.attempt(id='attempt-new', created_at='2026-10-27T09:59:00Z')
        feedback = self.feedback(first)
        result = index_learning_feedback(self.context, self.state([first, newer], [feedback]))
        self.assertEqual(result['feedback'][0]['status'], 'superseded')
        self.assertFalse(result['feedback'][0]['actionable'])
        changed_feedback = self.feedback(first, id='feedback-new')
        result = index_learning_feedback(self.context, self.state([first], [feedback, changed_feedback, feedback]))
        self.assertEqual([item['status'] for item in result['feedback']], ['superseded', 'current'])
        other_step = self.attempt(1, id='other-step')
        result = index_learning_feedback(self.context, self.state([first, other_step], [feedback]))
        self.assertEqual(result['feedback'][0]['status'], 'current')

    def test_stale_records_remain_visible_but_cannot_be_actionable_or_rebound(self):
        attempt = self.attempt()
        feedback = self.feedback(attempt)
        new_hashes = {**self.material_hashes, 'poster-brief': 'c' * 64}
        context = index_feedback_context(self.plan, self.corpus, self.learner, new_hashes)
        result = index_learning_feedback(context, self.state([attempt], [feedback]))
        self.assertEqual(result['feedback'][0]['status'], 'stale')
        self.assertFalse(result['feedback'][0]['actionable'])
        self.assertEqual(result['attempts'][0]['context_hash'], attempt['context_hash'])
        with self.assertRaises(ContractError):
            validate_learning_feedback(feedback, attempt, context)
        broken = copy.deepcopy(feedback)
        broken['criteria'][0]['evidence'][0]['quote'] = 'made-up'
        with self.assertRaises(ContractError):
            index_learning_feedback(context, self.state([attempt], [broken]))

    def test_late_history_from_an_old_context_does_not_supersede_current_guidance(self):
        current = self.attempt()
        late = self.attempt(id='late-old-attempt', context_hash='c' * 64)
        current_review = self.feedback(current)
        late_review = self.feedback(late, id='late-old-review')
        state = self.state([current, late], [current_review, late_review])
        projected = index_learning_feedback(self.context, state)
        self.assertEqual([f['status'] for f in projected['feedback']], ['current', 'stale'])
        self.assertTrue(projected['feedback'][0]['actionable'])
        self.assertFalse(projected['feedback'][1]['actionable'])
        self.assertEqual(projected['attempts'], [current, late])
        # A genuinely newer attempt in this context still supersedes its prior guidance.
        newer = self.attempt(id='new-current-attempt')
        projected = index_learning_feedback(self.context, self.state([current, late, newer], [current_review, late_review]))
        self.assertEqual([f['status'] for f in projected['feedback']], ['superseded', 'stale'])

    def test_state_rejects_cross_package_or_dangling_feedback_and_handles_empty_legacy(self):
        attempt = self.attempt()
        feedback = self.feedback(attempt)
        for state in (self.state([], [feedback]), {**self.state([attempt], [feedback]), 'package_id': 'another-package'}):
            with self.subTest(state=state), self.assertRaises(ContractError):
                index_learning_feedback(self.context, state)
        empty = index_learning_feedback(self.context, None)
        self.assertEqual(empty, dict(schema_version=1, package_id=self.context['package_id'], attempts=[], feedback=[]))
        self.assertEqual(index_learning_feedback(None, None)['feedback'], [])
        with self.assertRaises(ContractError):
            index_learning_feedback(None, self.state([attempt], [feedback]))


if __name__ == '__main__':
    unittest.main()
