const path = require('path');

const projectRoot = __dirname;
const venvBin = path.join(projectRoot, 'venv', 'bin');

module.exports = {
  apps: [
    {
      name: 'stib-frontend',
      cwd: path.join(projectRoot, 'stibFront'),
      script: 'ng',
      args: 'serve --port 4200',
      interpreter: 'node',
      watch: false
    },
    {
      name: 'stib-api',
      script: path.join(venvBin, 'gunicorn'),
      args: ['-w', '4', '-b', '0.0.0.0:5000', 'app:create_app()'],
      interpreter: 'python3',  // or 'bash' to run the gunicorn script directly if executable
      cwd: path.join(projectRoot, 'flask-web-server'),
      watch: false,
      env: {
        PATH: venvBin
      }
    },
    {
      name: 'stib-imports',
      script: path.join(venvBin, 'uvicorn'),
      args: ['app.main:app', '--host', '127.0.0.1', '--port', '8001', '--workers', '2'],
      interpreter: 'python3', // or 'bash'
      cwd: path.join(projectRoot, 'fastapi-server'),
      watch: false,
      env: {
        PATH: venvBin
      }
    }
  ]
};
