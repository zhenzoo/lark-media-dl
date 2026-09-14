// Produce the layout expected by Miaoda: server/, shared/, client/ assets and dist/client/index.html.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
process.chdir(root);
process.env.NODE_ENV = 'production';
const output = path.resolve(root, 'dist');
// Build only owns root/dist. A fresh directory prevents tracing stale bundled dependencies.
if (path.dirname(output) !== root || path.basename(output) !== 'dist') throw Error('Invalid build directory');
if (fs.existsSync(output)) fs.rmSync(output, {recursive: true});
function run(script, args) {
  const result = spawnSync(process.execPath, [script, ...args], {stdio: 'inherit', env: process.env});
  if (result.status !== 0) process.exit(result.status || 1);
}
run(require.resolve('@nestjs/cli/bin/nest.js'), ['build']);
run(path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js'), ['build']);
fs.mkdirSync(path.join(output, 'dist/client'), {recursive: true});
for (const name of fs.readdirSync(path.join(output, 'client'))) {
  if (name.endsWith('.html')) {
    fs.renameSync(path.join(output, 'client', name), path.join(output, 'dist/client', name));
  }
}
fs.copyFileSync(path.join(root, 'scripts/run.sh'), path.join(output, 'run.sh'));
// Trace runtime dependencies; copy only the referenced files, never credentials or source .env files.
const {nodeFileTrace} = require('@vercel/nft');
nodeFileTrace([path.join(output, 'server/main.js')], {base: root}).then(({fileList, warnings}) => {
  const optional = ['@nestjs/microservices', '@nestjs/websockets', 'fsevents', '@node-rs/xxhash', 'class-transformer/storage'];
  for (const warning of warnings) {
    if (warning.message.startsWith('Failed to resolve dependency') && !optional.some(name => warning.message.includes('"' + name))) {
      throw warning;
    }
  }
  for (const relative of fileList) {
    if (!relative.startsWith('node_modules' + path.sep) && !relative.startsWith('node_modules/')) continue;
    const from = path.resolve(root, relative);
    const to = path.resolve(output, relative);
    if (!from.startsWith(root + path.sep) || !to.startsWith(output + path.sep)) throw Error('Invalid dependency path');
    fs.mkdirSync(path.dirname(to), {recursive: true});
    fs.copyFileSync(from, to);
  }
  const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
  fs.writeFileSync(path.join(output, 'package.json'), JSON.stringify({name: pkg.name, version: pkg.version, private: true}));
  console.log('Miaoda runtime files prepared; trace warnings:', warnings.size);
}).catch(error => { console.error(error.message); process.exitCode = 1; });
