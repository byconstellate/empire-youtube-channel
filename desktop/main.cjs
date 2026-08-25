const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn, spawnSync } = require('node:child_process');
const { existsSync, mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const path = require('node:path');

const DEFAULT_REPOSITORY = 'https://github.com/byconstellate/empire-youtube-channel.git';
const LOCAL_PORT = 5187;
let rendererProcess;
let windowInstance;

function configPath() {
  return path.join(app.getPath('userData'), 'empire-config.json');
}

function readConfig() {
  try {
    return JSON.parse(readFileSync(configPath(), 'utf8'));
  } catch {
    return { repository: DEFAULT_REPOSITORY };
  }
}

function writeConfig(config) {
  mkdirSync(path.dirname(configPath()), { recursive: true });
  writeFileSync(configPath(), JSON.stringify(config, null, 2));
}

function commandExists(command) {
  return spawnSync('sh', ['-lc', `command -v ${command}`], { encoding: 'utf8' }).status === 0;
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(stderr.trim() || stdout.trim() || `${command} exited with code ${code}`));
    });
  });
}

async function chooseRepository() {
  const config = readConfig();
  if (config.repository) return config;

  const response = await dialog.showMessageBox({
    type: 'question',
    title: 'Connect Empire to GitHub',
    message: 'The Empire repository is ready to connect.',
    detail: `This app will use your Mac's Git credentials to pull:\n${DEFAULT_REPOSITORY}`,
    buttons: ['Use this repository', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
  });
  if (response.response !== 0) throw new Error('Repository setup was cancelled.');
  const nextConfig = { repository: DEFAULT_REPOSITORY };
  writeConfig(nextConfig);
  return nextConfig;
}

async function prepareRepository(repositoryUrl) {
  if (!/^https:\/\/github\.com\/[^/]+\/[^/]+(?:\.git)?$/.test(repositoryUrl) &&
      !/^git@github\.com:[^/]+\/[^/]+(?:\.git)?$/.test(repositoryUrl)) {
    throw new Error('For safety, the repository must be a GitHub HTTPS or SSH URL.');
  }

  const repoDirectory = path.join(app.getPath('documents'), 'Empire YouTube', 'empire-youtube-channel');
  mkdirSync(path.dirname(repoDirectory), { recursive: true });
  if (existsSync(path.join(repoDirectory, '.git'))) {
    await run('git', ['-C', repoDirectory, 'pull', '--ff-only']);
  } else {
    await run('git', ['clone', '--depth', '1', repositoryUrl, repoDirectory]);
  }
  return repoDirectory;
}

async function preparePython(repoDirectory) {
  const python = commandExists('python3') ? 'python3' : commandExists('python') ? 'python' : null;
  if (!python) throw new Error('Python 3 is required. Install it from python.org, then reopen Empire.');
  if (!commandExists('ffmpeg')) throw new Error('FFmpeg is required. Install it with Homebrew using: brew install ffmpeg');

  const virtualEnv = path.join(repoDirectory, '.venv');
  if (!existsSync(path.join(virtualEnv, 'bin', 'python'))) {
    await run(python, ['-m', 'venv', virtualEnv], { cwd: repoDirectory });
    await run(path.join(virtualEnv, 'bin', 'python'), ['-m', 'pip', 'install', '-r', 'requirements.txt'], { cwd: repoDirectory });
  }
  return path.join(virtualEnv, 'bin', 'python');
}

async function waitForServer() {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${LOCAL_PORT}/`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('The local Empire renderer did not start in time.');
}

async function startEmpire() {
  const config = await chooseRepository();
  const repoDirectory = await prepareRepository(config.repository);
  const python = await preparePython(repoDirectory);
  rendererProcess = spawn(python, ['server.py'], {
    cwd: repoDirectory,
    env: { ...process.env, PORT: String(LOCAL_PORT) },
    stdio: 'ignore',
  });
  await waitForServer();
  return `http://127.0.0.1:${LOCAL_PORT}/`;
}

async function openEmpire() {
  try {
    const url = await startEmpire();
    windowInstance = new BrowserWindow({
      width: 1440,
      height: 960,
      minWidth: 980,
      minHeight: 700,
      title: 'EMPIRE YouTube Studio',
      webPreferences: { contextIsolation: true, sandbox: true },
    });
    await windowInstance.loadURL(url);
    windowInstance.on('closed', () => { windowInstance = null; });
  } catch (error) {
    const result = await dialog.showMessageBox({
      type: 'error',
      title: 'Empire could not start',
      message: 'The local renderer needs one more setup step.',
      detail: error.message,
      buttons: ['Open setup notes', 'Close'],
    });
    if (result.response === 0) {
      await shell.openExternal('https://github.com/byconstellate/empire-youtube-channel');
    }
    app.quit();
  }
}

app.whenReady().then(openEmpire);
app.on('window-all-closed', () => {
  if (rendererProcess) rendererProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});
app.on('before-quit', () => {
  if (rendererProcess) rendererProcess.kill();
});