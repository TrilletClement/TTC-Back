# CLAUDE.md — TTC-Back

Working guidelines for AI assistants in this repo.
Edit freely — both humans and AI should keep this up to date.

> Ce repo est le **backend seul**. Le frontend Angular vit dans le repo frère
> `TTC-Front` (ancien monorepo `server-STIB`, archivé). Les sections ci-dessous
> qui parlent de pages/composants décrivent le **contrat côté API** ; le détail
> côté Angular est dans le `CLAUDE.md` de TTC-Front.
> Côte à côte en local : `~/projets/TTC-Back` et `~/projets/TTC-Front`.

---

## Project layout

```
TTC-Back/                  (racine = ancien fastapi-server/)
├── app/
│   ├── core/              Config, JWT, auth decorators, mail
│   ├── domain/            Pure exceptions (NotFoundError, BusinessError, ValidationError)
│   ├── orm_models/        SQLAlchemy table definitions
│   ├── repositories/      DB queries — one file per aggregate, no business logic
│   ├── schemas/           Pydantic request/response models
│   ├── services/          Business logic — called by routers, use repos + ORM
│   ├── routers/           FastAPI route handlers — thin, delegate to services
│   └── routines/          APScheduler background jobs (scheduler, GTFS imports)
├── migrations/versions/   Alembic migrations (named YYYYMMDD_NN_description.py)
├── tests/                 pytest (ORM en mémoire)
├── Dockerfile             Image `stib-api:latest` (api + scheduler)
├── docker-compose.yml     Stack de prod : db, api, scheduler, frontend (image seule)
├── deploy.sh              Build + déploiement api/scheduler/db/migrations
├── apache/ nginx/ ca/     Reverse proxy, CA des devices
├── ecosystem*.config.js   PM2 (prod / dev local)
└── doc/ scripts/          Docs, backup DB
```

**Déploiement** : `./deploy.sh` ne construit/envoie que l'image API.
L'image frontend (`server-stib-frontend:latest`) est livrée par le `deploy.sh`
de TTC-Front ; `docker-compose.yml` (ici) ne fait que la référencer. Les deux
repos partagent `/root/docker-compose.yml` sur le serveur Docker : ce fichier
est la propriété de TTC-Back.

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
- Run with `alembic upgrade head` from the repo root with the venv active.

### Config

All env vars live in `app/core/config.py` as a Pydantic `Settings` class.
Never read `os.environ` directly elsewhere.

---
## Frontend conventions

Voir `TTC-Front/CLAUDE.md` (standalone components, `models/`, services,
traductions, autocomplete pays).

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

## Newsletter — added 2026-09-16

- Single table `newsletter_subscriber` (email, nullable `user_id`, `source`,
  `unsubscribe_token`, `subscribed_at`, `unsubscribed_at`) covers **both**
  registered users and anonymous devblog visitors — no separate opt-in flag on
  `User`. `NewsletterService.subscribe(email, user_id, source)` is idempotent:
  re-subscribing an unsubscribed email just clears `unsubscribed_at` instead of
  erroring on the unique email constraint.
- Sign-up entry points: the register form checkbox (`newsletter_opt_in` on
  `RegisterRequest` → `AuthService.register` calls `NewsletterService`
  directly, source `"register"`), the devblog listing page, and the bottom of
  every article (`app-newsletter-signup`, source `"blog"`). Hidden on blog
  preview mode.
- Unsubscribe is public, token-based (`GET /api/newsletter/unsubscribe?token=`),
  soft (`unsubscribed_at` set, row kept) — link is auto-appended to every
  campaign email by `send_newsletter_email` in `mail.py`.
- Admin campaign send (`POST /api/admin/newsletter/send`, `require_admin` —
  not editor, since it emails the whole list) is fire-and-forget via FastAPI
  `BackgroundTasks`, sequential per-recipient SMTP send. No queue, no retry,
  no scheduling — fine for a hobby-project list size; revisit if the list
  grows enough that plain SMTP stops being viable (deliverability, send time).

## Éditeur d'articles par blocs — added 2026-09-17

- Un article de blog a deux représentations : `blog_post.blocks` (JSONB, liste
  de `{id, kind, data}` — **source de vérité** de l'éditeur visuel) et
  `blog_post.content` (HTML **rendu**, servi tel quel par `[slug].page.ts`,
  utilisé pour les extraits/temps de lecture/SEO). `blocks = NULL` signifie
  article HTML libre (articles d'avant l'éditeur, embeds d'artifact) :
  `blog-editor` s'ouvre alors en mode HTML au lieu d'écraser le contenu.
- **Un seul renderer**, `services/article-render.service.ts` (TS). Il produit
  l'aperçu live de l'éditeur ET le HTML persistué dans `content`. Ne pas
  écrire de renderer Python miroir : le backend stocke et assainit, il ne rend
  rien. Ajouter un bloc = un `kind` dans `models/article-block.ts`, une
  fonction dans le renderer, un `@case` dans l'inspecteur.
- Le rendu est **tout en styles inline** (aucune classe, aucun `<style>`) pour
  être identique dans l'aperçu, sur la page publique et dans un export. nh3
  autorise donc `style` sur les balises structurelles (`_STYLABLE` dans
  `blogService.py`) — écriture réservée aux rôles editor/admin, et
  `<style>`/`<link>`/`<script>` restent interdits. **Ne pas retirer `style` de
  l'allowlist** : tous les articles publiés perdraient leur mise en page.
- Une seule couleur d'accent par article (`blog_post.accent_color`, `#RRGGBB`),
  injectée par le renderer partout où la maquette portait du vert. Le
  sélecteur (`article-color-picker`, fork de `led-color-picker` + HEX +
  curseurs RGB) avertit sous 4.5:1 de contraste blanc/accent.
- Les numéros de section sont calculés par position dans la liste de blocs —
  jamais saisis. Réordonner renumérote.
- Les images des blocs passent par `POST /api/blog/covers` (même stockage
  `static/blog-embeds`, 8 Mo, JPG/PNG/WebP/GIF). Le recadrage est un
  `aspect-ratio` + `object-fit`, non destructif. Le nettoyage des fichiers
  orphelins fonctionne sans changement : `_referenced_filenames` scanne les
  `src=` du `content` rendu.
- `PUT /posts/{slug}` distingue « blocs non fournis » de « blocs effacés » via
  `blocks_provided="blocks" in payload.model_fields_set`. Ne pas remplacer ce
  test par une vérification de valeur : `PATCH /publish` ne parle pas de
  blocs et effacerait le document.

### What NOT to do (ajouts)

- Ne pas ajouter de renderer de blocs côté Python — un seul renderer, en TS.
- Ne pas retirer `style` de l'allowlist nh3 (voir ci-dessus).
- Ne pas stocker de largeur en pixels dans un bloc : les articles doivent
  reflow sur mobile.

## Pages de l'app Android (`/app`) — added 2026-09-26

- L'app Android (repo `TTC-App`, fork d'esp-idf-provisioning-android) affiche
  le site dans une WebView, mais **uniquement** les routes `/app/**`. Tout
  autre lien s'ouvre dans le navigateur du téléphone.
- **Le login est un écran natif Android** (`LoginActivity`, écran de
  lancement) qui appelle `POST /api/token` comme le site. L'app dépose le
  jeton dans le localStorage (`access_token`) avant d'ouvrir `/app`. Si le site
  navigue vers `/login` (jeton expiré ou refusé), l'app efface le jeton et
  réaffiche son écran natif. Inscription et mot de passe oublié s'ouvrent
  dans le navigateur. Garder `/api/token` et le message « non confirmé »
  (`AuthService.login`) stables : l'app les lit.
- `/app` (liste des boards) et `/app/board/:id` (lignes + appareil lié) ont
  leur propre header compact (`app-mobile-header`) ; `app.ts` masque
  navbar/footer pour tout le préfixe `/app`. Ne pas y ajouter la
  visualisation, l'aperçu, l'export ou le panier : ils restent sur le site.
- Détection : l'app ajoute `TTCApp/<versionCode>` au user agent
  (`NativeAppService.isNativeApp()`). Dans l'app, `/` redirige vers `/app`
  (`nativeAppHomeRedirect`).
- Pont JS : `window.EspProv.startProvisioning()` lance l'écran natif de scan
  du QR code (Wi-Fi BLE). Au retour, l'app appelle
  `window.onEspProvEvent({type: 'provisioningClosed'})`, et les pages
  rechargent l'état des appareils. Le succès se lit côté serveur
  (`last_connected`), pas dans l'app. L'app n'accepte ces appels que depuis
  `/app/**`. `window.EspProv.logout()` termine la session de l'app (bouton
  « Se déconnecter » de `/app`).
- Aucune donnée n'est envoyée à l'ESP pendant le provisioning : le
  propriétaire vient déjà de l'association MAC ↔ commande dans l'admin.
- Pas de connexion Google dans l'app (Google bloque l'OAuth en WebView).
- Lignes favorites (jusqu'à 8) : étoile sur une ligne de `/app/board/:id`
  (`FavoriteLineService`, localStorage `ttc_favorite_lines`, migre l'ancien
  `ttc_favorite_line`). Une carte compacte par favori sur l'accueil `/app`
  (rendu backend + nombre de véhicules via `X-Leds-On`). La liste est envoyée
  à l'app par `EspProv.setFavoriteLines(json)` ; chaque **widget Android**
  affiche sa propre ligne (choisie à l'ajout : `pinWidget(kind, boardId,
  stripId)` depuis l'app, ou écran de choix natif depuis le launcher) et relit
  `…/render.png` avec le jeton de l'app (15 min via WorkManager + bouton).
  Épingler une ligne propose le widget dans une notification (`app-mobile-toast`),
  pas de carte permanente sur l'accueil.
- `/app/profile` : email, date d'inscription, langue, widgets, aide, liens
  légaux (ouverts dans le navigateur), déconnexion, **suppression du compte**
  (`POST /api/user/delete-account`, exigence Google Play).
- `/app/register` (hors garde d'auth, dans `PUBLIC_ROUTES`) : création de
  compte dans l'app, mêmes règles et Turnstile que `/register`. L'app l'ouvre
  en mode inscription (`WebAppActivity.registrationIntent`) : seul
  `EspProv.registrationDone(email)` y est accepté.
- Assistant d'ajout de ligne : `LedStripModalComponent.compact` (mis par
  `/app`) remplace la colonne d'étapes par une barre de progression et fixe
  les boutons en bas ; `app-autocomplete [sheet]` ouvre un sélecteur plein
  écran au lieu du menu déroulant. Le site garde l'affichage desktop.
- Pas de bandeau Klaro dans l'app (`index.html` : `klaroConfig.noAutoLoad`
  si user agent `TTCApp/`). Le seul service optionnel (GTM) n'est injecté
  qu'après consentement Klaro, donc il reste désactivé.
- Test sans déployer : `ng serve --host 0.0.0.0` (proxy `/api` vers la prod
  si pas d'API locale), `adb reverse tcp:4200 tcp:4200`, puis
  `./gradlew installDebug -PwebviewUrl=http://localhost:4200/` dans TTC-App.

## Rendu unique d'une ligne (strip) — added 2026-09-30

- **Un seul générateur** : `board_svg_service._build_strip` (celui de
  l'export physique). `build_strip_svg(board, strip_id, lit)` le réutilise tel
  quel pour une seule bande, recadrée ; `lit` (led id → couleur) allume les
  LED pour les vues en direct. `lit=None` = rendu d'impression inchangé.
- Servi par `StripRenderService` (droits : propriétaire ou admin, sinon 404 ;
  état des LED = mêmes règles que `GET /boards/{id}/status`) :
  - `GET /api/boards/{id}/strips/{sid}/render.svg?live=` → pages `/app`
    (`app-strip-render`, affiché en `<img>` via object URL, jamais injecté
    en HTML) ;
  - `GET …/render.png?live=&width=200..1600` → widgets Android (cairosvg,
    cache LRU par hash du SVG).
  En-tête `X-Leds-On` (nombre de LED allumées), CSP stricte sur le SVG,
  `Cache-Control: private, no-store` en direct, rate limit 120/60 par minute.
- **Ne pas redessiner une ligne ailleurs** (TS, Kotlin…) : consommer ces
  routes. Exception connue : l'éditeur interactif du site
  (`led-visualization`) reste un rendu TS séparé (édition des libellés).
- Police : `app/assets/fonts/brusseline-bold.{woff2,ttf}`.
  Le woff2 est embarqué dans le SVG ; le ttf (famille renommée
  "Brusseline"/Bold pour fontconfig) est installé par le Dockerfile pour
  cairosvg, qui ignore `@font-face`. Avant, la police était lue dans
  `doc/`, hors du contexte Docker : l'export de prod retombait sur Arial.
- Tests : `PYTHONPATH=. venv/bin/python -m pytest tests`
  (`tests/test_strip_render.py`, ORM en mémoire, pas de base).

## En-têtes de sécurité — added 2026-09-30

HSTS, `nosniff`, `Referrer-Policy`, `X-Frame-Options: SAMEORIGIN`,
`Permissions-Policy` dans `apache/transport-le-ssl.conf` (à redéployer à la
main sur 192.168.14.150) et dans `TTC-Front/nginx.conf`. Pas encore de CSP
sur le site : à introduire d'abord en `Content-Security-Policy-Report-Only`
(Bootstrap CDN, Turnstile, Stripe, GTM, Google Fonts).

## Suppression de compte — added 2026-09-30

`POST /api/user/delete-account` (`AuthService.delete_account`), confirmation
par l'email + le mot de passe (sauf comptes Google). La ligne `user` ne peut
pas être supprimée (commandes gardées pour la comptabilité, tickets, articles
la référencent) : on **anonymise** — email `deleted-<id>-<hex>@deleted.invalid`,
mot de passe / google_id / jetons effacés, `active=False`, nouveau
`fs_uniquifier` — ce qui invalide tout JWT existant (lookup par email +
contrôle `active`). Boards archivées, abonnement newsletter supprimé.
Tests : `tests/test_delete_account.py`.

## What NOT to do

- Do not add `SENDCLOUD_SANDBOX` or `SENDCLOUD_SHIPPING_OPTION_CODE` env vars — removed intentionally.
- Do not add a `ShippingRate` DB table — shipping costs are dynamic from SendCloud.
- Do not bypass the `require_admin` / `require_roles` decorators with manual JWT checks.
- Do not query the DB directly in a router — go through a service.
- Do not add `countries` column back to `shipping_option_config` — options are global.
- Do not create standalone `.md` documentation files for features — put knowledge here.
- Do not add `board_id`, `svg_content`, or `esp_device_id` back to the `orders` table — those fields live on `order_item`.
- Do not create multiple `Order` rows for the same cart session — one `Order` + N `OrderItem`s.
