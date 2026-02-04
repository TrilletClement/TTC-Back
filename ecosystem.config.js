const path = require('path');

// Chemins absolus pour éviter les erreurs de déploiement
const PROJECT_ROOT = '/home/c.trillet/server-STIB';
const FASTAPI_ROOT = path.join(PROJECT_ROOT, 'fastapi-server');
const VENV_BIN = path.join(PROJECT_ROOT, 'venv/bin');

module.exports = {
  apps: [
    {
      name: 'stib-api',
      cwd: FASTAPI_ROOT,
      script: path.join(VENV_BIN, 'uvicorn'),
      // On écoute sur 127.0.0.1 car Apache fait le pont (Reverse Proxy)
      args: 'app.main:app --host 127.0.0.1 --port 8000 --workers 4',
      interpreter: 'none', // Important: on utilise le chemin direct vers uvicorn du venv
      autorestart: true,
      max_memory_restart: '500M',
      env: {
        PYTHONPATH: FASTAPI_ROOT,
        VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
        PATH: `${VENV_BIN}:${process.env.PATH}`,
        ENV: 'production',
        // Ajoute ici tes variables sensibles ou via un fichier .env
        DEPLOY_SECRET: "446334b8bd0a3addec75bccc25c9ec39202bab0f95a3a75db61c52760d9671501"
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(PROJECT_ROOT, 'logs/api-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/api-out.log'),
    },
    {
      name: 'stib-scheduler',
      cwd: FASTAPI_ROOT,
      script: path.join(VENV_BIN, 'python'),
      args: '-m app.routines.scheduler',
      interpreter: 'none',
      autorestart: true,
      restart_delay: 5000, // Attendre 5s avant de redémarrer en cas de crash
      env: {
        PYTHONPATH: FASTAPI_ROOT,
        VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
        PATH: `${VENV_BIN}:${process.env.PATH}`
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(PROJECT_ROOT, 'logs/scheduler-error.log'),
      out_file: path.join(PROJECT_ROOT, 'logs/scheduler-out.log'),
    }
  ]
};