'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Progress = require('../creator_curriculum/web/progress.js');

function memoryStorage() {
  const values = new Map();
  return {
    values,
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, value); }
  };
}
function open(storage, extra = {}) {
  return Progress.create({packageId: 'creator-one', topicIds: ['a', 'b'], pathIds: ['start', 'short'],
    storage, now: () => '2026-10-27T02:00:00.000Z', ...extra});
}

test('position, selected path and separate self-reports survive reopening without implying mastery', () => {
  const storage = memoryStorage(), progress = open(storage);
  assert.equal(progress.visit('b').persisted, true);
  progress.selectPath('short');
  assert.deepEqual(progress.state.topics, {});
  progress.updateTopic('b', {watched: true, practiced: true, notes: 'Need another example'});
  const reopened = open(storage);
  assert.equal(reopened.state.last_topic_id, 'b');
  assert.equal(reopened.state.selected_path_id, 'short');
  assert.deepEqual(reopened.state.topics.b, {
    watched: true, practiced: true, review: false, mastered: false, notes: 'Need another example'
  });
  reopened.updateTopic('b', {mastered: true, review: true});
  reopened.updateTopic('b', {watched: false});
  assert.equal(reopened.state.topics.b.mastered, true);
  assert.equal(reopened.state.topics.b.review, true);
});

test('three packages stay isolated, and reorder or missing topics never erase records', () => {
  const storage = memoryStorage();
  for (const [packageId, topic] of [['creator-one', 'a'], ['creator-two', 'b'], ['creator-three', 'a']]) {
    const progress = open(storage, {packageId});
    progress.visit(topic);
    progress.updateTopic(topic, {notes: packageId});
  }
  const reordered = open(storage, {topicIds: ['b', 'a'], pathIds: ['short', 'start']});
  assert.equal(reordered.state.topics.a.notes, 'creator-one');
  assert.equal(reordered.state.selected_path_id, 'start');
  const missing = open(storage, {topicIds: ['b'], pathIds: ['short']});
  assert.deepEqual(missing.status().orphaned_topic_ids, ['a']);
  assert.equal(missing.status().missing_last_topic_id, 'a');
  assert.equal(missing.status().missing_path_id, 'start');
  assert.ok(missing.warnings.length >= 2);
  missing.updateTopic('b', {watched: true});
  assert.equal(open(storage).state.topics.a.notes, 'creator-one');
  assert.equal(open(storage, {packageId: 'creator-two'}).state.topics.b.notes, 'creator-two');
  assert.equal(open(storage, {packageId: 'creator-three'}).state.topics.a.notes, 'creator-three');
});

test('write failure retains exportable memory, reports failure and can recover', () => {
  const storage = memoryStorage(), originalSet = storage.setItem;
  const progress = open(storage);
  storage.setItem = () => { throw new Error('QuotaExceededError'); };
  const result = progress.updateTopic('a', {notes: 'keep me'});
  assert.equal(result.ok, true);
  assert.equal(result.persisted, false);
  assert.match(result.error, /QuotaExceededError/);
  assert.equal(JSON.parse(progress.exportText()).topics.a.notes, 'keep me');
  assert.equal(storage.values.size, 0);
  storage.setItem = originalSet;
  assert.equal(progress.visit('a').persisted, true);
  assert.equal(progress.error, null);
  assert.equal(open(storage).state.topics.a.notes, 'keep me');
});

test('blocked reads, corrupt records and unsupported versions are never silently overwritten', () => {
  for (const raw of ['{broken', JSON.stringify({schema_version: 2, private_note: 'future data'})]) {
    const storage = memoryStorage(), key = open(storage).key;
    storage.values.set(key, raw);
    const progress = open(storage);
    assert.equal(progress.status().blocked, true);
    assert.equal(progress.raw, raw);
    assert.equal(progress.visit('a').persisted, false);
    assert.equal(storage.values.get(key), raw);
    const valid = open(memoryStorage()); valid.updateTopic('b', {notes: 'imported'});
    assert.equal(progress.importText(valid.exportText()).persisted, false);
    assert.equal(progress.state.topics.b.notes, 'imported');
    assert.equal(storage.values.get(key), raw);
  }
  let writes = 0;
  const blocked = open({getItem() { throw new Error('SecurityError'); }, setItem() { writes++; }});
  assert.match(blocked.error, /SecurityError/);
  blocked.updateTopic('a', {notes: 'session only'});
  assert.equal(writes, 0);
  assert.equal(blocked.status().persisted, false);
});

test('import validates before mutation, merges orphaned IDs, and never deletes other topics', () => {
  const progress = open(memoryStorage());
  progress.updateTopic('a', {notes: 'local note'});
  const original = progress.exportText();
  const base = JSON.parse(original);
  for (const invalid of [
    '{bad',
    JSON.stringify({...base, package_id: 'someone-else'}),
    JSON.stringify({...base, schema_version: 7}),
    JSON.stringify({...base, topics: {b: {watched: 'yes'}}}),
    JSON.stringify({...base, last_topic_id: []}),
    JSON.stringify({...base, topics: []})
  ]) {
    assert.equal(progress.importText(invalid).ok, false);
    assert.equal(progress.exportText(), original);
  }
  const incoming = open(memoryStorage(), {topicIds: ['b', 'removed'], pathIds: ['old']});
  incoming.visit('removed');
  incoming.updateTopic('removed', {review: true, notes: 'preserve orphan'});
  incoming.updateTopic('b', {practiced: true});
  assert.equal(progress.importText(incoming.exportText()).ok, true);
  assert.equal(progress.state.topics.a.notes, 'local note');
  assert.equal(progress.state.topics.removed.notes, 'preserve orphan');
  assert.equal(progress.state.topics.b.practiced, true);
  assert.equal(progress.state.last_topic_id, 'removed');
  assert.deepEqual(progress.status().orphaned_topic_ids, ['removed']);
  assert.equal(progress.status().missing_path_id, 'old');
});

test('invalid edits and caller mutation cannot corrupt saved state', () => {
  const progress = open(memoryStorage());
  progress.updateTopic('a', {notes: 'safe'});
  const original = progress.exportText();
  assert.equal(progress.visit('unknown').ok, false);
  assert.equal(progress.selectPath('unknown').ok, false);
  assert.equal(progress.updateTopic('a', {mastered: 'true'}).ok, false);
  assert.equal(progress.updateTopic('a', {surprise: true}).ok, false);
  assert.equal(progress.updateTopic('a', {notes: null}).ok, false);
  progress.state.topics.a.notes = 'mutated snapshot';
  assert.equal(progress.exportText(), original);
});

test('identifier names that match object prototype properties are safe record keys', () => {
  const storage = memoryStorage();
  const progress = open(storage, {topicIds: ['__proto__', 'constructor']});
  assert.equal(progress.updateTopic('__proto__', {notes: 'valid stable id'}).ok, true);
  assert.equal(progress.updateTopic('constructor', {watched: true}).ok, true);
  const reopened = open(storage, {topicIds: ['__proto__', 'constructor']});
  assert.equal(reopened.state.topics.__proto__.notes, 'valid stable id');
  assert.equal(reopened.state.topics.constructor.watched, true);
  assert.equal({}.watched, undefined);
});

test('changed sources require explicit acknowledgement, never a visit or ordinary record edit', () => {
  const storage = memoryStorage();
  const original = open(storage, {topicVersions: {a: 'source-v1', b: 'b-v1'}});
  original.updateTopic('a', {mastered: true, notes: 'understood original source'});
  original.visit('b');
  const updated = open(storage, {topicVersions: {a: 'source-v2', b: 'b-v1'}});
  assert.deepEqual(updated.status().changed_topic_ids, ['a']);
  updated.visit('a');
  assert.deepEqual(updated.status().changed_topic_ids, ['a']);
  assert.equal(updated.state.topic_versions.a, 'source-v1');
  assert.equal(updated.state.topics.a.mastered, true);
  assert.equal(updated.state.topics.a.notes, 'understood original source');
  for (const patch of [{notes: 'New source not watched yet'}, {review: true}, {mastered: false}]) {
    updated.updateTopic('a', patch);
    assert.deepEqual(updated.status().changed_topic_ids, ['a']);
    assert.equal(updated.state.topic_versions.a, 'source-v1');
  }
  const selfReport = updated.state.topics.a;
  assert.equal(updated.acknowledgeSource('a').persisted, true);
  assert.deepEqual(updated.status().changed_topic_ids, []);
  assert.equal(updated.state.topic_versions.a, 'source-v2');
  assert.deepEqual(updated.state.topics.a, selfReport);
  assert.deepEqual(open(storage, {topicVersions: {a: 'source-v2'}}).status().changed_topic_ids, []);
});

test('import of older unversioned self-reports does not borrow newer local source provenance', () => {
  const current = open(memoryStorage(), {topicVersions: {a: 'new-source'}});
  current.updateTopic('a', {notes: 'newer note'});
  const legacy = open(memoryStorage());
  legacy.updateTopic('a', {mastered: true, notes: 'older self-report'});
  const imported = JSON.parse(legacy.exportText());
  delete imported.topic_versions;
  current.importText(JSON.stringify(imported));
  assert.equal(current.state.topics.a.notes, 'older self-report');
  assert.deepEqual(current.status().unversioned_topic_ids, ['a']);
  assert.equal(current.state.topic_versions.a, undefined);
  current.visit('a');
  assert.deepEqual(current.status().unversioned_topic_ids, ['a']);
  assert.equal(current.state.topic_versions.a, undefined);
  current.updateTopic('a', {notes: 'This older note still needs checking'});
  assert.deepEqual(current.status().unversioned_topic_ids, ['a']);
  assert.equal(current.state.topic_versions.a, undefined);
  const selfReport = current.state.topics.a;
  current.acknowledgeSource('a');
  assert.deepEqual(current.status().unversioned_topic_ids, []);
  assert.deepEqual(current.state.topics.a, selfReport);
});

test('source acknowledgement rejects unavailable identity or provenance without mutation', () => {
  const progress = open(memoryStorage(), {topicVersions: {a: 'source-v1'}});
  progress.updateTopic('a', {notes: 'keep me'});
  const original = progress.exportText();
  for (const id of ['unknown', 'b']) {
    assert.equal(progress.acknowledgeSource(id).ok, false);
    assert.equal(progress.exportText(), original);
  }
});

test('study positions belong to each path and are independent of lookup, self-reports and source acceptance', () => {
  const storage = memoryStorage();
  const options = {pathTopics: {start: ['a', 'b'], short: ['b']}, topicVersions: {a: 'v1'}};
  const progress = open(storage, options);
  progress.updateTopic('a', {mastered: true});
  assert.equal(progress.startTask('start', 'a').persisted, true);
  progress.visit('b');
  progress.selectPath('short');
  assert.equal(progress.startTask('short', 'b').persisted, true);
  progress.selectPath('start');
  const reopened = open(storage, {...options, topicVersions: {a: 'v2'}});
  assert.deepEqual(reopened.state.study_topic_ids, {start: 'a', short: 'b'});
  assert.equal(reopened.state.last_topic_id, 'b');
  assert.equal(reopened.state.selected_path_id, 'start');
  assert.equal(reopened.state.topics.a.mastered, true);
  assert.equal(reopened.state.topics.b, undefined);
  assert.deepEqual(reopened.status().changed_topic_ids, ['a']);
  reopened.startTask('start', 'a');
  assert.deepEqual(reopened.status().changed_topic_ids, ['a']);
});

test('study positions preserve removed paths, removed topics and changed membership without guessing replacements', () => {
  const storage = memoryStorage();
  const progress = open(storage, {topicIds: ['a', 'b', 'gone'], pathIds: ['start', 'short', 'old'],
    pathTopics: {start: ['a', 'b'], short: ['gone'], old: ['b']}});
  progress.startTask('start', 'a');
  progress.startTask('short', 'gone');
  progress.startTask('old', 'b');
  const reopened = open(storage, {pathTopics: {start: ['b'], short: ['a']}});
  assert.deepEqual(reopened.state.study_topic_ids, {start: 'a', short: 'gone', old: 'b'});
  assert.deepEqual(reopened.status().unavailable_study_positions, [
    {path_id: 'start', topic_id: 'a', reason: 'outside_path'},
    {path_id: 'short', topic_id: 'gone', reason: 'missing_topic'},
    {path_id: 'old', topic_id: 'b', reason: 'missing_path'}
  ]);
  assert.ok(reopened.warnings.some(text => /学习位置/.test(text)));
  reopened.startTask('start', 'b');
  assert.deepEqual(JSON.parse(reopened.exportText()).study_topic_ids, {start: 'b', short: 'gone', old: 'b'});
});

test('v1 records without study positions remain compatible and imports merge positions per path', () => {
  const storage = memoryStorage();
  const options = {pathTopics: {start: ['a', 'b'], short: ['b']}};
  const legacy = open(memoryStorage());
  legacy.visit('b');
  const oldRecord = JSON.parse(legacy.exportText());
  delete oldRecord.study_topic_ids;
  storage.values.set(legacy.key, JSON.stringify(oldRecord));
  const progress = open(storage, options);
  assert.equal(progress.status().blocked, false);
  assert.deepEqual(progress.state.study_topic_ids, {});
  assert.equal(progress.state.last_topic_id, 'b');
  progress.startTask('start', 'a');
  progress.startTask('short', 'b');
  const incoming = open(memoryStorage(), {pathIds: ['start', 'archived'],
    pathTopics: {start: ['a', 'b'], archived: ['a']}});
  incoming.startTask('start', 'b');
  incoming.startTask('archived', 'a');
  assert.equal(progress.importText(incoming.exportText()).persisted, true);
  assert.deepEqual(progress.state.study_topic_ids, {start: 'b', short: 'b', archived: 'a'});
  progress.importText(JSON.stringify(oldRecord));
  assert.deepEqual(progress.state.study_topic_ids, {start: 'b', short: 'b', archived: 'a'});
});

test('study position edits and imports enforce identities and path membership before mutation', () => {
  const progress = open(memoryStorage(), {pathTopics: {start: ['a'], short: ['b']}});
  const original = progress.exportText();
  for (const [path, topic] of [['unknown', 'a'], ['start', 'unknown'], ['start', 'b']]) {
    assert.equal(progress.startTask(path, topic).ok, false);
    assert.equal(progress.exportText(), original);
  }
  assert.equal(open(memoryStorage()).startTask('start', 'a').ok, false);
  for (const value of [[], null, {start: null}, {start: 'invalid/id'}, {'invalid/id': 'a'}]) {
    const incoming = {...JSON.parse(original), study_topic_ids: value};
    assert.equal(progress.importText(JSON.stringify(incoming)).ok, false);
    assert.equal(progress.exportText(), original);
  }
  for (const pathTopics of [[], {start: ['unknown']}, {unknown: ['a']}, {start: 'a'}, {start: ['a', 'a']}]) {
    assert.throws(() => open(memoryStorage(), {pathTopics}), /路径/);
  }
  const named = open(memoryStorage(), {topicIds: ['__proto__'], pathIds: ['constructor'],
    pathTopics: {constructor: ['__proto__']}});
  assert.equal(named.startTask('constructor', '__proto__').ok, true);
  assert.equal(named.state.study_topic_ids.constructor, '__proto__');
});

test('imported position cannot silently reattribute an existing self-report to newer source content', () => {
  const storage = memoryStorage();
  const previous = open(storage, {topicVersions: {a: 'old-source'}});
  previous.updateTopic('a', {mastered: true});
  const current = open(storage, {topicVersions: {a: 'new-source'}});
  const visited = open(memoryStorage(), {topicVersions: {a: 'new-source'}});
  visited.visit('a');
  current.importText(visited.exportText());
  assert.equal(current.state.topics.a.mastered, true);
  assert.equal(current.state.topic_versions.a, 'old-source');
  assert.deepEqual(current.status().changed_topic_ids, ['a']);
});

test('stale controllers cannot overwrite newer notes with a visit or personal edit', () => {
  for (const operation of [progress => progress.visit('b'), progress => progress.updateTopic('b', {notes: 'my unsaved edit'}),
    progress => progress.startTask('start', 'b'), progress => progress.acknowledgeSource('a')]) {
    const storage = memoryStorage(), first = open(storage), stale = open(storage, {
      pathTopics: {start: ['a', 'b']}, topicVersions: {a: 'v2'}});
    first.updateTopic('a', {notes: 'saved in the other window'});
    const saved = storage.values.get(first.key);
    const result = operation(stale);
    assert.equal(result.persisted, false);
    assert.match(result.error, /其他窗口/);
    assert.equal(stale.status().blocked, true);
    assert.equal(storage.values.get(first.key), saved);
    assert.equal(stale.raw, saved);
    stale.updateTopic('b', {review: true});
    assert.equal(JSON.parse(stale.exportText()).topics.b.review, true);
    assert.equal(storage.values.get(first.key), saved);
    assert.equal(open(storage).state.topics.a.notes, 'saved in the other window');
  }
});

test('future versions or external deletions appearing after load are preserved on save', () => {
  for (const replacement of [JSON.stringify({schema_version: 4, private_note: 'future record'}), null]) {
    const storage = memoryStorage(), progress = open(storage);
    progress.updateTopic('a', {notes: 'loaded baseline'});
    if (replacement === null) storage.values.delete(progress.key);
    else storage.values.set(progress.key, replacement);
    const result = progress.visit('b');
    assert.equal(result.persisted, false);
    assert.equal(progress.status().blocked, true);
    assert.equal(storage.getItem(progress.key), replacement);
    assert.equal(progress.raw, replacement);
    assert.equal(JSON.parse(progress.exportText()).topics.a.notes, 'loaded baseline');
  }
});

test('failure to check the latest record blocks writes instead of assuming no concurrent changes', () => {
  const storage = memoryStorage(), progress = open(storage);
  progress.updateTopic('a', {notes: 'saved before access changed'});
  const saved = storage.values.get(progress.key);
  storage.getItem = () => { throw new Error('SecurityError'); };
  const result = progress.updateTopic('a', {notes: 'session only'});
  assert.equal(result.persisted, false);
  assert.equal(progress.status().blocked, true);
  assert.match(result.error, /SecurityError/);
  assert.equal(storage.values.get(progress.key), saved);
  assert.equal(JSON.parse(progress.exportText()).topics.a.notes, 'session only');
});

const designedPaths = {
  pathTopics: {start: ['a', 'b'], short: ['a']},
  pathSteps: {start: {observe: 'a', apply: 'a', finish: 'b'}, short: {compare: 'a'}}
};

test('activity positions preserve repeated-topic steps per path without marking learning', () => {
  const storage = memoryStorage(), progress = open(storage, designedPaths);
  progress.startStep('start', 'observe');
  progress.startStep('start', 'apply');
  progress.startStep('short', 'compare');
  progress.visit('b');
  const reopened = open(storage, designedPaths);
  assert.deepEqual(reopened.state.study_step_ids, {start: 'apply', short: 'compare'});
  assert.equal(reopened.state.last_topic_id, 'b');
  assert.deepEqual(reopened.state.topics, {});
  assert.deepEqual(reopened.state.study_topic_ids, {});
  assert.equal(reopened.startTask('start', 'a').ok, false);
  reopened.selectPath('start');
  assert.equal(reopened.state.study_step_ids.start, 'apply');
});

test('legacy topic positions do not become guessed activity steps', () => {
  const storage = memoryStorage(), legacy = open(storage, {pathTopics: designedPaths.pathTopics});
  legacy.startTask('start', 'a');
  const record = JSON.parse(legacy.exportText()); delete record.study_step_ids;
  storage.values.set(legacy.key, JSON.stringify(record));
  const current = open(storage, designedPaths);
  assert.deepEqual(current.state.study_step_ids, {});
  assert.deepEqual(current.state.study_topic_ids, {start: 'a'});
  assert.deepEqual(current.status().unassigned_step_paths, ['start']);
  current.startStep('start', 'apply');
  assert.deepEqual(current.status().unassigned_step_paths, []);
  assert.deepEqual(current.state.study_topic_ids, {start: 'a'});
});

test('removed steps and paths stay exportable and cannot silently resume another activity', () => {
  const storage = memoryStorage(), original = open(storage, designedPaths);
  original.startStep('start', 'apply'); original.startStep('short', 'compare');
  const current = open(storage, {pathIds: ['start'], pathTopics: {start: ['a', 'b']},
    pathSteps: {start: {observe: 'a', finish: 'b'}}});
  assert.deepEqual(current.state.study_step_ids, {start: 'apply', short: 'compare'});
  assert.deepEqual(current.status().unavailable_study_steps, [
    {path_id: 'start', step_id: 'apply', reason: 'missing_step'},
    {path_id: 'short', step_id: 'compare', reason: 'missing_path'}
  ]);
  current.startStep('start', 'finish');
  assert.deepEqual(JSON.parse(current.exportText()).study_step_ids, {start: 'finish', short: 'compare'});
});

test('activity imports merge per path and older records cannot clear step positions', () => {
  const local = open(memoryStorage(), designedPaths), incoming = open(memoryStorage(), designedPaths);
  local.startStep('start', 'observe'); local.startStep('short', 'compare');
  incoming.startStep('start', 'apply');
  assert.equal(local.importText(incoming.exportText()).ok, true);
  assert.deepEqual(local.state.study_step_ids, {start: 'apply', short: 'compare'});
  const old = JSON.parse(incoming.exportText()); delete old.study_step_ids;
  assert.equal(local.importText(JSON.stringify(old)).ok, true);
  assert.deepEqual(local.state.study_step_ids, {start: 'apply', short: 'compare'});
  const archived = {...old, study_step_ids: {old_path: 'old_step'}};
  assert.equal(local.importText(JSON.stringify(archived)).ok, true);
  assert.equal(local.state.study_step_ids.old_path, 'old_step');
  assert.ok(local.status().unavailable_study_steps.some(item => item.path_id === 'old_path'));
});

test('activity identities and registry membership are validated before mutation', () => {
  const progress = open(memoryStorage(), designedPaths), original = progress.exportText();
  for (const pair of [['missing', 'observe'], ['start', 'compare'], ['start', 'missing']]) {
    assert.equal(progress.startStep(...pair).ok, false);
    assert.equal(progress.exportText(), original);
  }
  for (const study_step_ids of [null, [], {start: null}, {'invalid/id': 'observe'}, {start: 'invalid/id'}]) {
    assert.equal(progress.importText(JSON.stringify({...JSON.parse(original), study_step_ids})).ok, false);
    assert.equal(progress.exportText(), original);
  }
  for (const pathSteps of [{unknown: {first: 'a'}}, {start: {first: 'unknown'}}, {short: {first: 'b'}}, {start: []}]) {
    assert.throws(() => open(memoryStorage(), {...designedPaths, pathSteps}), /步骤/);
  }
  const named = open(memoryStorage(), {topicIds: ['a'], pathIds: ['constructor'],
    pathTopics: {constructor: ['a']}, pathSteps: {constructor: JSON.parse('{"__proto__":"a"}')}});
  assert.equal(named.startStep('constructor', '__proto__').ok, true);
  assert.equal(named.state.study_step_ids.constructor, '__proto__');
});

test('a stale activity continuation cannot overwrite a newer saved record', () => {
  const storage = memoryStorage(), first = open(storage, designedPaths), stale = open(storage, designedPaths);
  first.updateTopic('a', {notes: 'saved elsewhere'});
  const saved = storage.values.get(first.key);
  const result = stale.startStep('start', 'apply');
  assert.equal(result.persisted, false);
  assert.match(result.error, /其他窗口/);
  assert.equal(storage.values.get(first.key), saved);
  assert.equal(JSON.parse(stale.exportText()).study_step_ids.start, 'apply');
});

// Synthetic context and CLI-validated display projection; no automatic assessment.
const feedbackHash = 'a'.repeat(64);
const feedbackContext = {schema_version: 1, package_id: 'creator-one', context_hash: feedbackHash, steps: [
  {path_id: 'start', step_id: 'observe', activity_id: 'explain', topic_id: 'a', success_criteria: ['Give a reason'], readiness: {status: 'ready'}},
  {path_id: 'start', step_id: 'apply', activity_id: 'make', topic_id: 'a', success_criteria: ['Show the result'], readiness: {status: 'ready'}},
  {path_id: 'start', step_id: 'finish', activity_id: 'review', topic_id: 'b', success_criteria: ['Compare results'], readiness: {status: 'ready'}},
  {path_id: 'short', step_id: 'compare', activity_id: 'compare', topic_id: 'a', success_criteria: ['Name the difference'], readiness: {status: 'ready'}}
]};
const attemptFields = {response: 'Because this preserves the original.', artifact_refs: [], blocker: '', work_origin: 'learner'};
function attempt(id = 'attempt-one', stepId = 'observe') {
  const step = feedbackContext.steps.find(item => item.step_id === stepId);
  return {schema_version: 1, id, package_id: 'creator-one', context_hash: feedbackHash, path_id: step.path_id,
    step_id: stepId, activity_id: step.activity_id, created_at: '2026-10-27T02:00:00.000Z', ...attemptFields, criteria: step.success_criteria};
}
function projection(attempts = [attempt()], feedback = null) {
  return {schema_version: 1, package_id: 'creator-one', attempts, feedback: feedback || [{
    schema_version: 1, id: 'feedback-one', attempt_id: attempts[0].id, attempt_hash: 'b'.repeat(64), context_hash: feedbackHash,
    created_at: '2026-10-27T03:00:00.000Z', summary: 'The reason is visible in this attempt.', observations: [],
    criteria: [{criterion_index: 0, result: 'met', evidence: [{field: 'response', quote: 'preserves the original'}], reason: 'Explicit reasoning'}],
    next_action: {kind: 'continue', reason: 'Try the next activity', instructions: ['Make one example'], output: 'An example', stop_when: 'Example saved', target: {path_id: 'start', step_id: 'apply'}},
    status: 'current', actionable: true, attempt: attempts[0]
  }]};
}
function feedbackOptions(extra = {}) {
  let sequence = 0;
  return {...designedPaths, feedbackContext, idFactory: prefix => prefix + '-local-' + (++sequence), ...extra};
}

test('attempts bind to an exact step, append immutably and leave positions and all self-reports unchanged', () => {
  const progress = open(memoryStorage(), feedbackOptions());
  progress.startStep('start', 'observe'); progress.updateTopic('a', {watched: true, practiced: true, review: true, mastered: true, notes: 'manual'});
  const initial = progress.state;
  assert.equal(progress.appendAttempt('start', 'observe', attemptFields).persisted, true);
  assert.equal(progress.appendAttempt('start', 'apply', {...attemptFields, response: 'A different activity'}).ok, true);
  assert.equal(progress.appendAttempt('start', 'observe', {...attemptFields, blocker: 'Still unsure'}).ok, true);
  assert.equal(progress.state.attempts.length, 3);
  assert.deepEqual(progress.attemptEntries('start', 'observe').map(item => item.attempt.criteria), [['Give a reason'], ['Give a reason']]);
  assert.equal(progress.attemptEntries('start', 'apply').length, 1);
  assert.deepEqual(progress.state.topics, initial.topics);
  assert.deepEqual(progress.state.study_step_ids, initial.study_step_ids);
  assert.deepEqual(progress.state.topic_versions, initial.topic_versions);
  assert.equal(progress.state.last_topic_id, initial.last_topic_id);
  const saved = progress.exportText();
  for (const fields of [{...attemptFields, score: 1}, {...attemptFields, response: ''}, {...attemptFields, artifact_refs: ['x', 'x']}]) {
    assert.equal(progress.appendAttempt('start', 'observe', fields).ok, false);
    assert.equal(progress.exportText(), saved);
  }
});

test('old imports preserve attempt history; immutable conflicts reject the entire import before other changes', () => {
  const progress = open(memoryStorage(), feedbackOptions());
  progress.appendAttempt('start', 'observe', attemptFields);
  const first = progress.state.attempts[0];
  const old = JSON.parse(progress.exportText()); delete old.attempts; delete old.feedback_adoptions;
  assert.equal(progress.importText(JSON.stringify(old)).ok, true);
  assert.deepEqual(progress.state.attempts, [first]);
  const exported = progress.exportText();
  assert.equal(progress.importText(exported).ok, true);
  assert.deepEqual(progress.state.attempts, [first]);
  for (const altered of [{...first, response: 'Replacement'}, {...first, mastery: true}, {...first, criteria: []}, {...first, context_hash: 'wrong'}]) {
    const incoming = {...JSON.parse(exported), selected_path_id: 'short', topics: {a: {watched: true, practiced: false, mastered: false, review: false, notes: 'must not change'}}, attempts: [altered]};
    assert.equal(progress.importText(JSON.stringify(incoming)).ok, false);
    assert.equal(progress.exportText(), exported);
  }
});

test('workspace attempts are read-only projections, and local snapshots must match before explicit adoption', () => {
  const storage = memoryStorage(), feedback = projection(), progress = open(storage, feedbackOptions({learningFeedback: feedback}));
  assert.equal(storage.values.size, 0);
  assert.deepEqual(progress.state.attempts, []);
  assert.equal(progress.attemptEntries()[0].origin, 'workspace');
  assert.equal(progress.feedbackEntries()[0].actionable, false);
  assert.equal(progress.adoptFeedback('feedback-one').ok, false);
  progress.startStep('start', 'observe');
  progress.updateTopic('a', {watched: true, notes: 'personal'});
  const before = progress.state;
  assert.equal(progress.feedbackEntries()[0].actionable, true);
  assert.equal(progress.state.study_step_ids.start, 'observe');
  const result = progress.adoptFeedback('feedback-one');
  assert.equal(result.persisted, true);
  assert.deepEqual(result.target, {path_id: 'start', step_id: 'apply'});
  assert.equal(progress.state.study_step_ids.start, 'apply');
  assert.equal(progress.state.feedback_adoptions.length, 1);
  assert.deepEqual(progress.state.attempts, []);
  assert.deepEqual(progress.state.topics, before.topics);
  assert.deepEqual(progress.state.topic_versions, before.topic_versions);
  progress.startStep('start', 'observe');
  assert.equal(progress.adoptFeedback('feedback-one').ok, false);
  assert.equal(progress.feedbackEntries()[0].adopted, true);
  const reopened = open(storage, feedbackOptions({learningFeedback: feedback}));
  assert.equal(reopened.state.feedback_adoptions.length, 1);
  const old = JSON.parse(reopened.exportText()); delete old.feedback_adoptions;
  assert.equal(reopened.importText(JSON.stringify(old)).ok, true);
  assert.equal(reopened.state.feedback_adoptions.length, 1);
});

test('new attempts supersede guidance immediately; steps sharing a topic remain independent', () => {
  const progress = open(memoryStorage(), feedbackOptions({learningFeedback: projection()}));
  progress.startStep('start', 'observe');
  progress.appendAttempt('start', 'apply', attemptFields);
  assert.equal(progress.feedbackEntries('start', 'observe')[0].actionable, true);
  progress.appendAttempt('start', 'observe', {...attemptFields, response: 'A newer reason'});
  assert.equal(progress.feedbackEntries()[0].status, 'superseded');
  assert.equal(progress.adoptFeedback('feedback-one').ok, false);
  assert.equal(progress.state.study_step_ids.start, 'observe');
  assert.equal(progress.state.feedback_adoptions.length, 0);
});

test('stale context, mismatched snapshots, older feedback and unavailable targets cannot be adopted', () => {
  const cases = [
    {options: {feedbackContext: {...feedbackContext, context_hash: 'c'.repeat(64)}}, expected: 'stale'},
    {local: {...attempt(), response: 'Different local content'}, expected: 'current'},
    {local: attempt(), expected: 'current', allowed: true},
    {feedback: {...projection().feedback[0], status: 'superseded', actionable: false}, expected: 'superseded'},
    {feedback: {...projection().feedback[0], next_action: {...projection().feedback[0].next_action, target: {path_id: 'start', step_id: 'missing'}}}, expected: 'current'}
  ];
  for (const item of cases) {
    const projected = item.feedback ? projection([attempt()], [item.feedback]) : projection();
    const progress = open(memoryStorage(), feedbackOptions({learningFeedback: projected, ...item.options}));
    if (item.local) assert.equal(progress.importText(JSON.stringify({...progress.state, attempts: [item.local]})).ok, true);
    progress.startStep('start', 'observe');
    assert.equal(progress.feedbackEntries()[0].status, item.expected);
    assert.equal(progress.adoptFeedback('feedback-one').ok, !!item.allowed);
    if (!item.allowed) assert.equal(progress.state.feedback_adoptions.length, 0);
  }
  const first = projection().feedback[0], second = {...first, id: 'feedback-newer'};
  const progress = open(memoryStorage(), feedbackOptions({learningFeedback: projection([attempt()], [first, second])}));
  progress.startStep('start', 'observe');
  assert.equal(progress.feedbackEntries()[0].status, 'superseded');
  assert.equal(progress.feedbackEntries()[1].actionable, true);
});

test('adopting a no-target instruction records the decision without marking mastery or changing position', () => {
  const projected = projection(); projected.feedback[0].next_action = {kind: 'request_evidence', reason: 'Need an artifact', instructions: ['Provide the result'], output: 'Original result', stop_when: 'Result attached', target: null};
  const progress = open(memoryStorage(), feedbackOptions({learningFeedback: projected}));
  progress.startStep('start', 'observe');
  const before = progress.state;
  assert.equal(progress.adoptFeedback('feedback-one').ok, true);
  assert.deepEqual(progress.state.study_step_ids, before.study_step_ids);
  assert.deepEqual(progress.state.topics, {});
  assert.equal(progress.state.feedback_adoptions.length, 1);
});

test('attempt and adoption writes retain cross-window protection and remain exportable on storage failure', () => {
  const storage = memoryStorage(), first = open(storage, feedbackOptions()), stale = open(storage, feedbackOptions());
  first.appendAttempt('start', 'observe', attemptFields);
  const saved = storage.values.get(first.key);
  const result = stale.appendAttempt('start', 'apply', attemptFields);
  assert.equal(result.persisted, false);
  assert.match(result.error, /其他窗口/);
  assert.equal(storage.values.get(first.key), saved);
  assert.equal(JSON.parse(stale.exportText()).attempts[0].step_id, 'apply');
  const projected = projection(), adopter = open(storage, feedbackOptions({learningFeedback: projected}));
  adopter.startStep('start', 'observe');
  // Use a separate empty store because the newer local attempt correctly blocks old guidance.
  const isolated = memoryStorage(), adopting = open(isolated, feedbackOptions({learningFeedback: projected}));
  adopting.startStep('start', 'observe');
  const other = open(isolated, feedbackOptions({learningFeedback: projected})); other.updateTopic('b', {notes: 'another window'});
  const otherSaved = isolated.values.get(other.key);
  const refused = adopting.adoptFeedback('feedback-one');
  assert.equal(refused.persisted, false);
  assert.equal(refused.ok, false);
  assert.equal(isolated.values.get(other.key), otherSaved);
  assert.equal(JSON.parse(adopting.exportText()).feedback_adoptions.length, 0);
  let fail = true;
  const limited = {getItem() { return null; }, setItem() { if (fail) throw new Error('quota'); }};
  const unsaved = open(limited, feedbackOptions());
  assert.equal(unsaved.appendAttempt('start', 'observe', attemptFields).persisted, false);
  assert.equal(unsaved.state.attempts.length, 1);
  fail = false;
  assert.equal(unsaved.retrySave().persisted, true);
  assert.equal(unsaved.state.attempts.length, 1);
});

const draftFields = {response: 'An unfinished explanation', artifact_refs_text: '  /tmp/my-result.txt  \n', blocker: 'One open question', work_origin: 'learner'};

test('supersession is isolated by context as well as path and step', () => {
  const projected = projection(), progress = open(memoryStorage(), feedbackOptions({learningFeedback: projected}));
  progress.startStep('start', 'observe');
  const old = {...attempt('old-context'), context_hash: 'd'.repeat(64), created_at: '2026-10-20T00:00:00Z'};
  assert.equal(progress.importText(JSON.stringify({...progress.state, attempts: [old]})).ok, true);
  assert.equal(progress.feedbackEntries()[0].status, 'current');
  assert.equal(progress.feedbackEntries()[0].actionable, true);
  progress.appendAttempt('start', 'observe', attemptFields);
  assert.equal(progress.feedbackEntries()[0].status, 'superseded');
  assert.equal(progress.attemptEntries().find(item => item.attempt.id === old.id).stale, true);
});

test('adopted instructions follow their effective target after reopening without becoming a new assessment there', () => {
  for (const [kind, target] of [
    ['retry', {path_id: 'start', step_id: 'apply'}],
    ['revisit', {path_id: 'start', step_id: 'observe'}],
    ['switch_path', {path_id: 'short', step_id: 'compare'}],
    ['resolve_gap', null]
  ]) {
    const source = attempt('a-source', 'apply'), projected = projection([source]);
    const feedback = projected.feedback[0]; feedback.next_action.kind = kind; feedback.next_action.target = target;
    const storage = memoryStorage(), progress = open(storage, feedbackOptions({learningFeedback: projected}));
    progress.startStep('start', 'apply');
    assert.equal(progress.adoptFeedback(feedback.id).ok, true);
    const reopened = open(storage, feedbackOptions({learningFeedback: projected})), guidance = reopened.currentGuidance();
    assert.equal(guidance.active, true, kind);
    assert.equal(guidance.feedback.attempt.step_id, 'apply');
    assert.deepEqual(guidance.feedback.next_action.instructions, feedback.next_action.instructions);
    assert.deepEqual(guidance.target, target || {path_id: 'start', step_id: 'apply'});
    if (target && target.step_id !== 'apply') assert.equal(reopened.feedbackEntries(target.path_id, target.step_id).length, 0);
    reopened.visit('b');
    assert.equal(reopened.currentGuidance().active, true);
    assert.deepEqual(reopened.state.topics, {});
    assert.equal(reopened.currentGuidance('start', 'finish'), null);
  }
});

test('adopted guidance stops being active on plan change, new source or target attempts, newer feedback, or explicit task change', () => {
  const projected = projection(), storage = memoryStorage(), progress = open(storage, feedbackOptions({learningFeedback: projected}));
  progress.startStep('start', 'observe'); progress.adoptFeedback('feedback-one');
  const adoptedRecord = progress.exportText();
  function restored(options = {}) {
    const p = open(memoryStorage(), feedbackOptions({learningFeedback: projected, ...options}));
    assert.equal(p.importText(adoptedRecord).ok, true); return p;
  }
  for (const step of ['observe', 'apply']) {
    const p = restored(); p.appendAttempt('start', step, attemptFields);
    assert.equal(p.currentGuidance().active, false, step);
  }
  const changed = restored({feedbackContext: {...feedbackContext, context_hash: 'd'.repeat(64)}});
  assert.equal(changed.currentGuidance().active, false);
  const targetAttempt = attempt('external-target-attempt', 'apply');
  const rebuilt = restored({learningFeedback: projection([...projected.attempts, targetAttempt], projected.feedback)});
  assert.equal(rebuilt.currentGuidance().active, false);
  const newerFeedback = {...projected.feedback[0], id: 'review-new'};
  assert.equal(restored({learningFeedback: projection(projected.attempts, [...projected.feedback, newerFeedback])}).currentGuidance().active, false);
  const manual = restored(); manual.startStep('start', 'finish'); manual.startStep('start', 'apply');
  assert.equal(manual.currentGuidance(), null);
  assert.equal(manual.state.feedback_adoptions.length, 1);
  const otherPath = restored(); otherPath.selectPath('short'); otherPath.selectPath('start');
  assert.equal(otherPath.currentGuidance(), null);
});

test('draft autosave survives reload by exact context and step, exports raw text, and is not a formal attempt', () => {
  const storage = memoryStorage(), progress = open(storage, feedbackOptions());
  assert.equal(progress.saveDraft('start', 'observe', draftFields).persisted, true);
  progress.saveDraft('start', 'apply', {...draftFields, response: 'Another step of the same topic'});
  const reopened = open(storage, feedbackOptions());
  assert.equal(reopened.draft('start', 'observe').artifact_refs_text, draftFields.artifact_refs_text);
  assert.equal(reopened.draft('start', 'apply').response, 'Another step of the same topic');
  assert.deepEqual(reopened.state.attempts, []);
  assert.deepEqual(reopened.state.topics, {});
  assert.deepEqual(reopened.state.study_step_ids, {});
  assert.equal(JSON.parse(reopened.exportText()).attempt_drafts[0].response, draftFields.response);
  const changed = open(storage, feedbackOptions({feedbackContext: {...feedbackContext, context_hash: 'd'.repeat(64)}}));
  assert.equal(changed.draft('start', 'observe'), null);
  assert.equal(changed.draftEntries().filter(item => item.stale).length, 2);
  assert.equal(changed.submitDraft('start', 'observe').ok, false);
  assert.equal(changed.state.attempts.length, 0);
});

test('submitting a draft atomically creates one immutable attempt and clears only that draft', () => {
  const storage = memoryStorage(), progress = open(storage, feedbackOptions());
  progress.saveDraft('start', 'observe', draftFields); progress.saveDraft('start', 'apply', draftFields);
  assert.equal(progress.submitDraft('start', 'observe').persisted, true);
  assert.equal(progress.state.attempts.length, 1);
  assert.deepEqual(progress.state.attempts[0].artifact_refs, ['/tmp/my-result.txt']);
  assert.equal(progress.draft('start', 'observe'), null);
  assert.notEqual(progress.draft('start', 'apply'), null);
  assert.equal(progress.submitDraft('start', 'observe').ok, false);
  const reopened = open(storage, feedbackOptions());
  assert.equal(reopened.state.attempts.length, 1);
  assert.equal(reopened.draftEntries().length, 1);
  assert.deepEqual(reopened.state.topics, {});
});

test('draft storage failures and stale tabs retain exportable text without overwriting external records or duplicating submissions', () => {
  const backing = memoryStorage(); let fail = false;
  const storage = {getItem: key => backing.getItem(key), setItem(key, value) { if (fail) throw new Error('quota'); backing.setItem(key, value); }};
  const progress = open(storage, feedbackOptions()); progress.saveDraft('start', 'observe', draftFields); fail = true;
  const result = progress.submitDraft('start', 'observe');
  assert.equal(result.persisted, false);
  assert.equal(progress.draft('start', 'observe').pending_attempt_id, result.attempt_id);
  assert.equal(JSON.parse(progress.exportText()).attempt_drafts[0].response, draftFields.response);
  assert.equal(progress.submitDraft('start', 'observe').persisted, false);
  assert.equal(progress.state.attempts.length, 1);
  fail = false;
  assert.equal(progress.submitDraft('start', 'observe').persisted, true);
  assert.equal(progress.state.attempts.length, 1);
  assert.equal(progress.draft('start', 'observe'), null);
  const first = open(backing, feedbackOptions()), stale = open(backing, feedbackOptions());
  first.saveDraft('start', 'apply', draftFields); const external = backing.getItem(first.key);
  const staleResult = stale.saveDraft('start', 'observe', {...draftFields, response: 'Typing in an older window'});
  assert.equal(staleResult.persisted, false); assert.match(staleResult.error, /其他窗口/);
  assert.equal(backing.getItem(first.key), external);
  assert.equal(JSON.parse(stale.exportText()).attempt_drafts[0].response, 'Typing in an older window');
});

test('legacy imports cannot erase drafts and conflicting draft imports reject all mutations', () => {
  const progress = open(memoryStorage(), feedbackOptions()); progress.saveDraft('start', 'observe', draftFields);
  const original = progress.exportText(), old = JSON.parse(original); delete old.attempt_drafts; delete old.guidance_cursor;
  assert.equal(progress.importText(JSON.stringify(old)).ok, true);
  assert.equal(progress.exportText(), original);
  const conflict = JSON.parse(original); conflict.selected_path_id = 'short'; conflict.attempt_drafts[0].response = 'Other browser draft';
  assert.equal(progress.importText(JSON.stringify(conflict)).ok, false);
  assert.equal(progress.exportText(), original);
  const malformed = JSON.parse(original); malformed.attempt_drafts[0].pending_attempt_id = 'missing-attempt';
  assert.equal(progress.importText(JSON.stringify(malformed)).ok, false);
  assert.equal(progress.exportText(), original);
  assert.equal(progress.importText(original).ok, true);
  assert.equal(progress.state.attempt_drafts.length, 1);
});

test('a failed submission export can restore the pending attempt over its identical saved draft and retry once', () => {
  const store = memoryStorage(); let fail = false;
  const storage = {getItem: key => store.getItem(key), setItem(key, value) { if (fail) throw new Error('quota'); store.setItem(key, value); }};
  const initial = open(storage, feedbackOptions()); initial.saveDraft('start', 'observe', draftFields);
  fail = true; const submitted = initial.submitDraft('start', 'observe'), backup = initial.exportText();
  assert.equal(submitted.persisted, false);
  fail = false;
  const recovered = open(storage, feedbackOptions());
  assert.equal(recovered.state.attempts.length, 0);
  assert.equal(recovered.importText(backup).persisted, true);
  assert.equal(recovered.draft('start', 'observe').pending_attempt_id, submitted.attempt_id);
  assert.equal(recovered.submitDraft('start', 'observe').persisted, true);
  assert.equal(recovered.state.attempts.length, 1);
  assert.equal(recovered.state.attempts[0].id, submitted.attempt_id);
  assert.equal(recovered.draft('start', 'observe'), null);
});

test('the real activity form restores drafts and explicitly submits before exporting, including failed persistence', () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const reader = fs.readFileSync(require.resolve('../creator_curriculum/web/reader.js'), 'utf8');
  const source = reader.slice(reader.indexOf('function attemptSection('), reader.indexOf('function stepView('));
  class Element {
    constructor(tag, text, className) { Object.assign(this, {tag, textContent: text || '', className, children: [], events: {}, value: ''}); }
    append(...items) { this.children.push(...items); }
    replaceChildren(...items) { this.children = items; }
    setAttribute() {}
    addEventListener(name, handler) { this.events[name] = handler; }
  }
  const find = (item, predicate) => predicate(item) ? item : item.children?.map(child => find(child, predicate)).find(Boolean);
  for (const failure of [false, true]) {
    const backing = memoryStorage(); let fail = false, exported = null;
    const storage = {getItem: key => backing.getItem(key), setItem(key, value) { if (fail) throw new Error('quota'); backing.setItem(key, value); }};
    function mount() {
      const progress = open(storage, feedbackOptions());
      const context = {progress, data: {package_id: 'creator-one'}, workOriginLabels: {learner: '自己完成', unknown: '来源不确定'},
        el: (...args) => new Element(...args), attemptHistoryItem: () => new Element('details'),
        refreshSaveStatus() {}, refreshGuidancePanels() {}, downloadRecord: text => { exported = JSON.parse(text); }};
      vm.createContext(context); vm.runInContext(source, context);
      return {progress, section: context.attemptSection({id: 'start'}, {id: 'observe'})};
    }
    let mounted = mount(), form = find(mounted.section, el => el.tag === 'form');
    find(form, el => el.id === 'attempt-response').value = 'My unsent draft'; form.events.input();
    assert.equal(mounted.progress.state.attempts.length, 0);
    mounted = mount(); form = find(mounted.section, el => el.tag === 'form');
    assert.equal(find(form, el => el.id === 'attempt-response').value, 'My unsent draft');
    const button = find(form, el => el.tag === 'button' && el.type === 'button');
    assert.equal(button.textContent, '保存本次尝试并导出');
    fail = failure; button.events.click();
    assert.equal(exported.attempts.length, 1);
    assert.equal(exported.attempts[0].response, 'My unsent draft');
    assert.deepEqual(exported.topics, {});
    assert.equal(exported.attempt_drafts.length, failure ? 1 : 0);
    assert.equal(find(form, el => el.id === 'attempt-response').value, failure ? 'My unsent draft' : '');
    if (failure) {
      fail = false; button.events.click();
      assert.equal(exported.attempts.length, 1);
      assert.equal(exported.attempt_drafts.length, 0);
    }
  }
});

test('optional feedback observations normalize at the shared projection and render through the real feedback card', () => {
  const vm = require('node:vm'), fs = require('node:fs');
  const reader = fs.readFileSync(require.resolve('../creator_curriculum/web/reader.js'), 'utf8');
  const source = reader.slice(reader.indexOf('function feedbackCard('), reader.indexOf('function guidanceContent('));
  class Element {
    constructor(tag, text) { Object.assign(this, {tag, textContent: text || '', children: []}); }
    append(...items) { this.children.push(...items); }
    setAttribute() {}
    addEventListener() {}
  }
  for (const omit of [true, false]) {
    const projected = projection(); if (omit) delete projected.feedback[0].observations;
    const original = JSON.stringify(projected);
    const progress = open(memoryStorage(), feedbackOptions({learningFeedback: projected}));
    progress.startStep('start', 'observe');
    const feedback = progress.feedbackEntries()[0];
    assert.deepEqual(feedback.observations, []);
    assert.equal(JSON.stringify(projected), original);
    const context = {el: (...args) => new Element(...args), textList: () => new Element('ol'), paths: [], feedbackActionLabels: {continue: '继续下一步'}};
    vm.createContext(context); vm.runInContext(source, context);
    assert.doesNotThrow(() => context.feedbackCard(feedback, () => {}));
    assert.equal(progress.adoptFeedback(feedback.id).ok, true);
    assert.deepEqual(progress.currentGuidance().feedback.observations, []);
  }
});

test('adoption rejects stale, unreadable or already blocked storage before changing decisions or navigation', () => {
  for (const condition of ['stale', 'unreadable', 'blocked']) {
    const backing = memoryStorage(); let unreadable = false;
    const storage = {getItem(key) { if (unreadable) throw new Error('unavailable'); return backing.getItem(key); }, setItem: (key, value) => backing.setItem(key, value)};
    const projected = projection(), initial = open(storage, feedbackOptions({learningFeedback: projected}));
    initial.startStep('start', 'observe');
    const stale = open(storage, feedbackOptions({learningFeedback: projected}));
    if (condition === 'unreadable') unreadable = true;
    else {
      initial.appendAttempt('start', 'observe', {...attemptFields, response: 'A newer attempt in another window'});
      if (condition === 'blocked') assert.equal(stale.saveDraft('start', 'observe', draftFields).persisted, false);
    }
    const before = stale.exportText(), external = backing.getItem(stale.key);
    const result = stale.adoptFeedback('feedback-one');
    assert.equal(result.ok, false, condition);
    assert.equal(result.target, undefined);
    assert.equal(stale.exportText(), before);
    assert.equal(stale.currentGuidance(), null);
    assert.equal(backing.getItem(stale.key), external);
    assert.equal(stale.status().blocked, true);
    // Blocking the decision does not discard ordinary local edits.
    assert.equal(stale.updateTopic('a', {notes: 'Preserved in this window'}).ok, true);
    assert.equal(stale.saveDraft('start', 'apply', draftFields).ok, true);
    assert.equal(JSON.parse(stale.exportText()).topics.a.notes, 'Preserved in this window');
    assert.equal(stale.draft('start', 'apply').response, draftFields.response);
    assert.equal(backing.getItem(stale.key), external);
  }
});

test('a freshness change during adoption rolls back only the decision; known conflicts deactivate existing guidance without erasing history', () => {
  const backing = memoryStorage(); let armed = false, reads = 0, external;
  const storage = {getItem(key) { if (armed && ++reads === 2) backing.setItem(key, external); return backing.getItem(key); }, setItem: (key, value) => backing.setItem(key, value)};
  const projected = projection(), progress = open(storage, feedbackOptions({learningFeedback: projected}));
  progress.startStep('start', 'observe'); progress.saveDraft('start', 'apply', draftFields);
  const before = progress.exportText(); external = JSON.stringify({...progress.state, last_topic_id: 'b'}); armed = true;
  assert.equal(progress.adoptFeedback('feedback-one').ok, false);
  assert.equal(progress.exportText(), before);
  assert.equal(backing.getItem(progress.key), external);
  assert.equal(progress.state.feedback_adoptions.length, 0);
  assert.equal(progress.draft('start', 'apply').response, draftFields.response);
  const isolated = memoryStorage(), adopted = open(isolated, feedbackOptions({learningFeedback: projected}));
  adopted.startStep('start', 'observe'); adopted.adoptFeedback('feedback-one');
  const cursor = adopted.state.guidance_cursor;
  const other = open(isolated, feedbackOptions({learningFeedback: projected})); other.appendAttempt('start', 'apply', attemptFields);
  assert.equal(adopted.saveDraft('start', 'apply', draftFields).persisted, false);
  assert.equal(adopted.currentGuidance().active, false);
  assert.deepEqual(adopted.state.guidance_cursor, cursor);
  assert.equal(adopted.state.feedback_adoptions.length, 1);
});
