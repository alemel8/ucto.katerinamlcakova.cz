module.exports = {
  apps: [
    {
      name: 'ucto-backend',
      script: '/opt/vytezovani-faktur/backend/.venv/bin/uvicorn',
      args: 'app.main:app --host 127.0.0.1 --port 8000',
      cwd: '/opt/vytezovani-faktur/backend',
      interpreter: 'none',
      restart_delay: 3000,
      max_restarts: 10,
      env: {
        PATH: '/opt/vytezovani-faktur/backend/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
      },
    },
  ],
}
