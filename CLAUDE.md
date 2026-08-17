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

### Interfaces and models

**Before creating any interface, check `models/` first.** The canonical model files are:

| File | What lives there |
|------|-----------------|
| `models/order.ts` | `Order`, `OrderItem`, `AdminOrder`, `AdminOrderItem`, `OrderAddress`, `OrderStatus`, `OrderPatch`, `DeviceSelectOption`, `CreateOrderPayload` |
| `models/shipping.ts` | `ShippingOption`, `AvailableShippingOption` |
| `models/device-admin.ts` | `DeviceAdminOut`, `DeviceBoardOut`, `DeviceFirmwareOut`, `DeviceHardwareOut`, `DeviceOrderOut`, `BoardListOut` |
| `models/ota.ts` | `FirmwarePackage`, `HardwareConfig`, `DeviceOverride`, `OtaData`, all settings types |
| `models/admin-user.ts` | `RoleInfo`, `UserAdminOut` |
| `models/autocomplete.ts` | `AutocompleteOption` |
| `models/led.ts` | `Led`, `LedTripStop` (not `TripStop` — that's the GTFS model in `models/tripStop.ts`) |

**Layering rule — dependency direction:**
```
models/ → services/ → Components/
```
- Services import from `models/`, never from `Components/`.
- Components import from `models/` directly (preferred) or from services (acceptable).
- **Never** import from a component file in a service.

**Where to put a new interface:**
- Used by more than one file → `models/`
- Only used inside one service and its direct component → can stay in the service file
- Local UI view-model (e.g. a draft row, a preview state) → stays in the component

**Re-exporting from services for backward compat:**
When moving a type out of a service to `models/`, keep a re-export shim in the service so existing callers don't break. Use `export type` (required by `isolatedModules`):
```typescript
import { MyType } from '../models/my-model';
export type { MyType };  // NOT export { MyType } — isolatedModules requires export type for interfaces
```

### Services

- One service per backend domain (`shipping.service.ts`, `order.service.ts`, …).
- Admin-only services are prefixed `admin-` (`admin-orders.service.ts`).
- Use `HttpClient` directly; no wrapper layer.
- Do not define interfaces that are already in `models/` — import them instead.

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

## Order model

One cart session = one `Order` + one or more `OrderItem`s.

| Table | Fields |
|-------|--------|
| `orders` | `id`, `cart_ref`, `user_id`, `status`, `amount_cents` (total boards), `shipping_cost_cents`, `currency`, `created_at`, `paid_at`, `stripe_session_id`, `payment_intent_id`, `price_version_id`, `shipping_details_id`, `billing_details_id`, `shipping_option_code`, `sendcloud_parcel_id`, `tracking_number`, `tracking_url`, `label_url` |
| `order_item` | `id`, `order_id` FK (CASCADE), `board_id`, `svg_content`, `amount_cents` (per-board), `esp_device_id` |

- **Device association** is per item: `POST /api/admin/orders/items/{item_id}/associate-device`
- **Shipping** is per order (one SendCloud parcel per cart); weight = `len(items) * 0.5 kg`
- `canShip` requires `status === 'processing'` AND no existing `sendcloud_parcel_id`
- `status → 'processing'` when the first item gets a device linked

## LED realtime semantics

- A LED lights when `vehicle_incoming` (STIB JSON positions, poll 20 s) OR an active
  interval exists in the `active_incoming_intervals` matview (window = prev-stop
  departure → this-stop arrival, RT-corrected when the trip is in the GTFS-RT feed).
- The matview is **service-day aware**: it covers today AND yesterday's cross-midnight
  trips (GTFS times > 24:00), each with its own midnight epoch; RT overrides join on
  the trip's own `start_date`. All GTFS dates use Europe/Brussels, never the server
  clock. RT override rows are kept for today + yesterday.
- The matview is refreshed by a **dedicated scheduler job every 20 s** (not by the
  per-agency RT cycles). Steady-state refresh ≈ 1 s; if you change the view, keep the
  `MATERIALIZED` CTEs and the `led_trips` pre-filter or refresh time explodes 10×.
- `is_realtime` is per **trip**: true if the trip has a valid RT prediction AND is
  still present in its agency's most recent feed (within 120 s of the agency's max
  `feed_timestamp` — relative, so a polling gap on our side doesn't flip everything).
  STIB never writes to `realtime_stop_time_override`, so STIB interval rows are
  always `is_realtime=false` — STIB shows green only via `vehicle_incoming`.
- `led_strip.rt_only` (opt-in, per strip, Board → ⚙ → "Temps réel uniquement"):
  LED lights **only** on confirmed realtime; theoretical schedule intervals stay dark.
  Applied in `BoardService._build_led_data`, so the ESP32 strip follows automatically.
- RT feed coverage is a data reality, not a bug: TEC covers ~90 % of running trips
  globally but far less on some lines; the Liège tram T1 has **no** RT at all.
  De Lijn RT only matches if its static import is fresh (trip_ids rotate).
- Delay-based feeds (TEC): timestamps are computed from schedule + delay after upsert;
  delays < −300 s are treated as bad data (fall back to static window).
- **Delay propagation** (GTFS-RT rule): TEC only predicts a horizon around the vehicle
  and marks later stops NO_DATA. For stops without their own prediction, the matview
  shifts the static window by the last specified delay (`eff` LATERAL) — otherwise a
  late bus traverses downstream stops with windows already in the past (LED dark).

## Branching lines (trip variants) — added 2026-08-17

Some lines have several **branches** sharing a common trunk but ending at different
termini with the same GTFS `direction_id` (canonical case: TEC tram T1 Liège —
trunk from Sclessin Standard, then Coronmeuse OR Liège Expo). How it works:

- **Canonical trips**: GTFS import dedupes raw trips by signature
  `(line_id, direction, ordered stop list)` → one `Trip` + `TripStop` rows per
  distinct pattern. A branching direction therefore has **several** canonical
  Trips. Only one wins `line.best_trip_{0,1}_id` (score = stop_count × trip_count);
  the others survive in DB but used to be unreachable from any UI/API path.
- **Variant listing**: `GET /lines/{id}/stops` now also returns
  `variants_by_direction` (`LineService.get_line_trip_variants`). Variants are
  **grouped by terminus** (`terminus_stop_id`) — technical signature duplicates
  (skipped stop, different first stop) collapse into one entry, represented by
  the **longest** pattern for that terminus (not the score formula — a frequent
  short-turn must not shadow the full pattern and hide trunk stops).
  `BRANCH_MIN_STOP_RATIO = 0.5`: a candidate terminus with < 50 % of the
  direction's longest pattern is a short-turn/depot fragment, not a branch —
  dropped. Non-branching lines end up with length-1 lists → the frontend shows
  no branch UI at all (`led-strip-modal`, step 3, `branchOptions0/1.length > 1`).
- **Per-strip override**: `led_strip.trip_0_id` / `trip_1_id` (nullable, FK →
  `trip.id`, `ondelete="SET NULL"`). NULL = follow the line's best trip (all
  pre-existing strips, all normal lines). Set = the wizard's branch choice; used
  by `GET /lines/{id}/stops?trip_0_id=&trip_1_id=` (stop picker) and
  `LedStripService._get_trips_by_direction` (create/update/preview). Both
  validate the trip belongs to the right line + direction (400 otherwise).
  `SET NULL` matters: gtfs_import's orphan cleanup bulk-DELETEs trips (bypasses
  ORM), so the DB FK is what makes a stale strip fall back to best-trip
  gracefully instead of erroring.
- **Shared trunk lights for any branch**: at LED creation
  (`LedStripService._create_leds`), each LED links not only its own TripStop but
  also every **sibling** TripStop (same line, same direction, same physical stop)
  from the line's other canonical trips
  (`LedStripRepository.get_sibling_trip_stops`, one bulk query). Trunk stops →
  linked to every branch's trip → a vehicle on either branch lights them.
  Post-divergence stops have no sibling on the other branch → branch-specific
  automatically. The realtime read side needed **zero changes**: the matview has
  no per-LED trip assumption, `vehicle_incoming` is per trip_stop, and
  `BoardService` computes `led_is_on = any(...)` over the LED's trip_stops.
  Primary TripStop is always appended **first** — `board_svg_service` reads
  `trip_stops[0]` for label fallback.
- **Reimport link rebuild**: `_rebuild_trip_stop_led_links` (gtfs_import) now
  remaps broken led↔trip_stop links by `(stop, line of the strip, direction from
  led.type)` → **all** matching trip_stops. Previously it picked the first
  trip_stop matching the stop alone — which collapsed trunk multi-links to a
  single link on every reimport AND could remap onto a different line serving
  the same physical stop.
- Old strips saved before this feature keep single links until re-saved via the
  wizard or until the next full GTFS reimport (whose rebuild now multi-links).
- Known follow-on (not done): the geolocation "use my location" shortcut
  (`find_nearest_stop_with_lines`) still only reads best trips — no branch
  awareness.

## What NOT to do

- Do not add `SENDCLOUD_SANDBOX` or `SENDCLOUD_SHIPPING_OPTION_CODE` env vars — removed intentionally.
- Do not add a `ShippingRate` DB table — shipping costs are dynamic from SendCloud.
- Do not bypass the `require_admin` / `require_roles` decorators with manual JWT checks.
- Do not query the DB directly in a router — go through a service.
- Do not add `countries` column back to `shipping_option_config` — options are global.
- Do not create standalone `.md` documentation files for features — put knowledge here.
- Do not add `board_id`, `svg_content`, or `esp_device_id` back to the `orders` table — those fields live on `order_item`.
- Do not create multiple `Order` rows for the same cart session — one `Order` + N `OrderItem`s.
