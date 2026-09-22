'use strict';

// Development-only behavioral test: execute the actual generated-page script.
// No browser, server, third-party package, or Node runtime dependency is added.
const { emitComplete, instrument } = require('./node_test_report.cjs');
const assert = instrument(require('node:assert/strict'));
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname,
  '../knowledge-base-manager/scripts/kb_core/static_build.py'), 'utf8');
const match = source.match(/<script id="kb-copy-script">([\s\S]*?)<\/script>/);
assert.ok(match, 'The page template must contain the actual copy script');
const script = match[1].replace(/\{\{/g, '{').replace(/\}\}/g, '}');

class Element {
  constructor(tag, text = '') {
    this.tagName = tag.toUpperCase();
    this.textContent = text;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.style = {};
    this.disabled = false;
    this.classList = { add: (...names) => {
      this.className = [this.className || '', ...names].join(' ').trim();
    } };
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  appendChild(child) { child.parentNode = this; child.parentElement = this; this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  insertBefore(child, sibling) {
    child.parentNode = this;
    child.parentElement = this;
    this.children.splice(this.children.indexOf(sibling), 0, child);
    return child;
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelector(selector) {
    return this.children.find(child => child.tagName.toLowerCase() === selector) || null;
  }
  focus() { this.focused = true; }
  async click() {
    assert.equal(this.disabled, false, 'Button must remain retryable');
    await this.listeners.click({ currentTarget: this, preventDefault() {} });
  }
}

function fixture(texts, clipboard, selectionAvailable = true) {
  const blocks = texts.map(text => {
    const pre = new Element('pre');
    pre.appendChild(new Element('code', text));
    new Element('section').appendChild(pre);
    return pre;
  });
  const selected = [];
  const selection = {
    removeAllRanges() { selected.length = 0; },
    addRange(range) { selected.push(range.node); }
  };
  const document = {
    querySelectorAll(selector) {
      assert.match(selector, /pre/);
      return selector.includes('code') ? blocks.map(pre => pre.children[0]) : blocks;
    },
    createElement(tag) { return new Element(tag); },
    createRange() { return { selectNodeContents(node) { this.node = node; } }; },
    getSelection() { return selection; },
    addEventListener(event, callback) {
      assert.equal(event, 'DOMContentLoaded'); callback();
    }
  };
  const context = {
    document, navigator: clipboard === undefined ? {} : { clipboard },
    window: { getSelection: () => selectionAvailable ? selection : null },
    setTimeout() {}, clearTimeout() {}
  };
  vm.runInNewContext(script, context, { filename: 'generated-kb-copy-script.js' });
  function descendants(node) { return node.children.flatMap(child => [child, ...descendants(child)]); }
  return { blocks, selected, buttons: blocks.map(pre => descendants(pre.parentNode).find(n => n.tagName === 'BUTTON')),
    status(index) { return descendants(blocks[index].parentNode).filter(n => n.tagName === 'SPAN').map(n => n.textContent).join(' '); } };
}

async function main() {
  const payloads = ['第一段\n<>& "引号" 😀\n', '第二段\r\n  保留缩进\n'];
  const writes = [];
  const success = fixture(payloads, { async writeText(text) { writes.push(text); } });
  assert.deepEqual(writes, [], 'Page initialization must not access the clipboard');
  assert.equal(success.buttons.length, 2);
  assert.ok(success.buttons.every(Boolean), 'Every code block gets a button');
  assert.ok(success.buttons.every(button => button.type === 'button'), 'Copy controls must not submit forms');
  await success.buttons[1].click();
  assert.deepEqual(writes, [payloads[1]], 'Copy only the clicked block, preserving text');
  await success.buttons[0].click();
  assert.deepEqual(writes, [payloads[1], payloads[0]]);
  assert.match(success.status(0) + success.buttons[0].textContent, /已复制/);
  await success.buttons[0].click();
  assert.equal(writes.length, 3, 'Successful copy remains retryable');

  for (const [name, clipboard] of [
    ['rejected', { async writeText() { throw new Error('permission denied'); } }],
    ['absent', undefined]
  ]) {
    const fallback = fixture(payloads, clipboard);
    assert.deepEqual(fallback.selected, [], `${name}: initialization must not select code`);
    await fallback.buttons[1].click();
    assert.equal(fallback.selected.length, 1, `${name}: select exactly one code block`);
    assert.equal(fallback.selected[0], fallback.blocks[1].children.find(n => n.tagName === 'CODE'));
    assert.match(fallback.status(1) + fallback.buttons[1].textContent, /手动|Ctrl|⌘|Command/,
      `${name}: explain manual copy`);
    assert.doesNotMatch(fallback.status(1), /已复制/, `${name}: never claim clipboard success`);
    await fallback.buttons[1].click();
    assert.equal(fallback.selected.length, 1, `${name}: fallback remains retryable`);
  }
  const noSelection = fixture(payloads, undefined, false);
  await noSelection.buttons[0].click();
  assert.deepEqual(noSelection.selected, []);
  assert.match(noSelection.status(0), /手动选中/);
  assert.doesNotMatch(noSelection.status(0), /已复制|已选中/);
  assert.equal(noSelection.buttons[0].disabled, false);
  assert.deepEqual(fixture([], undefined).buttons, [], 'No-code pages initialize safely');
  console.log('PASS: actual inline copy script; success, rejection, missing API, retry, exact text, no-code');
}

main().then(
  () => emitComplete({ suite: path.basename(__filename), assert }),
  error => { console.error(error); process.exitCode = 1; }
);
