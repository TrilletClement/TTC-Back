const path = require('path');

const projectRoot = __dirname;
const venvBin = path.join(projectRoot, 'venv', 'bin');

module.exports = {
  apps: [
    {
      name: 'stib-frontend',
      cwd: path.join(projectRoot, 'stibFront'),
      script: path.join('node_modules', '.bin', 'ng'),
      args: 'serve --port 4200 --proxy-config proxy.conf.json',
      interpreter: 'none',
      watch: false,
      env: {
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
        PATH: venvBin + path.delimiter + process.env.PATH,
        VIRTUAL_ENV: path.join(projectRoot, 'venv')
      }
    }
  ]
};
