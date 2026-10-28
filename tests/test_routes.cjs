'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Routes = require('../creator_curriculum/web/routes.js');

test('system pages and topics have disjoint addresses even when identities match', () => {
  const ids = ['overview', 'progress', 'materials', 'scope', 'knowledge-map', 'learning-advice', 'ordinary'];
  for (const id of ids.slice(0, -1)) {
    assert.deepEqual(Routes.resolve(id, ids), {route: id, topicId: null});
    assert.deepEqual(Routes.resolve(Routes.topic(id), ids), {route: 'topic/' + id, topicId: id});
  }
});

test('unambiguous legacy topic links normalize without changing topic identity', () => {
  assert.deepEqual(Routes.resolve('ordinary', ['ordinary']), {route: 'topic/ordinary', topicId: 'ordinary'});
  assert.deepEqual(Routes.resolve('topic/ordinary', ['ordinary']), {route: 'topic/ordinary', topicId: 'ordinary'});
  for (const route of ['', 'missing', 'topic/missing']) {
    assert.deepEqual(Routes.resolve(route, ['ordinary']), {route: 'overview', topicId: null});
  }
});

test('search and material detail routes stay page addresses', () => {
  for (const route of ['search=dynamic programming', 'materials/0']) {
    assert.deepEqual(Routes.resolve(route, ['ordinary']), {route, topicId: null});
  }
});

test('study addresses identify a specific path step even when steps share a topic', () => {
  const steps = {start: {observe: 'same', apply: 'same'}, review: {apply: 'same'}};
  for (const [pathId, stepId] of [['start', 'observe'], ['start', 'apply'], ['review', 'apply']]) {
    const route = Routes.study(pathId, stepId);
    assert.deepEqual(Routes.resolve(route, ['same'], steps), {route, topicId: 'same', pathId, stepId});
  }
  for (const route of ['study/start/missing', 'study/missing/apply', 'study/start/apply/extra']) {
    assert.deepEqual(Routes.resolve(route, ['same'], steps), {route: 'overview', topicId: null});
  }
  assert.deepEqual(Routes.resolve('study/start/apply', [], steps), {route: 'overview', topicId: null});
  assert.deepEqual(Routes.resolve('topic/same', ['same'], steps), {route: 'topic/same', topicId: 'same'});
  assert.deepEqual(Routes.resolve('study/constructor/toString', ['same'], {}), {route: 'overview', topicId: null});
});
