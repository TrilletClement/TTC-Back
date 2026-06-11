The problem is clear: you're using quick tunnels which are unstable by design — they crash, restart, and get a new random URL each time. Your current active URL is ranch-topics-answer-queries.trycloudflare.com but it'll change again on the next restart.

The fix is a named Cloudflare Tunnel — gives you a permanent URL like webhook.trillet.be. Here's the full setup:

Step 1 — Authenticate cloudflared with your Cloudflare account:


cloudflared tunnel login
This opens a browser. Log in and select your trillet.be zone. It saves a cert to ~/.cloudflared/cert.pem.

Step 2 — Create the named tunnel (run this once):


cloudflared tunnel create stib-webhook
This creates a stable tunnel UUID and saves credentials to ~/.cloudflared/<uuid>.json.

Step 3 — Route a subdomain to it:


cloudflared tunnel route dns stib-webhook webhook.trillet.be
This adds a CNAME in your Cloudflare DNS automatically.

Step 4 — Once you've done steps 1–3, I'll create the config file and update PM2. Let me prepare it now so you can paste it right after:

Bash Find PM2 ecosystem config or stib-sendcloud process details
IN
cat /home/trillet/projects/server-STIB/ecosystem.config.js 2>/dev/null || cat /home/trillet/projects/server-STIB/ecosystem.config.cjs 2>/dev/null || pm2 show stib-sendcloud 2>&1 | grep "script\|args\|cwd"

OUT
/**
 * PM2 production config.
 * Reads all secrets from .env at the project root — edit that file, not this one.
 * On the production server: copy .env.example → .env and fill in prod values.
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
// Paths — __dirname resolves to wherever the project is cloned on the server
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
// Apps
// ---------------------------------------------------------------------------
module.exports = {
  apps: [
    {
      name:        'stib-api',
      cwd:         FASTAPI_ROOT,
      script:      path.join(VENV_BIN, 'uvicorn'),
      // Listen on 127.0.0.1 only — Nginx proxies from outside
      args:        ['app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '4'],
      interpreter: 'none',
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
      autorestart: true,
      env:         backendEnv,
      out_file:    path.join(LOGS_DIR, 'scheduler-out.log'),
      error_file:  path.join(LOGS_DIR, 'scheduler-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
The stib-sendcloud process is not in ecosystem.config.js and uses a quick tunnel — that's the root cause. Let me prepare the full fix. When you've done steps 1–3 above, run:


cloudflared tunnel list
And paste me the UUID (looks like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx). Then I'll create the config file and update PM2.

While you do that, here's what I'll set up the moment you give me the UUID — let me prepare the templates:

Bash Check cloudflared state and current PM2 args
IN
ls ~/.cloudflared/ 2>/dev/null; echo "---current pm2 sendcloud args---"; pm2 show stib-sendcloud 2>/dev/null | grep "script args"

OUT
---current pm2 sendcloud args---
│ script args       │ tunnel --url http://localhost:8000                                 │
Here's the complete fix. Run these 3 commands — you'll need to approve the browser auth on step 1:


# Step 1: authenticate (opens browser — select trillet.be)
cloudflared tunnel login

# Step 2: create the named tunnel
cloudflared tunnel create stib-webhook

# Step 3: route a subdomain (pick a dev-specific one to avoid conflict with prod)
cloudflared tunnel route dns stib-webhook devhook.trillet.be
After step 2, you'll see output like:


Created tunnel stib-webhook with id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Paste me that UUID and I'll immediately:

Create ~/.cloudflared/config.yml
Add the named tunnel to ecosystem.config.js
Delete the broken quick-tunnel PM2 process and replace it
The SendCloud webhook URL becomes permanently: https://devhook.trillet.be/api/shipping/webhook/sendcloud
One thing to do now while waiting — stop the crashing process to avoid log spam:


pm2 stop stib-sendcloud