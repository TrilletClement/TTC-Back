const path = require('path');

const PROJECT_ROOT = '/home/c.trillet/server-STIB';
const FASTAPI_ROOT = path.join(PROJECT_ROOT, 'fastapi-server');
const VENV_BIN = path.join(PROJECT_ROOT, 'venv/bin');

const backendEnv = {
  DATABASE_URL: 'postgresql+psycopg2://mylocaldb:mylocaldb@localhost:5432/mylocaldb',
  JWT_SECRET_KEY: 'your-secret-key-min-32-characters-change-in-production',
  JWT_ALGORITHM: 'HS256',
  DEPLOY_SECRET: "446334b8bd0a3addec75bccc25c9ec39202bab0f95a3a75db61c52760d9671501",
  
  ENV: 'production',
  PYTHONPATH: FASTAPI_ROOT,
  VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
  PATH: `${VENV_BIN}:${process.env.PATH}`,
  STIB_API_KEY: 'ad3f387e38ed4a12a781c8e0201b018b',
  TEC_API_KEY: '36497DD5F3AD4262B24981633E73EF33',
  PROJECT_NAME: 'STIB Automation API'
};

module.exports = {
  apps: [
    {
      name: 'stib-api',
      cwd: FASTAPI_ROOT,
      script: path.join(VENV_BIN, 'uvicorn'),
      // On écoute sur 127.0.0.1 car Nginx fait le pont
      args: ['app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '4'],
      interpreter: 'none',
      autorestart: true,
      env: backendEnv,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(PROJECT_ROOT, 'logs/api-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/api-out.log'),
    },
    {
      name: 'stib-scheduler',
      cwd: FASTAPI_ROOT,
      script: path.join(VENV_BIN, 'python'),
      args: ['-m', 'app.routines.scheduler'],
      interpreter: 'none',
      autorestart: true,
      env: backendEnv,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(PROJECT_ROOT, 'logs/scheduler-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/scheduler-out.log'),
    }
  ]
};