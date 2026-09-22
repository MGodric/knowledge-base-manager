'use strict';
const REPORT_PREFIX = 'KB_NODE_TEST_REPORT ';
function instrument(assertions) {
  let count = 0; const wrapped = Object.create(assertions);
  for (const name of Object.getOwnPropertyNames(assertions)) {
    if (typeof assertions[name] !== 'function' || name === 'AssertionError') continue;
    wrapped[name] = (...args) => { count += 1; return assertions[name](...args); };
  }
  Object.defineProperty(wrapped, '__kbAssertionCount', { value: () => count });
  return wrapped;
}
function emitComplete({ suite, assert }) {
  const assertions = assert && typeof assert.__kbAssertionCount === 'function' ? assert.__kbAssertionCount() : 0;
  process.stdout.write(REPORT_PREFIX + JSON.stringify({ suite, status: 'passed', assertions }) + '\n');
}
module.exports = { emitComplete, instrument };
