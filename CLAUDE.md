# CLAUDE.md — server-STIB

Working guidelines for AI assistants in this repo.
Edit freely — both humans and AI should keep this up to date.

---

## Project layout

```
server-STIB/
├── fastapi-server/        Python backend (FastAPI + SQLAlchemy + Alembic)
│   ├── app/
│   │   ├── core/          Config, JWT, auth decorators, mail
│   │   ├── domain/        Pure exceptions (NotFoundError, BusinessError, ValidationError)
│   │   ├── orm_models/    SQLAlchemy table definitions
│   │   ├── repositories/  DB queries — one file per aggregate, no business logic
│   │   ├── schemas/       Pydantic request/response models
│   │   ├── services/      Business logic — called by routers, use repos + ORM
│   │   ├── routers/       FastAPI route handlers — thin, delegate to services
│   │   └── routines/      APScheduler background jobs
│   └── migrations/versions/  Alembic migrations (named YYYYMMDD_NN_description.py)
└── stibFront/             Angular 17+ standalone frontend
    └── src/app/
        ├── Components/    One folder per component (*.ts / *.html / *.scss)
        ├── services/      Angular injectable services — one per domain
        ├── models/        Plain TS interfaces shared across components
        ├── config/        Runtime config (API base URL, etc.)
        └── pages/         Route-level page components (if separate from Components)
```

---

## Backend conventions

### Layering — respect the dependency direction

```
router → service → repository → ORM model
```

- **Routers** handle HTTP only: parse input, call service, map domain exceptions to HTTPException.
- **Services** own all business logic. They call repositories, never query the DB directly.
- **Repositories** own all SQLAlchemy queries. No business logic, no HTTP concerns.
- **Never** import a router from a service, or a service from a repository.

### Auth decorators

Use the shortcuts from `app.core.user_access`:

```python
@router.get("/something")
@require_admin                   # blocks non-admins, no current_user in body needed
def my_endpoint(db: Session = Depends(get_db)):
    ...

@router.post("/something")
@require_admin_or_editor
def create(current_user: User, payload: MySchema, db: Session = Depends(get_db)):
    # current_user injected by the decorator when declared with bare annotation
    ...
```

Available: `require_user`, `require_editor`, `require_admin`, `require_admin_or_editor`.

### Domain exceptions

Services raise domain exceptions; routers catch them and convert:

```python
# service
raise NotFoundError("Order", order_id)
raise BusinessError("Cannot ship a cancelled order.")

# router
try:
    return svc.do_something(...)
except NotFoundError as e:
    raise HTTPException(404, str(e))
except (BusinessError, ValidationError) as e:
    raise HTTPException(400, str(e))
```

### Migrations

- File naming: `YYYYMMDD_NN_short_description.py`
- Set `revision`, `down_revision` manually — do not rely on autogenerate.
- Always implement `downgrade()`.
- Run with `alembic upgrade head` from `fastapi-server/` with the venv active.

### Config

All env vars live in `app/core/config.py` as a Pydantic `Settings` class.
Never read `os.environ` directly elsewhere.

---

## Frontend conventions

### Standalone components

All components are standalone (no NgModules). Declare imports in the `@Component` decorator:

```typescript
@Component({
  standalone: true,
  imports: [CommonModule, FormsModule, TranslateModule, RouterModule, MyChildComponent],
  ...
})
```

### Services

- One service per backend domain (`shipping.service.ts`, `order.service.ts`, …).
- Admin-only services are prefixed `admin-` (`admin-orders.service.ts`).
- Use `HttpClient` directly; no wrapper layer.
- Define interfaces for all API payloads and responses in the service file.

### Translations

All user-facing strings go through `TranslateModule` (`| translate` pipe).
Translation files: `stibFront/public/assets/i18n/en.json` and `fr.json`.
Always add keys to **both** files when adding new UI text.

### Autocomplete / country picker

Use `app-autocomplete` with `CountryService.getAllOptions()` for any country input —
it returns options localised to the current UI language, so users can type in French,
Dutch, English, etc.

```typescript
this.countryOptions = this.countryService.getAllOptions();
```

```html
<app-autocomplete
  [options]="countryOptions"
  placeholder="Search country…"
  [(ngModel)]="selectedCode"
  (selectionChange)="onSelect($event)"
></app-autocomplete>
```

---

## Shipping / SendCloud

- Shipping options are managed in Admin → Shipping tab, not hardcoded.
- **`shipping_option_config`** table: stores only *enabled* option codes (presence = enabled).
- **`shipping_country`** table: ISO-2 codes of countries the store ships to.
- Public `/api/shipping/options` validates country against `shipping_country` and filters
  SendCloud results against `shipping_option_config`.
- Weight for SendCloud pricing: **0.5 kg per cart item**.
- No DB-stored shipping costs — prices come from SendCloud at checkout time.
- `SENDCLOUD_SANDBOX` env var does not exist; use the `sendcloud:letter` option code in
  the admin panel for testing.

---

## What NOT to do

- Do not add `SENDCLOUD_SANDBOX` or `SENDCLOUD_SHIPPING_OPTION_CODE` env vars — removed intentionally.
- Do not add a `ShippingRate` DB table — shipping costs are dynamic from SendCloud.
- Do not bypass the `require_admin` / `require_roles` decorators with manual JWT checks.
- Do not query the DB directly in a router — go through a service.
- Do not add `countries` column back to `shipping_option_config` — options are global.
- Do not create standalone `.md` documentation files for features — put knowledge here.
