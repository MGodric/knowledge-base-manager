/**
 * Knowledge Base Graph - Zero-dependency Offline SVG Graph Component
 * Conforms to GraphDataV1 and PreviewDataV1 specifications.
 * Supports 'inline', 'overlay', and 'standalone' modes.
 */
(function (global) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const RADIUS_TABLE = [88, 72, 57, 44]; // L0, L1, L2, L3+

  function el(tag, attrs = {}) {
    const element = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      element.setAttribute(k, String(v));
    }
    return element;
  }

  const I18N = {
    zh: {
      mainTitle: '知识关系图',
      showAll: '展开全部页面',
      reset: '回到初始视图',
      exitFocus: '退出聚焦',
      exitFocusWithNode: '退出聚焦 (当前: {0})',
      close: '关闭 ×',
      zoomIn: '放大',
      zoomOut: '缩小',
      fit: '适应视图',
      focusBtn: '聚焦',
      exitBtn: '退出',
      previewBtn: '预览',
      openArticle: '在新标签页打开全文阅读 →',
      openExternal: '访问外部链接 ↗',
      dialogEyebrow: '节点预览',
      dialogClose: '关闭 ×',
      dialogFocus: '🎯 聚焦此节点与连接',
      dialogExitFocus: '退出聚焦模式',
      externalRefNotice: '外部来源：本条目来自知识库外部登记引用，预览仅展示元数据。',
      noPreviewNotice: '暂无详细正文预览。',
      truncatedNotice: '（正文较长，已截取前段文字）',
      stats: '{0} 个可见节点 / {1} 个总条目',
      statsFocus: '正在聚焦：{0}（显示 {1} 个直接连接节点）',
      noteLines: [
        '<strong>拖动任何位置</strong>：平移视角　·　<strong>节点空白</strong>：居中聚焦并展开 / 收起',
        '<strong>蓝色名称</strong>：新标签页打开　·　<strong>预览按钮</strong>：打开摘录浮窗',
        '<strong>层级越高节点越大</strong>　·　<strong>悬停</strong>：高亮直接关系　·　<strong>虚线</strong>：正文引用'
      ],
      kinds: {
        section: '页面章节',
        reference: '外部参考',
        collection: '总结页面',
        concept: '知识页面',
        page: '知识页面',
        item: '知识条目',
        unindexed: '未收录'
      },
      liveExpandedAll: '已展开全部页面与章节',
      liveResetInitial: '已重置为初始视图',
      liveFocusedEgo: '已激活聚焦模式：{0}，显示 {1} 个直接连接节点',
      liveExitFocusCentered: '已退出聚焦模式，已居中于 {0}',
      liveExitFocus: '已退出聚焦模式，恢复全图展示',
      liveNodeToggled: '{0}已居中聚焦{1}',
      liveExpandAction: '并展开',
      liveCollapseAction: '并收起',
      aria: {
        svg: '知识关系图：拖动平移视角，滚轮缩放',
        close: '关闭图谱',
        stage: '知识关系图画布',
        nodeLabel: '{0}：居中聚焦{1}',
        nodeExpandAction: '，{0} {1} 个子节点',
        expand: '展开',
        collapse: '收起',
        openLink: '打开 {0}',
        previewNode: '预览 {0}',
        focusNode: '聚焦 {0} 与连接节点',
        exitFocusNode: '退出聚焦'
      }
    },
    en: {
      mainTitle: 'Knowledge Graph',
      showAll: 'Expand All',
      reset: 'Reset View',
      exitFocus: 'Exit Focus',
      exitFocusWithNode: 'Exit Focus (Current: {0})',
      close: 'Close ×',
      zoomIn: 'Zoom In',
      zoomOut: 'Zoom Out',
      fit: 'Fit View',
      focusBtn: 'Focus',
      exitBtn: 'Exit',
      previewBtn: 'Preview',
      openArticle: 'Read Full Article in New Tab →',
      openExternal: 'Visit External Link ↗',
      dialogEyebrow: 'Node Preview',
      dialogClose: 'Close ×',
      dialogFocus: '🎯 Focus Node & Connections',
      dialogExitFocus: 'Exit Focus Mode',
      externalRefNotice: 'External Source: Registered external reference, displaying metadata only.',
      noPreviewNotice: 'No detailed text preview available.',
      truncatedNotice: '(Text is long, showing beginning excerpt)',
      stats: '{0} visible / {1} total items',
      statsFocus: 'Focusing: {0} ({1} connected nodes)',
      noteLines: [
        '<strong>Drag canvas</strong>: Pan view　·　<strong>Click node circle</strong>: Center & Expand / Collapse',
        '<strong>Blue title</strong>: Open in new tab　·　<strong>Preview button</strong>: Open excerpt modal',
        '<strong>Higher depth = larger node</strong>　·　<strong>Hover</strong>: Highlight direct relations　·　<strong>Dashed</strong>: In-text reference'
      ],
      kinds: {
        section: 'Section',
        reference: 'Reference',
        collection: 'Overview',
        concept: 'Topic',
        page: 'Topic',
        item: 'Item',
        unindexed: 'Unindexed'
      },
      liveExpandedAll: 'Expanded all pages and sections',
      liveResetInitial: 'Reset to initial view',
      liveFocusedEgo: 'Focus mode active: {0}, showing {1} directly connected nodes',
      liveExitFocusCentered: 'Exited focus mode, centered on {0}',
      liveExitFocus: 'Exited focus mode, restored full graph',
      liveNodeToggled: '{0} centered{1}',
      liveExpandAction: ' and expanded',
      liveCollapseAction: ' and collapsed',
      aria: {
        svg: 'Knowledge Graph: Drag to pan, scroll to zoom',
        close: 'Close graph',
        stage: 'Knowledge graph canvas',
        nodeLabel: '{0}: Center and focus{1}',
        nodeExpandAction: ', {0} {1} child nodes',
        expand: 'expand',
        collapse: 'collapse',
        openLink: 'Open {0}',
        previewNode: 'Preview {0}',
        focusNode: 'Focus {0} and connections',
        exitFocusNode: 'Exit focus'
      }
    }
  };

  function labelKind(node, t) {
    const k = (t && t.kinds) ? t.kinds : I18N.zh.kinds;
    if (!node) return k.item;
    if (node.kind === 'section') return k.section;
    if (node.kind === 'reference') return k.reference;
    if (node.kind === 'page') {
      const pType = node.page && node.page.type;
      if (pType === 'collection') return k.collection;
      return k.page;
    }
    return k.item;
  }

  function resolveHref(node, outputBaseUrl) {
    if (!node || !node.target) return null;
    const target = node.target;
    if (target.kind === 'web') {
      return target.url || null;
    }
    if (target.kind === 'internal') {
      const base = (outputBaseUrl !== undefined && outputBaseUrl !== null) ? String(outputBaseUrl).replace(/\/+$/, '') : '.';
      const relPath = target.path ? String(target.path).replace(/^\/+/, '') : '';
      let url = base ? (base + '/' + relPath) : relPath;
      if (target.fragment) {
        url += '#' + encodeURIComponent(target.fragment);
      }
      return url;
    }
    return null; // display-only
  }

  function mountKbGraph(container, options = {}) {
    if (!container || typeof container.appendChild !== 'function') {
      throw new Error('mountKbGraph requires a valid DOM container element.');
    }

    const data = options.data || (typeof window !== 'undefined' ? window.__KB_GRAPH_DATA__ : null);
    const previews = options.previews || (typeof window !== 'undefined' ? window.__KB_GRAPH_PREVIEWS__ : null);
    const mode = options.mode || 'inline'; // 'inline' | 'overlay' | 'standalone'
    const outputBaseUrl = options.outputBaseUrl !== undefined ? options.outputBaseUrl : '.';
    const initialPageId = options.initialPageId || null;
    const initialExpanded = options.initialExpanded || null;
    const initialFocusedId = options.initialFocusedId || null;
    const initialEgoFocusId = options.initialEgoFocusId || null;
    const onClose = typeof options.onClose === 'function' ? options.onClose : null;

    const lang = options.lang || (function () {
      if (typeof window !== 'undefined' && window.location && window.location.search) {
        try {
          const params = new URLSearchParams(window.location.search);
          const qLang = params.get('lang');
          if (qLang === 'en' || qLang === 'zh') return qLang;
        } catch (e) {}
      }
      const navLang = (typeof navigator !== 'undefined' && ((navigator.languages && navigator.languages[0]) || navigator.language || navigator.userLanguage)) || '';
      return navLang.toLowerCase().startsWith('zh') ? 'zh' : 'en';
    })();
    const t = I18N[lang] || I18N.en;

    if (!data || !Array.isArray(data.nodes)) {
      const errorDiv = document.createElement('div');
      errorDiv.className = 'kb-graph-root kb-graph-error';
      errorDiv.textContent = lang === 'zh' ? '暂无有效的图谱数据（缺少 GraphDataV1）。' : 'No valid graph data found (missing GraphDataV1).';
      container.appendChild(errorDiv);
      return {
        focus() {},
        highlightNodes() {},
        resetHighlight() {},
        fit() {},
        reset() {},
        getState() { return { expanded: [], focusedId: null, egoFocusId: null }; },
        setState() {},
        focusEgo() {},
        exitFocus() {},
        destroy() { errorDiv.remove(); }
      };
    }

    const idPrefix = 'kb-g-' + Math.random().toString(36).slice(2, 7) + '-';
    let isDestroyed = false;

    // -------------------------------------------------------------
    // 1. Data Indexing & Multi-parent BFS Depth Calculation
    // -------------------------------------------------------------
    const nodeMap = new Map();
    for (const n of data.nodes) {
      nodeMap.set(n.id, n);
    }

    const edges = Array.isArray(data.edges) ? data.edges : [];
    const collectsEdges = edges.filter(e => e.kind === 'collects');
    const containsEdges = edges.filter(e => e.kind === 'contains');
    const referenceEdges = edges.filter(e => e.kind === 'references');

    // -------------------------------------------------------------
    // 1. Candidate Structural Children for Each Node
    // -------------------------------------------------------------
    const potentialChildren = new Map();
    for (const n of data.nodes) {
      potentialChildren.set(n.id, []);
    }

    // A. contains edges: parent contains child section
    for (const edge of containsEdges) {
      if (potentialChildren.has(edge.source)) {
        potentialChildren.get(edge.source).push(edge.target);
      }
    }

    // B. collects edges: parent collects child page
    for (const edge of collectsEdges) {
      const occSec = edge.occurrences?.[0]?.source_section;
      const parentId = (occSec && nodeMap.has(occSec)) ? occSec : edge.source;
      if (potentialChildren.has(parentId)) {
        potentialChildren.get(parentId).push(edge.target);
      }
    }

    // C. references edges: links to pages or external references
    for (const edge of referenceEdges) {
      if (Array.isArray(edge.occurrences) && edge.occurrences.length > 0) {
        for (const occ of edge.occurrences) {
          const parentId = (occ.source_section && nodeMap.has(occ.source_section)) ? occ.source_section : edge.source;
          if (potentialChildren.has(parentId)) {
            potentialChildren.get(parentId).push(edge.target);
          }
        }
      } else {
        if (potentialChildren.has(edge.source)) {
          potentialChildren.get(edge.source).push(edge.target);
        }
      }
    }

    // Deduplicate child lists
    for (const [id, kids] of potentialChildren.entries()) {
      potentialChildren.set(id, [...new Set(kids)]);
    }

    // -------------------------------------------------------------
    // 2. Data Indexing & Multi-parent BFS Depth Calculation
    // -------------------------------------------------------------
    const depths = new Map(); // NodeId -> number | null
    const entryId = data.entry_id && nodeMap.has(data.entry_id) ? data.entry_id : (data.nodes[0] ? data.nodes[0].id : null);

    // Dynamic BFS shortest path starting from entryId
    if (entryId) {
      depths.set(entryId, 0);
      const queue = [entryId];
      while (queue.length > 0) {
        const curr = queue.shift();
        const currDepth = depths.get(curr);
        const kids = potentialChildren.get(curr) || [];
        for (const kid of kids) {
          if (!depths.has(kid) || currDepth + 1 < depths.get(kid)) {
            depths.set(kid, currDepth + 1);
            queue.push(kid);
          }
        }
      }
    }

    // Fallback: If node has explicit depth in data and was not reached by entry BFS
    for (const node of data.nodes) {
      if (!depths.has(node.id) && node.depth !== undefined && node.depth !== null) {
        depths.set(node.id, node.depth);
      }
    }

    function radiusFor(id) {
      const d = depths.get(id);
      if (d === null || d === undefined) return RADIUS_TABLE[3];
      return RADIUS_TABLE[Math.min(d, 3)];
    }

    // -------------------------------------------------------------
    // 3. Expansion State & Multi-parent Pivot Resolution
    // -------------------------------------------------------------
    const expanded = new Set();
    let egoFocusId = (initialEgoFocusId && nodeMap.has(initialEgoFocusId)) ? initialEgoFocusId : null;

    if (initialExpanded && (Array.isArray(initialExpanded) || initialExpanded instanceof Set)) {
      for (const id of initialExpanded) {
        if (nodeMap.has(id)) expanded.add(id);
      }
    } else {
      if (entryId) expanded.add(entryId);

      // If initialPageId is provided, expand ancestors along best path to initialPageId
      if (initialPageId && nodeMap.has(initialPageId)) {
        function expandPathTo(targetId) {
          const visited = new Set();
          let curr = targetId;
          while (curr && curr !== entryId && !visited.has(curr)) {
            visited.add(curr);
            // Find best parent
            let bestParent = null;
            let bestDepth = 99999;
            let bestOrder = 99999;

            // Check all candidate parents that have curr in potentialChildren
            for (const [pId, kids] of potentialChildren.entries()) {
              if (kids.includes(curr)) {
                const pDepth = depths.get(pId) ?? 99999;
                const edge = edges.find(e => e.target === curr && (e.source === pId || e.occurrences?.some(o => o.source_section === pId)));
                const pOrder = edge ? (edge.order ?? 99999) : 99999;
                if (pDepth < bestDepth || (pDepth === bestDepth && pOrder < bestOrder)) {
                  bestDepth = pDepth;
                  bestOrder = pOrder;
                  bestParent = pId;
                }
              }
            }
            if (bestParent) {
              expanded.add(bestParent);
              curr = bestParent;
            } else {
              break;
            }
          }
        }
        expandPathTo(initialPageId);
        expanded.add(initialPageId);
      }
    }

    // -------------------------------------------------------------
    // 4. Construct DOM Elements
    // -------------------------------------------------------------
    const root = document.createElement('div');
    root.className = `kb-graph-root kb-graph-mode-${mode}`;

    const overlayContainer = mode === 'overlay' ? document.createElement('div') : null;
    if (overlayContainer) {
      overlayContainer.className = 'kb-graph-overlay-container';
      root.appendChild(overlayContainer);
    }
    const mountParent = overlayContainer || root;

    // Header
    const header = document.createElement('div');
    header.className = 'kb-graph-header';

    const titleGroup = document.createElement('div');
    titleGroup.className = 'kb-graph-title-group';

    const mainTitle = document.createElement('span');
    mainTitle.className = 'kb-graph-main-title';
    mainTitle.textContent = t.mainTitle;

    const stats = document.createElement('span');
    stats.className = 'kb-graph-stats';

    titleGroup.appendChild(mainTitle);
    titleGroup.appendChild(stats);
    header.appendChild(titleGroup);

    const actions = document.createElement('div');
    actions.className = 'kb-graph-actions';

    const showAllBtn = document.createElement('button');
    showAllBtn.type = 'button';
    showAllBtn.className = 'kb-graph-btn kb-graph-btn-show-all';
    showAllBtn.textContent = t.showAll;

    const resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'kb-graph-btn kb-graph-btn-reset';
    resetBtn.textContent = t.reset;

    const exitFocusBtn = document.createElement('button');
    exitFocusBtn.type = 'button';
    exitFocusBtn.className = 'kb-graph-btn kb-graph-btn-exit-focus';
    exitFocusBtn.textContent = t.exitFocus;
    exitFocusBtn.style.display = egoFocusId ? '' : 'none';

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'kb-graph-btn kb-graph-btn-close';
    closeBtn.setAttribute('aria-label', t.aria.close);
    closeBtn.textContent = t.close;

    actions.appendChild(showAllBtn);
    actions.appendChild(resetBtn);
    actions.appendChild(exitFocusBtn);
    if (mode === 'overlay') {
      actions.appendChild(closeBtn);
    }
    header.appendChild(actions);
    mountParent.appendChild(header);

    // Stage & SVG
    const stage = document.createElement('div');
    stage.className = 'kb-graph-stage';
    stage.setAttribute('aria-label', t.aria.stage);

    const svg = el('svg', {
      class: 'kb-graph-svg',
      'aria-label': t.aria.svg
    });

    const defs = el('defs');
    const filter = el('filter', {
      id: `${idPrefix}shadow`,
      x: '-30%',
      y: '-50%',
      width: '160%',
      height: '200%'
    });
    const feDropShadow = el('feDropShadow', {
      dx: '0',
      dy: '3',
      stdDeviation: '5',
      'flood-color': '#4d7896',
      'flood-opacity': '.07'
    });
    filter.appendChild(feDropShadow);
    defs.appendChild(filter);
    svg.appendChild(defs);

    const viewport = el('g', { class: 'kb-graph-viewport' });
    const edgeLayer = el('g', { class: 'kb-graph-edge-layer' });
    const nodeLayer = el('g', { class: 'kb-graph-node-layer' });
    viewport.appendChild(edgeLayer);
    viewport.appendChild(nodeLayer);
    svg.appendChild(viewport);
    stage.appendChild(svg);

    // Note overlay
    const note = document.createElement('div');
    note.className = 'kb-graph-note';
    note.innerHTML = t.noteLines.map(line => '<div>' + line + '</div>').join('');
    stage.appendChild(note);

    // Tools
    const tools = document.createElement('div');
    tools.className = 'kb-graph-tools';

    const zoomOutBtn = document.createElement('button');
    zoomOutBtn.type = 'button';
    zoomOutBtn.className = 'kb-graph-tool-btn kb-graph-tool-zoom-out';
    zoomOutBtn.setAttribute('aria-label', t.zoomOut);
    zoomOutBtn.textContent = '−';

    const zoomOutput = document.createElement('output');
    zoomOutput.className = 'kb-graph-zoom-val';
    zoomOutput.textContent = '100%';

    const zoomInBtn = document.createElement('button');
    zoomInBtn.type = 'button';
    zoomInBtn.className = 'kb-graph-tool-btn kb-graph-tool-zoom-in';
    zoomInBtn.setAttribute('aria-label', t.zoomIn);
    zoomInBtn.textContent = '＋';

    const fitBtn = document.createElement('button');
    fitBtn.type = 'button';
    fitBtn.className = 'kb-graph-tool-btn kb-graph-tool-fit';
    fitBtn.setAttribute('aria-label', t.fit);
    fitBtn.textContent = t.fit;

    tools.appendChild(zoomOutBtn);
    tools.appendChild(zoomOutput);
    tools.appendChild(zoomInBtn);
    tools.appendChild(fitBtn);
    stage.appendChild(tools);

    mountParent.appendChild(stage);

    // Dialog for preview
    const dialog = document.createElement('dialog');
    dialog.className = 'kb-graph-dialog';
    dialog.setAttribute('aria-labelledby', `${idPrefix}dialog-title`);

    const dialogCloseBtn = document.createElement('button');
    dialogCloseBtn.type = 'button';
    dialogCloseBtn.className = 'kb-graph-dialog-close';
    dialogCloseBtn.setAttribute('aria-label', t.aria.close);
    dialogCloseBtn.textContent = t.dialogClose;

    const dialogEyebrow = document.createElement('div');
    dialogEyebrow.className = 'kb-graph-dialog-eyebrow';
    dialogEyebrow.textContent = t.dialogEyebrow;

    const dialogTitle = document.createElement('h2');
    dialogTitle.id = `${idPrefix}dialog-title`;
    dialogTitle.className = 'kb-graph-dialog-title';

    const dialogContent = document.createElement('div');
    dialogContent.className = 'kb-graph-dialog-content';

    dialog.appendChild(dialogCloseBtn);
    dialog.appendChild(dialogEyebrow);
    dialog.appendChild(dialogTitle);
    dialog.appendChild(dialogContent);
    mountParent.appendChild(dialog);

    // Screen reader live announcement region
    const liveRegion = document.createElement('div');
    liveRegion.className = 'kb-graph-sr-live';
    liveRegion.setAttribute('aria-live', 'polite');
    mountParent.appendChild(liveRegion);

    container.appendChild(root);

    // -------------------------------------------------------------
    // 5. Layout Engine
    // -------------------------------------------------------------
    let visible = [];
    const positions = new Map();
    let transform = { x: 0, y: 0, k: 1 };
    let drag = null;
    let suppressUntil = 0;
    let hoveredId = null;
    let focusedId = (initialFocusedId && nodeMap.has(initialFocusedId)) ? initialFocusedId : null;
    let customHighlightSet = null;
    let animationFrame = 0;
    let cameraFrame = 0;
    let visualState = new Map();

    const reducedMotion = (typeof window !== 'undefined' && window.matchMedia)
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : { matches: false };

    function stopCamera() {
      if (cameraFrame) {
        cancelAnimationFrame(cameraFrame);
        cameraFrame = 0;
      }
    }

    function applyTransform() {
      viewport.setAttribute('transform', `translate(${transform.x} ${transform.y}) scale(${transform.k})`);
      zoomOutput.textContent = Math.round(transform.k * 100) + '%';
    }

    /**
     * Compute radial layout for currently expanded nodes or ego-focus network.
     */
    function layout() {
      visible = [];
      positions.clear();

      if (!entryId) return;

      if (egoFocusId && nodeMap.has(egoFocusId)) {
        const neighborSet = new Set();
        for (const edge of containsEdges) {
          if (edge.source === egoFocusId && nodeMap.has(edge.target)) neighborSet.add(edge.target);
          if (edge.target === egoFocusId && nodeMap.has(edge.source)) neighborSet.add(edge.source);
        }
        for (const edge of collectsEdges) {
          const occSec = edge.occurrences?.[0]?.source_section;
          const src = (occSec && nodeMap.has(occSec)) ? occSec : edge.source;
          if (src === egoFocusId && nodeMap.has(edge.target)) neighborSet.add(edge.target);
          if (edge.target === egoFocusId && nodeMap.has(src)) neighborSet.add(src);
        }
        for (const edge of referenceEdges) {
          if (Array.isArray(edge.occurrences) && edge.occurrences.length > 0) {
            for (const occ of edge.occurrences) {
              const src = (occ.source_section && nodeMap.has(occ.source_section)) ? occ.source_section : edge.source;
              if (src === egoFocusId && nodeMap.has(edge.target)) neighborSet.add(edge.target);
              if (edge.target === egoFocusId && nodeMap.has(src)) neighborSet.add(src);
            }
          } else {
            if (edge.source === egoFocusId && nodeMap.has(edge.target)) neighborSet.add(edge.target);
            if (edge.target === egoFocusId && nodeMap.has(edge.source)) neighborSet.add(edge.source);
          }
        }
        const potential = potentialChildren.get(egoFocusId) || [];
        for (const kid of potential) {
          if (nodeMap.has(kid)) neighborSet.add(kid);
        }
        for (const [pId, kids] of potentialChildren.entries()) {
          if (kids.includes(egoFocusId) && nodeMap.has(pId)) {
            neighborSet.add(pId);
          }
        }
        neighborSet.delete(egoFocusId);

        const neighbors = Array.from(neighborSet);
        neighbors.sort((a, b) => {
          const dA = depths.get(a) ?? 99;
          const dB = depths.get(b) ?? 99;
          if (dA !== dB) return dA - dB;
          const nA = nodeMap.get(a);
          const nB = nodeMap.get(b);
          return (nA?.title || a).localeCompare(nB?.title || b);
        });

        visible = [egoFocusId, ...neighbors];
        positions.set(egoFocusId, { x: 0, y: 0 });

        const count = neighbors.length;
        if (count > 0) {
          const egoRadius = Math.max(175, Math.min(340, (count * 110) / (2 * Math.PI)));
          for (let i = 0; i < count; i++) {
            const angle = -Math.PI / 2 + (i * 2 * Math.PI) / count;
            positions.set(neighbors[i], {
              x: egoRadius * Math.cos(angle),
              y: egoRadius * Math.sin(angle)
            });
          }
        }
        return;
      }

      // Determine active layout parent for each child
      const activeLayoutKids = new Map();
      for (const id of nodeMap.keys()) {
        activeLayoutKids.set(id, []);
      }

      // Collect all candidate children from currently expanded nodes
      const candidateChildParents = new Map();
      for (const parentId of expanded) {
        const potential = potentialChildren.get(parentId) || [];
        for (const childId of potential) {
          if (!candidateChildParents.has(childId)) {
            candidateChildParents.set(childId, []);
          }
          candidateChildParents.get(childId).push(parentId);
        }
      }

      for (const [childId, parentList] of candidateChildParents.entries()) {
        parentList.sort((pA, pB) => {
          const depthA = depths.get(pA) ?? 99999;
          const depthB = depths.get(pB) ?? 99999;
          if (depthA !== depthB) return depthA - depthB;

          const edgeA = edges.find(e => e.target === childId && (e.source === pA || e.occurrences?.some(o => o.source_section === pA)));
          const edgeB = edges.find(e => e.target === childId && (e.source === pB || e.occurrences?.some(o => o.source_section === pB)));
          const orderA = edgeA ? (edgeA.order ?? 99999) : 99999;
          const orderB = edgeB ? (edgeB.order ?? 99999) : 99999;
          if (orderA !== orderB) return orderA - orderB;

          return pA.localeCompare(pB);
        });

        const bestParent = parentList[0];
        activeLayoutKids.get(bestParent).push(childId);
      }

      // Sort children within each parent by order, then id
      for (const [pId, kids] of activeLayoutKids.entries()) {
        kids.sort((a, b) => {
          const edgeA = edges.find(e => e.target === a && (e.source === pId || e.occurrences?.some(o => o.source_section === pId)));
          const edgeB = edges.find(e => e.target === b && (e.source === pId || e.occurrences?.some(o => o.source_section === pId)));
          const orderA = edgeA ? (edgeA.order ?? 0) : 0;
          const orderB = edgeB ? (edgeB.order ?? 0) : 0;
          if (orderA !== orderB) return orderA - orderB;
          return a.localeCompare(b);
        });
      }

      const weights = new Map();
      const rings = [];

      function measure(id) {
        const kids = expanded.has(id) ? (activeLayoutKids.get(id) || []) : [];
        const weight = kids.length ? kids.reduce((sum, kid) => sum + measure(kid), 0) : 1;
        weights.set(id, weight);
        return weight;
      }

      measure(entryId);

      function assign(id, depth, start, span) {
        const angle = start + span / 2;
        visible.push(id);
        (rings[depth] ??= []).push({ id, angle });

        let cursor = start;
        if (expanded.has(id)) {
          const kids = activeLayoutKids.get(id) || [];
          for (const kid of kids) {
            const kidWeight = weights.get(kid) || 1;
            const parentWeight = weights.get(id) || 1;
            const childSpan = span * kidWeight / parentWeight;
            assign(kid, depth + 1, cursor, childSpan);
            cursor += childSpan;
          }
        }
      }

      assign(entryId, 0, -Math.PI / 2, Math.PI * 2);

      let currentRadius = 0;
      rings.forEach((ring, depth) => {
        if (depth > 0) {
          let gap = Math.PI * 2;
          if (ring.length > 1) {
            ring.forEach((n, i) => {
              const next = ring[(i + 1) % ring.length].angle + (i === ring.length - 1 ? Math.PI * 2 : 0);
              gap = Math.min(gap, next - n.angle);
            });
          }
          const ownRadius = Math.max(...ring.map(n => radiusFor(n.id)));
          const prevRadius = Math.max(...rings[depth - 1].map(n => radiusFor(n.id)));
          currentRadius = Math.max(
            currentRadius + ownRadius + prevRadius + 48,
            ring.length > 1 ? (2 * ownRadius + 26) / (2 * Math.sin(gap / 2)) : 0
          );
        }
        for (const n of ring) {
          positions.set(n.id, {
            x: currentRadius * Math.cos(n.angle),
            y: currentRadius * Math.sin(n.angle)
          });
        }
      });
    }

    function fit() {
      stopCamera();
      const rect = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { width: 800, height: 600 };
      if (!rect.width || !rect.height) return;

      if (positions.size === 0) return;

      const pts = [...positions].map(([id, p]) => ({ ...p, padding: radiusFor(id) + 16 }));
      const minX = Math.min(...pts.map(p => p.x - p.padding));
      const maxX = Math.max(...pts.map(p => p.x + p.padding));
      const minY = Math.min(...pts.map(p => p.y - p.padding));
      const maxY = Math.max(...pts.map(p => p.y + p.padding));

      const availableW = Math.max(160, rect.width - 60);
      const availableH = Math.max(120, rect.height - 120);

      transform.k = Math.max(0.06, Math.min(1.15, availableW / (maxX - minX || 1), availableH / (maxY - minY || 1)));
      transform.x = rect.width / 2 - (minX + maxX) * transform.k / 2;
      transform.y = rect.height / 2 - (minY + maxY) * transform.k / 2;
      applyTransform();
    }

    function focusNode(id) {
      stopCamera();
      const p = positions.get(id);
      const rect = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { width: 800, height: 600 };
      if (!p || !rect.width || !rect.height) return;

      // Target zoom: fixed screen display diameter of 150px
      const targetK = 150 / (2 * radiusFor(id));
      const start = { ...transform };
      const target = {
        k: targetK,
        x: rect.width / 2 - p.x * targetK,
        y: rect.height / 2 - p.y * targetK
      };

      if (reducedMotion.matches) {
        transform = target;
        applyTransform();
        return;
      }

      const started = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      function tick(now) {
        const progress = Math.min(1, (now - started) / 320);
        const eased = 1 - Math.pow(1 - progress, 3);
        transform = {
          x: start.x + (target.x - start.x) * eased,
          y: start.y + (target.y - start.y) * eased,
          k: start.k + (target.k - start.k) * eased
        };
        applyTransform();
        if (progress < 1) {
          cameraFrame = requestAnimationFrame(tick);
        } else {
          cameraFrame = 0;
        }
      }
      cameraFrame = requestAnimationFrame(tick);
    }

    // -------------------------------------------------------------
    // 6. Highlighting & Neighbors
    // -------------------------------------------------------------
    function highlight() {
      const active = hoveredId || focusedId || egoFocusId;
      const neighbors = new Set(active ? [active] : []);

      if (customHighlightSet && customHighlightSet.size > 0) {
        // Search highlight mode
        for (const edge of edgeLayer.children) {
          const s = edge.dataset.source;
          const t = edge.dataset.target;
          const conn = customHighlightSet.has(s) && customHighlightSet.has(t);
          edge.classList.toggle('is-connected', conn);
          edge.classList.toggle('is-muted', !conn);
        }
        for (const node of nodeLayer.children) {
          const id = node.dataset.id;
          const isMatch = customHighlightSet.has(id);
          node.classList.toggle('is-search-match', isMatch);
          node.classList.toggle('is-muted', !isMatch);
          node.classList.remove('is-current', 'is-neighbor');
        }
        return;
      }

      // Normal hover/focus highlight mode
      for (const edge of edgeLayer.children) {
        const connected = !!active && (edge.dataset.source === active || edge.dataset.target === active);
        edge.classList.toggle('is-connected', connected);
        edge.classList.toggle('is-muted', !!active && !connected);
        if (connected) {
          neighbors.add(edge.dataset.source);
          neighbors.add(edge.dataset.target);
        }
      }
      for (const node of nodeLayer.children) {
        const id = node.dataset.id;
        node.classList.toggle('is-current', id === active);
        node.classList.toggle('is-neighbor', neighbors.has(id) && id !== active);
        node.classList.toggle('is-muted', !!active && !neighbors.has(id));
        node.classList.remove('is-search-match');
      }
    }

    function addEdge(source, target, isReference = false) {
      const path = el('path', {
        class: 'kb-graph-edge' + (isReference ? ' reference' : ''),
        'data-source': source,
        'data-target': target
      });
      edgeLayer.appendChild(path);
    }

    function paintFrame() {
      for (const node of nodeLayer.children) {
        const p = visualState.get(node.dataset.id);
        if (p) {
          node.setAttribute('transform', `translate(${p.x} ${p.y})`);
          node.setAttribute('opacity', String(p.opacity));
        }
      }
      for (const edge of edgeLayer.children) {
        const p = visualState.get(edge.dataset.source);
        const q = visualState.get(edge.dataset.target);
        if (p && q) {
          const distance = Math.hypot(q.x - p.x, q.y - p.y);
          const sourceRadius = radiusFor(edge.dataset.source);
          const targetRadius = radiusFor(edge.dataset.target);
          const trimScale = Math.min(1, distance / (sourceRadius + targetRadius || 1));
          const sourceTrim = sourceRadius * trimScale;
          const targetTrim = targetRadius * trimScale;
          const ux = distance ? (q.x - p.x) / distance : 0;
          const uy = distance ? (q.y - p.y) / distance : 0;

          edge.setAttribute('d', `M${p.x + ux * sourceTrim},${p.y + uy * sourceTrim} L${q.x - ux * targetTrim},${q.y - uy * targetTrim}`);
          edge.setAttribute('opacity', String(Math.min(p.opacity, q.opacity)));
        }
      }
    }

    // -------------------------------------------------------------
    // 7. Render Pass
    // -------------------------------------------------------------
    function render(animate = true) {
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = 0;
      }

      const previous = new Map(visualState);
      const oldEdges = [...edgeLayer.children].map(e => [
        e.dataset.source,
        e.dataset.target,
        e.classList.contains('reference')
      ]);

      layout();
      hoveredId = null;
      if (focusedId && !visible.includes(focusedId)) {
        focusedId = null;
      }

      const targetIds = new Set(visible);
      const allIds = [...new Set([...visible, ...previous.keys()])];
      const moving = animate && !reducedMotion.matches && previous.size > 0;

      function ancestorPosition(id, map) {
        // Find best parent that has a position in map
        for (const [pId, kids] of potentialChildren.entries()) {
          if (kids.includes(id) && map.has(pId)) {
            return map.get(pId);
          }
        }
        return map.get(entryId) || { x: 0, y: 0 };
      }

      const starts = new Map();
      const ends = new Map();
      for (const id of allIds) {
        starts.set(id, previous.get(id) || { ...ancestorPosition(id, previous), opacity: 0 });
        ends.set(id, targetIds.has(id) ? { ...positions.get(id), opacity: 1 } : { ...ancestorPosition(id, positions), opacity: 0 });
      }

      visualState = new Map(moving ? starts : ends);

      // Recreate edge and node DOM
      while (nodeLayer.firstChild) nodeLayer.removeChild(nodeLayer.firstChild);
      while (edgeLayer.firstChild) edgeLayer.removeChild(edgeLayer.firstChild);

      const edgeKeys = new Set();
      function connect(a, b, isRef = false) {
        const key = `${a}|${b}|${isRef}`;
        if (edgeKeys.has(key)) return;
        edgeKeys.add(key);
        addEdge(a, b, isRef);
      }

      // Draw all structural edges between visible nodes
      for (const edge of collectsEdges) {
        const occSec = edge.occurrences?.[0]?.source_section;
        const src = (occSec && targetIds.has(occSec)) ? occSec : edge.source;
        if (targetIds.has(src) && targetIds.has(edge.target)) {
          connect(src, edge.target, false);
        }
      }
      for (const edge of containsEdges) {
        if (targetIds.has(edge.source) && targetIds.has(edge.target)) {
          connect(edge.source, edge.target, false);
        }
      }
      // Draw reference edges between visible nodes
      for (const edge of referenceEdges) {
        if (Array.isArray(edge.occurrences) && edge.occurrences.length > 0) {
          for (const occ of edge.occurrences) {
            const src = (occ.source_section && targetIds.has(occ.source_section)) ? occ.source_section : edge.source;
            if (targetIds.has(src) && targetIds.has(edge.target)) {
              connect(src, edge.target, true);
            }
          }
        } else {
          if (targetIds.has(edge.source) && targetIds.has(edge.target)) {
            connect(edge.source, edge.target, true);
          }
        }
      }

      if (moving) {
        for (const [a, b, isRef] of oldEdges) {
          if (allIds.includes(a) && allIds.includes(b)) {
            connect(a, b, isRef);
          }
        }
      }

      for (const id of (moving ? allIds : visible)) {
        const n = nodeMap.get(id);
        if (!n) continue;

        const p = visualState.get(id) || { x: 0, y: 0, opacity: 1 };
        const kids = potentialChildren.get(id) || [];
        const count = kids.length;
        const depth = depths.get(id);
        const tone = (depth !== null && depth !== undefined) ? (depth % 6) : 5;

        const isEgoCenter = egoFocusId === id;
        const g = el('g', {
          class: `kb-graph-node ${n.kind}${count ? ' expandable' : ''}${isEgoCenter ? ' is-ego-center' : ''}`,
          transform: `translate(${p.x} ${p.y})`,
          'data-id': id,
          'data-depth': depth !== null && depth !== undefined ? depth : 'null',
          'data-tone': tone
        });

        if (!targetIds.has(id)) {
          g.style.pointerEvents = 'none';
          g.setAttribute('aria-hidden', 'true');
        }

        const radius = radiusFor(id);
        const contentScale = Math.min(1, radius / 57);

        const bodyAriaAction = count ? t.aria.nodeExpandAction.replace('{0}', expanded.has(id) ? t.aria.collapse : t.aria.expand).replace('{1}', count) : '';
        const body = el('circle', {
          class: 'kb-graph-body',
          r: radius,
          tabindex: '0',
          role: 'button',
          'aria-label': t.aria.nodeLabel.replace('{0}', n.title).replace('{1}', bodyAriaAction)
        });
        if (count > 0) {
          body.setAttribute('aria-expanded', String(expanded.has(id)));
        }
        body.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle(id);
          }
        });
        g.appendChild(body);

        const content = el('g', { transform: `scale(${contentScale})` });
        g.appendChild(content);

        // Kind label
        const kindText = el('text', { class: 'kb-graph-kind', x: 0, y: -24 });
        const depthLabel = (depth !== null && depth !== undefined) ? `L${depth}` : (t.kinds.unindexed || '未收录');
        kindText.textContent = `${depthLabel} ${labelKind(n, t)}${count ? ' ' + (expanded.has(id) ? '−' : '＋') + count : ''}`;
        content.appendChild(kindText);

        // Title link (opens in NEW TAB)
        const href = resolveHref(n, outputBaseUrl);
        const a = el('a', {
          'aria-label': t.aria.openLink.replace('{0}', n.title),
          target: '_blank',
          rel: 'noopener noreferrer'
        });
        if (href) {
          a.setAttribute('href', href);
        }

        const chars = Array.from(n.title);
        const lines = chars.length > 8 ? [chars.slice(0, 8).join(''), chars.slice(8).join('')] : [n.title];
        const titleText = el('text', {
          class: 'kb-graph-name',
          x: 0,
          y: lines.length > 1 ? -8 : 0
        });

        lines.forEach((line, i) => {
          const span = el('tspan', { x: 0, dy: i ? 15 : 0, 'pointer-events': 'auto' });
          span.textContent = line.length > 8 ? line.slice(0, 7) + '…' : line;
          titleText.appendChild(span);
        });

        const fullTitle = el('title');
        fullTitle.textContent = n.title;
        a.appendChild(titleText);
        a.appendChild(fullTitle);

        a.addEventListener('click', e => e.stopPropagation());
        content.appendChild(a);

        // Node Action Buttons: Focus + Preview
        const btnGroup = el('g', { class: 'kb-graph-btn-group' });

        const focusBtn = el('g', {
          class: `kb-graph-focus-btn${isEgoCenter ? ' is-active' : ''}`,
          tabindex: '0',
          role: 'button',
          'aria-label': isEgoCenter ? t.aria.exitFocusNode : t.aria.focusNode.replace('{0}', n.title)
        });
        focusBtn.appendChild(el('rect', { x: -34, y: 22, width: 32, height: 19, rx: 6 }));
        const focusText = el('text', { x: -18, y: 31.5 });
        focusText.textContent = isEgoCenter ? t.exitBtn : t.focusBtn;
        focusBtn.appendChild(focusText);

        focusBtn.addEventListener('click', e => {
          e.stopPropagation();
          if (isEgoCenter) {
            exitFocus();
          } else {
            enterFocus(id);
          }
        });
        focusBtn.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            if (isEgoCenter) {
              exitFocus();
            } else {
              enterFocus(id);
            }
          }
        });
        btnGroup.appendChild(focusBtn);

        // Preview button
        const previewBtn = el('g', {
          class: 'kb-graph-preview-btn',
          tabindex: '0',
          role: 'button',
          'aria-label': t.aria.previewNode.replace('{0}', n.title)
        });
        previewBtn.appendChild(el('rect', { x: 2, y: 22, width: 32, height: 19, rx: 6 }));
        const previewText = el('text', { x: 18, y: 31.5 });
        previewText.textContent = t.previewBtn;
        previewBtn.appendChild(previewText);

        previewBtn.addEventListener('click', e => {
          e.stopPropagation();
          openPreview(id);
        });
        previewBtn.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.stopPropagation();
            openPreview(id);
          }
        });
        btnGroup.appendChild(previewBtn);

        content.appendChild(btnGroup);

        // Main node click to toggle expand/collapse and focus
        g.addEventListener('click', () => toggle(id));

        g.addEventListener('pointerenter', () => {
          if (!drag) {
            hoveredId = id;
            highlight();
          }
        });
        g.addEventListener('pointerleave', () => {
          if (hoveredId === id) {
            hoveredId = null;
            highlight();
          }
        });
        g.addEventListener('focusin', () => {
          focusedId = id;
          highlight();
        });
        g.addEventListener('focusout', e => {
          if (!g.contains(e.relatedTarget)) {
            focusedId = null;
            highlight();
          }
        });

        if (!targetIds.has(id)) {
          for (const ctrl of g.querySelectorAll('[tabindex],a')) {
            ctrl.setAttribute('tabindex', '-1');
          }
          g.addEventListener('click', e => {
            e.preventDefault();
            e.stopImmediatePropagation();
          }, true);
        }

        nodeLayer.appendChild(g);
      }

      if (egoFocusId && nodeMap.has(egoFocusId)) {
        const cTitle = nodeMap.get(egoFocusId)?.title || egoFocusId;
        const neighborCount = Math.max(0, visible.length - 1);
        stats.textContent = t.statsFocus.replace('{0}', cTitle).replace('{1}', neighborCount);
      } else {
        stats.textContent = t.stats.replace('{0}', visible.length).replace('{1}', data.nodes.length);
      }
      highlight();
      applyTransform();
      paintFrame();

      function complete() {
        animationFrame = 0;
        visualState = new Map(visible.map(id => [id, ends.get(id)]));
        for (const node of [...nodeLayer.children]) {
          if (!targetIds.has(node.dataset.id)) node.remove();
        }
        for (const edge of [...edgeLayer.children]) {
          if (!targetIds.has(edge.dataset.source) || !targetIds.has(edge.dataset.target)) {
            edge.remove();
          }
        }
        paintFrame();
        highlight();
      }

      if (!moving) {
        complete();
        return;
      }

      const started = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      function tick(now) {
        const progress = Math.min(1, (now - started) / 320);
        const eased = 1 - Math.pow(1 - progress, 3);
        for (const id of allIds) {
          const a = starts.get(id);
          const b = ends.get(id);
          if (a && b) {
            visualState.set(id, {
              x: a.x + (b.x - a.x) * eased,
              y: a.y + (b.y - a.y) * eased,
              opacity: a.opacity + (b.opacity - a.opacity) * eased
            });
          }
        }
        paintFrame();
        if (progress < 1) {
          animationFrame = requestAnimationFrame(tick);
        } else {
          complete();
        }
      }
      animationFrame = requestAnimationFrame(tick);
    }

    function toggle(id) {
      if (egoFocusId) {
        if (id === egoFocusId) {
          exitFocus();
        } else {
          enterFocus(id);
        }
        return;
      }
      const kids = potentialChildren.get(id) || [];
      const count = kids.length;
      if (count > 0) {
        if (expanded.has(id)) {
          // Collapse id and its sub-branch (unless children are needed by another expanded parent)
          function collapse(key) {
            expanded.delete(key);
            const subKids = potentialChildren.get(key) || [];
            for (const sub of subKids) {
              // Only collapse descendant if it has no other expanded parents
              const otherParents = edges
                .filter(e => e.target === sub && e.source !== key && expanded.has(e.source));
              if (otherParents.length === 0) {
                collapse(sub);
              }
            }
          }
          collapse(id);
        } else {
          expanded.add(id);
        }
        render(true);
      }
      focusNode(id);
      const node = nodeMap.get(id);
      const title = node ? node.title : id;
      const actionStr = count ? (expanded.has(id) ? t.liveExpandAction : t.liveCollapseAction) : '';
      liveRegion.textContent = t.liveNodeToggled.replace('{0}', title).replace('{1}', actionStr);
    }

    // -------------------------------------------------------------
    // 8. Preview Modal Implementation
    // -------------------------------------------------------------
    let lastActiveElement = null;

    function openPreview(id) {
      const n = nodeMap.get(id);
      if (!n) return;

      lastActiveElement = document.activeElement;
      dialogTitle.textContent = n.title;

      while (dialogContent.firstChild) {
        dialogContent.removeChild(dialogContent.firstChild);
      }

      // Find matching preview record
      let record = null;
      if (previews && Array.isArray(previews.records)) {
        record = previews.records.find(r => (n.preview_key && r.key === n.preview_key) || r.node_id === n.id);
      }

      if (record && record.text) {
        const paragraphs = String(record.text).split(/\r?\n\r?\n/);
        for (const para of paragraphs) {
          if (para.trim()) {
            const p = document.createElement('p');
            p.textContent = para.trim();
            dialogContent.appendChild(p);
          }
        }
        if (record.truncated) {
          const hint = document.createElement('p');
          hint.className = 'kb-graph-preview-hint';
          hint.textContent = t.truncatedNotice;
          dialogContent.appendChild(hint);
        }
      } else {
        const emptyMsg = document.createElement('p');
        if (n.kind === 'reference') {
          emptyMsg.textContent = t.externalRefNotice;
        } else {
          emptyMsg.textContent = t.noPreviewNotice;
        }
        dialogContent.appendChild(emptyMsg);
      }

      // Add full navigation link
      const href = resolveHref(n, outputBaseUrl);
      if (href) {
        const linkWrap = document.createElement('div');
        linkWrap.className = 'kb-graph-preview-link-wrap';
        const a = document.createElement('a');
        a.className = 'kb-graph-preview-link';
        a.href = href;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = n.kind === 'reference' ? t.openExternal : t.openArticle;
        linkWrap.appendChild(a);
        dialogContent.appendChild(linkWrap);
      }

      const dialogActions = document.createElement('div');
      dialogActions.className = 'kb-graph-dialog-actions';
      const focusDialogBtn = document.createElement('button');
      focusDialogBtn.type = 'button';
      focusDialogBtn.className = 'kb-graph-btn kb-graph-dialog-focus-btn';
      focusDialogBtn.textContent = egoFocusId === id ? t.dialogExitFocus : t.dialogFocus;
      focusDialogBtn.addEventListener('click', () => {
        closePreview();
        if (egoFocusId === id) {
          exitFocus();
        } else {
          enterFocus(id);
        }
      });
      dialogActions.appendChild(focusDialogBtn);
      dialogContent.appendChild(dialogActions);

      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
        dialog.scrollTop = 0;
      } else {
        dialog.setAttribute('open', '');
      }
      dialogCloseBtn.focus();
    }

    function closePreview() {
      if (typeof dialog.close === 'function') {
        dialog.close();
      } else {
        dialog.removeAttribute('open');
      }
      if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
        lastActiveElement.focus();
      }
    }

    dialogCloseBtn.addEventListener('click', closePreview);
    dialog.addEventListener('cancel', e => {
      e.preventDefault();
      closePreview();
    });

    // -------------------------------------------------------------
    // 9. Zoom, Pan, Drag & Wheel
    // -------------------------------------------------------------
    function zoom(factor, cx, cy) {
      stopCamera();
      const oldK = transform.k;
      const nextK = Math.max(0.06, Math.min(3.2, oldK * factor));
      transform.x = cx - (cx - transform.x) * nextK / oldK;
      transform.y = cy - (cy - transform.y) * nextK / oldK;
      transform.k = nextK;
      applyTransform();
    }

    zoomInBtn.addEventListener('click', () => {
      const rect = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { width: 800, height: 600 };
      zoom(1.2, rect.width / 2, rect.height / 2);
    });

    zoomOutBtn.addEventListener('click', () => {
      const rect = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { width: 800, height: 600 };
      zoom(1 / 1.2, rect.width / 2, rect.height / 2);
    });

    fitBtn.addEventListener('click', fit);

    function onWheel(e) {
      e.preventDefault();
      const rect = svg.getBoundingClientRect ? svg.getBoundingClientRect() : { left: 0, top: 0 };
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      zoom(Math.exp(-e.deltaY * 0.001), cx, cy);
    }
    svg.addEventListener('wheel', onWheel, { passive: false });

    svg.addEventListener('dragstart', e => e.preventDefault());

    svg.addEventListener('click', e => {
      const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
      if (now < suppressUntil) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }, true);

    svg.addEventListener('pointerdown', e => {
      if (e.button !== 0 || drag) return;
      stopCamera();
      drag = {
        pointer: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        x: transform.x,
        y: transform.y,
        moved: false
      };
    });

    svg.addEventListener('pointermove', e => {
      if (!drag || drag.pointer !== e.pointerId) return;
      const dx = e.clientX - drag.startX;
      const dy = e.clientY - drag.startY;
      if (!drag.moved && Math.hypot(dx, dy) > 5) {
        drag.moved = true;
        hoveredId = null;
        highlight();
        if (typeof svg.setPointerCapture === 'function') {
          svg.setPointerCapture(e.pointerId);
        }
        svg.classList.add('dragging');
      }
      if (!drag.moved) return;
      transform.x = drag.x + dx;
      transform.y = drag.y + dy;
      applyTransform();
    });

    function finishDrag(e) {
      if (!drag || drag.pointer !== e.pointerId) return;
      if (drag.moved || e.type === 'pointercancel') {
        const now = (typeof performance !== 'undefined' ? performance.now() : Date.now());
        suppressUntil = now + 400;
      }
      if (typeof svg.releasePointerCapture === 'function' && svg.hasPointerCapture && svg.hasPointerCapture(e.pointerId)) {
        svg.releasePointerCapture(e.pointerId);
      }
      drag = null;
      svg.classList.remove('dragging');

      if (e.type === 'pointerup' && typeof document.elementFromPoint === 'function') {
        const target = document.elementFromPoint(e.clientX, e.clientY);
        hoveredId = target && target.closest ? (target.closest('.kb-graph-node')?.dataset?.id || null) : null;
      } else {
        hoveredId = null;
      }
      highlight();
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('pointerup', finishDrag);
      window.addEventListener('pointercancel', finishDrag);
    }
    svg.addEventListener('lostpointercapture', e => {
      if (drag) finishDrag(e);
    });

    // -------------------------------------------------------------
    // 10. Header Actions
    // -------------------------------------------------------------
    showAllBtn.addEventListener('click', () => {
      if (egoFocusId) {
        egoFocusId = null;
        exitFocusBtn.style.display = 'none';
      }
      for (const n of data.nodes) {
        if (potentialChildren.get(n.id)?.length) {
          expanded.add(n.id);
        }
      }
      render(true);
      fit();
      liveRegion.textContent = t.liveExpandedAll;
    });

    function resetToInitial() {
      egoFocusId = null;
      exitFocusBtn.style.display = 'none';
      expanded.clear();
      if (entryId) expanded.add(entryId);
      customHighlightSet = null;
      render(true);
      fit();
      liveRegion.textContent = t.liveResetInitial;
    }

    resetBtn.addEventListener('click', resetToInitial);

    function enterFocus(id) {
      if (!nodeMap.has(id)) return;
      egoFocusId = id;
      focusedId = id;
      render(true);
      fit();
      if (exitFocusBtn) {
        exitFocusBtn.style.display = '';
        const title = nodeMap.get(id)?.title || id;
        exitFocusBtn.textContent = t.exitFocusWithNode.replace('{0}', title);
      }
      const count = Math.max(0, visible.length - 1);
      const title = nodeMap.get(id)?.title || id;
      liveRegion.textContent = t.liveFocusedEgo.replace('{0}', title).replace('{1}', count);
    }

    function exitFocus() {
      if (!egoFocusId) return;
      const prevId = egoFocusId;
      egoFocusId = null;
      if (exitFocusBtn) {
        exitFocusBtn.style.display = 'none';
      }
      render(true);
      if (prevId && nodeMap.has(prevId)) {
        focusedId = prevId;
        focusNode(prevId);
        highlight();
        const title = nodeMap.get(prevId)?.title || prevId;
        liveRegion.textContent = t.liveExitFocusCentered.replace('{0}', title);
      } else {
        fit();
        liveRegion.textContent = t.liveExitFocus;
      }
    }

    exitFocusBtn.addEventListener('click', exitFocus);

    // -------------------------------------------------------------
    // 11. Overlay Mode: Close, Esc, and Focus Trap
    // -------------------------------------------------------------
    let overlayLastActive = null;

    function closeOverlay() {
      if (mode === 'overlay') {
        if (typeof onClose === 'function') {
          try {
            onClose(getState());
          } catch (err) {
            // Ignore callback error
          }
        }
        destroy();
        if (overlayLastActive && typeof overlayLastActive.focus === 'function') {
          overlayLastActive.focus();
        }
      }
    }

    if (mode === 'overlay') {
      overlayLastActive = document.activeElement;
      closeBtn.addEventListener('click', closeOverlay);
      root.addEventListener('click', e => {
        if (e.target === root) {
          closeOverlay();
        }
      });
    }

    function onKeyDown(e) {
      if (e.key === 'Escape') {
        if (dialog.open || dialog.hasAttribute('open')) {
          closePreview();
          e.stopPropagation();
        } else if (egoFocusId) {
          exitFocus();
          e.stopPropagation();
        } else if (mode === 'overlay') {
          closeOverlay();
          e.stopPropagation();
        }
      }

      // Focus trap for overlay
      if (mode === 'overlay' && e.key === 'Tab') {
        const focusables = root.querySelectorAll('button:not([disabled]), [tabindex="0"], a[href]');
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', onKeyDown);

    function onResize() {
      if (!isDestroyed && container.isConnected !== false) {
        fit();
      }
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', onResize);
    }

    // -------------------------------------------------------------
    // 12. Cleanup / Destroy
    // -------------------------------------------------------------
    function destroy() {
      if (isDestroyed) return;
      isDestroyed = true;

      stopCamera();
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = 0;
      }

      document.removeEventListener('keydown', onKeyDown);
      if (typeof window !== 'undefined') {
        window.removeEventListener('pointerup', finishDrag);
        window.removeEventListener('pointercancel', finishDrag);
        window.removeEventListener('resize', onResize);
      }

      if (root.parentElement) {
        root.parentElement.removeChild(root);
      }
    }

    // -------------------------------------------------------------
    // 13. Public Control Interface
    // -------------------------------------------------------------
    function ensureVisible(targetId) {
      if (!nodeMap.has(targetId)) return;
      // Trace primary parent path to root and add to expanded
      let curr = targetId;
      const visited = new Set();
      while (curr && curr !== entryId && !visited.has(curr)) {
        visited.add(curr);
        let bestParent = null;
        let bestDepth = 99999;
        let bestOrder = 99999;
        const candidateEdges = edges.filter(e => e.target === curr);
        for (const e of candidateEdges) {
          const pDepth = depths.get(e.source) ?? 99999;
          const pOrder = e.order ?? 99999;
          if (pDepth < bestDepth || (pDepth === bestDepth && pOrder < bestOrder)) {
            bestDepth = pDepth;
            bestOrder = pOrder;
            bestParent = e.source;
          }
        }
        if (bestParent) {
          expanded.add(bestParent);
          curr = bestParent;
        } else {
          break;
        }
      }
    }

    function getState() {
      return {
        expanded: Array.from(expanded),
        focusedId: focusedId,
        egoFocusId: egoFocusId
      };
    }

    function setState(newState) {
      if (!newState) return;
      if (Array.isArray(newState.expanded)) {
        expanded.clear();
        for (const id of newState.expanded) {
          if (nodeMap.has(id)) expanded.add(id);
        }
      }
      focusedId = (newState.focusedId && nodeMap.has(newState.focusedId)) ? newState.focusedId : null;
      egoFocusId = (newState.egoFocusId && nodeMap.has(newState.egoFocusId)) ? newState.egoFocusId : null;
      if (exitFocusBtn) {
        if (egoFocusId) {
          exitFocusBtn.style.display = '';
          const title = nodeMap.get(egoFocusId)?.title || egoFocusId;
          exitFocusBtn.textContent = t.exitFocusWithNode.replace('{0}', title);
        } else {
          exitFocusBtn.style.display = 'none';
        }
      }
      render(true);
      if (egoFocusId) {
        fit();
        highlight();
      } else if (focusedId) {
        focusNode(focusedId);
        highlight();
      } else {
        fit();
      }
    }

    // Initial render & fit
    render(false);
    if (egoFocusId && nodeMap.has(egoFocusId)) {
      if (exitFocusBtn) {
        exitFocusBtn.style.display = '';
        const title = nodeMap.get(egoFocusId)?.title || egoFocusId;
        exitFocusBtn.textContent = t.exitFocusWithNode.replace('{0}', title);
      }
      fit();
      highlight();
    } else if (initialPageId && nodeMap.has(initialPageId)) {
      focusNode(initialPageId);
      focusedId = initialPageId;
      highlight();
    } else {
      fit();
    }

    return {
      focus(nodeId) {
        if (!nodeMap.has(nodeId)) return;
        if (egoFocusId) exitFocus();
        ensureVisible(nodeId);
        render(true);
        focusNode(nodeId);
        focusedId = nodeId;
        highlight();
      },
      highlightNodes(nodeIds) {
        if (!Array.isArray(nodeIds) || nodeIds.length === 0) {
          customHighlightSet = null;
        } else {
          customHighlightSet = new Set(nodeIds);
        }
        highlight();
      },
      resetHighlight() {
        customHighlightSet = null;
        hoveredId = null;
        focusedId = null;
        highlight();
      },
      fit() {
        fit();
      },
      reset() {
        resetToInitial();
      },
      getState() {
        return getState();
      },
      setState(newState) {
        setState(newState);
      },
      focusEgo(nodeId) {
        enterFocus(nodeId);
      },
      exitFocus() {
        exitFocus();
      },
      destroy() {
        destroy();
      }
    };
  }

  // Export to global and CommonJS
  if (typeof window !== 'undefined') {
    window.mountKbGraph = mountKbGraph;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { mountKbGraph };
  }
})(typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : this));
