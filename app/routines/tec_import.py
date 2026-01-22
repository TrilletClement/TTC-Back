#!/usr/bin/env python3
"""
TEC GTFS Importer - Production ready module
Can be used as standalone script or imported in scheduler
"""

import csv
import time
import zipfile
import requests
import hashlib
import os
import sys
from io import BytesIO, TextIOWrapper
from typing import Iterable
from collections import defaultdict
from google.transit import gtfs_realtime_pb2

# Adjust path to find shared modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from shared.db import get_db
from shared.models import Agency, Line, Stop, Trip, TripStop, SubAgency, GTFSTrip
from sqlalchemy import text
import sqlalchemy as sa


# =============================================================================
# CONFIGURATION
# =============================================================================
GTFS_ZIP_URL = "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip"
TEC_API_KEY = os.environ.get("TEC_API_KEY", "").strip()
REALTIME_URL = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"
AGENCY_NAME = "TEC"

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; Python requests)",
}


# =============================================================================
# GTFS DOWNLOAD
# =============================================================================
def download_gtfs_zip(max_retries=3):
    """Download TEC GTFS ZIP file with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"Downloading TEC GTFS (attempt {attempt + 1}/{max_retries})...")
            response = requests.get(GTFS_ZIP_URL, headers=headers, timeout=120, stream=True)
            
            if response.status_code == 200:
                with open("tec_gtfs.zip", "wb") as f:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                print(f"  Progress: {progress:.1f}%", end='\r')
                print(f"\nDownloaded TEC GTFS successfully ({downloaded / 1024 / 1024:.1f} MB)")
                return True
            else:
                print(f"Error downloading GTFS: HTTP {response.status_code}")
        except Exception as e:
            print(f"Download failed: {e}")
            if attempt < max_retries - 1:
                print("Retrying...")
                time.sleep(2)
            else:
                print("Max retries reached")
                return False
    return False


# =============================================================================
# GTFS IMPORTER CLASS
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
            session.commit()
        return agency

    def import_agency(self, agency_reader):
        """Import agency and sub-agencies"""
        print("\nImporting agencies...")
        with get_db() as session:
            self.ensure_agency(session)
            count = 0
            for row in agency_reader:
                sub_id = row.get("agency_id")
                sub_name = row.get("agency_name")
                if not sub_id or not sub_name:
                    continue
                exists = session.query(SubAgency).filter_by(
                    id=sub_id, 
                    agency_name=self.agency_name
                ).first()
                if not exists:
                    session.add(SubAgency(
                        id=sub_id, 
                        name=sub_name, 
                        agency_name=self.agency_name
                    ))
                    count += 1
                else:
                    exists.name = sub_name
            session.commit()
            print(f"  Imported {count} sub-agencies")

    def import_routes(self, routes_reader):
        """Import routes/lines"""
        print("\nImporting routes...")
        with get_db() as session:
            self.ensure_agency(session)
            
            existing_lines = {
                (l.route_id, l.agency_name): l
                for l in session.query(Line).filter_by(agency_name=self.agency_name)
            }
            
            seen_combinations = {
                (l.short_name, l.long_name)
                for l in existing_lines.values()
            }
            
            added = 0
            updated = 0
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
                
                key = (route_id, self.agency_name)
                combo = (short_name, long_name)
                
                if key in existing_lines:
                    line = existing_lines[key]
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
                        updated += 1
                        seen_combinations.add(combo)
                elif combo in seen_combinations:
                    skipped += 1
                    continue
                else:
                    session.add(Line(
                        route_id=route_id,
                        short_name=short_name,
                        long_name=long_name,
                        route_type=route_type,
                        agency_name=self.agency_name,
                        subagency_id=subagency_id
                    ))
                    added += 1
                    seen_combinations.add(combo)
            
            session.commit()
            print(f"  Added {added} routes, updated {updated}, skipped {skipped}")

    def import_stops(self, stops_reader):
        """Import stops"""
        print("\nImporting stops...")
        with get_db() as session:
            self.ensure_agency(session)
            
            added = 0
            updated = 0
            
            for row in stops_reader:
                stop_id = row["stop_id"]
                stop_name = row["stop_name"]
                
                stop = session.query(Stop).filter_by(
                    stop_id=stop_id,
                    agency_name=self.agency_name
                ).first()
                
                if stop:
                    stop.name = stop_name
                    updated += 1
                else:
                    session.add(Stop(
                        stop_id=stop_id,
                        name=stop_name,
                        agency_name=self.agency_name
                    ))
                    added += 1
            
            session.commit()
            print(f"  Added {added} stops, updated {updated}")

    def import_trips(self, trips_reader, stop_times_reader):
        """Import trips and trip stops"""
        print("\nImporting trips...")
        tic = time.time()
        
        def build_signature(line_id, direction, stop_ids):
            payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
            return hashlib.sha1(payload.encode("utf-8")).hexdigest()

        # Load trips.txt
        trip_info = defaultdict(lambda: {"route_id": None, "direction": 0, "stops": []})
        trips_count = 0
        for row in trips_reader:
            trips_count += 1
            trip_info[row["trip_id"]]["route_id"] = row["route_id"]
            trip_info[row["trip_id"]]["direction"] = int(row.get("direction_id", 0))
        print(f"  Loaded {trips_count} trips from trips.txt")

        # Load stop_times.txt
        stops_count = 0
        for row in stop_times_reader:
            stops_count += 1
            trip_info[row["trip_id"]]["stops"].append({
                "stop_id": row["stop_id"],
                "sequence": int(row["stop_sequence"])
            })
        print(f"  Loaded {stops_count} stop_times from stop_times.txt")

        # Database work
        with get_db() as session:
            self.ensure_agency(session)

            route_map = {
                line.route_id: line.id
                for line in session.query(Line).filter_by(agency_name=self.agency_name)
            }
            print(f"  Route map has {len(route_map)} lines")

            trip_rows = []
            signature_counts = defaultdict(int)
            signature_meta = {}

            for gtfs_trip_id, data in trip_info.items():
                if not data["stops"]:
                    continue
                line_id = route_map.get(data["route_id"])
                if not line_id:
                    continue
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
                trip_rows.append({
                    "gtfs_trip_id": gtfs_trip_id,
                    "signature": signature,
                })

            # Build signature map from existing trips
            existing_signature_map = {
                trip.signature: trip.id
                for trip in session.query(Trip.id, Trip.signature)
                .filter(Trip.line_agency_name == self.agency_name, Trip.signature.isnot(None))
            }
            signature_updates = []

            trip_stop_rows = (
                session.query(
                    TripStop.trip_id,
                    TripStop.stop_stop_id,
                    TripStop.sequence,
                    Trip.line_id,
                    Trip.direction,
                    Trip.signature,
                )
                .join(Trip, TripStop.trip_id == Trip.id)
                .filter(Trip.line_agency_name == self.agency_name)
                .order_by(TripStop.trip_id, TripStop.sequence)
                .all()
            )

            current_trip_id = None
            current_stop_ids = []
            current_line_id = None
            current_direction = None
            current_signature = None
            for row in trip_stop_rows:
                if current_trip_id is None:
                    current_trip_id = row.trip_id
                    current_line_id = row.line_id
                    current_direction = row.direction
                    current_signature = row.signature
                if row.trip_id != current_trip_id:
                    signature = build_signature(current_line_id, current_direction, current_stop_ids)
                    existing_signature_map.setdefault(signature, current_trip_id)
                    if not current_signature:
                        signature_updates.append({"id": current_trip_id, "signature": signature})
                    current_trip_id = row.trip_id
                    current_line_id = row.line_id
                    current_direction = row.direction
                    current_signature = row.signature
                    current_stop_ids = []
                current_stop_ids.append(row.stop_stop_id)

            if current_trip_id is not None:
                signature = build_signature(current_line_id, current_direction, current_stop_ids)
                existing_signature_map.setdefault(signature, current_trip_id)
                if not current_signature:
                    signature_updates.append({"id": current_trip_id, "signature": signature})

            created_trips = 0
            updated_trips = 0

            # Create missing trips
            new_trip_items = []
            for signature, meta in signature_meta.items():
                if signature in existing_signature_map:
                    continue
                trip = Trip(
                    start_stop_id=meta["start_stop_id"],
                    terminus_stop_id=meta["terminus_stop_id"],
                    start_agency_name=self.agency_name,
                    terminus_agency_name=self.agency_name,
                    line_id=meta["line_id"],
                    line_agency_name=self.agency_name,
                    direction=meta["direction"],
                    trip_count=signature_counts[signature],
                    signature=signature,
                )
                new_trip_items.append((signature, trip))

            if new_trip_items:
                session.add_all([trip for _, trip in new_trip_items])
                session.flush()
                created_trips = len(new_trip_items)
                for signature, trip in new_trip_items:
                    existing_signature_map[signature] = trip.id

                trip_stop_rows = []
                for signature, trip in new_trip_items:
                    stop_ids = signature_meta[signature]["stop_ids"]
                    for idx, stop_id in enumerate(stop_ids):
                        trip_stop_rows.append({
                            "trip_id": trip.id,
                            "stop_stop_id": stop_id,
                            "stop_agency_name": self.agency_name,
                            "sequence": idx,
                        })
                if trip_stop_rows:
                    session.bulk_insert_mappings(TripStop, trip_stop_rows)
            if signature_updates:
                session.bulk_update_mappings(Trip, signature_updates)

            # Update trip counts
            update_rows = []
            for signature, count in signature_counts.items():
                trip_id = existing_signature_map.get(signature)
                if trip_id:
                    update_rows.append({
                        "id": trip_id,
                        "trip_count": count,
                    })
            if update_rows:
                session.bulk_update_mappings(Trip, update_rows)
                updated_trips = len(update_rows)

            # Sync GTFS trip mappings
            existing_gtfs = {
                row.id: row.trip_id
                for row in session.query(GTFSTrip.id, GTFSTrip.trip_id).all()
            }
            ids_to_delete = []
            gtfs_rows = []
            seen_gtfs = set()
            for row in trip_rows:
                gtfs_trip_id = row["gtfs_trip_id"]
                if gtfs_trip_id in seen_gtfs:
                    continue
                seen_gtfs.add(gtfs_trip_id)
                trip_id = existing_signature_map.get(row["signature"])
                if not trip_id:
                    continue
                existing_trip_id = existing_gtfs.get(gtfs_trip_id)
                if existing_trip_id is not None:
                    if existing_trip_id == trip_id:
                        continue
                    ids_to_delete.append(gtfs_trip_id)
                gtfs_rows.append({
                    "id": gtfs_trip_id,
                    "trip_id": trip_id,
                })
            if ids_to_delete:
                session.query(GTFSTrip).filter(GTFSTrip.id.in_(ids_to_delete)).delete(
                    synchronize_session=False
                )
            if gtfs_rows:
                session.bulk_insert_mappings(GTFSTrip, gtfs_rows)
            
            # Update best_trip_id on lines
            print("  Updating best trips...")
            lines = session.query(Line).filter_by(agency_name=self.agency_name).all()
            for line in lines:
                for direction in [0, 1]:
                    trips_dir = session.query(Trip).filter_by(
                        line_id=line.id,
                        line_agency_name=self.agency_name,
                        direction=direction
                    ).all()
                    
                    best_trip_id = None
                    best_score = -1
                    for trip in trips_dir:
                        max_seq = session.query(sa.func.max(TripStop.sequence)).filter_by(
                            trip_id=trip.id
                        ).scalar() or 0
                        score = max_seq * (trip.trip_count or 1)
                        if score > best_score:
                            best_score = score
                            best_trip_id = trip.id
                    
                    if best_trip_id:
                        if direction == 0:
                            line.best_trip_0_id = best_trip_id
                        else:
                            line.best_trip_1_id = best_trip_id
            
            session.commit()
            toc = time.time()
            print(f"  Created {created_trips} trips, updated {updated_trips}")
            print(f"  Completed in {toc - tic:.1f}s")


# =============================================================================
# MAIN FUNCTION FOR SCHEDULER - Real-time vehicle updates
# =============================================================================
def get_all_incoming_buses_tec():
    """
    Main function to be called by scheduler every 20 seconds
    Updates database with incoming TEC vehicles from GTFS-RT feed
    """
    tic = time.time()
    
    try:
        params = {"key": TEC_API_KEY} if TEC_API_KEY else None
        response = requests.get(REALTIME_URL, params=params, timeout=10)
        if response.status_code != 200:
            print(f"TEC: HTTP error {response.status_code}")
            return
        
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        with get_db() as session:
            # Load TripStops for TEC with Line info to get route_id
            tripstops = (
                session.query(
                    TripStop.id,
                    TripStop.trip_id,
                    TripStop.sequence,
                    TripStop.stop_stop_id,
                    Line.route_id
                )
                .join(Trip, TripStop.trip_id == Trip.id)
                .join(Line, Trip.line_id == Line.id)
                .filter(Trip.line_agency_name == AGENCY_NAME)
                .all()
            )
            
            # Build mapping: (route_id, stop_id) -> [(tripstop_id, trip_id, sequence)]
            ts_map = defaultdict(list)
            tripstop_next_map = {}
            
            for ts in tripstops:
                key = (ts.route_id, ts.stop_stop_id)
                ts_map[key].append((ts.id, ts.trip_id, ts.sequence))
                tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.id
            
            # Parse vehicles and find incoming stops
            incoming_ids = set()
            matched = 0
            missed = 0
            
            for entity in feed.entity:
                if not entity.HasField('vehicle'):
                    continue
                
                vehicle = entity.vehicle
                
                if not vehicle.HasField('trip') or not vehicle.HasField('stop_id'):
                    continue
                
                route_id = vehicle.trip.route_id
                stop_id = vehicle.stop_id
                status = vehicle.current_status if vehicle.HasField('current_status') else None
                
                # Look for this combination in our database
                key = (route_id, stop_id)
                
                if key in ts_map:
                    matched += 1
                    # Status: 0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT_TO
                    for ts_id, trip_id, seq in ts_map[key]:
                        # Mark current stop if incoming or stopped
                        if status in (0, 1):
                            incoming_ids.add(ts_id)
                        # Mark next stop if in transit
                        elif status == 2:
                            next_ts_id = tripstop_next_map.get((trip_id, seq + 1))
                            if next_ts_id:
                                incoming_ids.add(next_ts_id)
                else:
                    missed += 1
            
            # Update database with empty counter logic (like STIB)
            if not hasattr(get_all_incoming_buses_tec, "emptycounter"):
                get_all_incoming_buses_tec.emptycounter = 0
            
            if incoming_ids or get_all_incoming_buses_tec.emptycounter >= 3:
                # Reset all TEC vehicle_incoming flags
                session.query(TripStop).filter(
                    TripStop.stop_agency_name == AGENCY_NAME
                ).update({TripStop.vehicle_incoming: False}, synchronize_session=False)
                
                # Set incoming flags
                if incoming_ids:
                    ts_table = TripStop.__table__
                    stmt = ts_table.update().where(
                        ts_table.c.id.in_(incoming_ids)
                    ).values(vehicle_incoming=True)
                    session.execute(stmt)
                
                session.commit()
                get_all_incoming_buses_tec.emptycounter = 0
                
                toc = time.time()
                print(f"TEC: Updated {len(incoming_ids)} incoming stops (matched {matched}, missed {missed}) in {toc-tic:.2f}s")
            else:
                get_all_incoming_buses_tec.emptycounter += 1
                print(f"TEC: No incoming IDs found. Empty counter: {get_all_incoming_buses_tec.emptycounter}")
    
    except Exception as e:
        print(f"TEC realtime error: {str(e)}")


# =============================================================================
# MAIN FUNCTION FOR SCHEDULER - Daily GTFS import
# =============================================================================
def import_tec_gtfs(clean: bool = False, steps: Iterable[str] | None = None):
    """
    Main function to be called by scheduler daily (e.g., at 2 AM)
    Imports TEC GTFS data (agency, routes, stops, trips)
    """
    start_time = time.time()
    print(f"TEC GTFS import starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    importer = TECGtfsImporter()
    step_set = {s.lower() for s in steps} if steps else {"agency", "routes", "stops", "trips"}
    
    if clean:
        print("TEC: Cleaning existing data...")
        with get_db() as session:
            session.execute(text("DELETE FROM trip_stop WHERE stop_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM trip WHERE line_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM line WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM stop WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM sub_agency WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM agency WHERE name = 'TEC'"))
            session.commit()
    
    # Download GTFS
    if not download_gtfs_zip():
        print("TEC: Failed to download GTFS")
        return
    
    # Import GTFS
    try:
        with open("tec_gtfs.zip", "rb") as f:
            zip_content = f.read()
        
        with zipfile.ZipFile(BytesIO(zip_content)) as z:
            required_files = {"agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt"}
            missing = required_files - set(z.namelist())
            if missing:
                raise Exception(f"Missing GTFS files: {missing}")
            
            if "agency" in step_set:
                with z.open("agency.txt") as f:
                    importer.import_agency(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
            
            if "routes" in step_set:
                with z.open("routes.txt") as f:
                    importer.import_routes(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
            
            if "stops" in step_set:
                with z.open("stops.txt") as f:
                    importer.import_stops(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
            
            if "trips" in step_set:
                with z.open("trips.txt") as f1, z.open("stop_times.txt") as f2:
                    importer.import_trips(
                        csv.DictReader(TextIOWrapper(f1, encoding="utf-8")),
                        csv.DictReader(TextIOWrapper(f2, encoding="utf-8"))
                    )
        
        total_time = time.time() - start_time
        print(f"TEC GTFS import completed in {total_time:.1f}s ({total_time/60:.1f} minutes)")
    
    except Exception as e:
        print(f"TEC import error: {str(e)}")
        import traceback
        traceback.print_exc()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def inspect_realtime_feed(max_entities: int = 3):
    """
    Download the GTFS-RT feed and print its field structure plus a few sample entities.
    Use for manual debugging to see what the payload contains.
    """
    print("\nInspecting TEC realtime feed...")
    try:
        params = {"key": TEC_API_KEY} if TEC_API_KEY else None
        response = requests.get(REALTIME_URL, params=params, timeout=30)
        if response.status_code != 200:
            print(f"HTTP error {response.status_code}")
            return

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        print("FeedMessage fields:")
        for field in feed.DESCRIPTOR.fields:
            label = "repeated" if field.label == field.LABEL_REPEATED else "optional"
            print(f"  - {field.name} ({label}, type={field.type})")

        print(f"\nEntity count: {len(feed.entity)}")
        for idx, entity in enumerate(feed.entity[:max_entities], start=1):
            print(f"\nEntity #{idx} id={entity.id}")
            present_fields = [f[0].name for f in entity.ListFields()]
            print(f"  Present fields: {present_fields}")

            if entity.HasField("vehicle"):
                vehicle = entity.vehicle
                vehicle_fields = [f[0].name for f in vehicle.ListFields()]
                print(f"  Vehicle fields: {vehicle_fields}")

                if vehicle.HasField("trip"):
                    trip = vehicle.trip
                    print(f"    Trip: id={trip.trip_id} route_id={trip.route_id} direction_id={trip.direction_id}")

                if vehicle.HasField("position"):
                    pos = vehicle.position
                    print(f"    Position: lat={pos.latitude} lon={pos.longitude} bearing={getattr(pos, 'bearing', None)}")

                if vehicle.HasField("stop_id"):
                    print(f"    Stop ID: {vehicle.stop_id}")

                if vehicle.HasField("current_status"):
                    status_map = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}
                    print(f"    Status: {status_map.get(vehicle.current_status, vehicle.current_status)}")

            if entity.HasField("trip_update"):
                trip_update = entity.trip_update
                update_fields = [f[0].name for f in trip_update.ListFields()]
                print(f"  TripUpdate fields: {update_fields}")

            if entity.HasField("alert"):
                alert = entity.alert
                alert_fields = [f[0].name for f in alert.ListFields()]
                print(f"  Alert fields: {alert_fields}")

        if len(feed.entity) > max_entities:
            print(f"\n... {len(feed.entity) - max_entities} more entities not shown")

    except Exception as e:
        print(f"Error while inspecting feed: {e}")


def test_realtime_vehicles():
    """Test function - not for scheduler, for manual testing only"""
    print("\nTesting realtime vehicle positions...")
    
    try:
        params = {"key": TEC_API_KEY} if TEC_API_KEY else None
        response = requests.get(REALTIME_URL, params=params, timeout=30)
        
        if response.status_code != 200:
            print(f"HTTP error {response.status_code}")
            return
        
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        
        print(f"  Received {len(feed.entity)} vehicle positions")
        
        # Show first 5 vehicles as example
        count = 0
        for entity in feed.entity:
            if entity.HasField('vehicle') and count < 5:
                vehicle = entity.vehicle
                
                vehicle_id = entity.id
                trip_id = vehicle.trip.trip_id if vehicle.HasField('trip') else "N/A"
                route_id = vehicle.trip.route_id if vehicle.HasField('trip') else "N/A"
                
                lat = vehicle.position.latitude if vehicle.HasField('position') else None
                lon = vehicle.position.longitude if vehicle.HasField('position') else None
                
                stop_id = vehicle.stop_id if vehicle.HasField('stop_id') else "N/A"
                
                status_map = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}
                status = status_map.get(vehicle.current_status, "UNKNOWN") if vehicle.HasField('current_status') else "N/A"
                
                print(f"\n  Vehicle: {vehicle_id}")
                print(f"    Route: {route_id}")
                print(f"    Trip: {trip_id}")
                print(f"    Position: {lat}, {lon}")
                print(f"    Stop: {stop_id}")
                print(f"    Status: {status}")
                
                count += 1
        
        if len(feed.entity) > 5:
            print(f"\n  ... and {len(feed.entity) - 5} more vehicles")
    
    except Exception as e:
        print(f"Error: {str(e)}")


def update_incoming_vehicles():
    """Legacy function - use get_all_incoming_buses_tec() instead"""
    get_all_incoming_buses_tec()


# =============================================================================
# MAIN IMPORT FUNCTION
# =============================================================================
def import_tec_gtfs(clean: bool = False, steps: Iterable[str] | None = None):
    """Run TEC GTFS import"""
    start_time = time.time()
    importer = TECGtfsImporter()
    
    step_set = {s.lower() for s in steps} if steps else {"agency", "routes", "stops", "trips"}
    
    if clean:
        print("\nCleaning existing TEC data...")
        clean_start = time.time()
        with get_db() as session:
            session.execute(text("DELETE FROM trip_stop WHERE stop_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM trip WHERE line_agency_name = 'TEC'"))
            session.execute(text("DELETE FROM line WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM stop WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM sub_agency WHERE agency_name = 'TEC'"))
            session.execute(text("DELETE FROM agency WHERE name = 'TEC'"))
            session.commit()
        print(f"  Cleaned in {time.time() - clean_start:.1f}s")
    
    # Download GTFS if needed
    if not os.path.exists("tec_gtfs.zip"):
        if not download_gtfs_zip():
            print("Failed to download GTFS")
            return
    else:
        print("Using existing tec_gtfs.zip")
    
    # Import GTFS
    with open("tec_gtfs.zip", "rb") as f:
        zip_content = f.read()
    
    with zipfile.ZipFile(BytesIO(zip_content)) as z:
        required_files = {"agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt"}
        missing = required_files - set(z.namelist())
        if missing:
            raise Exception(f"Missing GTFS files: {missing}")
        
        if "agency" in step_set:
            with z.open("agency.txt") as f:
                importer.import_agency(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
        
        if "routes" in step_set:
            with z.open("routes.txt") as f:
                importer.import_routes(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
        
        if "stops" in step_set:
            with z.open("stops.txt") as f:
                importer.import_stops(csv.DictReader(TextIOWrapper(f, encoding="utf-8")))
        
        if "trips" in step_set:
            with z.open("trips.txt") as f1, z.open("stop_times.txt") as f2:
                importer.import_trips(
                    csv.DictReader(TextIOWrapper(f1, encoding="utf-8")),
                    csv.DictReader(TextIOWrapper(f2, encoding="utf-8"))
                )
    
    total_time = time.time() - start_time
    print(f"\nTEC GTFS import completed in {total_time:.1f}s ({total_time/60:.1f} minutes)")


# =============================================================================
# MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":
    TEC_API_KEY = "36497DD5F3AD4262B24981633E73EF33"
    print("=" * 70)
    print("TEC GTFS IMPORTER")
    print("=" * 70)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Import TEC GTFS data")
    parser.add_argument("--clean", action="store_true", help="Clean existing TEC data")
    parser.add_argument("--steps", nargs="+", help="Steps to run (agency, routes, stops, trips)")
    parser.add_argument("--test-realtime", action="store_true", help="Test realtime vehicle positions")
    parser.add_argument("--inspect-realtime", action="store_true", help="Print raw realtime feed structure and sample entities")
    parser.add_argument("--update-incoming", action="store_true", help="Update incoming vehicles in DB")
    parser.add_argument("--download-only", action="store_true", help="Only download GTFS file")
    
    args = parser.parse_args()
    
    try:
        if args.download_only:
            download_gtfs_zip()
        elif args.test_realtime:
            test_realtime_vehicles()
        elif args.inspect_realtime:
            inspect_realtime_feed()
        elif args.update_incoming:
            update_incoming_vehicles()
        else:
            import_tec_gtfs(clean=args.clean, steps=args.steps)
            
            # Optionally test realtime after import
            print("\n" + "=" * 70)
            test_realtime_vehicles()
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
