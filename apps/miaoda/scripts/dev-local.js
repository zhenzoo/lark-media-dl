const path = require('node:path');
const {spawn} = require('node:child_process');
process.chdir(path.resolve(__dirname, '..'));
require('dotenv').config({path: '.env.local', quiet: true});
require('dotenv').config({path: '.env', quiet: true});
process.env.NODE_ENV = 'development';
process.env.MIAODA_LOCAL_DEV = '1';
if (process.env.SUDA_WEBUSER) {
  try { JSON.parse(process.env.SUDA_WEBUSER); }
  catch { process.env.SUDA_WEBUSER = process.env.SUDA_WEBUSER.replace(/\\"/g, '"'); }
}
const tasks = [
  spawn(process.execPath, [require.resolve('@nestjs/cli/bin/nest.js'), 'start', '--watch'], {stdio: 'inherit'}),
  spawn(process.execPath, [path.join(path.dirname(require.resolve('vite/package.json')), 'bin/vite.js')], {stdio: 'inherit'}),
];
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => tasks.forEach(task => task.kill(signal)));
tasks.forEach(task => task.on('exit', code => { if (code) { tasks.forEach(other => other.kill()); process.exitCode = code; } }));
