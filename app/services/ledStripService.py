from fastapi import HTTPException
from sqlalchemy.orm import Session
import sqlalchemy as sa
from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop

class LedStripService:
    ALLOWED_COLORS = {'red', 'blue', 'white', 'green', 'yellow'}

    @staticmethod
    def create_led_strip(
        board_id: int,
        agency_name: str,
        line_id: int,
        central_stop_left_name: str,
        central_stop_right_name: str,
        led_color: str = None,
        order_index_override: int = None,
        db: Session = None
    ):
        if not all([agency_name, line_id]) or (not central_stop_left_name and not central_stop_right_name):
            raise HTTPException(status_code=400,
                                detail="agency_name, line_id, and (central_stop_left_name or central_stop_right_name) are required")

        if led_color and led_color not in LedStripService.ALLOWED_COLORS:
            raise HTTPException(status_code=400,
                                detail=f"Invalid led_color. Allowed: {', '.join(sorted(LedStripService.ALLOWED_COLORS))}")
    
        board = db.query(Board).filter_by(id=board_id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Board not found")

        next_order = order_index_override or ((db.query(sa.func.max(LedStrip.order_index))
                                              .filter(LedStrip.board_id == board.id).scalar() or 0) + 1)

        trips = LedStripService._get_trips_by_direction(db, agency_name, line_id)
        if not trips[0] and not trips[1]:
            raise HTTPException(status_code=404, detail="Could not find any trips for this line")

        trip_stops = LedStripService._get_trip_stops_by_direction(db, trips)
        central_indexes = LedStripService._find_central_indexes(db, trip_stops,
                                                                central_stop_left_name,
                                                                central_stop_right_name)
        selected_stops = LedStripService._select_stops_around_central(db, trip_stops, central_indexes)

        led_strip = LedStrip(
            board_id=board.id,
            line_id=line_id,
            line_agency_name=agency_name,
            order_index=next_order,
            led_color=led_color or 'red'
        )
        db.add(led_strip)
        db.flush()

        led_ids = LedStripService._create_leds(db, selected_stops)
        for idx, led_id in enumerate(led_ids):
            setattr(led_strip, f'led{idx+1}', led_id)

        db.commit()
        return {"message": "LED strip created successfully", "led_strip_id": led_strip.id}

    @staticmethod
    def _get_trips_by_direction(db, agency_name, line_id):
        line = db.query(Line).filter_by(id=line_id, agency_name=agency_name).first()
        if not line:
            raise HTTPException(status_code=404,
                                detail=f"Line with id {line_id} and agency_name {agency_name} not found")
        return {
            0: db.query(Trip).filter_by(id=line.best_trip_0_id).first(),
            1: db.query(Trip).filter_by(id=line.best_trip_1_id).first()
        }

    @staticmethod
    def _get_trip_stops_by_direction(db, trips):
        result = {}
        for dir in [0, 1]:
            if trips[dir]:
                result[dir] = db.query(TripStop).filter_by(trip_id=trips[dir].id).order_by(TripStop.sequence).all()
            else:
                result[dir] = []
        return result

    @staticmethod
    def _find_central_indexes(db, trip_stops, central_stop_left_name, central_stop_right_name):
        """
        Trouve l'index du stop central dans les trip_stops.
        Stratégie SIMPLE: On prend toujours le DERNIER match pour éviter les doublons.
        """
        central_indexes = {}
        
        for dir in [0, 1]:
            if not trip_stops[dir]:
                central_indexes[dir] = None
                continue
            
            # Déterminer quel nom chercher
            if dir == 0:
                target_name = central_stop_left_name
            else:
                target_name = central_stop_right_name
            
            if not target_name:
                central_indexes[dir] = None
                continue
            
            # Chercher le DERNIER arrêt avec ce nom (parcourir à l'envers)
            central_index = None
            for i in range(len(trip_stops[dir]) - 1, -1, -1):
                ts = trip_stops[dir][i]
                s = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=ts.stop_agency_name
                ).first()
                if s and s.name.strip().lower() == target_name.strip().lower():
                    central_index = i
                    break
            
            if central_index is None:
                raise HTTPException(status_code=404,
                                    detail=f'Central stop "{target_name}" not found in trip direction {dir}')
            central_indexes[dir] = central_index
        
        return central_indexes

    @staticmethod
    def _select_stops_around_central(db, trip_stops, central_indexes):
        selected_stops = {}
        
        # Combien de stops on doit prendre?
        only_one_direction = (central_indexes[0] is None) != (central_indexes[1] is None)
        stops_to_take = 12 if only_one_direction else 6
        
        for dir in [0, 1]:
            if central_indexes[dir] is None:
                selected_stops[dir] = None
            else:
                # Prendre jusqu'à stops_to_take arrêts AVANT le central (inclus)
                start = max(0, central_indexes[dir] - (stops_to_take - 1))
                selected = trip_stops[dir][start:central_indexes[dir] + 1]
                
                # Pour direction 1, inverser pour que le central soit à droite
                if dir == 1:
                    selected = list(reversed(selected))
                
                # Padding avec None au début si pas assez d'arrêts
                while len(selected) < stops_to_take:
                    selected.insert(0, None)
                
                # Si trop d'arrêts (ne devrait pas arriver), prendre les derniers
                if len(selected) > stops_to_take:
                    selected = selected[-stops_to_take:]
                
                selected_stops[dir] = selected
        
        return selected_stops

    @staticmethod
    def _create_leds(db, selected_stops):
        led_ids = []
        only0 = selected_stops[1] is None
        only1 = selected_stops[0] is None

        for i in range(12):
            # Déterminer direction, index, et type
            if not only0 and not only1:
                # Double sens: 6 LEDs par direction
                if i < 6:
                    dir, stop_idx = 0, i
                    is_c_left = (i == 5)
                    is_c_right = False
                    is_left = (i < 5)
                    is_right = False
                else:
                    dir, stop_idx = 1, i - 6
                    is_c_left = False
                    is_c_right = (i == 6)
                    is_left = False
                    is_right = (i > 6)
                    
            elif only0:
                # Sens unique direction 0: 12 LEDs
                dir, stop_idx = 0, i
                is_c_left = (i == 11)
                is_c_right = False
                is_left = (i < 11)
                is_right = False
                
            else:  # only1
                # Sens unique direction 1: 12 LEDs
                # Après reverse dans _select_stops, le central est à la fin (index 11)
                dir, stop_idx = 1, i
                is_c_left = False
                is_c_right = (i == 11)
                is_left = False
                is_right = (i < 11)

            # Récupérer le TripStop
            ts = selected_stops[dir][stop_idx] if selected_stops[dir] else None
            
            custom_name = None
            if ts:
                stop = db.query(Stop).filter_by(
                    stop_id=ts.stop_stop_id,
                    agency_name=ts.stop_agency_name).first()
                custom_name = stop.name if stop else ts.stop_stop_id

            # Type de LED
            if is_c_left:
                led_type = 'c_left'
            elif is_c_right:
                led_type = 'c_right'
            elif is_left:
                led_type = 'left'
            else:
                led_type = 'right'

            led = Led(custom_name=custom_name, type=led_type)
            db.add(led)
            db.flush()
            
            if ts:
                led.trip_stops.append(ts)
                
            led_ids.append(led.id)
            
        return led_ids