const path = require('path');

const projectRoot = __dirname;
const venvBin = path.join(projectRoot, 'venv', 'bin');
const frontendEnv = {
  API_BASE_URL: 'https://transport.trillet.be/'
};
const backendEnv = {
  DATABASE_URL: 'postgresql+psycopg2://myappuser:mypassword@192.168.14.13:5432/myappdb',
  SQL_HEAVY_LOGS: 'false',
  SECRET_KEY: 'a_default_secret_key',
  SECURITY_PASSWORD_SALT: 'a_default_salt',
  STIB_API_KEY: '36109cef239270c05417ed2b4001d76f7b160a0824c2caa87fce5966',
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
      }
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
      }
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
      }
    }
  ]
};
