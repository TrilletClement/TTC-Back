module.exports = {
  apps: [
    {
      name: 'stib-frontend',
      cwd: '/home/c.trillet/server-STIB/stibFront',
      script: '/usr/bin/ng',
      args: 'serve --port 4200',
      interpreter: 'node',
      watch: false
    },
    {
      name: 'stib-api',
      script: '/home/c.trillet/server-STIB/venv/bin/gunicorn',
      args: ['-w', '4', '-b', '0.0.0.0:5000', 'app:create_app()'],
      interpreter: 'python3',  // or 'bash' to run the gunicorn script directly if executable
      cwd: '/home/c.trillet/server-STIB/flask-web-server',
      watch: false,
      env: {
        PATH: '/home/c.trillet/server-STIB/venv/bin'
      }
    },
    {
      name: 'stib-imports',
      script: '/home/c.trillet/server-STIB/venv/bin/uvicorn',
      args: ['app.main:app', '--host', '127.0.0.1', '--port', '8001', '--workers', '2'],
      interpreter: 'python3', // or 'bash'
      cwd: '/home/c.trillet/server-STIB/fastapi-server',
      watch: false,
      env: {
        PATH: '/home/c.trillet/server-STIB/venv/bin'
      }
    }
  ]
};
