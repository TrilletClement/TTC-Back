const path = require('path');

const projectRoot = __dirname;
const venvBin = path.join(projectRoot, 'venv', 'bin');
const frontendEnv = {
  API_BASE_URL: 'http://localhost:5000/'
};
const backendEnv = {
  DATABASE_URL: 'postgresql+psycopg2://mylocaldb:mylocaldb@localhost:5432/mylocaldb',
  SQL_HEAVY_LOGS: 'true',
  SECRET_KEY: 'a_default_secret_key',
  SECURITY_PASSWORD_SALT: 'a_default_salt',
  STIB_API_KEY: 'd93b118966fc799fc52d8f63f936478f4b88dbed35370559a7d961f7',
  TEC_API_KEY: '36497DD5F3AD4262B24981633E73EF33'
};

module.exports = {
  apps: [
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
    {
      name: 'stib-api',
      script: path.join('..', 'venv', 'bin', 'gunicorn'),
      args: ['-w', '4', '-b', '0.0.0.0:5000', 'app:create_app()'],
      interpreter: 'none',
      cwd: path.join(projectRoot, 'flask-web-server'),
      watch: false,
      env: {
        ...backendEnv,
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: path.join(projectRoot, 'venv')
      },
      log_file: path.join(projectRoot, 'logs', 'stib-api.log'),
      out_file: path.join(projectRoot, 'logs', 'stib-api.out.log'),
      error_file: path.join(projectRoot, 'logs', 'stib-api.err.log')
    },
    {
      name: 'stib-imports',
      script: path.join('..', 'venv', 'bin', 'uvicorn'),
      args: ['app.main:app', '--host', '127.0.0.1', '--port', '8001', '--workers', '2'],
      interpreter: 'none',
      cwd: path.join(projectRoot, 'fastapi-server'),
      watch: false,
      env: {
        ...backendEnv,
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: path.join(projectRoot, 'venv')
      },
      log_file: path.join(projectRoot, 'logs', 'stib-imports.log'),
      out_file: path.join(projectRoot, 'logs', 'stib-imports.out.log'),
      error_file: path.join(projectRoot, 'logs', 'stib-imports.err.log')
    }
  ]
};
