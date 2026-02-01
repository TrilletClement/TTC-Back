const path = require('path');

const projectRoot = __dirname;
const venvBin = path.join(projectRoot, 'venv', 'bin');
const fastapiRoot = path.join(projectRoot, 'fastapi-server');

const frontendEnv = {
  API_BASE_URL: 'http://localhost:8000'  // Pointe vers FastAPI
};

const backendEnv = {
  DATABASE_URL: 'postgresql+psycopg2://mylocaldb:clement@localhost:5432/mylocaldb',

  ACCESS_TOKEN_EXPIRE_MINUTES: '60',

  JWT_SECRET_KEY: 'your-secret-key-min-32-characters-change-in-production',
  JWT_ALGORITHM: 'HS256',
  JWT_EXPIRE_MINUTES: '1440',

  API_V1_PREFIX: '/api/v1',
  PROJECT_NAME: 'STIB Automation API',
  DEBUG: 'false',
  ENV: 'prod',
  CORS_ORIGINS: '["http://localhost:4200","http://127.0.0.1:4200","http://localhost:8000","http://127.0.0.1:8000"]',
  STIB_API_KEY: 'd93b118966fc799fc52d8f63f936478f4b88dbed35370559a7d961f7',
  TEC_API_KEY: '36497DD5F3AD4262B24981633E73EF33'
};

module.exports = {
  apps: [
    // Frontend - Configuration IDENTIQUE à celle qui fonctionne
    {
      name: 'stib-frontend',
      cwd: path.join(projectRoot, 'stibFront'),
      script: path.join('scripts', 'start-frontend.js'),
      args: ['serve', '--port', '4200', '--proxy-config', 'proxy.conf.json'],
      interpreter: 'node',
      watch: false,
      env: {
        ...frontendEnv,
        PATH: path.join(projectRoot, 'stibFront', 'node_modules', '.bin') + path.delimiter + process.env.PATH
      },
      log_file: path.join(projectRoot, 'logs', 'stib-frontend.log'),
      out_file: path.join(projectRoot, 'logs', 'stib-frontend.out.log'),
      error_file: path.join(projectRoot, 'logs', 'stib-frontend.err.log')
    },
    
    // Backend FastAPI - Remplace Flask
    {
      name: 'stib-api',
      script: path.join('..', 'venv', 'bin', 'uvicorn'),
      args: ['app.main:app', '--host', '0.0.0.0', '--port', '8000', '--workers', '4'],
      interpreter: 'none',
      cwd: path.join(projectRoot, 'fastapi-server'),
      watch: false,
      env: {
        ...backendEnv,
        PYTHONPATH: fastapiRoot,
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: path.join(projectRoot, 'venv')
      },
      log_file: path.join(projectRoot, 'logs', 'stib-api.log'),
      out_file: path.join(projectRoot, 'logs', 'stib-api.out.log'),
      error_file: path.join(projectRoot, 'logs', 'stib-api.err.log')
    },
    
    // Scheduler pour les imports automatiques
    {
      name: 'stib-scheduler',
      script: path.join('..', 'venv', 'bin', 'python'),
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
        VIRTUAL_ENV: path.join(projectRoot, 'venv')
      },
      log_file: path.join(projectRoot, 'logs', 'stib-scheduler.log'),
      out_file: path.join(projectRoot, 'logs', 'stib-scheduler.out.log'),
      error_file: path.join(projectRoot, 'logs', 'stib-scheduler.err.log')
    }
  ]
};