Here you go — a neat, minimal **README.md** for your colleagues:

````markdown
# PM2 Usage — STIB Project

This project uses PM2 to run/manage these apps:

- **stib-frontend** (Angular `ng serve`)
- **stib-api** (Flask with Gunicorn)
- **stib-imports** (FastAPI with Uvicorn)

---

## Basic commands

```bash
# Start all apps from ecosystem.config.js
pm2 start ecosystem.config.js

# Restart all apps
pm2 restart all

# Stop all apps
pm2 stop all

# Show status of all apps
pm2 status

# Show logs (live tail)
pm2 logs

# Save current PM2 process list for auto resurrection
pm2 save
````

---

## Notes

* Apps run from different working directories as defined in `ecosystem.config.js`
* Python apps use virtualenv paths set in env `PATH`
* Frontend runs Angular CLI via Node

---

This is all you need to start, monitor, and stop the services on the shared machine.

```

Want me to save it as a file you can download?
```
