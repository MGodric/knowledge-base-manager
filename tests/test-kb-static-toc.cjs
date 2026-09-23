'use strict';

// Execute the actual inline template script, using only Node built-ins.
// This checks DOM behavior, not browser layout or native scrolling.
const { emitComplete, instrument } = require('./node_test_report.cjs');
const assert = instrument(require('node:assert/strict'));
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname,
  '../knowledge-base-manager/scripts/kb_core/static_build.py'), 'utf8');
const match = source.match(/<script id="kb-toc-script">([\s\S]*?)<\/script>/);
assert.ok(match, 'The generated-page template must contain the actual TOC script');
const script = match[1].replace(/\{\{/g, '{').replace(/\}\}/g, '}');

function descendants(node) {
  return node.children.flatMap(child => [child, ...descendants(child)]);
}

class Element {
  constructor(tag, text = '', id = '') {
    this.tagName = tag.toUpperCase();
    this.textContent = text;
    this.id = id;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.open = false;
    this.className = '';
    this.classList = {
      add: name => { this.className = `${this.className} ${name}`.trim(); },
      contains: name => this.className.split(/\s+/).includes(name)
    };
  }
  set innerHTML(value) { throw new Error('TOC must use textContent, never parse heading text as HTML'); }
  appendChild(child) {
    child.parentElement = this;
    child.parentNode = this;
    this.children.push(child);
    return child;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'id' || name === 'href') this[name] = String(value);
  }
  getAttribute(name) { return this.attributes[name] ?? this[name] ?? null; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelectorAll(selector) {
    const tags = selector.split(',').map(tag => tag.trim().toUpperCase());
    return descendants(this).filter(node => tags.includes(node.tagName));
  }
  closest(selector) {
    const tags = selector.split(',').map(tag => tag.trim().toUpperCase());
    for (let node = this; node; node = node.parentElement) {
      if (tags.includes(node.tagName)) return node;
    }
    return null;
  }
  click() {
    let prevented = false;
    if (this.listeners.click) this.listeners.click({ preventDefault() { prevented = true; } });
    assert.equal(prevented, false, 'TOC link must preserve native hash navigation');
  }
}

function fixture(populate) {
  const body = new Element('body');
  const content = body.appendChild(new Element('main'));
  content.className = 'kb-content';
  const toc = body.appendChild(new Element('aside', '', 'kb-toc'));
  toc.hidden = true;
  const data = populate({ body, content, toc });
  const document = {
    body,
    getElementById(id) { return [body, ...descendants(body)].find(node => node.id === id) || null; },
    createElement(tag) { return new Element(tag); },
    querySelectorAll(selector) {
      // Restrict each selector to its actual subtree, so scope/level regressions fail.
      const matches = new Set();
      for (const part of selector.split(',')) {
        const parsed = part.trim().match(/^(?:(\.kb-content)\s+)?(h[1-6])$/i);
        assert.ok(parsed, `Unsupported selector in minimal DOM: ${part}`);
        const root = parsed[1] ? content : body;
        descendants(root).filter(node => node.tagName === parsed[2].toUpperCase())
          .forEach(node => matches.add(node));
      }
      return descendants(body).filter(node => matches.has(node));
    },
    addEventListener(event, callback) {
      assert.equal(event, 'DOMContentLoaded');
      callback();
    }
  };
  vm.runInNewContext(script, { document }, { filename: 'generated-kb-toc-script.js' });
  return { body, content, toc, data, links: descendants(toc).filter(node => node.tagName === 'A') };
}

const result = fixture(({ body, content }) => {
  body.appendChild(new Element('div', '', 'kb-heading-1'));
  body.appendChild(new Element('h2', 'Outside article'));
  content.appendChild(new Element('h1', 'Page title'));
  const heading2 = content.appendChild(new Element('h2', '重复标题'));
  const heading3 = content.appendChild(new Element('h3', '重复标题'));
  const special = '<img src=x onerror="alert(1)"> 中文 & 😀';
  const heading4 = content.appendChild(new Element('h4', special, '已有 id/#中文&'));
  content.appendChild(new Element('h5', 'Too deep'));
  content.appendChild(new Element('h6', 'Also too deep'));
  const pre = content.appendChild(new Element('pre'));
  pre.appendChild(new Element('h2', 'Code example heading'));
  const code = content.appendChild(new Element('code'));
  code.appendChild(new Element('h3', 'Inline example heading'));
  const outer = content.appendChild(new Element('details'));
  const inner = outer.appendChild(new Element('details'));
  const nested = inner.appendChild(new Element('h2', 'Nested collapsed section'));
  const unrelated = content.appendChild(new Element('details'));
  return { heading2, heading3, heading4, nested, outer, inner, unrelated, special };
});

const { heading2, heading3, heading4, nested, outer, inner, unrelated, special } = result.data;
assert.equal(result.links.length, 4, 'Only article h2-h4 outside code are included');
assert.deepEqual(result.links.map(link => link.textContent), ['重复标题', '重复标题', special, 'Nested collapsed section']);
assert.deepEqual(result.links.map(link => link.parentElement.className), [
  'kb-toc-level-2', 'kb-toc-level-3', 'kb-toc-level-4', 'kb-toc-level-2'
]);
assert.equal(heading4.id, '已有 id/#中文&', 'Existing heading anchors must be preserved');
const generated = [heading2.id, heading3.id, nested.id];
assert.ok(generated.every(Boolean), 'Every missing heading id is generated');
assert.equal(new Set(generated).size, 3, 'Repeated headings still receive unique anchors');
assert.ok(!generated.includes('kb-heading-1'), 'Generated ids avoid collisions elsewhere in the page');
assert.equal(new Set(descendants(result.body).filter(node => node.id).map(node => node.id)).size,
  descendants(result.body).filter(node => node.id).length, 'All fixture ids remain unique');
for (const [index, heading] of [heading2, heading3, heading4, nested].entries()) {
  assert.equal(result.links[index].getAttribute('href'), '#' + encodeURIComponent(heading.id));
  assert.equal(result.links[index].children.length, 0, 'Heading markup must remain plain link text');
}
assert.equal(result.toc.hidden, false);
assert.equal(result.body.classList.contains('kb-has-toc'), true);
assert.equal(outer.open, false);
assert.equal(inner.open, false);
result.links[3].click();
assert.equal(outer.open, true, 'Click opens outer details');
assert.equal(inner.open, true, 'Click opens inner details');
assert.equal(unrelated.open, false, 'Unrelated details retain their state');

for (const populate of [() => ({}), ({ body, content }) => {
  body.appendChild(new Element('h2', 'Outside'));
  content.appendChild(new Element('h1', 'Title only'));
  content.appendChild(new Element('h5', 'Excluded level'));
  return {};
}]) {
  const empty = fixture(populate);
  assert.equal(empty.links.length, 0);
  assert.equal(empty.toc.hidden, true, 'No eligible headings keeps TOC hidden');
  assert.equal(empty.toc.children.length, 0, 'No empty list is appended');
  assert.equal(empty.body.classList.contains('kb-has-toc'), false, 'No headings must not enable TOC layout');
}
emitComplete({ suite: path.basename(__filename), assert });
