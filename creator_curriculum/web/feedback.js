/* Attempt history is immutable. Only generated, CLI-validated feedback can guide navigation. */
(function (root) {
  'use strict';
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,120}$/.test(value);
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const nonempty = value => typeof value === 'string' && value.trim().length > 0;
  const clone = value => JSON.parse(JSON.stringify(value));
  const requireValue = (condition, message) => { if (!condition) throw new Error(message); };
  const canonical = value => JSON.stringify(normalize(value));
  function normalize(value) {
    if (Array.isArray(value)) return value.map(normalize);
    if (object(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, normalize(value[key])]));
    return value;
  }
  function fields(value, expected, label) {
    requireValue(object(value) && Object.keys(value).length === expected.length && expected.every(key => own(value, key)), `${label}字段不完整或包含未知字段。`);
  }
  function date(value) {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
  }
  function strings(value, nonemptyArray = false) {
    return Array.isArray(value) && (!nonemptyArray || value.length > 0) && value.every(nonempty);
  }
  function validateAttempt(attempt, packageId, context = null) {
    fields(attempt, ['schema_version', 'id', 'package_id', 'context_hash', 'path_id', 'step_id', 'activity_id', 'created_at', 'work_origin', 'response', 'artifact_refs', 'blocker', 'criteria'], '尝试记录');
    requireValue(attempt.schema_version === 1 && identifier(attempt.id) && attempt.package_id === packageId && identifier(attempt.package_id), '尝试记录的版本、标识或学习包不匹配。');
    requireValue(hash(attempt.context_hash) && ['path_id', 'step_id', 'activity_id'].every(key => identifier(attempt[key])) && date(attempt.created_at), '尝试记录的上下文、步骤或日期无效。');
    requireValue(['learner', 'assisted', 'reference', 'unknown'].includes(attempt.work_origin), '请选择产物来源。');
    requireValue(typeof attempt.response === 'string' && typeof attempt.blocker === 'string' && strings(attempt.artifact_refs) && new Set(attempt.artifact_refs).size === attempt.artifact_refs.length && strings(attempt.criteria, true), '尝试内容、产物引用或自查标准无效。');
    requireValue(nonempty(attempt.response) || nonempty(attempt.blocker) || attempt.artifact_refs.length > 0, '请至少填写尝试内容、产物位置或卡点。');
    if (context) {
      const step = context.steps.find(item => item.path_id === attempt.path_id && item.step_id === attempt.step_id);
      requireValue(context.package_id === packageId && attempt.context_hash === context.context_hash && step && step.activity_id === attempt.activity_id && canonical(step.success_criteria) === canonical(attempt.criteria), '尝试与当前活动或学习计划不匹配，原记录不能自动归到新任务。');
    }
    return clone(attempt);
  }
  function validateAdoption(item) {
    fields(item, ['id', 'feedback_id', 'attempt_id', 'context_hash', 'adopted_at'], '建议采用记录');
    requireValue(['id', 'feedback_id', 'attempt_id'].every(key => identifier(item[key])) && hash(item.context_hash) && date(item.adopted_at), '建议采用记录的标识、上下文或日期无效。');
    return clone(item);
  }
  const draftKey = item => item.context_hash + '/' + item.path_id + '/' + item.step_id;
  function validateDraft(item) {
    fields(item, ['context_hash', 'path_id', 'step_id', 'activity_id', 'updated_at', 'response', 'artifact_refs_text', 'blocker', 'work_origin', 'pending_attempt_id'], '尝试草稿');
    requireValue(hash(item.context_hash) && ['path_id', 'step_id', 'activity_id'].every(key => identifier(item[key])) && date(item.updated_at), '草稿的上下文、步骤或日期无效。');
    requireValue(['response', 'artifact_refs_text', 'blocker'].every(key => typeof item[key] === 'string') && ['learner', 'assisted', 'reference', 'unknown'].includes(item.work_origin), '草稿内容或来源无效。');
    requireValue(item.pending_attempt_id === null || identifier(item.pending_attempt_id), '草稿关联的尝试标识无效。');
    return clone(item);
  }
  function draftFields(item) {
    return {response: item.response, artifact_refs: item.artifact_refs_text.split(/\r?\n/).map(value => value.trim()).filter(Boolean), blocker: item.blocker, work_origin: item.work_origin};
  }
  function mergeDrafts(existing, incoming) {
    requireValue(Array.isArray(existing) && Array.isArray(incoming), '尝试草稿必须是列表。');
    const result = [], seen = new Map();
    for (const value of [...existing, ...incoming]) {
      const item = validateDraft(value), key = draftKey(item);
      if (seen.has(key)) {
        const content = entry => { const copy = clone(entry); delete copy.updated_at; delete copy.pending_attempt_id; return copy; };
        requireValue(canonical(content(seen.get(key))) === canonical(content(item)), '同一步骤有不同的未提交草稿，未覆盖任何内容。请先导出并处理本页草稿，再导入。');
        // A failed submission backup may add a pending attempt to the exact
        // same saved input. Recover that association without creating a copy.
        if (!seen.get(key).pending_attempt_id && item.pending_attempt_id) seen.get(key).pending_attempt_id = item.pending_attempt_id;
      } else { seen.set(key, item); result.push(item); }
    }
    return result;
  }
  function validateCursor(item) {
    if (item === null) return null;
    fields(item, ['adoption_id', 'feedback_id', 'context_hash', 'path_id', 'step_id', 'baseline_attempt_ids'], '当前指导位置');
    requireValue(['adoption_id', 'feedback_id', 'path_id', 'step_id'].every(key => identifier(item[key])) && hash(item.context_hash) && Array.isArray(item.baseline_attempt_ids) && item.baseline_attempt_ids.every(identifier) && new Set(item.baseline_attempt_ids).size === item.baseline_attempt_ids.length, '当前指导位置或已有尝试标识无效。');
    return clone(item);
  }
  function mergeImmutable(existing, incoming, validate, label) {
    requireValue(Array.isArray(existing) && Array.isArray(incoming), `${label}必须是列表。`);
    const result = [], seen = new Map();
    for (const item of [...existing, ...incoming]) {
      const validated = validate(item);
      if (seen.has(validated.id)) {
        requireValue(canonical(seen.get(validated.id)) === canonical(validated), `${label} ${validated.id} 的内容与已保存记录冲突；未覆盖任何原记录。`);
      } else { seen.set(validated.id, validated); result.push(validated); }
    }
    return result;
  }
  function create({packageId, context = null, projection = null}) {
    if (context) requireValue(object(context) && context.schema_version === 1 && context.package_id === packageId && hash(context.context_hash) && Array.isArray(context.steps), '反馈上下文与当前学习包不匹配。');
    const steps = new Map((context?.steps || []).map(step => [step.path_id + '/' + step.step_id, step]));
    const projected = projection || {schema_version: 1, package_id: packageId, attempts: [], feedback: []};
    requireValue(object(projected) && projected.schema_version === 1 && projected.package_id === packageId && Array.isArray(projected.feedback), '页面反馈数据格式或学习包不匹配。');
    const workspaceAttempts = mergeImmutable([], projected.attempts, attempt => validateAttempt(attempt, packageId), '工作区尝试');
    const workspaceById = new Map(workspaceAttempts.map(attempt => [attempt.id, attempt]));
    const feedbackIds = new Set();
    for (const feedback of projected.feedback) {
      requireValue(object(feedback) && identifier(feedback.id) && !feedbackIds.has(feedback.id) && ['current', 'stale', 'superseded'].includes(feedback.status) && typeof feedback.actionable === 'boolean', '页面反馈标识或状态无效。');
      feedbackIds.add(feedback.id);
      requireValue(workspaceById.has(feedback.attempt_id) && canonical(workspaceById.get(feedback.attempt_id)) === canonical(feedback.attempt), '页面反馈与工作区尝试内容不匹配。');
      requireValue(feedback.context_hash === feedback.attempt.context_hash && object(feedback.next_action), '页面反馈上下文或建议无效。');
    }
    // The validated contract allows observations to be omitted. Normalize the
    // display copy once for activity cards, history and adopted guidance alike.
    const generatedFeedback = projected.feedback.map(item => ({...clone(item),
      observations: item.observations === undefined ? [] : clone(item.observations)}));
    function attempts(local) {
      const entries = workspaceAttempts.map(attempt => ({attempt: clone(attempt), origin: 'workspace', conflict: false}));
      const indices = new Map(entries.map((item, index) => [item.attempt.id, index]));
      for (const attempt of local) {
        if (indices.has(attempt.id)) {
          const item = entries[indices.get(attempt.id)];
          if (canonical(item.attempt) === canonical(attempt)) item.origin = 'both';
          else { item.workspace_attempt = item.attempt; item.attempt = clone(attempt); item.origin = 'local'; item.conflict = true; }
        } else { indices.set(attempt.id, entries.length); entries.push({attempt: clone(attempt), origin: 'local', conflict: false}); }
      }
      return entries.map(item => ({...item, stale: !context || item.attempt.context_hash !== context.context_hash}));
    }
    function feedback(local, adoptions, current) {
      const combined = attempts(local);
      const latest = new Map();
      for (const item of combined) latest.set(draftKey(item.attempt), item);
      const latestFeedback = new Map();
      for (const item of generatedFeedback) latestFeedback.set(item.attempt_id, item.id);
      return generatedFeedback.map(item => {
        let status = item.status, reason = '';
        const attempt = item.attempt;
        const recorded = combined.find(entry => entry.attempt.id === item.attempt_id);
        const newest = latest.get(draftKey(attempt));
        const adopted = adoptions.some(adoption => adoption.feedback_id === item.id && adoption.attempt_id === item.attempt_id && adoption.context_hash === item.context_hash);
        if (!context || item.context_hash !== context.context_hash) { status = 'stale'; reason = '学习需求、任务、来源或资料已变化；请让 Agent 按当前计划重新反馈。'; }
        else if (recorded?.conflict || !recorded || canonical(recorded.attempt) !== canonical(attempt)) reason = '本地与工作区尝试内容不一致；请先导出记录交由 Agent 核对。';
        else if (newest?.attempt.id !== attempt.id || latestFeedback.get(attempt.id) !== item.id) { status = 'superseded'; reason = '已有更新的尝试或反馈；这条建议保留作历史。'; }
        else if (status !== 'current' || !item.actionable) reason = '这条反馈仅供历史查阅，不能直接采用。';
        else if (item.next_action.target && !steps.has(item.next_action.target.path_id + '/' + item.next_action.target.step_id)) reason = '建议指向的步骤不在当前学习计划中。';
        const guidanceReason = reason;
        if (!reason && adopted) reason = '这条建议已经采用。';
        else if (!reason && (current.path_id !== attempt.path_id || current.step_id !== attempt.step_id)) reason = '当前学习任务已变化；如需采用，请先明确返回这次反馈对应的步骤。';
        return {...clone(item), status, actionable: !reason, adoption_reason: reason, adopted, guidance_valid: !guidanceReason, guidance_reason: guidanceReason};
      });
    }
    function guidance(local, adoptions, cursor, current) {
      if (!cursor || cursor.path_id !== current.path_id || cursor.step_id !== current.step_id) return null;
      const item = feedback(local, adoptions, current).find(value => value.id === cursor.feedback_id);
      const adoption = adoptions.find(value => value.id === cursor.adoption_id && value.feedback_id === cursor.feedback_id && value.context_hash === cursor.context_hash);
      let reason = '';
      if (!item || !adoption || adoption.attempt_id !== item.attempt_id) reason = '原反馈或采用记录当前不可用，请查看学习记录中的历史。';
      else if (cursor.context_hash !== context?.context_hash || item.context_hash !== cursor.context_hash) reason = '学习计划已变化，这份已采用指导仅作为历史保留。';
      else if (!item.guidance_valid) reason = item.guidance_reason;
      else {
        const target = item.next_action.target || {path_id: item.attempt.path_id, step_id: item.attempt.step_id};
        if (target.path_id !== cursor.path_id || target.step_id !== cursor.step_id) reason = '指导与当前步骤不匹配。';
        else if (attempts(local).some(entry => !entry.stale && entry.attempt.path_id === cursor.path_id && entry.attempt.step_id === cursor.step_id && !cursor.baseline_attempt_ids.includes(entry.attempt.id))) reason = '此步骤已有后续尝试；请根据新产物取得反馈，原指导保留作历史。';
      }
      return {active: !reason, reason, feedback: item || null, target: {path_id: cursor.path_id, step_id: cursor.step_id}};
    }
    return {context: context ? clone(context) : null, attempts, feedback, guidance,
      currentStep(pathId, stepId) { return clone(steps.get(pathId + '/' + stepId) || null); }};
  }
  const api = {validateAttempt, validateAdoption, validateDraft, draftFields, draftKey, mergeDrafts, validateCursor, mergeImmutable, create, canonical};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.C2CFeedback = api;
})(typeof globalThis === 'object' ? globalThis : this);
