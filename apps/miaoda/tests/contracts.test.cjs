const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
function load(name) {
  const file = path.resolve(__dirname, '../server/modules/jobs', name + '.ts');
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, experimentalDecorators: true,
  }}).outputText;
  const compiled = new Module(file);
  compiled.filename = file;
  compiled.paths = Module._nodeModulePaths(path.dirname(file));
  compiled._compile(output, file);
  return compiled.exports;
}
const {validateCompletion} = load('completion');
test('local download completes without a phone URL', () => assert.doesNotThrow(() => validateCompletion('video', 'post.txt')));
test('download completion must identify saved files', () => assert.throws(() => validateCompletion('video', '  ')));
test('metadata inspection requires no downloaded file', () => assert.doesNotThrow(() => validateCompletion('inspect')));
const {WorkerGuard} = load('worker.guard');
test('missing or wrong Worker Key fails closed', () => {
  const old = process.env.MEDIA_WORKER_API_KEY;
  try {
    delete process.env.MEDIA_WORKER_API_KEY;
    const guard = new WorkerGuard();
    const ctx = value => ({switchToHttp: () => ({getRequest: () => ({headers: {authorization: value}})})});
    assert.throws(() => guard.canActivate(ctx('Bearer test')));
    process.env.MEDIA_WORKER_API_KEY = 'test-only-key';
    assert.throws(() => guard.canActivate(ctx('Bearer wrong-key')));
    assert.throws(() => guard.canActivate(ctx('test-only-key')));
    assert.equal(guard.canActivate(ctx('Bearer test-only-key')), true);
  } finally {
    if (old === undefined) delete process.env.MEDIA_WORKER_API_KEY;
    else process.env.MEDIA_WORKER_API_KEY = old;
  }
});
