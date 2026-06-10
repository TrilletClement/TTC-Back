/**
 * PM2 local development config.
 * Reads all secrets from .env at the project root — edit that file, not this one.
 * This file is gitignored.
 */
const path = require('path');
const fs   = require('fs');

// ---------------------------------------------------------------------------
// Minimal .env parser (no external dependencies needed)
// ---------------------------------------------------------------------------
function loadEnv(filePath) {
  try {
    return Object.fromEntries(
      fs.readFileSync(filePath, 'utf8')
        .split('\n')
        .filter(l => l.trim() && !l.trim().startsWith('#') && l.includes('='))
        .map(l => {
          const eq  = l.indexOf('=');
          const key = l.slice(0, eq).trim();
          let   val = l.slice(eq + 1).trim();
          if ((val.startsWith('"') && val.endsWith('"')) ||
              (val.startsWith("'") && val.endsWith("'"))) {
            val = val.slice(1, -1);
          }
          return [key, val];
        })
    );
  } catch (e) {
    console.error(`[ecosystem] Could not read ${filePath}:`, e.message);
    process.exit(1);
  }
}

const env = loadEnv(path.join(__dirname, '.env'));

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const PROJECT_ROOT = __dirname;
const VENV_BIN     = path.join(PROJECT_ROOT, 'venv/bin');
const FASTAPI_ROOT = path.join(PROJECT_ROOT, 'fastapi-server');
const LOGS_DIR     = path.join(PROJECT_ROOT, 'logs');

const backendEnv = {
  ...env,
  // Process-management vars — not secrets, don't belong in .env
  PYTHONPATH:  FASTAPI_ROOT,
  VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
  PATH:        `${VENV_BIN}:${process.env.PATH}`,
};

// ---------------------------------------------------------------------------
// Auto-generate runtime-env.js so the Angular dev server picks up API_BASE_URL
// without requiring a manual "node scripts/gen-runtime-env.js" step.
// ---------------------------------------------------------------------------
const runtimeEnvPath = path.join(PROJECT_ROOT, 'stibFront/public/runtime-env.js');
fs.writeFileSync(
  runtimeEnvPath,
  `window.__env = ${JSON.stringify({ API_BASE_URL: env.API_BASE_URL })};\n`,
);
console.log(`[ecosystem] runtime-env.js → API_BASE_URL=${env.API_BASE_URL}`);

// ---------------------------------------------------------------------------
// Apps
// ---------------------------------------------------------------------------
module.exports = {
  apps: [
    {
      name:        'stib-frontend',
      cwd:         path.join(PROJECT_ROOT, 'stibFront'),
      script:      path.join('scripts', 'start-frontend.js'),
      args:        ['serve', '--port', '4200', '--proxy-config', 'proxy.conf.json'],
      interpreter: 'node',
      watch:       false,
      env:         { PORT: '4200' },
      out_file:    path.join(LOGS_DIR, 'frontend-out.log'),
      error_file:  path.join(LOGS_DIR, 'frontend-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name:        'stib-api',
      cwd:         FASTAPI_ROOT,
      script:      path.join(VENV_BIN, 'uvicorn'),
      args:        ['app.main:app', '--host', '0.0.0.0', '--port', '8000', '--reload'],
      interpreter: 'none',
      watch:       false,
      autorestart: true,
      env:         backendEnv,
      out_file:    path.join(LOGS_DIR, 'api-out.log'),
      error_file:  path.join(LOGS_DIR, 'api-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name:        'stib-scheduler',
      cwd:         FASTAPI_ROOT,
      script:      path.join(VENV_BIN, 'python'),
      args:        ['-m', 'app.routines.scheduler'],
      interpreter: 'none',
      watch:       false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 4000,
      env:         backendEnv,
      out_file:    path.join(LOGS_DIR, 'scheduler-out.log'),
      error_file:  path.join(LOGS_DIR, 'scheduler-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      // Stripe CLI webhook tunnel for local development.
      // Prerequisites:
      //   1. Install Stripe CLI: https://docs.stripe.com/stripe-cli
      //   2. Authenticate once: stripe login
      //   3. On first run, note the printed "whsec_..." secret and set it
      //      as STRIPE_WEBHOOK_SECRET in .env, then restart stib-api.
      name:        'stib-stripe',
      script:      'stripe',
      args:        ['listen', '--forward-to', `${env.API_BASE_URL}/api/payments/webhook`],
      interpreter: 'none',
      watch:       false,
      autorestart: true,
      max_restarts: 5,
      restart_delay: 5000,
      out_file:    path.join(LOGS_DIR, 'stripe-out.log'),
      error_file:  path.join(LOGS_DIR, 'stripe-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name:        'stib-sendcloud',
      script:      'cloudflared',
      args:        ['tunnel', '--url', 'http://localhost:8000'],
      interpreter: 'none',
      autorestart: false,
      out_file:    path.join(LOGS_DIR, 'sendcloud-tunnel-out.log'),
      error_file:  path.join(LOGS_DIR, 'sendcloud-tunnel-error.log'),
    },
  ],
};
