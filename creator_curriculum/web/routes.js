/* Topic identity stays independent from the reader's page addresses. */
(function (root) {
  'use strict';
  const pages = new Set(['overview', 'progress', 'materials', 'scope', 'knowledge-map', 'learning-advice']);
  const topic = id => 'topic/' + id;
  const study = (pathId, stepId) => 'study/' + pathId + '/' + stepId;
  function resolve(route, topicIds, pathSteps = {}) {
    const known = new Set(topicIds);
    // Built-in pages win ambiguous old addresses; new topic links never collide.
    if (pages.has(route) || route.startsWith('search=') || /^materials\/\d+$/.test(route)) return {route, topicId: null};
    const match = /^study\/([A-Za-z0-9_-]+)\/([A-Za-z0-9_-]+)$/.exec(route);
    if (match && Object.prototype.hasOwnProperty.call(pathSteps, match[1]) &&
        Object.prototype.hasOwnProperty.call(pathSteps[match[1]], match[2])) {
      const topicId = pathSteps[match[1]][match[2]];
      if (known.has(topicId)) return {route: study(match[1], match[2]), topicId, pathId: match[1], stepId: match[2]};
    }
    const id = route.startsWith('topic/') ? route.slice(6) : null;
    if (id !== null && known.has(id)) return {route: topic(id), topicId: id};
    if (known.has(route)) return {route: topic(route), topicId: route};
    return {route: 'overview', topicId: null};
  }
  const api = {topic, study, resolve};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.C2CRoutes = api;
})(typeof globalThis === 'object' ? globalThis : this);
