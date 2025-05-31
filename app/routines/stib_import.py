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
from io import StringIO
from collections import defaultdict


headers_julien = {
    "Authorization": "Apikey d93b118966fc799fc52d8f63f936478f4b88dbed35370559a7d961f7"
}

headers_antoine = {
    'Authorization': 'Apikey 36109cef239270c05417ed2b4001d76f7b160a0824c2caa87fce5966'
}


def import_stib_lines():
    tic = time.time()
    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/92c45d9df99624d7e05e9ade35ba0ce8"
    response = requests.get(export_url)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code}: {response.text}")
        return

    try:
        content = response.content.decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        
        with get_db() as session:  # Use the context manager to handle the session
            # Ensure the agency exists
            stib = session.query(Agency).filter_by(name="STIB").first()
            if not stib:
                stib = Agency(name="STIB")
                session.add(stib)
                session.commit()

            for row in reader:
                route_id = int(row.get("route_id"))
                short_name = row.get("route_short_name")
                long_name = row.get("route_long_name")
                route_type = row.get("route_type")
                color = row.get("route_color")
                text_color = row.get("route_text_color")

                if not short_name:
                    continue

                # Try to find an existing line
                existing_line = session.query(Line).filter_by(route_id=route_id, agency_name="STIB").first()

                if existing_line:
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

def import_stib_stops():
    tic = time.time()
    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7068c8d492df76c5125fac081b5e09e9"
    response = requests.get(export_url)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code}: {response.text}")
        return

    try:
        content = response.content.decode('utf-8')
        reader = csv.DictReader(StringIO(content))

        
        with get_db() as session:  # Use the context manager to handle the session  
            # Ensure the agency exists
            stib = session.query(Agency).filter_by(name="STIB").first()
            if not stib:
                stib = Agency(name="STIB")
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


def import_trips():
    trips_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7831854a320cbf4ea5b6b327cd4581af"
    stop_times_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/3cc9124c230b72e07df09e27c59eba88"

    tic = time.time()
    # Fetch the CSV files
    trips_csv = requests.get(trips_url).content.decode("utf-8")
    stop_times_csv = requests.get(stop_times_url).content.decode("utf-8")


    trips_reader = csv.DictReader(StringIO(trips_csv))
    stop_times_reader = csv.DictReader(StringIO(stop_times_csv))

    trip_info = {}
    for row in trips_reader:
        trip_info[row["trip_id"]] = [int(row["route_id"])]

    for row in stop_times_reader:
        trip_id = row.get("trip_id")
        stop_id = row.get("stop_id")
        stop_sequence = int(row.get("stop_sequence"))

        if trip_id not in trip_info:
            trip_info[trip_id] = []

        trip_info[trip_id].append({
            "stop_id": stop_id,
            "stop_sequence": stop_sequence
        })

    with get_db() as session:  # Use the context manager to handle the session  
        agency = session.query(Agency).filter_by(name="STIB").first()
        if not agency:
            raise Exception("Agency 'STIB' not found.")

        grouped_trips = {}

        for trip_id, info in trip_info.items():
            route_id = info[0]
            stops = info[1:]

            if not stops:
                continue  # Skip trips without stops
        
            ordered_stops = sorted(stops, key=lambda x: x["stop_sequence"])
            start_stop_id = ordered_stops[0]["stop_id"]
            terminus_stop_id = ordered_stops[-1]["stop_id"]
            key = (start_stop_id, terminus_stop_id, route_id)
            
            if key not in grouped_trips:
                grouped_trips[key] = []
            grouped_trips[key].append(ordered_stops)

        for (start_id, terminus_id, line_id), trips_list in grouped_trips.items():
            # Check if the start and terminus stops exist
            trip = session.query(Trip).filter_by(start_stop_id=start_id, start_agency_name=agency.name, terminus_stop_id=terminus_id, line_route_id=line_id).first()
            
            if not trip:
                trip = Trip(
                    start_stop_id=start_id,
                    start_agency_name=agency.name,
                    terminus_agency_name=agency.name,
                    terminus_stop_id=terminus_id,
                    line_route_id=line_id,
                    line_agency_name=agency.name,
                    trip_count=len(trips_list)
                )
                session.add(trip)
                session.flush()
            else:
                trip.trip_count = len(trips_list)
                session.flush()

            existing_trip_stops = session.query(TripStop).filter_by(trip_id=trip.id).first()
            if existing_trip_stops:
                continue

            best_stops = trips_list[0]

            for idx, stop_data in enumerate(best_stops):
                stop_id = stop_data["stop_id"]
                trip_stop = TripStop(
                    trip_id=trip.id,
                    stop_stop_id=stop_id,
                    stop_agency_name=agency.name,
                    sequence=idx,
                )
                session.add(trip_stop)

        session.commit()
        toc = time.time()
        print("Trips and TripStops imported successfully in {:.2f} seconds.".format(toc - tic))


# note 1: ifdistance from stopp is 0: put current triop stop to true else put the next trip stop in trip to true
# note 2: STIb returnbs stops without the extra letters that are in gtfs actual stop id. so i propose here to put true 
# to all trip stops with stop id or stopid + "something" (like A, 1A, AB, etc.) . For a more precise match, we could
# use the stop_id + "A" or stop_id + "1A" etc. but this would require a more complex logic.
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

        with get_db() as session:
            # 1. Reset all flags in one go
            session.query(TripStop).filter(TripStop.stop_agency_name == "STIB").update(
                {TripStop.vehicle_incoming: False}, synchronize_session=False
            )
            session.commit()

            # 2. Load all relevant TripStops
            tripstops = (
                session.query(
                    TripStop.id,
                    TripStop.trip_id,
                    TripStop.sequence,
                    TripStop.stop_stop_id,
                    TripStop.stop_agency_name,
                    TripStop.id.label("ts_id"),
                    Trip.line_route_id,
                    Trip.terminus_stop_id,
                    Trip.line_agency_name,
                    Trip.terminus_agency_name,
                )
                .join(Trip)
                .filter(Trip.line_agency_name == "STIB", Trip.terminus_agency_name == "STIB", TripStop.stop_agency_name == "STIB")
                .all()
            )

            # Build mapping: (route_id, terminus_stop_id, stop_stop_id) → [TripStop(ts_id, trip_id, seq)]
            from collections import defaultdict
            ts_map = defaultdict(list)
            tripstop_next_map = {}  # (trip_id, sequence) → ts_id

            for ts in tripstops:
                key = (ts.line_route_id, ts.terminus_stop_id, ts.stop_stop_id)
                ts_map[key].append((ts.ts_id, ts.trip_id, ts.sequence))
                tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.ts_id

            # 3. Precompute line map
            line_map = {
                line.short_name: line.route_id
                for line in session.query(Line).filter(Line.agency_name == "STIB").all()
            }

            # 4. Collect IDs to update
            incoming_ids = set()

            for entry in data:
                route_id = line_map.get(entry['lineid'])
                if not route_id:
                    continue
                for pos in entry['vehiclepositions']:
                    dir_ids = [pos['directionId']] + [f"{pos['directionId']}{x}" for x in "ABFGH"]
                    stop_ids = [pos['pointId']] + [f"{pos['pointId']}{x}" for x in "ABFGH"]
                    distance = pos['distanceFromPoint']

                    for d_id in dir_ids:
                        for s_id in stop_ids:
                            for ts_id, trip_id, sequence in ts_map.get((route_id, d_id, s_id), []):
                                if distance == 0:
                                    incoming_ids.add(ts_id)
                                else:
                                    next_ts_id = tripstop_next_map.get((trip_id, sequence + 1))
                                    if next_ts_id:
                                        incoming_ids.add(next_ts_id)

            

            # 5. Bulk update using raw SQL or SQLAlchemy Core
            if incoming_ids:
                ts_table = TripStop.__table__
                stmt = ts_table.update().where(ts_table.c.id.in_(incoming_ids)).values(vehicle_incoming=True)
                session.execute(stmt)
                session.commit()
        toc = time.time()
        print(f"Matched {len(incoming_ids)} incoming TripStops in {toc - tic:.2f} seconds")
    except ValueError as e:
        print("JSON decode error:", e)
        print("Response content:", response.text)
    except Exception as e:
        print("General error:", str(e))

def import_stib_gtfs():
    import_stib_lines()
    import_stib_stops()
    import_trips()

    
if __name__ == "__main__":
    #import_stib_lines()
    #import_stib_stops()
    #import_trips()
    get_all_incoming_buses_export()

