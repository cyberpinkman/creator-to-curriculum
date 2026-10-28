"""Shared source/build boundaries keep the default journey resumable."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from creator_curriculum.cli import parser, run
from creator_curriculum.core import ContractError, digest, read_json, write_json
from creator_curriculum.feedback import feedback_context_for_workspace, record_attempt
from creator_curriculum.index import build_index
from creator_curriculum.index_workflow import initialize_index
from creator_curriculum.pipeline import initialize
from creator_curriculum.scenarios import scenario_data


class WorkspaceJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus, self.learner, self.plan, _ = scenario_data('concept')
        self.subtitle = self.root / 'lesson.srt'
        self.subtitle.write_text('1\n00:00:01,000 --> 00:00:02,000\nA newly supplied statement.\n', encoding='utf-8')

    def attach(self, workspace, subtitle=None):
        return run(parser().parse_args(['attach-transcript', str(workspace), '--video', self.corpus['videos'][0]['id'],
                                        '--file', str(subtitle or self.subtitle), '--source', 'platform_subtitles']))

    def snapshot(self, root):
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}

    def test_attach_transcript_refreshes_default_handoff_without_inventing_learner_or_deep_jobs(self):
        for known in (False, True):
            with self.subTest(known=known):
                root = self.root / str(known)
                learner = copy.deepcopy(self.learner)
                if not known:
                    learner.update(level=None, minutes_per_session=None)
                initialize_index(root, self.corpus, learner)
                plan = {**self.plan, 'learner_hash': digest(learner)}
                plan.pop('package_id', None)
                write_json(root / 'index-plan.json', plan)
                before_plan = (root / 'index-plan.json').read_bytes()
                result = self.attach(root)
                self.assertEqual(result['existing_plan']['status'], 'needs_revision')
                corpus = read_json(root / 'corpus.json')
                self.assertEqual(corpus['videos'][0]['transcript_source'], 'platform_subtitles')
                self.assertEqual(corpus['videos'][0]['segments'][0]['text'], 'A newly supplied statement.')
                self.assertEqual(read_json(root / 'planning-input.json')['source_hash'], digest(corpus))
                self.assertEqual(read_json(root / 'learner.json'), learner)
                self.assertEqual((root / 'index-plan.json').read_bytes(), before_plan)
                self.assertFalse((root / 'config.json').exists())
                self.assertFalse((root / 'jobs').exists())
                bad = self.root / 'plain.txt'
                bad.write_text('No timestamps; do not invent them.', encoding='utf-8')
                before = self.snapshot(root)
                with self.assertRaises(ContractError):
                    self.attach(root, bad)
                self.assertEqual(self.snapshot(root), before)

    def test_attach_transcript_retains_deep_preparation_and_invalid_input_is_nonmutating(self):
        root = self.root / 'deep'
        learner = dict(goal='Understand the source', level='beginner', language='en', minutes_per_session=30)
        initialize(root, self.corpus, learner)
        config = (root / 'config.json').read_bytes()
        result = self.attach(root)
        self.assertEqual(result['transcript_ready_count'], len(self.corpus['videos']))
        self.assertEqual(read_json(root / 'jobs/index.json')['active_jobs'], result['pending_jobs'])
        self.assertEqual((root / 'config.json').read_bytes(), config)
        bad = self.root / 'invalid.srt'
        bad.write_text('1\n00:00:03,000 --> 00:00:02,000\nInvalid order.\n', encoding='utf-8')
        before = self.snapshot(root)
        with self.assertRaises(ContractError):
            self.attach(root, bad)
        self.assertEqual(self.snapshot(root), before)

    def test_attach_preflights_workspace_metadata_before_replacing_evidence(self):
        for mode in ('index', 'deep'):
            with self.subTest(mode=mode):
                root = self.root / mode
                if mode == 'index':
                    initialize_index(root, self.corpus, self.learner)
                    write_json(root / 'index-workspace.json', {'schema_version': 99})
                else:
                    initialize(root, self.corpus, dict(goal='Understand the source', level='beginner', language='en', minutes_per_session=30))
                    write_json(root / 'config.json', {'schema_version': 1, 'max_chars': 1})
                before = self.snapshot(root)
                with self.assertRaises(ContractError):
                    self.attach(root)
                self.assertEqual(self.snapshot(root), before)

    def test_external_build_persists_the_same_input_version_used_by_feedback(self):
        inputs, out = self.root / 'inputs', self.root / 'output'
        for name, value in [('corpus.json', self.corpus), ('index-plan.json', self.plan), ('learner.json', self.learner)]:
            write_json(inputs / name, value)
        run(parser().parse_args(['build-index', '--corpus', str(inputs / 'corpus.json'), '--plan', str(inputs / 'index-plan.json'),
                                '--learner', str(inputs / 'learner.json'), '--out', str(out)]))
        record_attempt(out, path_id='start', step_id='explain', blocker='Please clarify this criterion.')
        changed = copy.deepcopy(self.plan)
        changed['activities'][0]['success_criteria'][0] = 'A changed standard for the next attempt.'
        build_index(self.corpus, changed, out, learner=self.learner)
        result = record_attempt(out, path_id='start', step_id='explain', blocker='Please clarify the new standard.')
        state = read_json(out / 'feedback-state.json')
        attempt = next(item for item in state['attempts'] if item['id'] == result['attempt_id'])
        display = read_json(out / 'index.json')['feedback_context']
        self.assertEqual(attempt['context_hash'], display['context_hash'])
        self.assertEqual(attempt['criteria'], display['steps'][0]['success_criteria'])
        self.assertEqual(read_json(out / 'index-plan.json'), changed)
        self.assertEqual(feedback_context_for_workspace(out), display)

    def test_preflight_failure_preserves_canonical_and_generated_files(self):
        out = self.root / 'output'
        build_index(self.corpus, self.plan, out, learner=self.learner)
        before = self.snapshot(out)
        bad_plan = {**self.plan, 'source_hash': '0' * 64}
        for label, plan in [('stale-plan', bad_plan), ('missing-material', {
                **self.plan, 'materials': [dict(id='missing', title='Missing', description='Must be supplied explicitly.',
                    origin='agent', status='local', availability='available', url=None,
                    local_path='materials/missing.md', topic_ids=[self.plan['topics'][0]['id']])]} )]:
            with self.subTest(label=label), self.assertRaises(ContractError):
                build_index(self.corpus, plan, out, learner=self.learner)
            self.assertEqual(self.snapshot(out), before)
        foreign_state = dict(schema_version=1, package_id='another-package', attempts=[], feedback=[])
        with self.assertRaises(ContractError):
            build_index(self.corpus, self.plan, out, learner=self.learner, feedback_state=foreign_state)
        self.assertEqual(self.snapshot(out), before)
        original = Path.read_text
        def unavailable_template(path, *args, **kwargs):
            if path.name == 'reader.html':
                raise OSError('Synthetic unavailable bundled reader template')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', unavailable_template), self.assertRaises(OSError):
            build_index(self.corpus, {**self.plan, 'title': 'A proposed update'}, out, learner=self.learner)
        self.assertEqual(self.snapshot(out), before)

    def test_materials_resolve_only_inside_output_and_cannot_be_overwritten_by_build(self):
        corpus, learner, plan, materials = scenario_data('project')
        inputs, out = self.root / 'input-files', self.root / 'project-output'
        for name, content in materials.items():
            path = inputs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        with self.assertRaisesRegex(ContractError, 'Material file missing'):
            build_index(corpus, plan, out, learner=learner)
        self.assertFalse(out.exists())
        for name, content in materials.items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content + '\nLearner-added content.\n', encoding='utf-8')
        before_materials = self.snapshot(out)
        build_index(corpus, plan, out, learner=learner)
        for name, content in before_materials.items():
            self.assertEqual((out / name).read_bytes(), content)
        alias = out / 'materials' / 'outside.md'
        alias.symlink_to(inputs / 'materials/poster-brief.md')
        for path in ['index-plan.json', 'materials/outside.md']:
            changed = copy.deepcopy(plan)
            changed['materials'][0]['local_path'] = path
            before = self.snapshot(out)
            with self.subTest(path=path), self.assertRaises(ContractError):
                build_index(corpus, changed, out, learner=learner)
            self.assertEqual(self.snapshot(out), before)

    def test_nonfeedback_build_does_not_create_history(self):
        out = self.root / 'output'
        build_index(self.corpus, self.plan, out, learner=self.learner)
        self.assertFalse((out / 'feedback-state.json').exists())


if __name__ == '__main__':
    unittest.main()
