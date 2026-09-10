'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const projectRoot = path.resolve(__dirname, '..');
const graphJsPath = path.join(projectRoot, 'knowledge-base-manager/assets/graph/graph.js');
const graphCssPath = path.join(projectRoot, 'knowledge-base-manager/assets/graph/graph.css');

assert.ok(fs.existsSync(graphJsPath), 'graph.js must exist');
assert.ok(fs.existsSync(graphCssPath), 'graph.css must exist');

const jsCode = fs.readFileSync(graphJsPath, 'utf8');
const cssCode = fs.readFileSync(graphCssPath, 'utf8');

// =========================================================================
// 1. Static Syntax & Security Checks
// =========================================================================
console.log('--- 1. Static Syntax & Security Checks ---');

// Check JS syntax with Node vm
new vm.Script(jsCode, { filename: 'graph.js' });
console.log('  [PASS] graph.js parsed without syntax errors.');

// Check forbidden network / import keywords
const forbiddenPatterns = [
  /\bfetch\s*\(/i,
  /\bXMLHttpRequest\b/i,
  /\bWebSocket\b/i,
  /\bimport\s+.*\s+from\b/i,
  /\bimport\s*\(/i,
  /\bnavigator\.sendBeacon\b/i
];
for (const pat of forbiddenPatterns) {
  assert.ok(!pat.test(jsCode), `graph.js must not contain forbidden pattern: ${pat}`);
}
console.log('  [PASS] No forbidden dynamic network or import APIs found.');

// Check CSS scope safety: every rule selector must be scoped under .kb-graph-
// Strip comments and media queries
const strippedCss = cssCode
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/@media[^{]+\{([\s\S]+?\})\s*\}/g, '$1');

// Match selectors before {
const ruleRegex = /([^{}]+)\{/g;
let match;
while ((match = ruleRegex.exec(strippedCss)) !== null) {
  const selectorGroup = match[1].trim();
  if (selectorGroup.startsWith('@')) continue; // keyframes, etc.
  const selectors = selectorGroup.split(',').map(s => s.trim()).filter(Boolean);
  for (const sel of selectors) {
    // Each selector MUST contain .kb-graph-
    assert.ok(
      sel.includes('.kb-graph-'),
      `CSS selector must be scoped to .kb-graph-*: "${sel}"`
    );
  }
}
console.log('  [PASS] All CSS selectors in graph.css are strictly scoped to .kb-graph-*.');

// =========================================================================
// 2. DOM Mock Environment
// =========================================================================
console.log('--- 2. DOM Mock & Component Logic Tests ---');

class MockClassList {
  constructor(el) {
    this._el = el;
  }
  _tokens() {
    return (this._el.className || '').split(/\s+/).filter(Boolean);
  }
  contains(name) {
    return this._tokens().includes(name);
  }
  add(...names) {
    const set = new Set(this._tokens());
    names.forEach(n => set.add(n));
    this._el.className = Array.from(set).join(' ');
  }
  remove(...names) {
    const set = new Set(this._tokens());
    names.forEach(n => set.delete(n));
    this._el.className = Array.from(set).join(' ');
  }
  toggle(name, force) {
    const has = this.contains(name);
    const next = typeof force === 'boolean' ? force : !has;
    if (next) this.add(name); else this.remove(name);
    return next;
  }
}

class MockElement {
  constructor(tag, isSvg = false) {
    this.tagName = tag.toUpperCase();
    this.isSvg = isSvg;
    this.children = [];
    this.parentElement = null;
    this.attributes = {};
    this.listeners = {};
    this.className = '';
    this.classList = new MockClassList(this);
    this.dataset = {};
    this.style = {};
    this.id = '';
    this._textContent = '';
    this._open = false;
  }

  get textContent() {
    if (this.children.length === 0) return this._textContent;
    return this.children.map(c => c.textContent).join('');
  }
  set textContent(val) {
    this.children = [];
    this._textContent = String(val);
  }

  get innerHTML() {
    return this._textContent;
  }
  set innerHTML(html) {
    // Minimal mock for setting innerHTML (used for legend / note)
    this._textContent = html;
  }

  get firstChild() {
    return this.children[0] || null;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) {
      this.children.splice(idx, 1);
      child.parentElement = null;
    }
    return child;
  }

  remove() {
    if (this.parentElement) {
      this.parentElement.removeChild(this);
    }
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'id') this.id = String(value);
    if (name === 'class') this.className = String(value);
    if (name.startsWith('data-')) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      this.dataset[key] = String(value);
    }
    if (name === 'open') this._open = true;
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
    if (name === 'open') this._open = false;
  }

  hasAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name);
  }

  addEventListener(type, listener) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type, listener) {
    if (!this.listeners[type]) return;
    this.listeners[type] = this.listeners[type].filter(l => l !== listener);
  }

  dispatchEvent(event) {
    event.target = this;
    const list = this.listeners[event.type] || [];
    for (const fn of list) {
      fn.call(this, event);
    }
    return !event.defaultPrevented;
  }

  click() {
    let prevented = false;
    let stopped = false;
    const event = {
      type: 'click',
      target: this,
      preventDefault() { prevented = true; this.defaultPrevented = true; },
      stopPropagation() { stopped = true; },
      stopImmediatePropagation() { stopped = true; },
      defaultPrevented: false
    };
    let curr = this;
    while (curr && !stopped) {
      curr.dispatchEvent(event);
      curr = curr.parentElement;
    }
  }

  focus() {
    mockDocument.activeElement = this;
  }

  getBoundingClientRect() {
    return { width: 800, height: 600, left: 0, top: 0, right: 800, bottom: 600 };
  }

  showModal() {
    this._open = true;
    this.setAttribute('open', '');
  }

  close() {
    this._open = false;
    this.removeAttribute('open');
  }

  get open() {
    return this._open;
  }

  querySelectorAll(sel) {
    const results = [];
    function walk(node) {
      for (const child of node.children) {
        if (matchesSimple(child, sel)) {
          results.push(child);
        }
        walk(child);
      }
    }
    walk(this);
    return results;
  }

  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }

  closest(sel) {
    let curr = this;
    while (curr) {
      if (matchesSimple(curr, sel)) return curr;
      curr = curr.parentElement;
    }
    return null;
  }
}

function matchesSimple(el, sel) {
  if (sel.startsWith('.')) {
    return el.classList.contains(sel.slice(1));
  }
  if (sel.startsWith('#')) {
    return el.id === sel.slice(1);
  }
  if (sel.includes('[tabindex]')) {
    return el.hasAttribute('tabindex');
  }
  if (sel.includes('a[href]')) {
    return el.tagName === 'A' && el.hasAttribute('href');
  }
  if (sel.includes('button')) {
    return el.tagName === 'BUTTON';
  }
  return el.tagName.toLowerCase() === sel.toLowerCase();
}

const mockDocument = {
  activeElement: null,
  createElement(tag) {
    return new MockElement(tag, false);
  },
  createElementNS(ns, tag) {
    return new MockElement(tag, true);
  },
  addEventListener(type, listener) {
    if (!this._listeners) this._listeners = {};
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(listener);
  },
  removeEventListener(type, listener) {
    if (!this._listeners || !this._listeners[type]) return;
    this._listeners[type] = this._listeners[type].filter(l => l !== listener);
  },
  dispatchEvent(event) {
    const list = (this._listeners && this._listeners[event.type]) || [];
    for (const fn of list) fn(event);
  }
};

const mockWindow = {
  document: mockDocument,
  __KB_GRAPH_DATA__: null,
  __KB_GRAPH_PREVIEWS__: null,
  matchMedia(query) {
    return { matches: false, media: query, addEventListener() {}, removeEventListener() {} };
  },
  addEventListener(type, listener) {
    mockDocument.addEventListener(type, listener);
  },
  removeEventListener(type, listener) {
    mockDocument.removeEventListener(type, listener);
  },
  requestAnimationFrame(cb) {
    return setTimeout(() => cb(Date.now()), 0);
  },
  cancelAnimationFrame(id) {
    clearTimeout(id);
  },
  performance: {
    now() { return Date.now(); }
  }
};

// Execute graph.js inside mock context
const context = vm.createContext({
  window: mockWindow,
  document: mockDocument,
  performance: mockWindow.performance,
  requestAnimationFrame: mockWindow.requestAnimationFrame,
  cancelAnimationFrame: mockWindow.cancelAnimationFrame,
  setTimeout,
  clearTimeout,
  console
});

vm.runInContext(jsCode, context, { filename: 'graph.js' });
assert.equal(typeof mockWindow.mountKbGraph, 'function', 'window.mountKbGraph must be defined');
console.log('  [PASS] window.mountKbGraph mounted successfully.');

// =========================================================================
// 3. Multi-Parent BFS Depth Calculation & Radius Verification
// =========================================================================
console.log('--- 3. Multi-Parent BFS Depth Calculation & Radius ---');

/**
 * Topology:
 * entry: "page:entry" (L0)
 * col1: "page:col1" (collected by entry, order=0) -> L1
 * col2: "page:col2" (collected by entry, order=1) -> L1
 * shared_leaf: "page:shared"
 *   - collected by col1 (order=10)
 *   - collected by col2 (order=5) -> shortest path depth 2 (L2)
 * sec1: "sec:page:shared#sec-1" -> contained by shared -> L3
 * ref1: "ref:web1" -> referenced by shared -> L3
 * uncollected: "page:uncollected" -> no incoming collects -> depth null
 */
const mockGraphData = {
  schema: 'kb-graph',
  schema_version: 1,
  graph_digest: 'test-digest-001',
  entry_id: 'page:entry',
  nodes: [
    {
      id: 'page:entry',
      kind: 'page',
      title: '入口主页',
      target: { kind: 'internal', path: 'index.html', fragment: null },
      preview_key: 'page:entry',
      page: { source_path: 'index.md', kb_id: 'entry', type: 'collection', status: 'stable', tags: [] },
      section: null,
      reference: null
    },
    {
      id: 'page:col1',
      kind: 'page',
      title: '第一专题',
      target: { kind: 'internal', path: 'col1.html', fragment: null },
      preview_key: 'page:col1',
      page: { source_path: 'col1.md', kb_id: 'col1', type: 'collection', status: 'stable', tags: [] },
      section: null,
      reference: null
    },
    {
      id: 'page:col2',
      kind: 'page',
      title: '第二专题',
      target: { kind: 'internal', path: 'col2.html', fragment: null },
      preview_key: 'page:col2',
      page: { source_path: 'col2.md', kb_id: 'col2', type: 'collection', status: 'stable', tags: [] },
      section: null,
      reference: null
    },
    {
      id: 'page:shared',
      kind: 'page',
      title: '双父共享知识页',
      target: { kind: 'internal', path: 'shared.html', fragment: null },
      preview_key: 'page:shared',
      page: { source_path: 'shared.md', kb_id: 'shared', type: 'concept', status: 'stable', tags: [] },
      section: null,
      reference: null
    },
    {
      id: 'sec:page:shared#sec-1',
      kind: 'section',
      title: '核心原理章节',
      target: { kind: 'internal', path: 'shared.html', fragment: 'sec-1' },
      preview_key: 'sec:page:shared#sec-1',
      page: null,
      section: { owner_page: 'page:shared', heading_level: 2, ordinal: 0 },
      reference: null
    },
    {
      id: 'ref:web1',
      kind: 'reference',
      title: '外部文献规范',
      target: { kind: 'web', url: 'https://example.org/spec' },
      preview_key: 'ref:web1',
      page: null,
      section: null,
      reference: { medium: 'web', source_label: 'RFC 9999' }
    },
    {
      id: 'page:uncollected',
      kind: 'page',
      title: '未收录页面',
      target: { kind: 'internal', path: 'orphan.html', fragment: null },
      preview_key: 'page:uncollected',
      page: { source_path: 'orphan.md', kb_id: 'orphan', type: 'page', status: 'draft', tags: [] },
      section: null,
      reference: null
    }
  ],
  edges: [
    {
      id: 'e1',
      kind: 'collects',
      source: 'page:entry',
      target: 'page:col1',
      order: 0,
      occurrences: []
    },
    {
      id: 'e2',
      kind: 'collects',
      source: 'page:entry',
      target: 'page:col2',
      order: 1,
      occurrences: []
    },
    // Multi-parent edges to shared:
    {
      id: 'e3_col1',
      kind: 'collects',
      source: 'page:col1',
      target: 'page:shared',
      order: 10,
      occurrences: []
    },
    {
      id: 'e4_col2',
      kind: 'collects',
      source: 'page:col2',
      target: 'page:shared',
      order: 5,
      occurrences: []
    },
    // Section contained in shared:
    {
      id: 'e5_sec',
      kind: 'contains',
      source: 'page:shared',
      target: 'sec:page:shared#sec-1',
      order: 0,
      occurrences: []
    },
    // Reference from shared:
    {
      id: 'e6_ref',
      kind: 'references',
      source: 'page:shared',
      target: 'ref:web1',
      order: 0,
      occurrences: []
    }
  ],
  diagnostics: []
};

const mockPreviewData = {
  schema: 'kb-graph-previews',
  schema_version: 1,
  preview_digest: 'test-preview-digest',
  graph_digest: 'test-digest-001',
  records: [
    {
      key: 'page:shared',
      node_id: 'page:shared',
      mode: 'excerpt',
      text: '这是双父共享页面的正文首段内容。\n\n包含关于密码学与协议的核心描述。',
      truncated: true,
      origin: 'rendered-body'
    },
    {
      key: 'ref:web1',
      node_id: 'ref:web1',
      mode: 'metadata',
      text: 'RFC 9999 (外部规范)',
      truncated: false,
      origin: 'link-registration'
    }
  ]
};

const container = mockDocument.createElement('div');
const graph = mockWindow.mountKbGraph(container, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline',
  outputBaseUrl: '..',
  lang: 'zh'
});

// Check API return methods
assert.equal(typeof graph.focus, 'function', 'API must return focus(nodeId)');
assert.equal(typeof graph.highlightNodes, 'function', 'API must return highlightNodes(nodeIds)');
assert.equal(typeof graph.resetHighlight, 'function', 'API must return resetHighlight()');
assert.equal(typeof graph.fit, 'function', 'API must return fit()');
assert.equal(typeof graph.reset, 'function', 'API must return reset()');
assert.equal(typeof graph.destroy, 'function', 'API must return destroy()');
assert.equal(typeof graph.getState, 'function', 'API must return getState()');
assert.equal(typeof graph.setState, 'function', 'API must return setState()');
assert.equal(typeof graph.focusEgo, 'function', 'API must return focusEgo()');
assert.equal(typeof graph.exitFocus, 'function', 'API must return exitFocus()');
console.log('  [PASS] All 10 API methods returned.');

// Check rendered SVG elements
const svg = container.querySelector('.kb-graph-svg');
assert.ok(svg, 'SVG canvas must exist');
const nodeLayer = svg.querySelector('.kb-graph-node-layer');
assert.ok(nodeLayer, 'Node layer must exist');
const edgeLayer = svg.querySelector('.kb-graph-edge-layer');
assert.ok(edgeLayer, 'Edge layer must exist');

// Check entry node: initially expanded
const entryNodeEl = nodeLayer.children.find(n => n.dataset.id === 'page:entry');
assert.ok(entryNodeEl, 'Entry node must be rendered');
assert.equal(entryNodeEl.dataset.depth, '0', 'Entry node must have depth 0');

const entryCircle = entryNodeEl.children.find(c => c.classList.contains('kb-graph-body'));
assert.equal(entryCircle.getAttribute('r'), '88', 'L0 entry radius must be 88');

// Check col1 and col2: children of entry (L1)
const col1El = nodeLayer.children.find(n => n.dataset.id === 'page:col1');
const col2El = nodeLayer.children.find(n => n.dataset.id === 'page:col2');
assert.ok(col1El, 'col1 must be rendered');
assert.ok(col2El, 'col2 must be rendered');
assert.equal(col1El.dataset.depth, '1', 'col1 must have depth 1');
assert.equal(col2El.dataset.depth, '1', 'col2 must have depth 1');

const col1Circle = col1El.children.find(c => c.classList.contains('kb-graph-body'));
assert.equal(col1Circle.getAttribute('r'), '72', 'L1 radius must be 72');
console.log('  [PASS] L0 radius 88 and L1 radius 72 verified.');

// =========================================================================
// 4. Multi-Parent Pivot & BFS Shortest Path Selection
// =========================================================================
console.log('--- 4. Multi-Parent Pivot & BFS Shortest Path ---');

// Expand col1 and col2
graph.focus('page:shared'); // Should expand path and focus shared

const sharedEl = nodeLayer.children.find(n => n.dataset.id === 'page:shared');
assert.ok(sharedEl, 'page:shared must now be visible after focus()');
assert.equal(sharedEl.dataset.depth, '2', 'page:shared BFS depth must be 2 (L2)');
const sharedCircle = sharedEl.children.find(c => c.classList.contains('kb-graph-body'));
assert.equal(sharedCircle.getAttribute('r'), '57', 'L2 radius must be 57');

// Expand page:shared to view its section and reference
sharedCircle.dispatchEvent({
  type: 'keydown',
  key: 'Enter',
  defaultPrevented: false,
  preventDefault() {}
});

const secEl = nodeLayer.children.find(n => n.dataset.id === 'sec:page:shared#sec-1');
assert.ok(secEl, 'Section node must be rendered');
assert.equal(secEl.dataset.depth, '3', 'Section depth must be parent depth + 1 (L3)');
const secCircle = secEl.children.find(c => c.classList.contains('kb-graph-body'));
assert.equal(secCircle.getAttribute('r'), '44', 'L3 radius must be 44');

const refEl = nodeLayer.children.find(n => n.dataset.id === 'ref:web1');
assert.ok(refEl, 'Reference node must be rendered');
assert.equal(refEl.dataset.depth, '3', 'Reference depth must be source depth + 1 (L3)');
const refCircle = refEl.children.find(c => c.classList.contains('kb-graph-body'));
assert.equal(refCircle.getAttribute('r'), '44', 'Reference radius must be 44');
console.log('  [PASS] Section and reference L3 depths and radii 44 verified.');

// Check links and target="_blank"
const sharedLink = sharedEl.querySelector('a');
assert.ok(sharedLink, 'Title link must exist');
assert.equal(sharedLink.getAttribute('target'), '_blank', 'Title link must open in new tab (_blank)');
assert.equal(sharedLink.getAttribute('rel'), 'noopener noreferrer', 'Title link must have rel="noopener noreferrer"');
assert.equal(sharedLink.getAttribute('href'), '../shared.html', 'Path must prepend outputBaseUrl (..) properly');

const secLink = secEl.querySelector('a');
assert.equal(secLink.getAttribute('href'), '../shared.html#sec-1', 'Section path must include anchor #sec-1');
console.log('  [PASS] New tab links with outputBaseUrl and anchors verified.');

// =========================================================================
// 5. Search Highlight Interactivity API
// =========================================================================
console.log('--- 5. Search Highlight Interactivity API ---');

// Re-query active elements in nodeLayer after re-render
const activeSharedEl = nodeLayer.children.find(n => n.dataset.id === 'page:shared');
const activeEntryEl = nodeLayer.children.find(n => n.dataset.id === 'page:entry');
assert.ok(activeSharedEl, 'page:shared must exist in nodeLayer');
assert.ok(activeEntryEl, 'page:entry must exist in nodeLayer');

// Call highlightNodes(['page:shared'])
graph.highlightNodes(['page:shared']);
assert.ok(activeSharedEl.classList.contains('is-search-match'), 'Target node has is-search-match');
assert.ok(!activeSharedEl.classList.contains('is-muted'), 'Target node is not muted');
assert.ok(activeEntryEl.classList.contains('is-muted'), 'Other node is muted');

// Reset highlight
graph.resetHighlight();
assert.ok(!activeSharedEl.classList.contains('is-search-match'), 'is-search-match cleared');
assert.ok(!activeEntryEl.classList.contains('is-muted'), 'is-muted cleared');
console.log('  [PASS] highlightNodes and resetHighlight work as specified.');

// =========================================================================
// 6. Preview Dialog Modal & XSS Safety
// =========================================================================
console.log('--- 6. Preview Dialog Modal & XSS Safety ---');

const previewBtn = activeSharedEl.querySelector('.kb-graph-preview-btn');
assert.ok(previewBtn, 'Preview button must exist');
previewBtn.click();

const dialog = container.querySelector('.kb-graph-dialog');
assert.ok(dialog.open, 'Dialog must be open after clicking preview');
const dialogTitle = dialog.querySelector('.kb-graph-dialog-title');
assert.equal(dialogTitle.textContent, '双父共享知识页', 'Dialog title matched');

const dialogContent = dialog.querySelector('.kb-graph-dialog-content');
assert.ok(dialogContent.textContent.includes('这是双父共享页面的正文首段内容'), 'Excerpt text rendered');
assert.ok(dialogContent.textContent.includes('已截取前段文字'), 'Truncated hint displayed');

// Check dialog close
const closeDialogBtn = dialog.querySelector('.kb-graph-dialog-close');
closeDialogBtn.click();
assert.ok(!dialog.open, 'Dialog must be closed after clicking close button');
console.log('  [PASS] Preview dialog opened and closed cleanly with safe textContent.');

// =========================================================================
// 7. Overlay Mode & Esc Key Handling
// =========================================================================
console.log('--- 7. Overlay Mode & Esc Key Handling ---');

const overlayContainer = mockDocument.createElement('div');
const overlayGraph = mockWindow.mountKbGraph(overlayContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'overlay',
  outputBaseUrl: '.'
});

const overlayRoot = overlayContainer.querySelector('.kb-graph-root');
assert.ok(overlayRoot.classList.contains('kb-graph-mode-overlay'), 'Root has overlay class');

const overlayCloseBtn = overlayRoot.querySelector('.kb-graph-btn-close');
assert.ok(overlayCloseBtn, 'Overlay must have close button');

// Press Escape key on document to close overlay
mockDocument.dispatchEvent({
  type: 'keydown',
  key: 'Escape',
  stopPropagation() {}
});

assert.equal(overlayRoot.parentElement, null, 'Overlay destroyed and removed from DOM on Escape');
console.log('  [PASS] Overlay mode Esc key and cleanup verified.');

// Clean up inline graph
graph.destroy();
assert.equal(container.querySelector('.kb-graph-root'), null, 'Inline graph destroyed and cleaned up');
console.log('  [PASS] graph.destroy() cleaned up successfully.');

// =========================================================================
// 8. Multi-Parent Collapse Invariant
// =========================================================================
console.log('--- 8. Multi-Parent Collapse Invariant ---');

const multiParentContainer = mockDocument.createElement('div');
const mpGraph = mockWindow.mountKbGraph(multiParentContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline'
});

// Expand both col1 and col2
const mpNodeLayer = multiParentContainer.querySelector('.kb-graph-node-layer');
const mpCol1El = mpNodeLayer.children.find(n => n.dataset.id === 'page:col1');
const mpCol2El = mpNodeLayer.children.find(n => n.dataset.id === 'page:col2');
assert.ok(mpCol1El && mpCol2El, 'Both col1 and col2 exist');

// Click col1 body to expand
const mpCol1Body = mpCol1El.querySelector('.kb-graph-body');
mpCol1Body.click();
let mpShared = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:shared');
assert.ok(mpShared, 'shared visible after col1 expanded');

// Click col2 body to expand
const mpCol2Body = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:col2').querySelector('.kb-graph-body');
mpCol2Body.click();
mpShared = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:shared');
assert.ok(mpShared, 'shared remains visible after both col1 and col2 expanded');

// Now collapse col1
const mpCol1BodyToCollapse = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:col1').querySelector('.kb-graph-body');
mpCol1BodyToCollapse.click();

// shared MUST STILL BE VISIBLE and active because col2 is still expanded!
mpShared = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:shared');
assert.ok(mpShared, 'INVARIANT HELD: shared node remains in DOM when col1 collapses because col2 is still expanded!');
assert.ok(!mpShared.hasAttribute('aria-hidden'), 'shared node is active (not aria-hidden) because col2 is still expanded');

// Now collapse col2
const mpCol2BodyToCollapse = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:col2').querySelector('.kb-graph-body');
mpCol2BodyToCollapse.click();

// Now shared should be collapsed (marked aria-hidden during exit animation or removed)
mpShared = multiParentContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:shared');
assert.ok(mpShared === undefined || mpShared.hasAttribute('aria-hidden'), 'shared node is collapsed/hidden when both parents are collapsed');
console.log('  [PASS] Multi-parent branch collapse invariant fully verified.');

mpGraph.destroy();

// =========================================================================
// 9. Standalone Mode & Global Window Fallbacks
// =========================================================================
console.log('--- 9. Standalone Mode & Global Window Fallbacks ---');

mockWindow.__KB_GRAPH_DATA__ = mockGraphData;
mockWindow.__KB_GRAPH_PREVIEWS__ = mockPreviewData;

const standaloneContainer = mockDocument.createElement('div');
const standaloneGraph = mockWindow.mountKbGraph(standaloneContainer, {
  mode: 'standalone' // data and previews omitted: must use window globals!
});

const saRoot = standaloneContainer.querySelector('.kb-graph-root');
assert.ok(saRoot.classList.contains('kb-graph-mode-standalone'), 'Root has standalone class');
assert.ok(saRoot.querySelector('.kb-graph-svg'), 'SVG rendered from global __KB_GRAPH_DATA__');

// In standalone mode, close button is NOT added
const saCloseBtn = saRoot.querySelector('.kb-graph-btn-close');
assert.equal(saCloseBtn, null, 'Standalone mode must not have close button in header');
console.log('  [PASS] Standalone mode and window global fallback verified.');

// Test reset and fit
standaloneGraph.fit();
standaloneGraph.reset();
console.log('  [PASS] standaloneGraph.fit() and reset() executed without error.');

standaloneGraph.destroy();
mockWindow.__KB_GRAPH_DATA__ = null;
mockWindow.__KB_GRAPH_PREVIEWS__ = null;

// =========================================================================
// 10. State Synchronization & Ego-Focus Network Tests
// =========================================================================
console.log('--- 10. State Synchronization & Ego-Focus Network Tests ---');

const syncContainer = mockDocument.createElement('div');
const syncGraph = mockWindow.mountKbGraph(syncContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline'
});

// Test 1: Initial state
const initialState = syncGraph.getState();
assert.ok(Array.isArray(initialState.expanded), 'initialState.expanded is array');
assert.ok(initialState.expanded.includes('page:entry'), 'initialState includes page:entry');
assert.equal(initialState.egoFocusId, null, 'initialState egoFocusId is null');

// Test 2: setState updates expanded
syncGraph.setState({
  expanded: ['page:entry', 'page:col1'],
  focusedId: 'page:col1',
  egoFocusId: null
});
const updatedState = syncGraph.getState();
assert.ok(updatedState.expanded.includes('page:col1'), 'updatedState includes page:col1');
assert.equal(updatedState.focusedId, 'page:col1', 'focusedId is page:col1');

// Test 3: Overlay inherits state and triggers onClose on close
let receivedCloseState = null;
const overlayTestContainer = mockDocument.createElement('div');
const overlaySyncGraph = mockWindow.mountKbGraph(overlayTestContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'overlay',
  initialExpanded: updatedState.expanded,
  initialFocusedId: updatedState.focusedId,
  onClose: function (finalState) {
    receivedCloseState = finalState;
  }
});

const overlayInitState = overlaySyncGraph.getState();
assert.deepEqual(overlayInitState.expanded.sort(), updatedState.expanded.sort(), 'Overlay inherited expanded nodes');
assert.equal(overlayInitState.focusedId, 'page:col1', 'Overlay inherited focusedId');

// Close overlay via close button
const syncOverlayCloseBtn = overlayTestContainer.querySelector('.kb-graph-btn-close');
assert.ok(syncOverlayCloseBtn, 'Overlay close button exists');
syncOverlayCloseBtn.click();
assert.ok(receivedCloseState, 'onClose callback was triggered');
assert.deepEqual(receivedCloseState.expanded.sort(), updatedState.expanded.sort(), 'onClose returned final state');

// Test 4: Ego Focus Mode (focusEgo)
syncGraph.focusEgo('page:col1');
const egoState = syncGraph.getState();
assert.equal(egoState.egoFocusId, 'page:col1', 'egoFocusId set to page:col1');

// Check visible nodes in ego mode: only center and 1-hop connected neighbors
const syncNodeLayer = syncContainer.querySelector('.kb-graph-node-layer');
const egoCenterEl = syncNodeLayer.children.find(n => n.dataset.id === 'page:col1');
assert.ok(egoCenterEl, 'Ego center page:col1 is present');
assert.ok(egoCenterEl.classList.contains('is-ego-center'), 'Ego center has is-ego-center class');

// Test 5: Initial mount in ego focus mode (synchronous render without animation)
const egoMountContainer = mockDocument.createElement('div');
const egoMountedGraph = mockWindow.mountKbGraph(egoMountContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline',
  initialEgoFocusId: 'page:col1'
});
const egoInitCenterEl = egoMountContainer.querySelector('.kb-graph-node-layer').children.find(n => n.dataset.id === 'page:col1');
assert.ok(egoInitCenterEl, 'Ego mounted center is present');
assert.ok(egoInitCenterEl.classList.contains('is-ego-center'), 'Ego mounted center has is-ego-center class');
assert.equal(egoInitCenterEl.getAttribute('transform'), 'translate(0 0)', 'Ego center positioned at (0, 0)');
egoMountedGraph.destroy();

// Check exit focus button
const exitFocusBtn = syncContainer.querySelector('.kb-graph-btn-exit-focus');
assert.ok(exitFocusBtn, 'Exit focus button exists in header');
assert.notEqual(exitFocusBtn.style.display, 'none', 'Exit focus button is visible in ego focus mode');

// Check exit focus restores normal layout AND centers on previous focused node
syncGraph.exitFocus();
const postExitState = syncGraph.getState();
assert.equal(postExitState.egoFocusId, null, 'egoFocusId cleared after exitFocus()');
assert.equal(postExitState.focusedId, 'page:col1', 'focusedId centered on previously focused node (page:col1)');
assert.equal(exitFocusBtn.style.display, 'none', 'Exit focus button hidden after exit');
console.log('  [PASS] State sync and ego-focus network invariants verified.');

syncGraph.destroy();

// =========================================================================
// 11. Layout Coordinates, Legend Removal & Node Button Centering
// =========================================================================
console.log('--- 11. Layout Coordinates, Legend Removal & Node Button Centering ---');

const layoutTestContainer = mockDocument.createElement('div');
const layoutGraph = mockWindow.mountKbGraph(layoutTestContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline'
});

// Invariant: Legend removed from DOM
const legendEl = layoutTestContainer.querySelector('.kb-graph-legend');
assert.equal(legendEl, null, 'Legend element must not exist in DOM');

// Check entry node elements and positioning
const layoutNodeLayer = layoutTestContainer.querySelector('.kb-graph-node-layer');
const entryEl = layoutNodeLayer.children.find(n => n.dataset.id === 'page:entry');
assert.ok(entryEl, 'Entry node rendered');

const kindTextEl = entryEl.querySelector('.kb-graph-kind');
assert.ok(kindTextEl, 'Kind text exists');
assert.equal(kindTextEl.getAttribute('y'), '-24', 'Kind text y must be -24');

const focusBtnEl = entryEl.querySelector('.kb-graph-focus-btn');
assert.ok(focusBtnEl, 'Focus button exists');
const focusRect = focusBtnEl.querySelector('rect');
assert.equal(focusRect.getAttribute('y'), '22', 'Focus button rect y must be 22');
assert.equal(focusRect.getAttribute('height'), '19', 'Focus button rect height must be 19');
const focusTextEl = focusBtnEl.querySelector('text');
assert.equal(focusTextEl.getAttribute('y'), '31.5', 'Focus button text y must be 31.5');

const previewBtnEl = entryEl.querySelector('.kb-graph-preview-btn');
assert.ok(previewBtnEl, 'Preview button exists');
const previewRect = previewBtnEl.querySelector('rect');
assert.equal(previewRect.getAttribute('y'), '22', 'Preview button rect y must be 22');
assert.equal(previewRect.getAttribute('height'), '19', 'Preview button rect height must be 19');
const previewTextEl = previewBtnEl.querySelector('text');
assert.equal(previewTextEl.getAttribute('y'), '31.5', 'Preview button text y must be 31.5');
console.log('  [PASS] Node coordinates and legend removal verified.');

layoutGraph.destroy();

// =========================================================================
// 12. Bilingual Support (English and Chinese Offline Dictionaries)
// =========================================================================
console.log('--- 12. Bilingual Support (English and Chinese Offline Dictionaries) ---');

const enContainer = mockDocument.createElement('div');
const enGraph = mockWindow.mountKbGraph(enContainer, {
  data: mockGraphData,
  previews: mockPreviewData,
  mode: 'inline',
  lang: 'en'
});

const enRoot = enContainer.querySelector('.kb-graph-root');
const enMainTitle = enRoot.querySelector('.kb-graph-main-title');
assert.equal(enMainTitle.textContent, 'Knowledge Graph', 'Main title in English is "Knowledge Graph"');

const enShowAll = enRoot.querySelector('.kb-graph-btn-show-all');
assert.equal(enShowAll.textContent, 'Expand All', 'Show all button in English is "Expand All"');

const enReset = enRoot.querySelector('.kb-graph-btn-reset');
assert.equal(enReset.textContent, 'Reset View', 'Reset button in English is "Reset View"');

const enNodeLayer = enContainer.querySelector('.kb-graph-node-layer');
const enEntryEl = enNodeLayer.children.find(n => n.dataset.id === 'page:entry');
const enFocusBtn = enEntryEl.querySelector('.kb-graph-focus-btn');
const enFocusText = enFocusBtn.querySelector('text');
assert.equal(enFocusText.textContent, 'Focus', 'Focus button text in English is "Focus"');

const enPreviewBtn = enEntryEl.querySelector('.kb-graph-preview-btn');
const enPreviewText = enPreviewBtn.querySelector('text');
assert.equal(enPreviewText.textContent, 'Preview', 'Preview button text in English is "Preview"');

// Test preview dialog in English
enPreviewBtn.click();
const enDialog = enContainer.querySelector('.kb-graph-dialog');
const enDialogEyebrow = enDialog.querySelector('.kb-graph-dialog-eyebrow');
assert.equal(enDialogEyebrow.textContent, 'Node Preview', 'Dialog eyebrow in English is "Node Preview"');
console.log('  [PASS] English offline dictionary verified.');

enGraph.destroy();

console.log('\nALL GRAPH COMPONENT TESTS PASSED SUCCESSFULLY!');
