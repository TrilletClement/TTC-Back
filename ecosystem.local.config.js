const path = require('path');

const projectRoot = __dirname;
const projectVenv = path.join(projectRoot, 'venv');
const venvBin = path.join(projectVenv, 'bin');
const fastapiRoot = path.join(projectRoot, 'fastapi-server');
const logsDir = path.join(projectRoot, 'logs');

const FRONTEND_PORT = '4200';
const BACKEND_PORT = '8000';

const backendEnv = {
  PORT: BACKEND_PORT,
  DATABASE_URL: 'postgresql+psycopg2://mylocaldb:clement@localhost:5432/mylocaldb',

  ACCESS_TOKEN_EXPIRE_MINUTES: '60',

  JWT_SECRET_KEY: 'your-secret-key-min-32-characters-change-in-production',
  JWT_ALGORITHM: 'HS256',
  JWT_EXPIRE_MINUTES: '1440',

  API_V1_PREFIX: '/api/v1',
  PROJECT_NAME: 'STIB Automation API',
  DEBUG: 'false',
  ENV: 'prod',
  CORS_ORIGINS: '["*"]',
  STIB_API_KEY: 'd93b118966fc799fc52d8f63f936478f4b88dbed35370559a7d961f7',
  TEC_API_KEY: '36497DD5F3AD4262B24981633E73EF33'
};

const frontendEnv = {
  PORT: FRONTEND_PORT,
  API_BASE_URL: `http://localhost:${BACKEND_PORT}`  // Pointe vers FastAPI
};

module.exports = {
  apps: [
    // Frontend - Configuration IDENTIQUE à celle qui fonctionne
    {
      name: 'stib-frontend',
      cwd: path.join(projectRoot, 'stibFront'),
      script: path.join('scripts', 'start-frontend.js'),
      args: ['serve', '--port', FRONTEND_PORT, '--proxy-config', 'proxy.conf.json'],
      interpreter: 'node',
      watch: false,
      env: {
        ...frontendEnv,
      },
      log_file: path.join(logsDir, 'stib-frontend.log'),
      out_file: path.join(logsDir, 'stib-frontend.out.log'),
      error_file: path.join(logsDir, 'stib-frontend.err.log'),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    
    // Backend FastAPI - Remplace Flask
    {
      name: 'stib-api',
      script: 'uvicorn',
      args: ['app.main:app', '--host', '0.0.0.0', '--port', BACKEND_PORT, '--workers', '4'],
      interpreter: 'none',
      cwd: path.join(projectRoot, 'fastapi-server'),
      watch: false,
      env: {
        ...backendEnv,
        PYTHONPATH: fastapiRoot,
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: projectVenv
      },
      log_file: path.join(logsDir, 'stib-api.log'),
      out_file: path.join(logsDir, 'stib-api.out.log'),
      error_file: path.join(logsDir, 'stib-api.err.log'),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
    
    // Scheduler pour les imports automatiques
    {
      name: 'stib-scheduler',
      script: 'python',
      args: ['-m', 'app.routines.scheduler'],
      interpreter: 'none',
      cwd: path.join(projectRoot, 'fastapi-server'),
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 4000,
      env: {
        ...backendEnv,
        PYTHONPATH: fastapiRoot,
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: projectVenv
      },
      log_file: path.join(logsDir, 'stib-scheduler.log'),
      out_file: path.join(logsDir, 'stib-scheduler.out.log'),
      error_file: path.join(logsDir, 'stib-scheduler.err.log'),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    }
  ]
};
