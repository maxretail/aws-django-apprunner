---
name: SailArchive Migration Plan
overview: Migrate and adapt the time-collector codebase into sailarchive, bringing over GPX parsing, map visualization, data models, and user/sharing features while using Digital Ocean for deployment.
todos:
  - id: phase0-infra
    content: "Phase 0: Replace AWS CDK with Digital Ocean App Platform - copy .do/ config, update Dockerfile, remove cdk/"
    status: completed
  - id: phase1-auth
    content: "Phase 1: Set up user authentication - add django-registration-redux, create registration templates, configure auth URLs"
    status: completed
  - id: phase2-models
    content: "Phase 2: Create apps/tracks app with models (Vessel, Collection, Event, Recording metadata, VesselPermission) - NO TrackPoint table"
    status: completed
  - id: phase3-gpx
    content: "Phase 3: Async GPX pipeline with Django-Q2 - upload triggers async task, parse/simplify/upload to S3, poll for status"
    status: completed
  - id: phase4-maps
    content: "Phase 4: Map visualization - OpenLayers template, fetch zoom-appropriate JSON from S3, client-side rendering"
    status: completed
  - id: phase5-sharing
    content: "Phase 5: Implement sharing/permissions - VesselPermission workflow, visibility controls on recordings"
    status: completed
isProject: false
---

# SailArchive Migration Plan

> **Note:** Throughout this document, "S3" refers to **DigitalOcean Spaces**, which provides an S3-compatible API. We use boto3 and django-storages which work identically with both AWS S3 and DO Spaces.

## Current State

**sailarchive**: Fresh Django 4.2 template with API key auth, Docker/devcontainer setup, and AWS CDK deployment (to be replaced with Digital Ocean) - no models or business logic yet.

**time-collector**: Fully functional sailing race tracker with:

- Models: Series, Race, Boat, Result, TrackPoint, Session, UserBoatAssociation
- GPX parsing ([`apps/races/gpx_parser.py`](time-collector/apps/races/gpx_parser.py)) supporting RaceQs, Tacktracker, Strava, Garmin
- Map display using OpenLayers ([`apps/races/templates/races/race_map.html`](time-collector/apps/races/templates/races/race_map.html))
- User registration via django-registration-redux
- Boat claim/permission workflow

---

## Migration Strategy

### Phase 0: Infrastructure - Switch to Digital Ocean

Replace AWS CDK with Digital Ocean App Platform (already configured in time-collector):

- Remove `cdk/` directory (AWS-specific)
- Copy `.do/` directory from time-collector with `app.yaml` configuration
- Copy `DEPLOYMENT-DO.md` documentation
- Update `Dockerfile` for DO App Platform compatibility
- Configure environment variables:
  - `DO_SPACES_NAME`, `DO_SPACES_ENDPOINT`, `DO_SPACES_REGION` for media storage
  - Database connection via DO Managed PostgreSQL
  - SMTP via Brevo (or other provider)
- Update GitHub Actions workflow for DO deployment (replace `.github/workflows/deploy.yml`)

**Key DO config from time-collector** ([`.do/app.yaml`](time-collector/.do/app.yaml)):

- App Platform with `basic-xxs` instance (~$5/month dev)
- Managed PostgreSQL (~$15/month)
- DO Spaces for media files (vessel icons, etc.)
- Health check at `/health/`

### Phase 1: Foundation - Authentication and User Management

Replace API key auth with user account system:

- Add `django-registration-redux` to requirements
- Configure Django's built-in auth with registration workflow
- Create base templates ([`templates/base.html`](time-collector/templates/base.html), registration templates)
- Remove or make API key auth optional (keep for future API access)

### Phase 2: Core Data Models

Create new Django app `apps/tracks/` (broader than "races" for general sailing):

**Models (simplified from time-collector - NO TrackPoint table):**

- `Vessel` - boat/craft info (name, sail_number, model, icon, aliases)
- `Collection` - groups related recordings (like a regatta or trip)
- `Event` - specific event within a collection (race, leg, day)
- `Recording` - metadata only, track data lives on S3 (see below)
- `VesselPermission` - user-vessel associations for sharing

**Recording model (lightweight metadata):**

```python
class Recording(TimeStampedModel):
    vessel = ForeignKey(Vessel)
    event = ForeignKey(Event, null=True)  # Optional event association
    user = ForeignKey(User)               # Who uploaded
    
    # Time bounds
    start_time = DateTimeField()
    end_time = DateTimeField()
    
    # Spatial bounds (for map viewport calculations)
    bounding_box = JSONField()  # {"min_lat", "max_lat", "min_lon", "max_lon"}
    
    # S3 reference
    s3_prefix = CharField()  # e.g., "tracks/abc123/"
    
    # Stats
    point_count = IntegerField()
    distance_nm = DecimalField(null=True)  # Nautical miles
    
    # Access control
    visibility = CharField(choices=['private', 'shared', 'public'])
```

Key differences from time-collector:

- **No TrackPoint table** - all GPS data on S3
- Recording stores only metadata needed for queries/display
- Bounding box enables efficient "tracks in viewport" queries

### Phase 3: GPX Upload, Parsing, and S3 Storage (Async with Django-Q2)

**Async upload pipeline using Django-Q2:**

```
User uploads GPX
       ↓
Save temp file → Create Recording (status=processing) → Queue async task → Return immediately
                                                               ↓
                                            Django-Q2 worker picks up task
                                                               ↓
                                  Parse GPX → Extract metadata → Generate zoom levels → Upload to S3
                                                               ↓
                                            Update Recording (status=ready)
```

**Why Django-Q2:**

- Uses existing Postgres as task broker (no extra Redis service)
- Simple setup, lightweight dependency
- Built-in Django admin integration for task monitoring
- Retry and failure handling out of the box

**Recording status flow:**

- `processing` - task queued, GPX being processed
- `ready` - all zoom levels generated and on S3
- `failed` - processing error (stores error message)

**User experience:**

- Upload returns immediately with Recording ID and status=processing
- Frontend polls `GET /api/recordings/{id}/` until status=ready (or shows spinner)
- Once ready, map loads track data via signed S3 URLs

**Implementation:**

- Add `django-q2` to requirements, configure ORM broker in settings
- Create async task: `tasks.process_gpx_upload(recording_id, temp_file_path)`
- Adapt `GPXTrackParser` from time-collector for parsing
- Add track simplification using Douglas-Peucker algorithm (via `simplify` library)
- Generate multiple zoom levels in the async task:

**S3 file structure per recording:**

```
tracks/{recording_id}/
  raw.json       # Full resolution normalized JSON
  z6.json        # ~50 points (continental view)
  z10.json       # ~200 points (regional view)
  z14.json       # ~1000 points (local view)
  z18.json       # ~5000 points (detail view, near-full)
```

**JSON format (GeoJSON-compatible):**

```json
{
  "type": "Feature",
  "properties": {"recording_id": "abc123", "vessel": "Boat Name"},
  "geometry": {
    "type": "LineString",
    "coordinates": [[lon, lat, timestamp, speed], ...]
  }
}
```

### Phase 4: Map Visualization

**Authenticated S3 access via signed URLs:**

- S3 bucket is **private** (no public access)
- Client requests track through Django API (requires authentication)
- Django verifies auth + checks subscription/permissions
- Django generates **signed S3 URL** (time-limited, e.g., 15 min expiry)
- Client fetches track JSON from S3 using signed URL
```
Client --> Django API (auth check) --> Returns signed URL --> Client fetches from S3
```


**Benefits:**

- All access gated by authentication
- Easy to add subscription tier checks later
- Can log/track access for analytics
- S3 still serves the data (scalable, fast)

**Hybrid Frontend: Django Templates + React Map Component:**

Django templates handle:

- Login, registration, password reset
- Recording list/upload pages
- Vessel management, profile pages
- Simple forms and navigation

React components handle (complex interactivity):

- `<TrackMap />` - OpenLayers/MapLibre map with track rendering
- `<PlaybackControls />` - timeline, speed control, play/pause
- `<UploadProgress />` - real-time upload status with polling
- `<TrackLegend />` - boat selection, stats, visibility toggles

**React integration with Django (via WhiteNoise):**

- Vite builds React components to `static/frontend/` directory
- WhiteNoise serves static files (already in project, production-ready)
- Django template includes: `<div id="track-map" data-recording-id="{{ recording.id }}"></div>`
- React mounts to container, fetches data via authenticated API

**Build flow:**

```
npm run build (in frontend/)  →  static/frontend/main.js, main.css
                                        ↓
python manage.py collectstatic  →  staticfiles/  →  WhiteNoise serves with caching/compression
```

**Map features (ported from time-collector):**

- Speed-based track coloring (red/orange/green)
- Playback animation with timeline scrubbing
- Multi-track display and comparison
- Zoom-based track resolution (fetches appropriate S3 file)

**API endpoints (all authenticated):**

- `GET /api/recordings/` - list recordings user can access
- `GET /api/recordings/{id}/` - recording metadata
- `GET /api/recordings/{id}/track/?zoom=14` - returns signed S3 URL for zoom level
- `GET /api/recordings/in-bounds/?bbox=...` - find recordings in viewport

### Phase 5: Sharing and Access Control

Implement permission system based on `UserBoatAssociation`:

- VesselPermission model with statuses (pending, approved, rejected)
- Recording visibility levels (private, shared with specific users, public)
- Views for claiming vessels, managing permissions
- Admin approval workflow

**Future: Subscription integration (Phase 6 placeholder):**

- Add `Subscription` model or integrate with Stripe
- Access check in track API: `user.has_active_subscription()` or `recording.is_accessible_by(user)`
- Free tier: limited track views or own tracks only
- Paid tier: full access to shared/public tracks

---

## File Structure (New)

```
apps/
  core/           # Keep existing (health checks, base middleware)
  tracks/         # New app
    models.py     # Vessel, Collection, Event, Recording, VesselPermission (NO TrackPoint)
    tasks.py      # Django-Q2 async tasks (process_gpx_upload)
    gpx_parser.py # Parse GPX, extract metadata
    track_processor.py  # Simplification, zoom level generation
    storage.py    # DO Spaces helper functions (upload, signed URLs)
    views.py      # Page views (upload, lists, etc.)
    api.py        # DRF API (recordings, vessels, signed URLs)
    forms.py      # Upload forms, vessel edit forms
    admin.py      # Model admin + Q task monitoring
    urls.py
    templates/tracks/
      map.html          # Contains React mount point
      upload.html       # Upload form + React progress component
      vessel_detail.html
      recording_list.html
      ...
templates/
  base.html
  registration/   # Login, register, password reset

frontend/         # React app (Vite)
  src/
    components/
      TrackMap.tsx        # OpenLayers/MapLibre map component
      PlaybackControls.tsx
      UploadProgress.tsx
      TrackLegend.tsx
    api/
      client.ts           # API client with auth (uses Django session)
    hooks/
      useRecording.ts     # Data fetching hooks
    main.tsx              # Mount points for each component
  vite.config.ts          # Build outputs to ../static/frontend/
  package.json

static/           # Django static files (served by WhiteNoise)
  frontend/       # Vite build output (gitignored, built on deploy)
  css/            # Django template styles
```

**Django-Q2 configuration (in settings):**

```python
Q_CLUSTER = {
    'name': 'sailarchive',
    'workers': 2,
    'timeout': 300,  # 5 min max per task
    'retry': 360,
    'orm': 'default',  # Use Postgres as broker
}
```

---

## Dependencies to Add

**Python (requirements.txt):**

```
gpxpy>=1.6.2              # GPX parsing
simplification>=0.7.0     # Douglas-Peucker track simplification (Rust-based, fast)
django-q2>=1.6.0          # Async task queue using Postgres as broker
django-extensions>=3.2.0
django-registration-redux>=2.11
djangorestframework>=3.14.0  # API endpoints
Pillow>=10.0.0            # Vessel icons
django-storages>=1.14.0   # DO Spaces for media files (S3-compatible)
boto3>=1.28.0             # Required by django-storages for DO Spaces
# whitenoise already in project - serves static files including React build
```

**JavaScript (frontend/package.json):**

```json
{
  "dependencies": {
    "react": "^18.x",
    "react-dom": "^18.x",
    "ol": "^9.x",           // OpenLayers for maps
    "@tanstack/react-query": "^5.x"  // Data fetching
  },
  "devDependencies": {
    "vite": "^5.x",
    "typescript": "^5.x",
    "@types/react": "^18.x"
  }
}
```

---

## Deployment Architecture (Digital Ocean)

```
                                   +---------------------+
                                   | DO Spaces           |
                                   | - Track JSON files  |
                                   | - Vessel icons      |
                                   +---------------------+
                                          ↑ upload    ↓ signed URL
+------------------+     +---------------------+     +------------------+
|  DO App Platform | --> | DO Managed Postgres |     |     Browser      |
|  - Web service   |     | - Recording metadata|     | (OpenLayers map) |
|  - Q worker      |     | - Django-Q2 tasks   |     +------------------+
|  (same container)|     | - Vessel, User, etc |
+------------------+     +---------------------+
        ↑
+------------------+
| GitHub Actions   |
| (CI/CD deploy)   |
+------------------+
```

**Deployment note:** Run Q worker in same container using supervisor or as background process:

```bash
# In Dockerfile or entrypoint
python manage.py qcluster &   # Q worker in background
gunicorn config.wsgi:application  # Web server in foreground
```

**Data flow:**

1. User uploads GPX → Django saves temp file, creates Recording (status=processing), queues task
2. Django-Q2 worker picks up task → parses GPX → generates zoom levels → uploads to S3
3. Worker updates Recording (status=ready, bounding_box, s3_prefix)
4. Frontend polls until ready, then requests signed S3 URL
5. Client fetches track JSON from S3 using signed URL (15 min expiry)

**Estimated costs**: ~$20/month (dev) or ~$42/month (production)

- DO Spaces: $5/month for 250GB + $0.01/GB transfer

---

## Key Files to Reference from time-collector

**Infrastructure:**

- DO App config: [`.do/app.yaml`](time-collector/.do/app.yaml)
- DO deployment docs: [`DEPLOYMENT-DO.md`](time-collector/DEPLOYMENT-DO.md)
- Dockerfile: [`Dockerfile`](time-collector/Dockerfile)

**Application:**

- Models: [`apps/races/models.py`](time-collector/apps/races/models.py) (504 lines)
- GPX Parser: [`apps/races/gpx_parser.py`](time-collector/apps/races/gpx_parser.py)
- Map Template: [`apps/races/templates/races/race_map.html`](time-collector/apps/races/templates/races/race_map.html)
- Base Template: [`templates/base.html`](time-collector/templates/base.html)
- Registration Templates: [`templates/registration/`](time-collector/templates/registration/)