module.exports = {
  apps: [
    {
      name: 'stib-frontend',
      cwd: '/home/clement/projets/server-STIB/stibFront',
      script: 'ng',
      args: 'serve --port 4200 --proxy-config proxy.conf.json',
      interpreter: 'none',
      watch: false,
      env: {
        PATH: '/home/clement/projets/server-STIB/stibFront/node_modules/.bin:' + process.env.PATH
      }
    },
    {
      name: 'stib-api',
      script: '/home/clement/projets/server-STIB/venv/bin/gunicorn',
      args: ['-w', '4', '-b', '0.0.0.0:5000', 'app:create_app()'],
      interpreter: 'none',
      cwd: '/home/clement/projets/server-STIB/flask-web-server',
      watch: false,
      env: {
        PATH: '/home/clement/projets/server-STIB/venv/bin:' + process.env.PATH,
        VIRTUAL_ENV: '/home/clement/projets/server-STIB/venv'
      }
    },
    {
      name: 'stib-imports',
      script: '/home/clement/projets/server-STIB/venv/bin/uvicorn',
      args: ['app.main:app', '--host', '127.0.0.1', '--port', '8001', '--workers', '2'],
      interpreter: 'none',
      cwd: '/home/clement/projets/server-STIB/fastapi-server',
      watch: false,
      env: {
        PATH: '/home/clement/projets/server-STIB/venv/bin:' + process.env.PATH,
        VIRTUAL_ENV: '/home/clement/projets/server-STIB/venv'
      }
    }
  ]
};