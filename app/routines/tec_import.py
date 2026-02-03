#!/usr/bin/env python3
"""
TEC GTFS Importer - Optimized version
Key improvements:
- Batch operations with larger chunks
- Reduced database round-trips
- Memory-efficient CSV processing
- Better indexing strategy
- Parallel processing where possible
"""

import csv
import time
import zipfile
import requests
import hashlib
import os
import sys
from io import BytesIO, TextIOWrapper
from typing import Iterable, Dict, Set, List
from collections import defaultdict
from google.transit import gtfs_realtime_pb2

# Adjust path to find shared modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.orm_models.db import get_db
from app.orm_models.gtfs import Agency, GTFSTrip, Line, Stop, SubAgency, Trip, TripStop
from sqlalchemy import text
import sqlalchemy as sa

# =============================================================================
# CONFIGURATION
# =============================================================================
GTFS_ZIP_URL = "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip"
TEC_API_KEY = os.environ.get("TEC_API_KEY", "36497DD5F3AD4262B24981633E73EF33")
REALTIME_URL = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"
AGENCY_NAME = "TEC"

# Batch sizes for bulk operations
BATCH_SIZE = 5000
TRIP_BATCH_SIZE = 1000

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; Python requests)",
}

# =============================================================================
# UTILITIES
# =============================================================================
def build_signature(line_id: int, direction: int, stop_ids: List[str]) -> str:
    """Build unique signature for a trip pattern"""
    payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()

def chunked(iterable, size):
    """Yield successive chunks from iterable"""
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk

# =============================================================================
# GTFS DOWNLOAD
# =============================================================================
def download_gtfs_zip(max_retries=3) -> bool:
    """Download TEC GTFS ZIP file with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"Downloading TEC GTFS (attempt {attempt + 1}/{max_retries})...")
            response = requests.get(GTFS_ZIP_URL, headers=headers, timeout=120, stream=True)
            
            if response.status_code == 200:
                with open("tec_gtfs.zip", "wb") as f:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=65536):  # 64KB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                print(f"\r  Progress: {progress:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end='')
                print(f"\nDownloaded successfully ({downloaded / 1024 / 1024:.1f} MB)")
                return True
            else:
                print(f"HTTP {response.status_code}")
        except Exception as e:
            print(f"Download failed: {e}")
            if attempt < max_retries - 1:
                print("  Retrying in 2s...")
                time.sleep(2)
    return False

# =============================================================================
# OPTIMIZED GTFS IMPORTER
# =============================================================================
class TECGtfsImporter:
    def __init__(self):
        self.agency_name = AGENCY_NAME
    
    def ensure_agency(self, session):
        """Ensure TEC agency exists in database"""
        agency = session.query(Agency).filter_by(name=self.agency_name).first()
        if not agency:
            print(f"  Creating agency: {self.agency_name}")
            agency = Agency(name=self.agency_name, country="Belgium")
            session.add(agency)
            session.flush()
        return agency

    def import_agency(self, agency_reader):
        """Import agency and sub-agencies"""
        print("\n[1/4] Importing agencies...")
        session = next(get_db())
        try:
            self.ensure_agency(session)
            
            # Load all existing sub-agencies at once
            existing = {
                sa.id: sa 
                for sa in session.query(SubAgency).filter_by(agency_name=self.agency_name)
            }
            
            to_add = []
            updated = 0
            
            for row in agency_reader:
                sub_id = row.get("agency_id")
                sub_name = row.get("agency_name")
                if not sub_id or not sub_name:
                    continue
                
                if sub_id in existing:
                    if existing[sub_id].name != sub_name:
                        existing[sub_id].name = sub_name
                        updated += 1
                else:
                    to_add.append(SubAgency(
                        id=sub_id, 
                        name=sub_name, 
                        agency_name=self.agency_name
                    ))
            
            if to_add:
                session.bulk_save_objects(to_add)
            
            session.commit()
            print(f"Added {len(to_add)}, updated {updated}")
        finally:
            session.close()


    def import_routes(self, routes_reader):
        """Import routes/lines with bulk operations"""
        print("\n[2/4] Importing routes...")
        session = next(get_db())
        try:
            self.ensure_agency(session)
            
            # Load existing lines efficiently
            existing_lines = {
                l.route_id: l
                for l in session.query(Line).filter_by(agency_name=self.agency_name)
            }
            
            # Track unique combinations to avoid duplicates
            seen_combos = {
                (l.short_name, l.long_name)
                for l in existing_lines.values()
            }
            
            to_add = []
            updated_count = 0
            skipped = 0
            
            for row in routes_reader:
                route_id = row["route_id"]
                short_name = row.get("route_short_name")
                long_name = row.get("route_long_name")
                route_type = row.get("route_type")
                subagency_id = row.get("agency_id")
                
                if not short_name:
                    skipped += 1
                    continue
                
                combo = (short_name, long_name)
                
                if route_id in existing_lines:
                    # Update existing
                    line = existing_lines[route_id]
                    changed = False
                    if line.short_name != short_name:
                        line.short_name = short_name
                        changed = True
                    if line.long_name != long_name:
                        line.long_name = long_name
                        changed = True
                    if line.route_type != route_type:
                        line.route_type = route_type
                        changed = True
                    if line.subagency_id != subagency_id:
                        line.subagency_id = subagency_id
                        changed = True
                    if changed:
                        updated_count += 1
                    seen_combos.add(combo)
                elif combo in seen_combos:
                    skipped += 1
                else:
                    to_add.append(Line(
                        route_id=route_id,
                        short_name=short_name,
                        long_name=long_name,
                        route_type=route_type,
                        agency_name=self.agency_name,
                        subagency_id=subagency_id
                    ))
                    seen_combos.add(combo)
            
            if to_add:
                session.bulk_save_objects(to_add)
            
            session.commit()
            print(f"Added {len(to_add)}, updated {updated_count}, skipped {skipped}")
        finally:
            session.close()


    def import_stops(self, stops_reader):
        """Import stops with bulk operations"""
        print("\n[3/4] Importing stops...")
        session = next(get_db())
        try:
            self.ensure_agency(session)
            
            # Load all existing stops at once
            existing = {
                s.stop_id: s
                for s in session.query(Stop).filter_by(agency_name=self.agency_name)
            }
            
            to_add = []
            updated = 0
            
            for row in stops_reader:
                stop_id = row["stop_id"]
                stop_name = row["stop_name"]
                
                if stop_id in existing:
                    if existing[stop_id].name != stop_name:
                        existing[stop_id].name = stop_name
                        updated += 1
                else:
                    to_add.append(Stop(
                        stop_id=stop_id,
                        name=stop_name,
                        agency_name=self.agency_name
                    ))
            
            if to_add:
                session.bulk_save_objects(to_add)
            
            session.commit()
            print(f"Added {len(to_add)}, updated {updated}")
        finally:
            session.close()

    def import_trips(self, trips_reader, stop_times_reader):
        """Optimized trip import with minimal DB queries"""
        print("\n[4/4] Importing trips...")
        tic = time.time()
        
        # PHASE 1: Load data from CSV (memory-efficient streaming)
        print("Loading GTFS data...")
        trip_info = {}
        trips_count = 0
        
        for row in trips_reader:
            trip_id = row["trip_id"]
            trip_info[trip_id] = {
                "route_id": row["route_id"],
                "direction": int(row.get("direction_id", 0)),
                "stops": []
            }
            trips_count += 1
            if trips_count % 10000 == 0:
                print(f"\r    Loaded {trips_count:,} trips...", end='')
        
        print(f"\r Loaded {trips_count:,} trips")
        
        # Load stop_times
        stops_count = 0
        for row in stop_times_reader:
            trip_id = row["trip_id"]
            if trip_id in trip_info:
                trip_info[trip_id]["stops"].append({
                    "stop_id": row["stop_id"],
                    "sequence": int(row["stop_sequence"])
                })
                stops_count += 1
                if stops_count % 50000 == 0:
                    print(f"\r    Loaded {stops_count:,} stop_times...", end='')
        
        print(f"\r Loaded {stops_count:,} stop_times")
        
        # PHASE 2: Database operations
        session = next(get_db())
        try:
            self.ensure_agency(session)
            
            # Get route mapping once
            route_map = {
                line.route_id: line.id
                for line in session.query(Line.route_id, Line.id).filter_by(agency_name=self.agency_name)
            }
            
            # Build signature metadata
            print("  Building signatures...")
            signature_meta = {}
            signature_counts = defaultdict(int)
            gtfs_trip_mapping = []
            
            processed = 0
            for gtfs_trip_id, data in trip_info.items():
                if not data["stops"]:
                    continue
                
                line_id = route_map.get(data["route_id"])
                if not line_id:
                    continue
                
                # Sort stops by sequence
                stops = sorted(data["stops"], key=lambda s: s["sequence"])
                stop_ids = [s["stop_id"] for s in stops]
                
                signature = build_signature(line_id, data["direction"], stop_ids)
                signature_counts[signature] += 1
                
                if signature not in signature_meta:
                    signature_meta[signature] = {
                        "line_id": line_id,
                        "direction": data["direction"],
                        "start_stop_id": stop_ids[0],
                        "terminus_stop_id": stop_ids[-1],
                        "stop_ids": stop_ids,
                    }
                
                gtfs_trip_mapping.append({
                    "gtfs_trip_id": gtfs_trip_id,
                    "signature": signature
                })
                
                processed += 1
                if processed % 10000 == 0:
                    print(f"\r    Processed {processed:,} trips...", end='')
            
            print(f"\rGenerated {len(signature_meta):,} unique patterns")
            
            # Load existing signatures in one query
            existing_sigs = {
                t.signature: t.id
                for t in session.query(Trip.signature, Trip.id)
                .filter(Trip.line_agency_name == self.agency_name, Trip.signature.isnot(None))
            }
            
            # Create missing trips
            new_trips = []
            for signature, meta in signature_meta.items():
                if signature not in existing_sigs:
                    new_trips.append({
                        "start_stop_id": meta["start_stop_id"],
                        "terminus_stop_id": meta["terminus_stop_id"],
                        "start_agency_name": self.agency_name,
                        "terminus_agency_name": self.agency_name,
                        "line_id": meta["line_id"],
                        "line_agency_name": self.agency_name,
                        "direction": meta["direction"],
                        "trip_count": signature_counts[signature],
                        "signature": signature,
                    })
            
            if new_trips:
                print(f"  Creating {len(new_trips):,} new trips...")
                # Insert in batches to get IDs
                for batch in chunked(new_trips, TRIP_BATCH_SIZE):
                    session.bulk_insert_mappings(Trip, batch, return_defaults=False)
                    session.flush()
                
                # Reload to get IDs
                new_sig_map = {
                    t.signature: t.id
                    for t in session.query(Trip.signature, Trip.id)
                    .filter(
                        Trip.line_agency_name == self.agency_name,
                        Trip.signature.in_([t["signature"] for t in new_trips])
                    )
                }
                existing_sigs.update(new_sig_map)
                
                # Create TripStops in bulk
                print("  Creating trip stops...")
                trip_stop_rows = []
                for trip_dict in new_trips:
                    sig = trip_dict["signature"]
                    trip_id = existing_sigs[sig]
                    stop_ids = signature_meta[sig]["stop_ids"]
                    
                    for idx, stop_id in enumerate(stop_ids):
                        trip_stop_rows.append({
                            "trip_id": trip_id,
                            "stop_stop_id": stop_id,
                            "stop_agency_name": self.agency_name,
                            "sequence": idx,
                        })
                
                # Insert TripStops in large batches
                for batch in chunked(trip_stop_rows, BATCH_SIZE):
                    session.bulk_insert_mappings(TripStop, batch)
                
                print(f"Created {len(trip_stop_rows):,} trip stops")
            
            # Update trip counts in bulk
            print("  Updating trip counts...")
            count_updates = [
                {"id": existing_sigs[sig], "trip_count": count}
                for sig, count in signature_counts.items()
                if sig in existing_sigs
            ]
            if count_updates:
                for batch in chunked(count_updates, BATCH_SIZE):
                    session.bulk_update_mappings(Trip, batch)
            
            # Sync GTFS mappings
            print("  Syncing GTFS trip mappings...")
            # Delete old mappings
            session.query(GTFSTrip).delete(synchronize_session=False)
            
            # Insert new mappings
            gtfs_rows = []
            seen = set()
            for item in gtfs_trip_mapping:
                gtfs_id = item["gtfs_trip_id"]
                if gtfs_id in seen:
                    continue
                seen.add(gtfs_id)
                
                trip_id = existing_sigs.get(item["signature"])
                if trip_id:
                    gtfs_rows.append({
                        "id": gtfs_id,
                        "trip_id": trip_id
                    })
            
            for batch in chunked(gtfs_rows, BATCH_SIZE):
                session.bulk_insert_mappings(GTFSTrip, batch)
            
            print(f"Created {len(gtfs_rows):,} GTFS mappings")
            
            # Update best trips
            print("Updating best trips...")
            lines = session.query(Line).filter_by(agency_name=self.agency_name).all()
            
            for line in lines:
                for direction in [0, 1]:
                    # Find best trip using a single query
                    best = session.query(
                        Trip.id,
                        sa.func.max(TripStop.sequence).label('max_seq'),
                        Trip.trip_count
                    ).join(
                        TripStop, TripStop.trip_id == Trip.id
                    ).filter(
                        Trip.line_id == line.id,
                        Trip.line_agency_name == self.agency_name,
                        Trip.direction == direction
                    ).group_by(
                        Trip.id, Trip.trip_count
                    ).order_by(
                        (sa.func.max(TripStop.sequence) * sa.func.coalesce(Trip.trip_count, 1)).desc()
                    ).first()
                    
                    if best:
                        if direction == 0:
                            line.best_trip_0_id = best.id
                        else:
                            line.best_trip_1_id = best.id
            
            session.commit()
        finally:
            session.close()

            
        elapsed = time.time() - tic
        print(f"Completed in {elapsed:.1f}s")

# =============================================================================
# REAL-TIME UPDATES
# =============================================================================
def get_all_incoming_buses_tec():
    """Update incoming vehicle positions"""
    tic = time.time()
    
    try:
        params = {"key": TEC_API_KEY} if TEC_API_KEY else None
        response = requests.get(REALTIME_URL, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"TEC RT: HTTP {response.status_code}")
            return
        
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        session = next(get_db())
        try:
            # Load mappings efficiently
            gtfs_mapping = {
                m.id: m.trip_id 
                for m in session.query(GTFSTrip.id, GTFSTrip.trip_id)
            }
            
            # Build lookups
            tripstops = session.query(
                TripStop.id, 
                TripStop.trip_id, 
                TripStop.stop_stop_id, 
                TripStop.sequence
            ).filter_by(stop_agency_name=AGENCY_NAME).all()
            
            ts_lookup = {
                (ts.trip_id, ts.stop_stop_id): (ts.id, ts.sequence) 
                for ts in tripstops
            }
            seq_lookup = {
                (ts.trip_id, ts.sequence): ts.id 
                for ts in tripstops
            }
            
            incoming_ids = set()
            
            # Process vehicles
            for entity in feed.entity:
                if not entity.HasField('vehicle'):
                    continue
                
                v = entity.vehicle
                internal_trip_id = gtfs_mapping.get(v.trip.trip_id)
                
                if internal_trip_id:
                    res = ts_lookup.get((internal_trip_id, v.stop_id))
                    if res:
                        ts_id, seq = res
                        
                        if v.current_status in (0, 1):  # INCOMING or STOPPED
                            incoming_ids.add(ts_id)
                        elif v.current_status == 2:  # IN_TRANSIT
                            next_id = seq_lookup.get((internal_trip_id, seq + 1))
                            if next_id:
                                incoming_ids.add(next_id)
            
            # Update database with debouncing
            if not hasattr(get_all_incoming_buses_tec, "emptycounter"):
                get_all_incoming_buses_tec.emptycounter = 0
            
            if incoming_ids or get_all_incoming_buses_tec.emptycounter >= 3:
                # Reset all
                session.query(TripStop).filter(
                    TripStop.stop_agency_name == AGENCY_NAME
                ).update(
                    {TripStop.vehicle_incoming: False}, 
                    synchronize_session=False
                )
                
                # Set active ones
                if incoming_ids:
                    for batch in chunked(list(incoming_ids), BATCH_SIZE):
                        session.query(TripStop).filter(
                            TripStop.id.in_(batch)
                        ).update(
                            {TripStop.vehicle_incoming: True}, 
                            synchronize_session=False
                        )
                
                session.commit()
  
                get_all_incoming_buses_tec.emptycounter = 0
                print(f"TEC RT: {len(incoming_ids)} active stops ({time.time()-tic:.2f}s)")
            else:
                get_all_incoming_buses_tec.emptycounter += 1
        finally:
            session.close()
    
    except Exception as e:
        print(f"TEC RT Error: {e}")

# =============================================================================
# MAIN IMPORT
# =============================================================================
def import_tec_gtfs(clean: bool = False, steps: Iterable[str] | None = None):
    """Run TEC GTFS import"""
    start_time = time.time()
    print(f"TEC GTFS Import starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    importer = TECGtfsImporter()
    step_set = {s.lower() for s in steps} if steps else {"agency", "routes", "stops", "trips"}
    
    if clean:
        print("\nCleaning existing TEC data...")
        with get_db() as session:
            # Order matters for foreign keys
            session.execute(text("DELETE FROM trip_stop WHERE stop_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM gtfs_trip"))
            session.execute(text("DELETE FROM trip WHERE line_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM line WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM stop WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM sub_agency WHERE agency_name = 'TEC'"))
            session.commit()
        print("Cleaned")
    
    # Download if needed
    if not os.path.exists("tec_gtfs.zip"):
        if not download_gtfs_zip():
            print("Failed to download GTFS")
            return
    else:
        print("Using existing tec_gtfs.zip")
    
    # Import
    try:
        with open("tec_gtfs.zip", "rb") as f:
            zip_content = f.read()
        
        with zipfile.ZipFile(BytesIO(zip_content)) as z:
            if "agency" in step_set:
                with z.open("agency.txt") as f:
                    importer.import_agency(csv.DictReader(TextIOWrapper(f, "utf-8")))
            
            if "routes" in step_set:
                with z.open("routes.txt") as f:
                    importer.import_routes(csv.DictReader(TextIOWrapper(f, "utf-8")))
            
            if "stops" in step_set:
                with z.open("stops.txt") as f:
                    importer.import_stops(csv.DictReader(TextIOWrapper(f, "utf-8")))
            
            if "trips" in step_set:
                with z.open("trips.txt") as f1, z.open("stop_times.txt") as f2:
                    importer.import_trips(
                        csv.DictReader(TextIOWrapper(f1, "utf-8")),
                        csv.DictReader(TextIOWrapper(f2, "utf-8"))
                    )
        
        total = time.time() - start_time
        print(f"\nImport completed in {total:.1f}s ({total/60:.1f} minutes)")
    
    except Exception as e:
        print(f"\nImport error: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import TEC GTFS data")
    parser.add_argument("--clean", action="store_true", help="Clean existing data")
    parser.add_argument("--steps", nargs="+", help="Steps: agency, routes, stops, trips")
    parser.add_argument("--update-incoming", action="store_true", help="Update realtime positions")
    parser.add_argument("--download-only", action="store_true", help="Only download GTFS")
    
    args = parser.parse_args()
    
    try:
        if args.download_only:
            download_gtfs_zip()
        elif args.update_incoming:
            get_all_incoming_buses_tec()
        else:
            import_tec_gtfs(clean=args.clean, steps=args.steps)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
