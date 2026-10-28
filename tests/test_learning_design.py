"""Shared planning invariants; authored inputs, no platform or learner data."""
import copy
import unittest

from creator_curriculum.core import (
    ContractError, digest, index_learning_design, index_paths,
    validate_index_learner, validate_index_plan,
)
from creator_curriculum.demo import demo_corpus


class LearningDesignTests(unittest.TestCase):
    def setUp(self):
        self.corpus = demo_corpus()
        self.video = next(video for video in self.corpus['videos'] if video['id'] == 'v_foundation')
        self.learner = dict(schema_version=1, goal='写出一个有依据的问题陈述', level='能描述一个实际场景',
                            language='zh-CN', minutes_per_session=20, mode='systematic',
                            prior_knowledge=[], constraints=[], assumptions=[])
        self.plan = dict(
            schema_version=2, package_id='authored-design-test', source_hash=digest(self.corpus),
            learner_hash=digest(self.learner), title='自写学习设计', goal=self.learner['goal'], overview='只用虚构材料。',
            topics=[dict(id='problem', title='问题陈述', group='问题', question='怎样描述问题？',
                         guidance='先区分，再改写。', video_ids=['v_foundation'], prerequisites=[])],
            reviews={'v_foundation': dict(note='仓库自写材料。', evidence=[
                dict(segment_id=s['id'], quote=s['text']) for s in self.video['segments']])},
            materials=[dict(id='worksheet', title='记录表', description='自写记录模板。', status='已提供入口',
                            origin='agent', availability='available', url='https://example.com/worksheet', topic_ids=['problem'])],
            capabilities=[
                dict(id='distinguish', title='区分问题与方案', outcome='能区分两个示例', required=True,
                     prerequisites=[], coverage=dict(status='supported', reason='原材料给出区分案例。',
                                                      sources=[dict(video_id='v_foundation', segment_ids=['s1'])])),
                dict(id='formulate', title='写问题陈述', outcome='写出一条陈述', required=True,
                     prerequisites=['distinguish'], coverage=dict(status='supported', reason='原材料给出句式。',
                                                                 sources=[dict(video_id='v_foundation', segment_ids=['s2'])])),
            ],
            activities=[self.activity('compare-example', 'distinguish', 'understand', 's1'),
                        self.activity('write-example', 'formulate', 'practice', 's2')],
            paths=[dict(id='start', title='从区分到改写', outcome='一条问题陈述', reason='先理解差别再应用。',
                        steps=[dict(id='notice', activity_id='compare-example', reason='先识别差别。'),
                               dict(id='write', activity_id='write-example', reason='再留下自己的陈述。')],
                        capability_exemptions=[], prerequisite_exemptions=[])])

    @staticmethod
    def activity(aid, capability, kind, segment):
        return dict(id=aid, title=aid, topic_id='problem', capability_ids=[capability], kind=kind,
                    objective='完成一个有限的小目标', instructions=['核对材料中的示例。', '留下自己的尝试。'],
                    output='一条可回看的尝试记录', success_criteria=['能够区分原话和自己的解释。'],
                    stop_when='留下记录和未解决的疑问后停下。', primary_video_id='v_foundation',
                    sources=[dict(video_id='v_foundation', segment_ids=[segment])],
                    required_material_ids=['worksheet'], practice_minutes=5)

    def validate(self, plan=None, learner=None):
        return validate_index_plan(plan or self.plan, self.corpus, learner or self.learner)

    def design(self, plan=None, learner=None):
        return index_learning_design(plan or self.plan, self.corpus, learner or self.learner)

    def test_current_brief_and_goal_are_required_and_changes_invalidate_plan(self):
        self.validate()
        with self.assertRaisesRegex(ContractError, 'expected an object'):
            validate_index_plan(self.plan, self.corpus)
        for change in (dict(goal='只查一个现成问题'), dict(level=None), dict(minutes_per_session=5),
                       dict(mode='problem'), dict(prior_knowledge=['已能独立写陈述']), dict(constraints=['没有记录模板'])):
            with self.subTest(change=change):
                learner = {**self.learner, **change}
                with self.assertRaisesRegex(ContractError, 'learner brief changed'):
                    self.validate(learner=learner)
        plan = copy.deepcopy(self.plan)
        plan['goal'] = '只换标题不能代表重新规划'
        with self.assertRaisesRegex(ContractError, 'goal must match'):
            self.validate(plan)
        learner = {**self.learner, 'goal': '另一个目标'}
        plan['learner_hash'] = digest(learner)
        with self.assertRaisesRegex(ContractError, 'goal must match'):
            self.validate(plan, learner)

    def test_explicit_unknowns_are_retained_without_inventing_fit(self):
        learner = {**self.learner, 'level': None, 'minutes_per_session': None}
        validate_index_learner(learner)
        plan = {**self.plan, 'learner_hash': digest(learner)}
        result = self.design(plan, learner)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any('已有基础尚未明确' in issue for issue in result['issues']))
        self.assertTrue(any('可用时间未知' in issue for issue in result['issues']))
        self.assertIsNone(learner['level'])
        for change in (dict(minutes_per_session=True), dict(minutes_per_session=0), dict(level=''),
                       dict(mode=[]), dict(assumptions='guess'), dict(schema_version=True)):
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_index_learner({**self.learner, **change})

    def test_activities_have_explicit_outputs_and_valid_source_material_references(self):
        mutations = [
            lambda p: p['activities'][0].pop('output'),
            lambda p: p['activities'][0].update(instructions=[]),
            lambda p: p['activities'][0].update(success_criteria=[]),
            lambda p: p['activities'][0].update(stop_when=''),
            lambda p: p['activities'][0].update(kind='watch'),
            lambda p: p['activities'][0].update(capability_ids=['invented']),
            lambda p: p['activities'][0].update(required_material_ids=['absent']),
            lambda p: p['activities'][0]['sources'][0].update(segment_ids=['invented']),
            lambda p: p['activities'][0].update(sources=[dict(video_id='v_questions', segment_ids=[])]),
            lambda p: p['activities'][0].update(primary_video_id='v_questions'),
            lambda p: p['activities'][0].update(practice_minutes=False),
            lambda p: p['activities'][0].pop('practice_minutes'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                plan = copy.deepcopy(self.plan)
                mutate(plan)
                with self.assertRaises(ContractError):
                    self.validate(plan)

    def test_supported_coverage_needs_exact_existing_reviewed_source_refs(self):
        for refs in ([], ['invented'], ['s1', 's1']):
            with self.subTest(refs=refs):
                plan = copy.deepcopy(self.plan)
                plan['capabilities'][0]['coverage']['sources'][0]['segment_ids'] = refs
                with self.assertRaises(ContractError):
                    self.validate(plan)
        plan = copy.deepcopy(self.plan)
        plan['reviews']['v_foundation']['evidence'][0]['quote'] = '作者没有说过的内容'
        with self.assertRaisesRegex(ContractError, 'not verbatim'):
            self.validate(plan)

    def test_gap_capability_needs_no_fake_topic_or_video_and_blocks_dependents(self):
        plan = copy.deepcopy(self.plan)
        plan['capabilities'].append(dict(id='context', title='补充场景基础', outcome='明确情境', required=True,
                                        prerequisites=[], coverage=dict(status='missing', reason='此作者没有讲。',
                                                                       sources=[], next_action='先补充场景描述的材料。')))
        plan['capabilities'][0]['prerequisites'] = ['context']
        self.validate(plan)
        result = self.design(plan)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual([step['readiness']['status'] for step in result['paths'][0]['steps']], ['blocked', 'blocked'])
        self.assertEqual(len(plan['topics']), 1)
        self.assertTrue(any('补充场景基础' in issue for issue in result['issues']))
        for status, expected in [('skipped', 'blocked'), ('assumed_known', 'ready')]:
            with self.subTest(status=status):
                plan['paths'][0]['capability_exemptions'] = [dict(capability_id='context', status=status,
                                                                 reason='本路径明确声明的起点假设或跳过。')]
                self.assertEqual(self.design(plan)['status'], expected)

    def test_candidate_or_conflicting_sources_do_not_unlock_later_capabilities(self):
        for status, source_refs in [('candidate', []), ('conflicting', ['s1', 's2'])]:
            with self.subTest(status=status):
                plan = copy.deepcopy(self.plan)
                plan['capabilities'][0]['coverage'].update(status=status, next_action='核对来源适用条件。')
                plan['capabilities'][0]['coverage']['sources'][0]['segment_ids'] = source_refs
                steps = self.design(plan)['paths'][0]['steps']
                self.assertEqual(steps[0]['readiness']['status'], 'needs_review')
                self.assertEqual(steps[1]['readiness']['status'], 'blocked')
        plan = copy.deepcopy(self.plan)
        plan['activities'][0]['sources'][0]['segment_ids'] = []
        steps = self.design(plan)['paths'][0]['steps']
        self.assertEqual(steps[0]['readiness']['status'], 'needs_review')
        self.assertEqual(steps[1]['readiness']['status'], 'blocked')

    def test_required_material_readiness_is_distinct_from_reference_validity(self):
        for availability in ('unknown', 'unavailable'):
            with self.subTest(availability=availability):
                plan = copy.deepcopy(self.plan)
                plan['materials'][0]['availability'] = availability
                self.validate(plan)
                self.assertEqual(self.design(plan)['status'], 'blocked')
        plan = copy.deepcopy(self.plan)
        plan['materials'][0].pop('url')
        with self.assertRaisesRegex(ContractError, 'actual URL or local file'):
            self.validate(plan)
        self.assertEqual(self.design()['status'], 'ready')

    def test_activity_source_selection_must_overlap_each_supported_capability_evidence(self):
        for selected, expected, following in [(['s2'], 'needs_review', 'blocked'),
                                               (['s1'], 'ready', 'ready'),
                                               (['s1', 's2'], 'ready', 'ready')]:
            with self.subTest(selected=selected):
                plan = copy.deepcopy(self.plan)
                plan['activities'][0]['sources'][0]['segment_ids'] = selected
                before = copy.deepcopy(plan)
                self.validate(plan)  # Mismatched evidence is a reviewable draft, not a broken document.
                steps = self.design(plan)['paths'][0]['steps']
                self.assertEqual(steps[0]['readiness']['status'], expected)
                self.assertEqual(steps[1]['readiness']['status'], following)
                self.assertEqual(plan, before)  # No automatic repair or substituted source evidence.
                if expected == 'needs_review':
                    self.assertTrue(any('尚未关联到能力覆盖依据' in issue for issue in steps[0]['readiness']['issues']))

    def test_same_topic_supports_distinct_ordered_steps_and_path_specific_activities(self):
        plan = copy.deepcopy(self.plan)
        plan['paths'].append(dict(id='refresh', title='直接练习', outcome='一条改写结果', reason='明确假设已有区分能力。',
                                 steps=[dict(id='apply', activity_id='write-example', reason='直接应用句式。')],
                                 capability_exemptions=[dict(capability_id='distinguish', status='assumed_known',
                                                             reason='这条复习路径假设用户已经会区分。')]))
        self.validate(plan)
        paths = index_paths(plan)
        self.assertEqual(paths[0]['topic_ids'], ['problem'])
        self.assertEqual([step['id'] for step in paths[0]['steps']], ['notice', 'write'])
        self.assertEqual(paths[1]['steps'][0]['topic_id'], 'problem')
        self.assertEqual(paths[0]['steps'][0]['activity_id'], 'compare-example')
        self.assertEqual(paths[1]['steps'][0]['activity_id'], 'write-example')
        plan['paths'].reverse()
        self.assertEqual(index_paths(plan)[0]['id'], 'start')
        self.assertEqual(self.design(plan)['status'], 'ready')

    def test_capability_graph_and_path_identity_are_validated_at_the_boundary(self):
        mutations = [
            lambda p: p['capabilities'][0].update(prerequisites=['formulate']),
            lambda p: p['capabilities'][0].update(prerequisites=['missing']),
            lambda p: p['paths'][0]['steps'][1].update(id='notice'),
            lambda p: p['paths'][0]['steps'][1].update(activity_id='missing'),
            lambda p: p['paths'][0].update(id='only-other'),
            lambda p: p['paths'][0]['steps'].pop(),
            lambda p: p.update(start_path=['problem']),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                plan = copy.deepcopy(self.plan)
                mutate(plan)
                with self.assertRaises(ContractError):
                    self.validate(plan)

    def test_declared_topic_prerequisites_still_apply_to_v2_steps(self):
        plan = copy.deepcopy(self.plan)
        plan['topics'].append({**copy.deepcopy(plan['topics'][0]), 'id': 'applied', 'prerequisites': ['problem']})
        plan['activities'][1]['topic_id'] = 'applied'
        self.validate(plan)
        plan['paths'][0]['steps'].reverse()
        with self.assertRaisesRegex(ContractError, 'requires earlier topics'):
            self.validate(plan)

    def test_unaddressed_goal_capabilities_are_visible_without_disabling_a_valid_first_step(self):
        plan = copy.deepcopy(self.plan)
        plan['capabilities'].append(dict(id='transfer', title='迁移到新情境', outcome='完成陌生场景任务', required=True,
                                        prerequisites=[], coverage=dict(status='missing', reason='材料没有涉及。',
                                                                       sources=[], next_action='补充迁移练习来源。')))
        result = self.design(plan)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['paths'][0]['steps'][0]['readiness']['status'], 'ready')
        self.assertTrue(any('迁移到新情境' in issue for issue in result['issues']))

    def test_practice_budget_is_only_a_lower_bound_and_projection_is_pure(self):
        before = copy.deepcopy(self.plan)
        self.design()
        self.assertEqual(self.plan, before)
        self.plan['activities'][0]['practice_minutes'] = 25
        result = self.design()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['paths'][0]['steps'][0]['readiness']['status'], 'needs_review')
        self.assertTrue(any('观看与准备时间另计' in issue for issue in result['issues']))

    def test_legacy_index_is_compatible_but_not_promoted_to_learning_design(self):
        legacy = {key: copy.deepcopy(value) for key, value in self.plan.items()
                  if key not in {'learner_hash', 'capabilities', 'activities', 'paths'}}
        legacy.update(schema_version=1, start_path=['problem'])
        result = index_learning_design(legacy, self.corpus)
        self.assertEqual(result['status'], 'legacy')
        self.assertEqual(result['paths'][0]['topic_ids'], ['problem'])
        self.assertNotIn('steps', result['paths'][0])


if __name__ == '__main__':
    unittest.main()
