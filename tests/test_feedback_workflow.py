import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from creator_curriculum.cli import parser, run
from creator_curriculum.core import ContractError, digest, read_json, write_json
from creator_curriculum.feedback import (feedback_context_for_workspace, prepare_feedback,
                                         record_attempt, record_feedback)
from creator_curriculum.index import build_index
from creator_curriculum.index_workflow import initialize_index, prepare_index
from creator_curriculum.scenarios import build_scenario, scenario_data


def uncertain_feedback(attempt):
    return dict(schema_version=1, id='review-one', attempt_id=attempt['id'], attempt_hash=digest(attempt),
                context_hash=attempt['context_hash'], created_at='2026-10-27T12:00:00Z',
                summary='尚未取得足够的产物证据，先补充本次尝试。', observations=[],
                criteria=[dict(criterion_index=i, result='not_observed', evidence=[], reason='没有可核对的完整产物。')
                          for i, _ in enumerate(attempt['criteria'])],
                next_action=dict(kind='request_evidence', target=None, reason='完成状态不能代替产物。',
                                 instructions=['提交本次实际产物，并保留不确定的部分。'],
                                 output='一份可核对的尝试记录', stop_when='提交产物和卡点后停下。'))


class FeedbackWorkflowTests(unittest.TestCase):
    def test_default_cli_handoff_and_feedback_rebuild_without_changing_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            source_files = {name: (root / name).read_bytes() for name in ['corpus.json', 'learner.json', 'index-plan.json']}
            result = run(parser().parse_args(['record-attempt', str(root), '--path', 'start', '--step', 'explain',
                                              '--blocker', '我还不知道怎样给出一个反例。']))
            state = read_json(root / 'feedback-state.json')
            attempt = state['attempts'][0]
            self.assertEqual(result['attempt_id'], attempt['id'])
            self.assertEqual(attempt['work_origin'], 'unknown')
            prepare_index(root)
            self.assertEqual(read_json(root / 'planning-input.json')['feedback_history']['path'], 'feedback-state.json')
            handoff = read_json(root / 'feedback-input.json')
            self.assertEqual(handoff['attempts'][0]['attempt_hash'], digest(attempt))
            feedback = uncertain_feedback(attempt)
            write_json(root / 'review.json', feedback)
            result = run(parser().parse_args(['record-feedback', str(root), '--file', str(root / 'review.json')]))
            self.assertEqual(result['status'], 'current')
            data = read_json(root / 'index.json')
            self.assertTrue(data['learning_feedback']['feedback'][0]['actionable'])
            self.assertIn('learning_feedback', (root / 'index.html').read_text())
            self.assertTrue((root / 'learning-feedback.md').exists())
            for name, before in source_files.items():
                self.assertEqual((root / name).read_bytes(), before)
            record_feedback(root, root / 'review.json')
            self.assertEqual(len(read_json(root / 'feedback-state.json')['feedback']), 1)

    def test_browser_import_is_atomic_immutable_and_flags_are_not_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            context = feedback_context_for_workspace(root)
            export = dict(schema_version=1, package_id=context['package_id'], attempts=[],
                          topics={'scale': dict(watched=True, practiced=True, mastered=True, notes='已完成')})
            write_json(root / 'browser.json', export)
            self.assertEqual(prepare_feedback(root, root / 'browser.json')['current_attempts'], 0)
            export.pop('attempts')  # Old browser exports contain no attempt history.
            write_json(root / 'browser.json', export)
            self.assertEqual(prepare_feedback(root, root / 'browser.json')['current_attempts'], 0)
            record_attempt(root, path_id='start', step_id='explain', response='目前只有口头完成声明。', work_origin='learner')
            attempt = read_json(root / 'feedback-state.json')['attempts'][0]
            export['attempts'] = [attempt]
            write_json(root / 'browser.json', export)
            self.assertEqual(prepare_feedback(root, root / 'browser.json')['history_attempts'], 1)
            before = (root / 'feedback-state.json').read_bytes()
            changed = {**attempt, 'response': '不允许覆盖既有产物'}
            new = {**attempt, 'id': 'a-valid-new-attempt'}
            export['attempts'] = [new, changed]
            write_json(root / 'browser.json', export)
            with self.assertRaisesRegex(ContractError, 'conflict'):
                prepare_feedback(root, root / 'browser.json')
            self.assertEqual((root / 'feedback-state.json').read_bytes(), before)
            export['attempts'] = [None]
            write_json(root / 'browser.json', export)
            with self.assertRaises(ContractError):
                prepare_feedback(root, root / 'browser.json')
            self.assertEqual((root / 'feedback-state.json').read_bytes(), before)

    def test_material_bytes_change_stales_feedback_without_rebinding_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('project', root)
            record_attempt(root, path_id='start', step_id='brief', blocker='还需要确认参加条件。')
            attempt = read_json(root / 'feedback-state.json')['attempts'][0]
            feedback = uncertain_feedback(attempt)
            write_json(root / 'review.json', feedback)
            record_feedback(root, root / 'review.json')
            old_context = feedback_context_for_workspace(root)
            material = root / 'materials/poster-brief.md'
            material.write_text(material.read_text() + '\n新增一个要核对的字段。\n')
            new_context = feedback_context_for_workspace(root)
            self.assertNotEqual(old_context['context_hash'], new_context['context_hash'])
            prepared = prepare_feedback(root)
            self.assertTrue(prepared['index_rebuilt'])
            review = read_json(root / 'index.json')['learning_feedback']['feedback'][0]
            self.assertEqual(review['status'], 'stale')
            self.assertFalse(review['actionable'])
            self.assertEqual(review['attempt'], attempt)
            self.assertEqual(prepare_feedback(root)['current_attempts'], 0)
            before = (root / 'feedback-state.json').read_bytes()
            with self.assertRaises(ContractError):
                record_feedback(root, root / 'review.json')
            self.assertEqual((root / 'feedback-state.json').read_bytes(), before)

    def test_invalid_assessment_does_not_write_or_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            record_attempt(root, path_id='start', step_id='explain', blocker='没有产物，只有疑问。')
            attempt = read_json(root / 'feedback-state.json')['attempts'][0]
            invalid = uncertain_feedback(attempt)
            invalid['criteria'][0].update(result='met', evidence=[dict(field='response', quote='并未提交的答案')])
            write_json(root / 'invalid.json', invalid)
            before = {name: (root / name).read_bytes() for name in ['feedback-state.json', 'index.html']}
            with self.assertRaises(ContractError):
                record_feedback(root, root / 'invalid.json')
            for name, raw in before.items():
                self.assertEqual((root / name).read_bytes(), raw)

    def test_new_attempt_refreshes_generated_guidance_for_conversation_and_import(self):
        for through_import in (False, True):
            with self.subTest(through_import=through_import), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                build_scenario('concept', root)
                record_attempt(root, path_id='start', step_id='explain', blocker='第一版需要补例子。')
                first = read_json(root / 'feedback-state.json')['attempts'][0]
                write_json(root / 'review.json', uncertain_feedback(first))
                record_feedback(root, root / 'review.json')
                page_before = (root / 'index.html').read_bytes()
                if through_import:
                    newer = {**first, 'id': 'new-imported-attempt', 'blocker': '第二版仍需核对。'}
                    write_json(root / 'attempt.json', newer)
                    prepare_feedback(root, root / 'attempt.json')
                else:
                    record_attempt(root, path_id='start', step_id='explain', blocker='第二版仍需核对。')
                state = read_json(root / 'feedback-state.json')
                projection = read_json(root / 'index.json')['learning_feedback']
                self.assertEqual(projection['attempts'], state['attempts'])
                self.assertEqual(projection['feedback'][0]['status'], 'superseded')
                self.assertFalse(projection['feedback'][0]['actionable'])
                self.assertEqual(read_json(root / 'learning-feedback.json'), projection)
                self.assertNotEqual((root / 'index.html').read_bytes(), page_before)

    def test_prepare_keeps_current_attempt_when_old_context_history_arrives_late(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            record_attempt(root, path_id='start', step_id='explain', blocker='当前尝试。')
            current = read_json(root / 'feedback-state.json')['attempts'][0]
            stale = {**current, 'id': 'late-old-context', 'context_hash': 'f' * 64}
            write_json(root / 'late.json', stale)
            result = prepare_feedback(root, root / 'late.json')
            self.assertEqual(result['current_attempts'], 1)
            self.assertEqual(read_json(root / 'feedback-input.json')['attempts'][0]['attempt'], current)
            self.assertIn(stale['id'], read_json(root / 'feedback-input.json')['historical_attempt_ids'])

    def test_no_change_prepare_or_identical_import_does_not_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            record_attempt(root, path_id='start', step_id='explain', blocker='保留本次疑问。')
            attempt = read_json(root / 'feedback-state.json')['attempts'][0]
            write_json(root / 'attempt.json', attempt)
            with patch('creator_curriculum.index.build_index') as rebuild:
                prepare_feedback(root)
                prepare_feedback(root, root / 'attempt.json')
                rebuild.assert_not_called()
            self.assertEqual(len(read_json(root / 'feedback-state.json')['attempts']), 1)

    def test_failed_refresh_does_not_commit_a_new_attempt_or_feedback(self):
        for operation in ('record', 'import', 'review'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                build_scenario('concept', root)
                record_attempt(root, path_id='start', step_id='explain', blocker='既有尝试。')
                first = read_json(root / 'feedback-state.json')['attempts'][0]
                write_json(root / 'incoming.json', {**first, 'id': 'incoming-attempt'})
                write_json(root / 'review.json', uncertain_feedback(first))
                names = ('feedback-state.json', 'feedback-input.json', 'learning-feedback.json',
                         'learning-feedback.md', 'index.json', 'index.html')
                before = {name: (root / name).read_bytes() for name in names}
                with patch('creator_curriculum.index.build_index', side_effect=OSError('simulated refresh failure')):
                    with self.assertRaises(OSError):
                        if operation == 'record':
                            record_attempt(root, path_id='start', step_id='explain', blocker='待保存的新尝试。')
                        elif operation == 'import':
                            prepare_feedback(root, root / 'incoming.json')
                        else:
                            record_feedback(root, root / 'review.json')
                self.assertEqual({name: (root / name).read_bytes() for name in names}, before)

    def test_feedback_uses_initialized_identity_and_rejects_unbound_manual_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            corpus, learner, plan, _ = scenario_data('concept')
            plan.pop('package_id')
            initialized = Path(temporary) / 'initialized'
            initialize_index(initialized, corpus, learner)
            write_json(initialized / 'index-plan.json', plan)
            expected = read_json(initialized / 'index-workspace.json')['package_id']
            record_attempt(initialized, path_id='start', step_id='explain', blocker='首次构建前记录实际问题。')
            state = read_json(initialized / 'feedback-state.json')
            self.assertEqual(state['package_id'], expected)
            self.assertEqual(state['attempts'][0]['package_id'], expected)
            self.assertEqual(read_json(initialized / 'index.json')['package_id'], expected)
            self.assertEqual(prepare_feedback(initialized)['current_attempts'], 1)

            manual = Path(temporary) / 'manual'
            for filename, value in [('corpus.json', corpus), ('learner.json', learner), ('index-plan.json', plan)]:
                write_json(manual / filename, value)
            with self.assertRaisesRegex(ContractError, 'run build-index'):
                record_attempt(manual, path_id='start', step_id='explain', blocker='不能绑定临时随机身份。')
            self.assertFalse((manual / 'feedback-state.json').exists())
            self.assertFalse((manual / 'index-workspace.json').exists())

    def test_prepare_recovers_when_html_publication_was_interrupted_after_history_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_scenario('concept', root)
            record_attempt(root, path_id='start', step_id='explain', blocker='第一版问题。')
            first = read_json(root / 'feedback-state.json')['attempts'][0]
            write_json(root / 'review.json', uncertain_feedback(first))
            record_feedback(root, root / 'review.json')
            old_page = (root / 'index.html').read_bytes()
            from creator_curriculum import index
            real_write = index.atomic_text

            def interrupt_html(path, body):
                if Path(path).name == 'index.html':
                    raise OSError('simulated interrupted HTML publication')
                return real_write(path, body)

            with patch.object(index, 'atomic_text', interrupt_html), self.assertRaises(OSError):
                record_attempt(root, path_id='start', step_id='explain', blocker='第二版新问题。')
            committed_state = read_json(root / 'feedback-state.json')
            self.assertEqual(len(committed_state['attempts']), 2)
            self.assertEqual(read_json(root / 'index.json')['learning_feedback']['feedback'][0]['status'], 'superseded')
            self.assertEqual((root / 'index.html').read_bytes(), old_page)
            result = prepare_feedback(root)
            self.assertTrue(result['index_rebuilt'])
            self.assertNotEqual((root / 'index.html').read_bytes(), old_page)
            self.assertEqual(read_json(root / 'feedback-state.json'), committed_state)
            # Recovery keeps the submitted ID; repeating the handoff must be quiet again.
            with patch('creator_curriculum.index.build_index') as rebuild:
                self.assertFalse(prepare_feedback(root)['index_rebuilt'])
                rebuild.assert_not_called()


if __name__ == '__main__':
    unittest.main()
