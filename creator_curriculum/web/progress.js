/* Personal records are independent of generated content and are keyed by stable IDs. */
(function (root) {
  'use strict';
  const Feedback = typeof module === 'object' && module.exports ? require('./feedback.js') : root.C2CFeedback;
  const VERSION = 1;
  const flags = ['watched', 'practiced', 'review', 'mastered'];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,120}$/.test(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  const emptyTopic = () => ({watched: false, practiced: false, review: false, mastered: false, notes: ''});
  const put = (map, key, value) => Object.defineProperty(map, key, {value, enumerable: true, writable: true, configurable: true});
  const message = error => error instanceof Error ? error.message : String(error);

  function validateRecord(value, packageId) {
    if (!object(value)) throw new Error('学习记录格式无效：需要 JSON 对象。');
    if (value.schema_version !== VERSION) throw new Error('学习记录版本不兼容；原记录已保留，请导出备份。');
    if (value.package_id !== packageId) throw new Error('这份记录属于其他学习包，不能导入当前学习包。');
    for (const field of ['selected_path_id', 'last_topic_id']) {
      if (value[field] !== null && !identifier(value[field])) throw new Error(`学习记录字段无效：${field}。`);
    }
    if (typeof value.updated_at !== 'string' || !Number.isFinite(Date.parse(value.updated_at))) {
      throw new Error('学习记录的更新时间无效。');
    }
    if (!object(value.topics)) throw new Error('学习记录的知识点列表无效。');
    for (const [id, record] of Object.entries(value.topics)) {
      if (!identifier(id) || !object(record) || flags.some(flag => typeof record[flag] !== 'boolean') || typeof record.notes !== 'string') {
        throw new Error(`知识点学习记录无效：${id}。`);
      }
    }
    if (value.topic_versions !== undefined && (!object(value.topic_versions) || Object.entries(value.topic_versions).some(
      ([id, version]) => !identifier(id) || typeof version !== 'string' || !version.trim()))) {
      throw new Error('学习记录的来源指纹无效。');
    }
    if (value.study_topic_ids !== undefined && (!object(value.study_topic_ids) || Object.entries(value.study_topic_ids).some(
      ([pathId, topicId]) => !identifier(pathId) || !identifier(topicId)))) {
      throw new Error('学习记录的路径学习位置无效。');
    }
    if (value.study_step_ids !== undefined && (!object(value.study_step_ids) || Object.entries(value.study_step_ids).some(
      ([pathId, stepId]) => !identifier(pathId) || !identifier(stepId)))) {
      throw new Error('学习记录的活动学习位置无效。');
    }
    const attempts = Feedback.mergeImmutable([], value.attempts === undefined ? [] : value.attempts,
      attempt => Feedback.validateAttempt(attempt, packageId), '尝试记录');
    const adoptions = Feedback.mergeImmutable([], value.feedback_adoptions === undefined ? [] : value.feedback_adoptions,
      Feedback.validateAdoption, '建议采用记录');
    const drafts = Feedback.mergeDrafts([], value.attempt_drafts === undefined ? [] : value.attempt_drafts);
    if (own(value, 'guidance_cursor')) Feedback.validateCursor(value.guidance_cursor);
    for (const draft of drafts.filter(item => item.pending_attempt_id)) {
      const attempt = attempts.find(item => item.id === draft.pending_attempt_id);
      if (!attempt || Feedback.draftKey(attempt) !== Feedback.draftKey(draft) || attempt.activity_id !== draft.activity_id ||
          Feedback.canonical(Feedback.draftFields(draft)) !== Feedback.canonical(Object.fromEntries(['response', 'artifact_refs', 'blocker', 'work_origin'].map(key => [key, attempt[key]])))) {
        throw new Error('草稿与待保存的尝试不匹配；原内容未覆盖。');
      }
    }
    // Legacy v1 records only tracked browsing. Do not infer a study task from it.
    return {...clone(value), topic_versions: clone(value.topic_versions || {}),
      study_topic_ids: clone(value.study_topic_ids || {}), study_step_ids: clone(value.study_step_ids || {}),
      attempts, feedback_adoptions: adoptions, attempt_drafts: drafts};
  }

  function create(options) {
    const {packageId, topicIds, pathIds, topicVersions = {}, pathTopics = {}, pathSteps = {},
      feedbackContext = null, learningFeedback = null, now = () => new Date().toISOString(),
      idFactory = prefix => prefix + '-' + (root.crypto?.randomUUID?.() || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2))} = options;
    if (!identifier(packageId) || !Array.isArray(topicIds) || !topicIds.every(identifier) || !Array.isArray(pathIds) || !pathIds.every(identifier)) {
      throw new Error('学习包或知识点标识无效。');
    }
    if (!object(topicVersions) || Object.entries(topicVersions).some(([id, version]) => !identifier(id) || typeof version !== 'string' || !version.trim())) {
      throw new Error('知识点来源指纹无效。');
    }
    const knownTopics = new Set(topicIds), knownPaths = new Set(pathIds);
    if (!object(pathTopics) || Object.entries(pathTopics).some(([pathId, ids]) =>
      !knownPaths.has(pathId) || !Array.isArray(ids) || new Set(ids).size !== ids.length || ids.some(id => !knownTopics.has(id)))) {
      throw new Error('路径的知识点清单无效。');
    }
    if (!object(pathSteps) || Object.entries(pathSteps).some(([pathId, steps]) =>
      !knownPaths.has(pathId) || !object(steps) || Object.entries(steps).some(([stepId, topicId]) =>
        !identifier(stepId) || !knownTopics.has(topicId) || !Array.isArray(pathTopics[pathId]) || !pathTopics[pathId].includes(topicId)))) {
      throw new Error('路径的学习步骤清单无效。');
    }
    const stepMembers = new Map(Object.entries(pathSteps).map(([pathId, steps]) => [pathId, new Map(Object.entries(steps))]));
    const pathMembers = new Map(Object.entries(pathTopics).map(([id, ids]) => [id, new Set(ids)]));
    const feedbackIndex = Feedback.create({packageId, context: feedbackContext, projection: learningFeedback});
    const key = 'c2c-progress:' + packageId;
    let storage, blocked = false, persisted = false, error = null, raw = null, observedRaw = null;
    let state = {schema_version: VERSION, package_id: packageId, selected_path_id: pathIds[0] || null,
      last_topic_id: null, study_topic_ids: {}, study_step_ids: {}, topics: {}, topic_versions: {},
      attempts: [], feedback_adoptions: [], attempt_drafts: [], guidance_cursor: null, updated_at: now()};
    try {
      storage = own(options, 'storage') ? options.storage : root.localStorage;
      if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') {
        throw new Error('浏览器没有可用的本地存储');
      }
      const saved = storage.getItem(key);
      if (saved !== null) {
        // Keep the exact bytes if parsing or version validation fails.
        raw = saved;
        state = validateRecord(JSON.parse(saved), packageId);
        raw = null;
      }
      observedRaw = saved;
      persisted = true;
    } catch (cause) {
      blocked = true;
      error = `无法读取或兼容原学习记录，已停止覆盖本地记录。当前修改仅在本页内，请导出保存。${message(cause)}`;
    }

    function status() {
      const orphaned = [...new Set([...Object.keys(state.topics), ...Object.keys(state.topic_versions)])].filter(id => !knownTopics.has(id));
      const missingPath = state.selected_path_id && !knownPaths.has(state.selected_path_id) ? state.selected_path_id : null;
      const missingLast = state.last_topic_id && !knownTopics.has(state.last_topic_id) ? state.last_topic_id : null;
      const changed = Object.keys(state.topic_versions).filter(id => knownTopics.has(id) && own(topicVersions, id) && state.topic_versions[id] !== topicVersions[id]);
      const unversioned = Object.keys(state.topics).filter(id => knownTopics.has(id) && own(topicVersions, id) && !own(state.topic_versions, id));
      const unavailableStudy = Object.entries(state.study_topic_ids).flatMap(([pathId, topicId]) => {
        const reason = !knownPaths.has(pathId) ? 'missing_path' : !knownTopics.has(topicId) ? 'missing_topic' :
          pathMembers.has(pathId) && !pathMembers.get(pathId).has(topicId) ? 'outside_path' : null;
        return reason ? [{path_id: pathId, topic_id: topicId, reason}] : [];
      });
      const unavailableSteps = Object.entries(state.study_step_ids).flatMap(([pathId, stepId]) => {
        const reason = !knownPaths.has(pathId) ? 'missing_path' : !stepMembers.get(pathId)?.has(stepId) ? 'missing_step' : null;
        return reason ? [{path_id: pathId, step_id: stepId, reason}] : [];
      });
      const unassignedSteps = Object.keys(state.study_topic_ids).filter(pathId => stepMembers.has(pathId) && !own(state.study_step_ids, pathId));
      const warnings = [];
      if (orphaned.length) warnings.push(`${orphaned.length} 个知识点已不在当前学习包中；原学习记录仍保留在导出文件内。`);
      if (missingPath) warnings.push(`上次选择的路径（${missingPath}）已不在当前学习包中，请重新选择；原路径标识仍保留。`);
      if (missingLast) warnings.push(`最近查阅的知识点（${missingLast}）已不在当前学习包中；没有自动替换为其他知识点。`);
      if (unavailableStudy.length) warnings.push(`${unavailableStudy.length} 条路径的学习位置因路径、知识点或成员关系变化暂不可用；原位置仍保留，请明确选择新的当前任务。`);
      if (unavailableSteps.length) warnings.push(`${unavailableSteps.length} 条路径的活动步骤已变化或不可用；原步骤仍保留，请明确选择新步骤。`);
      if (unassignedSteps.length) warnings.push('旧学习位置只记录了知识点，尚未选择这条路径中的具体活动；原位置保留，请从概览选择一步。');
      if (changed.length) warnings.push(`${changed.length} 个知识点的来源内容已更新；原标记仍保留，请核对后明确确认来源，普通编辑不会清除提醒。`);
      if (unversioned.length) warnings.push(`${unversioned.length} 个知识点的旧记录没有来源指纹，无法确认是否对应当前内容；原记录仍保留。`);
      const attemptEntries = feedbackIndex.attempts(state.attempts);
      const staleAttempts = attemptEntries.filter(item => item.stale);
      const conflictingAttempts = attemptEntries.filter(item => item.conflict);
      if (staleAttempts.length) warnings.push(`${staleAttempts.length} 次尝试属于已变化的学习计划；历史保留，不会自动归到当前活动或采用旧建议。`);
      if (conflictingAttempts.length) warnings.push(`${conflictingAttempts.length} 次尝试的本地与工作区内容不一致；请导出交由 Agent 核对，相关建议已停用。`);
      const staleDrafts = state.attempt_drafts.filter(item => item.context_hash !== feedbackContext?.context_hash);
      if (staleDrafts.length) warnings.push(`${staleDrafts.length} 份草稿属于旧学习计划；原文字可在学习记录中查看与导出，不会自动提交到新任务。`);
      return {persisted, blocked, error, warnings, orphaned_topic_ids: orphaned, missing_path_id: missingPath,
        missing_last_topic_id: missingLast, changed_topic_ids: changed, unversioned_topic_ids: unversioned,
        unavailable_study_positions: unavailableStudy, unavailable_study_steps: unavailableSteps, unassigned_step_paths: unassignedSteps};
    }
    function result(ok, problem = null) {
      return {ok, persisted: ok && persisted, error: problem || error, warnings: status().warnings};
    }
    function storageIsCurrent() {
      if (blocked) return false;
      let latest;
      try { latest = storage.getItem(key); }
      catch (cause) {
        blocked = true; persisted = false;
        error = `无法核对浏览器中的最新记录，已停止覆盖。请先导出当前修改，再重新打开页面。${message(cause)}`;
        return false;
      }
      // Optimistic protection: localStorage has no cross-process compare-and-swap.
      if (latest !== observedRaw) {
        blocked = true; persisted = false; raw = latest;
        error = '其他窗口或外部操作已更改本学习包的记录，已停止覆盖。当前修改仅在本页内；请先导出当前修改，再重新打开页面读取最新记录。';
        return false;
      }
      return true;
    }
    function save() {
      state.updated_at = now();
      persisted = false;
      if (storageIsCurrent()) {
        try {
          const encoded = JSON.stringify(state);
          storage.setItem(key, encoded);
          observedRaw = encoded;
          persisted = true;
          error = null;
        } catch (cause) {
          error = `未能保存到浏览器。当前修改仅在本页内，请导出保存。${message(cause)}`;
        }
      }
      return result(true);
    }
    function captureVersion(id, replace) {
      if (own(topicVersions, id) && (replace || !own(state.topic_versions, id))) put(state.topic_versions, id, topicVersions[id]);
    }
    function feedbackEntries() {
      return feedbackIndex.feedback(state.attempts, state.feedback_adoptions,
        {path_id: state.selected_path_id, step_id: state.study_step_ids[state.selected_path_id] || null});
    }
    function currentPosition() {
      return {path_id: state.selected_path_id, step_id: state.study_step_ids[state.selected_path_id] || null};
    }
    function draftFor(pathId, stepId) {
      return state.attempt_drafts.find(item => item.context_hash === feedbackContext?.context_hash && item.path_id === pathId && item.step_id === stepId) || null;
    }
    function makeAttempt(pathId, stepId, fields) {
      const step = feedbackIndex.currentStep(pathId, stepId);
      if (!step || !stepMembers.get(pathId)?.has(stepId)) throw new Error('当前页面没有这一步的有效反馈上下文，请更新学习页后再记录。');
      if (!object(fields) || Object.keys(fields).length !== 4 || !['response', 'artifact_refs', 'blocker', 'work_origin'].every(field => own(fields, field))) {
        throw new Error('请填写产物内容、引用、卡点和来源；不能在尝试中加入评分或掌握标记。');
      }
      return Feedback.validateAttempt({schema_version: 1, id: idFactory('attempt'), package_id: packageId,
        context_hash: feedbackContext.context_hash, path_id: pathId, step_id: stepId, activity_id: step.activity_id,
        created_at: now(), ...fields, criteria: clone(step.success_criteria)}, packageId, feedbackContext);
    }
    function scoped(items, pathId, stepId, attemptOf) {
      return items.filter(item => (!pathId || attemptOf(item).path_id === pathId) && (!stepId || attemptOf(item).step_id === stepId));
    }

    return {
      key,
      get state() { return clone(state); },
      get warnings() { return status().warnings; },
      get error() { return error; },
      get raw() { return raw; },
      status,
      attemptEntries(pathId, stepId) { return scoped(feedbackIndex.attempts(state.attempts), pathId, stepId, item => item.attempt); },
      feedbackEntries(pathId, stepId) { return scoped(feedbackEntries(), pathId, stepId, item => item.attempt); },
      currentGuidance(pathId = state.selected_path_id, stepId = state.study_step_ids[pathId]) {
        const position = currentPosition();
        if (position.path_id !== pathId || position.step_id !== stepId) return null;
        const guidance = feedbackIndex.guidance(state.attempts, state.feedback_adoptions, state.guidance_cursor, position);
        return guidance?.active && blocked ? {...guidance, active: false, reason: '浏览器中的最新记录无法确认，暂不把原指导作为当前安排。请导出本页内容，再重新打开读取最新记录。'} : guidance;
      },
      draft(pathId, stepId) { return clone(draftFor(pathId, stepId)); },
      draftEntries() { return state.attempt_drafts.map(item => ({draft: clone(item), stale: item.context_hash !== feedbackContext?.context_hash})); },
      saveDraft(pathId, stepId, fields) {
        const step = feedbackIndex.currentStep(pathId, stepId);
        if (!step || !stepMembers.get(pathId)?.has(stepId)) return result(false, '当前活动已不可用，不能把草稿归入其他步骤。');
        let draft;
        try {
          if (!object(fields) || Object.keys(fields).length !== 4 || !['response', 'artifact_refs_text', 'blocker', 'work_origin'].every(key => own(fields, key))) throw new Error('草稿字段不完整或包含未知字段。');
          const previous = draftFor(pathId, stepId);
          const unchanged = previous && Object.entries(fields).every(([key, value]) => previous[key] === value);
          if (unchanged) return result(true);
          draft = Feedback.validateDraft({context_hash: feedbackContext.context_hash, path_id: pathId, step_id: stepId,
            activity_id: step.activity_id, updated_at: now(), ...fields, pending_attempt_id: null});
          state.attempt_drafts = state.attempt_drafts.filter(item => Feedback.draftKey(item) !== Feedback.draftKey(draft));
          if (['response', 'artifact_refs_text', 'blocker'].some(key => draft[key].trim())) state.attempt_drafts.push(draft);
        } catch (cause) { return result(false, message(cause)); }
        return save();
      },
      submitDraft(pathId, stepId) {
        const draft = draftFor(pathId, stepId);
        if (!draft) return result(false, '请先填写本次内容、产物引用或卡点。');
        let attempt;
        try {
          attempt = draft.pending_attempt_id ? state.attempts.find(item => item.id === draft.pending_attempt_id) : makeAttempt(pathId, stepId, Feedback.draftFields(draft));
          if (!attempt) throw new Error('上次待保存的尝试无法找到，草稿已保留。');
          Feedback.validateAttempt(attempt, packageId, feedbackContext);
          state.attempts = Feedback.mergeImmutable(state.attempts, [attempt], value => Feedback.validateAttempt(value, packageId), '尝试记录');
        } catch (cause) { return result(false, message(cause)); }
        // Submit and remove the draft in the same storage write. A failed write
        // restores the input with its attempt ID so retry cannot duplicate it.
        state.attempt_drafts = state.attempt_drafts.filter(item => Feedback.draftKey(item) !== Feedback.draftKey(draft));
        const saved = save();
        if (!saved.persisted) state.attempt_drafts.push({...draft, pending_attempt_id: attempt.id});
        return {...saved, attempt_id: attempt.id};
      },
      appendAttempt(pathId, stepId, fields) {
        let attempt;
        try {
          attempt = makeAttempt(pathId, stepId, fields);
          state.attempts = Feedback.mergeImmutable(state.attempts, [attempt], value => Feedback.validateAttempt(value, packageId), '尝试记录');
        } catch (cause) { return result(false, message(cause)); }
        return {...save(), attempt_id: attempt.id};
      },
      retrySave() { return save(); },
      adoptFeedback(id) {
        // A navigation decision cannot rely on a snapshot already known to be
        // stale. Ordinary notes and drafts still keep their in-memory edits.
        if (!storageIsCurrent()) return result(false, error);
        const feedback = feedbackEntries().find(item => item.id === id);
        if (!feedback || !feedback.actionable) return result(false, feedback?.adoption_reason || '当前没有可采用的这条反馈。');
        const target = feedback.next_action.target;
        if (target && !stepMembers.get(target.path_id)?.has(target.step_id)) return result(false, '建议的目标步骤已不可用。');
        let adoptions;
        try {
          adoptions = Feedback.mergeImmutable(state.feedback_adoptions, [{id: idFactory('adoption'), feedback_id: feedback.id,
            attempt_id: feedback.attempt_id, context_hash: feedback.context_hash, adopted_at: now()}], Feedback.validateAdoption, '建议采用记录');
        } catch (cause) { return result(false, message(cause)); }
        const previous = clone(state);
        state.feedback_adoptions = adoptions;
        const destination = target || {path_id: feedback.attempt.path_id, step_id: feedback.attempt.step_id};
        state.guidance_cursor = {adoption_id: adoptions[adoptions.length - 1].id, feedback_id: feedback.id,
          context_hash: feedback.context_hash, ...destination,
          baseline_attempt_ids: feedbackIndex.attempts(state.attempts).filter(item => !item.stale && item.attempt.path_id === destination.path_id && item.attempt.step_id === destination.step_id).map(item => item.attempt.id)};
        if (target) { state.selected_path_id = target.path_id; put(state.study_step_ids, target.path_id, target.step_id); }
        const saved = save();
        // The second freshness check may discover a change between preflight
        // and writing. Roll back only this decision, retaining all prior edits.
        if (blocked) { state = previous; return result(false, error); }
        return {...saved, target: clone(target)};
      },
      visit(id) {
        if (!knownTopics.has(id)) return result(false, '无法定位不在当前学习包中的知识点。');
        state.last_topic_id = id;
        // Opening a changed source never accepts it on behalf of the learner.
        // Older self-reports without a fingerprint also remain unverified.
        if (!own(state.topics, id)) captureVersion(id, false);
        return save();
      },
      selectPath(id) {
        if (!knownPaths.has(id)) return result(false, '这条路径已不在当前学习包中。');
        if (state.selected_path_id !== id) state.guidance_cursor = null;
        state.selected_path_id = id;
        return save();
      },
      startStep(pathId, stepId) {
        if (!knownPaths.has(pathId)) return result(false, '这条路径已不在当前学习包中。');
        if (!stepMembers.get(pathId)?.has(stepId)) return result(false, '该活动步骤不属于这条路径，无法设为当前任务。');
        if (state.selected_path_id !== pathId || state.study_step_ids[pathId] !== stepId) state.guidance_cursor = null;
        state.selected_path_id = pathId;
        put(state.study_step_ids, pathId, stepId);
        return save();
      },
      startTask(pathId, topicId) {
        if (stepMembers.has(pathId)) return result(false, '这条路径按活动继续，请选择具体步骤。');
        if (!knownPaths.has(pathId)) return result(false, '这条路径已不在当前学习包中。');
        if (!knownTopics.has(topicId)) return result(false, '无法开始不在当前学习包中的知识点。');
        if (!pathMembers.has(pathId) || !pathMembers.get(pathId).has(topicId)) {
          return result(false, '该知识点不属于这条路径，无法设为当前任务。');
        }
        state.selected_path_id = pathId;
        put(state.study_topic_ids, pathId, topicId);
        return save();
      },
      updateTopic(id, patch) {
        if (!knownTopics.has(id)) return result(false, '无法修改不在当前学习包中的知识点。');
        if (!object(patch) || Object.entries(patch).some(([field, value]) => field === 'notes' ? typeof value !== 'string' : !flags.includes(field) || typeof value !== 'boolean')) {
          return result(false, '学习标记或笔记格式无效。');
        }
        const existing = own(state.topics, id);
        const previous = existing ? state.topics[id] : emptyTopic();
        put(state.topics, id, {...previous, ...patch});
        // A new self-report belongs to the currently displayed source. An edit
        // to an older report is not confirmation that its source was reviewed.
        if (!existing) captureVersion(id, true);
        return save();
      },
      acknowledgeSource(id) {
        if (!knownTopics.has(id)) return result(false, '无法核对不在当前学习包中的知识点。');
        if (!own(topicVersions, id)) return result(false, '当前知识点没有可核对的来源指纹。');
        captureVersion(id, true);
        return save();
      },
      exportText() { return JSON.stringify(state, null, 2) + '\n'; },
      importText(text) {
        let incoming, attempts, adoptions, drafts;
        try {
          if (typeof text !== 'string') throw new Error('请选择 JSON 学习记录文件。');
          incoming = validateRecord(JSON.parse(text), packageId);
          // Validate every immutable ID before any topic, position or history mutation.
          attempts = Feedback.mergeImmutable(state.attempts, incoming.attempts, value => Feedback.validateAttempt(value, packageId), '尝试记录');
          adoptions = Feedback.mergeImmutable(state.feedback_adoptions, incoming.feedback_adoptions, Feedback.validateAdoption, '建议采用记录');
          drafts = Feedback.mergeDrafts(state.attempt_drafts, incoming.attempt_drafts);
        } catch (cause) {
          return result(false, `未导入，现有记录未改变。${message(cause)}`);
        }
        // An explicit import replaces matching records, retaining all other IDs.
        // Preserve missing provenance for imported topics rather than attributing
        // an older imported self-report to the local source's newer fingerprint.
        const versions = {...state.topic_versions};
        for (const id of Object.keys(incoming.topics)) delete versions[id];
        for (const [id, version] of Object.entries(incoming.topic_versions)) {
          // An imported visit alone cannot assign its source to a local self-report.
          if (!own(state.topics, id) || own(incoming.topics, id)) put(versions, id, version);
        }
        state = {...state, ...incoming, topics: {...state.topics, ...incoming.topics},
          topic_versions: versions, study_topic_ids: {...state.study_topic_ids, ...incoming.study_topic_ids},
          study_step_ids: {...state.study_step_ids, ...incoming.study_step_ids}, attempts, feedback_adoptions: adoptions, attempt_drafts: drafts};
        return save();
      }
    };
  }
  const api = {create};
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.C2CProgress = api;
})(typeof globalThis !== 'undefined' ? globalThis : window);
