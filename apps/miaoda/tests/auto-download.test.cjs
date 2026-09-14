const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const moduleValue = {exports: {}};
const source = fs.readFileSync(path.join(__dirname, '../client/src/lib/auto-download.ts'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
new Function('exports', 'module', compiled)(moduleValue.exports, moduleValue);
const {createDownloadQueue} = moduleValue.exports;
const storage = () => {const m = new Map(); return {getItem: k => m.get(k), setItem: (k,v) => m.set(k,v)};};
const job = (id, extra = {}) => ({id, status:'completed', workflow:'video', deliveryUrl:'https://files.example/f.mp4', outputName:'movie.mp4', ...extra});

test('downloads only tasks submitted from this device, never history', async () => {
  const saved=[];
  const q=createDownloadQueue(storage(),'pending',async (...x)=>saved.push(x),()=>{});
  q.remember('mine');
  await q.inspect([job('history'),job('mine')]);
  await q.inspect([job('mine')]);
  assert.deepEqual(saved,[['https://files.example/f.mp4','movie.mp4']]);
});
test('concurrent polls cannot start duplicate file transfers', async () => {
  let resolve, count=0;
  const q=createDownloadQueue(storage(),'pending',()=>{count++;return new Promise(r=>resolve=r);},()=>{});
  q.remember('mine');
  const first=q.inspect([job('mine')]);
  await q.inspect([job('mine')]);
  assert.equal(count,1);
  resolve(); await first;
});
test('pending task survives a page reload and is cleared after saving', async () => {
  const s=storage();let count=0;
  createDownloadQueue(s,'pending',async()=>{},()=>{}).remember('mine');
  await createDownloadQueue(s,'pending',async()=>count++,()=>{}).inspect([job('mine')]);
  await createDownloadQueue(s,'pending',async()=>count++,()=>{}).inspect([job('mine')]);
  assert.equal(count,1);
});
test('failed automatic transfer offers manual retry instead of looping', async () => {
  let count=0;const notices=[];
  const q=createDownloadQueue(storage(),'pending',async()=>{count++;throw Error('CORS');},(...x)=>notices.push(x));
  q.remember('mine');await q.inspect([job('mine')]);await q.inspect([job('mine')]);
  assert.equal(count,1);assert.equal(notices.at(-1)[1],true);
});
test('local-only and metadata results do not invent a download URL', async () => {
  let count=0;
  const q=createDownloadQueue(storage(),'pending',async()=>count++,()=>{});
  q.remember('local');q.remember('meta');
  await q.inspect([job('local',{deliveryUrl:undefined}),job('meta',{workflow:'inspect'})]);
  assert.equal(count,0);
});
