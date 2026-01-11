#!/usr/bin/env python3
if __name__ == "__main__":
    import sys, os
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
    sys.path.insert(0, BASE_DIR)
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    sys.path.insert(0, FASTAPI_DIR)

import requests
from sqlalchemy.orm import Session
import sqlalchemy as sa
from shared.models import Line, Agency, Stop, Trip, TripStop
from shared.db import get_db
import json
import csv
import time
import re
from io import StringIO
from collections import defaultdict
import os
import sys
from app.routines import tec_import

headers_julien = {
    "Authorization": "Apikey d93b118966fc799fc52d8f63f936478f4b88dbed35370559a7d961f7"
}

headers_antoine = {
    'Authorization': 'Apikey 36109cef239270c05417ed2b4001d76f7b160a0824c2caa87fce5966'
}


def import_stib_lines(response):
    tic = time.time()

    try:
        content = response.content.decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        
        with get_db() as session:  # Use the context manager to handle the session
            # Ensure the agency exists
            stib = session.query(Agency).filter_by(name="STIB").first()
            if not stib:
                stib = Agency(name="STIB", country="Belgium")
                session.add(stib)
                session.commit()

            previous_rows = []
            for row in reader:
                route_id = row.get("route_id")
                short_name = row.get("route_short_name")
                long_name = row.get("route_long_name")
                route_type = row.get("route_type")
                color = row.get("route_color")
                text_color = row.get("route_text_color")
                multiple = False
                
                if not short_name:
                    continue
                
                for rid in previous_rows:
                    if rid.get("route_short_name") == short_name:
                        if rid.get("route_long_name") != long_name or rid.get("route_id") != route_id:
                            print(f"Warning: Found multiple lines with short name {short_name} and different long names or route IDs.")
                            multiple = True
                            break
                        
                previous_rows.append(row)         

                # Try to find an existing line
                # Vérifie si dans notre db, la ligne existe déjà et surtout on regarde combien de fois elle existe. 
                # Si elle n'existe pas, on la crée, si elle existe une seule fois, on la met à jour classiquement
                # Si elle existe plus d'une fois, on verifie si elle correspond a un des long name qu'on a déjà
                # Si oui, on la met à jour, si non, la crée.
                
                # En gros, si elle existe une seule fois, le long name est mis à jour au cas où il change.
                # Si elle existe plusieurs fois et qu'aucun long name ne correspond, on crée une nouvelle ligne
                
                # Problème possible : Si une ligne existe plusieurs fois avec un long name différent et que l'un d'eux change,
                # on ne peut pas savoir ni lequel mettre à jour ni si c'est un simple changement de nom ou si c'est réelement 
                # une nouvelle ligne avec le même short name. On pourrait ajouter une logique pour gérer ça
                
                
                existing_lines = session.query(Line).filter_by(short_name=short_name, agency_name="STIB").all()
                if len(existing_lines) == 1 and not multiple:
                    existing_line = existing_lines[0] if existing_lines else None
                elif len(existing_lines) == 0:
                    existing_line = None
                else:
                    print(f"Warning: Found {len(existing_lines)} lines with short name {short_name} in the database.")
                    found = False
                    for exist_l in existing_lines:
                        if exist_l.long_name == long_name:
                            existing_line = exist_l
                            found = True
                            break
                    if not found:
                        existing_line = None
                        print(f"Warning: No matching long name found for {short_name}. Creating a new line.")
                                
                if existing_line:
                    if route_id != existing_line.route_id:
                        print(f"Warning: Route ID changes for line {short_name} ({long_name}). Route ID: {existing_line.route_id} changes to the new route ID: {route_id}")
                    # Update existing
                    existing_line.route_id = route_id
                    existing_line.short_name = short_name
                    existing_line.long_name = long_name
                    existing_line.route_type = route_type
                    existing_line.color = "#" + color.zfill(6)
                    existing_line.text_color = "#" + text_color.zfill(6)
                else:
                    # Insert new
                    new_line = Line(
                        route_id=route_id,
                        short_name=short_name,
                        long_name=long_name,
                        route_type=route_type,
                        agency_name="STIB",
                        color="#" + color.zfill(6),
                        text_color="#" + text_color.zfill(6)
                    )
                    session.add(new_line)

            session.commit()
            toc = time.time()
            print("Successfully imported and updated STIB lines from routes.txt in {:.2f} seconds.".format(toc - tic))
    except Exception as e:
        print("Error processing routes.txt:", e)

def import_stib_stops(response):
    tic = time.time()

    try:
        content = response.content.decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        
        with get_db() as session:  # Use the context manager to handle the session  
            # Ensure the agency exists
            stib = session.query(Agency).filter_by(name="STIB").first()
            if not stib:
                stib = Agency(name="STIB", country="Belgium")
                session.add(stib)
                session.commit()

            for row in reader:
                stop_id = row.get("stop_id")
                stop_name = row.get("stop_name")

                if not stop_id or not stop_name:
                    continue

                existing_stop = session.query(Stop).filter_by(stop_id=stop_id, agency_name="STIB").first()

                if  existing_stop:
                    # Update existing
                    existing_stop.stop_id = stop_id
                    existing_stop.name = stop_name
                else:
                    # Insert new
                    stop = Stop(
                        stop_id=stop_id,
                        name=stop_name,
                        agency_name="STIB"
                    )
                    session.add(stop)

            session.commit()
            toc = time.time()
            print("Successfully imported STIB stops from stops.txt in {:.2f} seconds.".format(toc - tic))

    except Exception as e:
        print("Error processing stops.txt:", e)


def import_trips(trips_reader, stop_times_reader):

    tic = time.time()

    # Map trip_id -> [route_id, direction_id, {stop_id, stop_sequence}, ...]
    trip_info = {}
    for row in trips_reader:
        trip_id = row["trip_id"]
        route_id = row.get("route_id")
        direction_id = int(row.get("direction_id", 0))  # Default to 0 if not present
        trip_info[trip_id] = [route_id, direction_id]

    for row in stop_times_reader:
        trip_id = row.get("trip_id")
        stop_id = row.get("stop_id")
        stop_sequence = int(row.get("stop_sequence"))

        if trip_id not in trip_info:
            continue  # Skip stop_times without corresponding trip

        trip_info[trip_id].append({
            "stop_id": stop_id,
            "stop_sequence": stop_sequence
        })

    with get_db() as session:
        agency = session.query(Agency).filter_by(name="STIB").first()
        if not agency:
            raise Exception("Agency 'STIB' not found.")

        grouped_trips = {}
        route_id_to_line_id = {
            line.route_id: line.id
            for line in session.query(Line).filter_by(agency_name=agency.name).all()
        }
        for trip_id, info in trip_info.items():
            route_id, direction_id = info[0], info[1]
            stops = info[2:]

            if not stops:
                continue  # Skip trips without stops

            ordered_stops = sorted(stops, key=lambda x: x["stop_sequence"])
            start_stop_id = ordered_stops[0]["stop_id"]
            terminus_stop_id = ordered_stops[-1]["stop_id"]
            
            key = (start_stop_id, terminus_stop_id, route_id_to_line_id[route_id], direction_id)

            if key not in grouped_trips:
                grouped_trips[key] = []
            grouped_trips[key].append(ordered_stops)

        for (start_id, terminus_id, line_id, direction_id), trips_list in grouped_trips.items():
            # Look for an existing Trip with the same start, terminus, line, direction
            trip = session.query(Trip).filter_by(
                start_stop_id=start_id,
                start_agency_name=agency.name,
                terminus_stop_id=terminus_id,
                terminus_agency_name=agency.name,
                line_id=line_id,
                line_agency_name=agency.name,
                direction=direction_id,
            ).first()

            if not trip:
                trip = Trip(
                    start_stop_id=start_id,
                    start_agency_name=agency.name,
                    terminus_stop_id=terminus_id,
                    terminus_agency_name=agency.name,
                    line_id=line_id,
                    line_agency_name=agency.name,
                    direction=direction_id,
                    trip_count=len(trips_list)
                )
                session.add(trip)
                session.flush()
            else:
                trip.trip_count = len(trips_list)
                session.flush()

            # Skip if TripStops already exist
            existing_trip_stops = session.query(TripStop).filter_by(trip_id=trip.id).first()
            if existing_trip_stops:
                continue

            # Use the first trip's stop list as representative
            best_stops = trips_list[0]

            # Add TripStops for this trip
            for idx, stop_data in enumerate(best_stops):
                stop_id = stop_data["stop_id"]
                trip_stop = TripStop(
                    trip_id=trip.id,
                    stop_stop_id=stop_id,
                    stop_agency_name=agency.name,
                    sequence=idx,
                )
                session.add(trip_stop)

        # After all trips are created, assign best_trip_0_id for each line
        # For each line, find the trip with direction 0 that has the highest (max sequence * trip_count)
        lines = session.query(Line).filter_by(agency_name=agency.name).all()
        for line in lines:
            trips_dir_0 = session.query(Trip).filter_by(
                line_id=line.id,
                line_agency_name=agency.name,
                direction=0
            ).all()
            
            best_trip_id = None
            best_score = -1
            for trip in trips_dir_0:
                max_seq = session.query(sa.func.max(TripStop.sequence)).filter_by(trip_id=trip.id).scalar() or 0
                score = max_seq * (trip.trip_count or 1)
                if score > best_score:
                    best_score = score
                    best_trip_id = trip.id
            if best_trip_id:
                line.best_trip_0_id = best_trip_id
                
                
            trips_dir_1 = session.query(Trip).filter_by(
                line_id=line.id,
                line_agency_name=agency.name,
                direction=1
            ).all()
            best_trip_id = None
            best_score = -1
            for trip in trips_dir_1:
                max_seq = session.query(sa.func.max(TripStop.sequence)).filter_by(trip_id=trip.id).scalar() or 0
                score = max_seq * (trip.trip_count or 1)
                if score > best_score:
                    best_score = score
                    best_trip_id = trip.id
            if best_trip_id:
                line.best_trip_1_id = best_trip_id
        session.flush()
                
        

        session.commit()
        toc = time.time()
        print("Trips and TripStops imported successfully in {:.2f} seconds.".format(toc - tic))

# note 1: ifdistance from stopp is 0: put current triop stop to true else put the next trip stop in trip to true
# note 2: STIb returnbs stops without the extra letters that are in gtfs actual stop id. so i propose here to put true 
# to all trip stops with stop id or stopid + "something" (like A, 1A, AB, etc.) . For a more precise match, we could
# use the stop_id + "A" or stop_id + "1A" etc. but this would require a more complex logic.
# def get_all_incoming_buses_export():
#     tic = time.time()

#     export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/vehicle-position-rt-production/exports/json"

#     try:
#         response = requests.get(export_url, headers=headers_antoine)
#         response.encoding = 'utf-8'
#         if response.status_code != 200:
#             print(f"HTTP error {response.status_code}: {response.text}")
#             return

#         data = response.json()
#         for entry in data:
#             entry['vehiclepositions'] = json.loads(entry['vehiclepositions'])

#         with get_db() as session:
#             # 1. Reset all flags in one go
#             session.query(TripStop).filter(TripStop.stop_agency_name == "STIB").update(
#                 {TripStop.vehicle_incoming: False}, synchronize_session=False
#             )
#             session.commit()

#             # 2. Load all relevant TripStops
#             tripstops = (
#                 session.query(
#                     TripStop.id,
#                     TripStop.trip_id,
#                     TripStop.sequence,
#                     TripStop.stop_stop_id,
#                     TripStop.stop_agency_name,
#                     TripStop.id.label("ts_id"),
#                     Trip.line_id,
#                     Trip.terminus_stop_id,
#                     Trip.line_agency_name,
#                     Trip.terminus_agency_name,
#                 )
#                 .join(Trip)
#                 .filter(
#                     Trip.line_agency_name == "STIB",
#                     Trip.terminus_agency_name == "STIB",
#                     TripStop.stop_agency_name == "STIB"
#                 )
#                 .all()
#             )

#             # Build mapping: (line_id, terminus_stop_id, stop_stop_id) → [TripStop(ts_id, trip_id, seq)]
#             from collections import defaultdict
#             ts_map = defaultdict(list)
#             tripstop_next_map = {}  # (trip_id, sequence) → ts_id

#             for ts in tripstops:
#                 key = (ts.line_id, ts.terminus_stop_id, ts.stop_stop_id)
#                 ts_map[key].append((ts.ts_id, ts.trip_id, ts.sequence))
#                 tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.ts_id

#             # 3. Precompute line map: short_name → line.id
#             line_map = {
#                 line.short_name: line.id
#                 for line in session.query(Line).filter(Line.agency_name == "STIB").all()
#             }

#             # 4. Collect IDs to update
#             incoming_ids = set()

#             for entry in data:
#                 line_id = line_map.get(entry['lineid'])
#                 if not line_id:
#                     continue
#                 for pos in entry['vehiclepositions']:
#                     dir_ids = [pos['directionId']] + [f"{pos['directionId']}{x}" for x in "ABFGH"]
#                     stop_ids = [pos['pointId']] + [f"{pos['pointId']}{x}" for x in "ABFGH"]
#                     distance = pos['distanceFromPoint']

#                     for d_id in dir_ids:
#                         for s_id in stop_ids:
#                             for ts_id, trip_id, sequence in ts_map.get((line_id, d_id, s_id), []):
#                                 if distance == 0:
#                                     incoming_ids.add(ts_id)
#                                 else:
#                                     next_ts_id = tripstop_next_map.get((trip_id, sequence + 1))
#                                     if next_ts_id:
#                                         incoming_ids.add(next_ts_id)

#             # 5. Bulk update using raw SQL or SQLAlchemy Core
#             if incoming_ids:
#                 ts_table = TripStop.__table__
#                 stmt = ts_table.update().where(ts_table.c.id.in_(incoming_ids)).values(vehicle_incoming=True)
#                 session.execute(stmt)
#                 session.commit()
#         toc = time.time()
#     except ValueError as e:
#         print("JSON decode error:", e)
#         print("Response content:", response.text)
#     except Exception as e:
#         print("General error:", str(e))

def normalize_stib_id(stop_id):
    digits = re.sub(r'[A-Z]+$', '', str(stop_id))
    if len(digits) < 4:
        digits = digits.zfill(4)
    return digits

def get_all_incoming_buses_export():
    tic = time.time()

    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/vehicle-position-rt-production/exports/json"

    try:
        response = requests.get(export_url, headers=headers_antoine)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"HTTP error {response.status_code}: {response.text}")
            return

        data = response.json()
        for entry in data:
            entry['vehiclepositions'] = json.loads(entry['vehiclepositions'])
            
        with open("/home/c.trillet/server-STIB/fastapi-server/app/routines/missed_buses/mapping.json", "r") as f:
                mapping_data = json.load(f)

        # Extract the mapping data into a dictionary for quick lookup
        mapping_dict = {row[0]: row[1] for row in mapping_data}
        
        def mapping(value):
            if value in mapping_dict:
                print(f"Mapping terminus ID {value} to {mapping_dict[value]}")
                return mapping_dict[value]
            else:
                return value

        with get_db() as session:
            # 1. Load TripStops for STIB
            tripstops = (
                session.query(
                    TripStop.id,
                    TripStop.trip_id,
                    TripStop.sequence,
                    TripStop.stop_stop_id,
                    TripStop.stop_agency_name,
                    TripStop.id.label("ts_id"),
                    Trip.line_id,
                    Trip.terminus_stop_id,
                    Trip.line_agency_name,
                    Trip.terminus_agency_name,
                )
                .join(Trip)
                .filter(
                    Trip.line_agency_name == "STIB",
                    Trip.terminus_agency_name == "STIB",
                    TripStop.stop_agency_name == "STIB"
                )
                .all()
            )

            # 2. Build tripstop mapping: (line_id, terminus_id, stop_id) → [TripStop]
            ts_map = defaultdict(list)
            tripstop_next_map = {}

            for ts in tripstops:
                # Garder l'original ET créer des variantes
                original_terminus = ts.terminus_stop_id
                original_stop = ts.stop_stop_id
                norm_terminus = normalize_stib_id(original_terminus)
                norm_stop = normalize_stib_id(original_stop)
                
                # Clé originale (au cas où)
                ts_map[(ts.line_id, original_terminus, original_stop)].append((ts.ts_id, ts.trip_id, ts.sequence))
                
                # Toutes les variantes normalisées
                suffixes = ['', 'A', 'B', 'F', 'G', 'H', '1A', '1B']
                for t_suf in suffixes:
                    for s_suf in suffixes:
                        variant_key = (
                            ts.line_id,
                            norm_terminus + t_suf if t_suf else norm_terminus,
                            norm_stop + s_suf if s_suf else norm_stop
                        )
                        ts_map[variant_key].append((ts.ts_id, ts.trip_id, ts.sequence))
                
                tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.ts_id
            # 3. Build short_name → [line.id] mapping
            line_map = defaultdict(list)
            for line in session.query(Line).filter(Line.agency_name == "STIB").all():
                line_map[line.short_name].append(line.id)

            # 4. Find all incoming trip stop IDs
            incoming_ids = set()
            missed = 0
            matched = 0
            no_terminus = 0
            no_last_stop = 0
            no_trips = 0
            unknown = 0
            found = {}
            missed_lines = set()
            matched_lines = set()
            missed_lines_shornames = set()
            matched_lines_shornames = set()
            missed_terminus = set()
            missed_buses = []
            missed_no_terminus = []
            missed_no_last_stop = []
            missed_no_trips = []
            missed_unknown = []

            for entry in data:
                line_ids = line_map.get(entry['lineid'])  # entry['lineid'] is short_name
                
                if not line_ids:
                    continue

                for pos in entry['vehiclepositions']:
                    terminus_id = normalize_stib_id(pos['directionId'])  # already normalized
                    last_stop_id = normalize_stib_id(pos['pointId'])    # already normalized
                    distance = pos['distanceFromPoint']

                    for line_id in line_ids:
                        terminus_id = mapping(terminus_id)
                        key = (line_id, terminus_id, last_stop_id)
                        if key in ts_map:
                            matched += 1
                            matched_lines.add(line_id)
                            # Query the line short_name for this line_id
                            line_short_name = session.query(Line.short_name).filter_by(id=line_id).scalar()
                            found.setdefault(line_short_name, 0)
                            found[line_short_name] += 1
                            matched_lines_shornames.add(line_short_name)
                        else:
                            # Collect missed bus details
                            line_short_name = session.query(Line.short_name).filter_by(id=line_id).scalar()
                            missed_buses.append((line_short_name, terminus_id))
                            missed += 1
                            missed_lines.add(line_id)
                            missed_lines_shornames.add(line_short_name)
                            missed_terminus.add(terminus_id)
                            
                            # Investigate the problem origins
                            stop_exists = session.query(Stop).filter_by(
                                stop_id=terminus_id, 
                                agency_name="STIB"
                            ).first()
                            if not stop_exists:
                                #print(f"Terminus stop ID {terminus_id} not found in database for line {line_short_name}")
                                no_terminus += 1
                                missed_no_terminus.append((line_short_name, terminus_id))
                                continue
                            else:
                                # last stop id does not exist in the db
                                stop_exists = session.query(Stop).filter_by(
                                    stop_id=last_stop_id, 
                                    agency_name="STIB"
                                ).first()
                                if not stop_exists:
                                    #print(f"Last stop ID {last_stop_id} not found in database for line {line_short_name} with terminus ID {terminus_id}")
                                    no_last_stop += 1
                                    missed_no_last_stop.append((line_short_name, last_stop_id))
                                    continue
                                # line does not have any trip with this terminus
                                trips_with_terminus = session.query(Trip).filter_by(
                                    terminus_stop_id=terminus_id,
                                    terminus_agency_name="STIB",
                                    line_id=line_id,
                                    line_agency_name="STIB"
                                ).first()
                                if not trips_with_terminus:
                                    #print(f"No trips found for line {line_short_name} with terminus ID {terminus_id}")
                                    no_trips += 1
                                    missed_no_trips.append((line_short_name, terminus_id))
                                    continue
                                
                                # Log unknown problem details
                                print(f"Unknown problem for line {line_short_name} with:")
                                print(f"  Terminus ID: {terminus_id}")
                                print(f"  Last Stop ID: {last_stop_id}")
                                print(f"  Line ID: {line_id}")
                                print(f"  Key: {key}")
                                print(f"  Vehicle Position Data: {pos}")
                                missed_unknown.append((line_short_name, terminus_id))
                                #print("ts_map keys sample for this short:",)
                                unknown += 1
                                

                        for ts_id, trip_id, seq in ts_map.get(key, []):
                            # Also mark the next stop in sequence for this trip
                            next_ts_id = tripstop_next_map.get((trip_id, seq + 1))
                            # Always mark the current tripstop if distance == 0
                            if distance == 0:
                                incoming_ids.add(ts_id)
                            elif next_ts_id:
                                incoming_ids.add(next_ts_id)
                
            # Save missed buses to separate JSON files
            missed_buses_dir = "/home/c.trillet/server-STIB/fastapi-server/app/routines/missed_buses/"
            os.makedirs(missed_buses_dir, exist_ok=True)

            missed_files = {
                "no_terminus.json": missed_no_terminus,
                "no_last_stop.json": missed_no_last_stop,
                "no_trips.json": missed_no_trips,
                "unknown.json": missed_unknown,
            }

            for filename, missed_list in missed_files.items():
                file_path = os.path.join(missed_buses_dir, filename)
                if os.path.exists(file_path):
                    with open(file_path, "r") as f:
                        existing_missed = set(tuple(item) for item in json.load(f))
                else:
                    existing_missed = set()

                new_missed = set(missed_list)
                updated_missed = existing_missed.union(new_missed)

                with open(file_path, "w") as f:
                    json.dump(list(updated_missed), f, indent=4)

            if not hasattr(get_all_incoming_buses_export, "emptycounter"):
                get_all_incoming_buses_export.emptycounter = 0

            if incoming_ids or get_all_incoming_buses_export.emptycounter >= 3:
                # 5. Reset all vehicle_incoming flags for STIB
                session.query(TripStop).filter(TripStop.stop_agency_name == "STIB").update(
                    {TripStop.vehicle_incoming: False}, synchronize_session=False
                )
                # 6. Update TripStops
                ts_table = TripStop.__table__
                stmt = ts_table.update().where(ts_table.c.id.in_(incoming_ids)).values(vehicle_incoming=True)
                session.execute(stmt)
                session.commit()
                get_all_incoming_buses_export.emptycounter = 0
            else : 
                get_all_incoming_buses_export.emptycounter += 1
                print(f"No incoming IDs found. Empty counter: {get_all_incoming_buses_export.emptycounter}")
                
            total_lines = len(matched_lines.union(missed_lines))
  
   
    except ValueError as e:
        print("JSON decode error:", e)
        print("Response content:", response.text)
    except Exception as e:
        print("General error:", str(e))
        
    
def get_all_incoming_buses_export_test():
    tic = time.time()
    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/vehicle-position-rt-production/exports/json"

    try:
        response = requests.get(export_url, headers=headers_antoine)
        response.encoding = 'utf-8'

        if response.status_code != 200:
            print(f"HTTP error {response.status_code}: {response.text}")
            return

        data = response.json()
        for entry in data:
            entry['vehiclepositions'] = json.loads(entry['vehiclepositions'])

        with get_db() as session:
            # 1. Reset
            session.query(TripStop).filter(TripStop.stop_agency_name == "STIB").update(
                {TripStop.vehicle_incoming: False}, synchronize_session=False
            )
            session.commit()

            # 2. Charger les TripStops
            tripstops = (
                session.query(
                    TripStop.id,
                    TripStop.trip_id,
                    TripStop.sequence,
                    TripStop.stop_stop_id,
                    Trip.line_id,
                    Trip.terminus_stop_id,
                )
                .join(Trip)
                .filter(
                    Trip.line_agency_name == "STIB",
                    TripStop.stop_agency_name == "STIB"
                )
                .all()
            )

            # 3. Construire le mapping SANS DOUBLONS
            ts_map = defaultdict(set)  # set au lieu de list
            tripstop_next_map = {}

            for ts in tripstops:
                norm_terminus = normalize_stib_id(ts.terminus_stop_id)
                norm_stop = normalize_stib_id(ts.stop_stop_id)
                
                # Variantes
                for t_suf in ['', 'A', 'B', 'F', 'G', 'H']:
                    for s_suf in ['', 'A', 'B', 'F', 'G', 'H']:
                        key = (
                            ts.line_id,
                            f"{norm_terminus}{t_suf}" if t_suf else norm_terminus,
                            f"{norm_stop}{s_suf}" if s_suf else norm_stop
                        )
                        ts_map[key].add((ts.id, ts.trip_id, ts.sequence))
                
                tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.id

            # 4. Line mapping
            line_map = defaultdict(list)
            for line in session.query(Line).filter(Line.agency_name == "STIB").all():
                line_map[line.short_name].append(line.id)

            # 5. Trouver les TripStops incoming
            incoming_ids = set()
            matched_positions = 0
            missed_positions = 0

            for entry in data:
                line_ids = line_map.get(entry['lineid'])
                if not line_ids:
                    continue

                for pos in entry['vehiclepositions']:
                    terminus_id = normalize_stib_id(pos['directionId'])
                    last_stop_id = normalize_stib_id(pos['pointId'])
                    distance = pos['distanceFromPoint']

                    found_match = False
                    for line_id in line_ids:
                        key = (line_id, terminus_id, last_stop_id)
                        matches = ts_map.get(key, set())
                        
                        if matches:
                            found_match = True
                            # Logique dynamique
                            for ts_id, trip_id, seq in matches:
                                if distance == 0:
                                    incoming_ids.add(ts_id)
                                else:
                                    next_ts_id = tripstop_next_map.get((trip_id, seq + 1))
                                    if next_ts_id:
                                        incoming_ids.add(next_ts_id)
                    
                    if found_match:
                        matched_positions += 1
                    else:
                        missed_positions += 1

            # 6. Update
            if incoming_ids:
                ts_table = TripStop.__table__
                stmt = ts_table.update().where(ts_table.c.id.in_(incoming_ids)).values(vehicle_incoming=True)
                session.execute(stmt)
                session.commit()
                
                # VÉRIFICATION
                count_true = session.query(TripStop).filter(
                    TripStop.stop_agency_name == "STIB",
                    TripStop.vehicle_incoming == True
                ).count()
                
                print(f"{len(incoming_ids)} TripStops uniques mis à jour")
                print(f"VÉRIF DB: {count_true} TripStops à True après commit")
            else:
                print("Aucun véhicule entrant trouvé")

            # Stats
            total_positions = matched_positions + missed_positions
            if total_positions > 0:
                print(f"Positions matchées: {matched_positions}/{total_positions} ({matched_positions/total_positions*100:.1f}%)")
            
            print(f"Temps: {time.time() - tic:.2f}s")

    except Exception as e:
        print(f"Erreur: {str(e)}")
        import traceback
        traceback.print_exc()
        
def import_stib_gtfs():
    # lines
    routes_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/92c45d9df99624d7e05e9ade35ba0ce8"
    route_response = requests.get(routes_url)

    if route_response.status_code != 200:
        print(f"HTTP error {route_response.status_code}: {route_response.text}")
        return
    
    # stops
    stops_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7068c8d492df76c5125fac081b5e09e9"
    stop_response = requests.get(stops_url)

    if stop_response.status_code != 200:
        print(f"HTTP error {stop_response.status_code}: {stop_response.text}")
        return
    
    # trips & stop_times
    trips_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7831854a320cbf4ea5b6b327cd4581af"
    stop_times_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/3cc9124c230b72e07df09e27c59eba88"
    
    # Fetch CSVs
    trips_csv = requests.get(trips_url).content.decode("utf-8")
    stop_times_csv = requests.get(stop_times_url).content.decode("utf-8")

    trips_reader = csv.DictReader(StringIO(trips_csv))
    stop_times_reader = csv.DictReader(StringIO(stop_times_csv))
    
    # Make the imports
    import_stib_lines(route_response)
    import_stib_stops(stop_response)
    import_trips(trips_reader, stop_times_reader)

if __name__ == "__main__":    
    if "--tec" in sys.argv:
        tec_import.import_tec_gtfs(clean=True)
    elif "--stib" in sys.argv:
        import_stib_gtfs()
    else:
        get_all_incoming_buses_export()
        import_stib_gtfs()
        

    



