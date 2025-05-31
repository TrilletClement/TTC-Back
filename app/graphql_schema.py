import strawberry
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from shared.db import get_db
from strawberry.types import Info
from datetime import datetime
from shared.models import (
    User, Role, Device, LedStrip, Led,
    Stop, Line, Agency, Trip, TripStop, TemporaryToken
)

# --- Strawberry Types ---
@strawberry.type
class RoleType:
    id: int
    name: str
    description: Optional[str]

@strawberry.type
class AgencyType:
    id: int
    name: str

@strawberry.type
class StopType:
    stop_id: str
    name: str
    agency: AgencyType

@strawberry.type
class LineType:
    route_id: int
    short_name: str
    long_name: str
    route_type: Optional[str]
    color: Optional[str]
    text_color: Optional[str]
    agency: AgencyType

@strawberry.type
class LedType:
    id: int
    custom_name: Optional[str]
    central: bool

@strawberry.type
class LedStripType:
    id: int
    device_id: int
    line: LineType

    @strawberry.field
    def led1(self) -> Optional[LedType]:
        return self.led1_obj

    @strawberry.field
    def led2(self) -> Optional[LedType]:
        return self.led2_obj

    @strawberry.field
    def led3(self) -> Optional[LedType]:
        return self.led3_obj

    @strawberry.field
    def led4(self) -> Optional[LedType]:
        return self.led4_obj

    @strawberry.field
    def led5(self) -> Optional[LedType]:
        return self.led5_obj

    @strawberry.field
    def led6(self) -> Optional[LedType]:
        return self.led6_obj

    @strawberry.field
    def led7(self) -> Optional[LedType]:
        return self.led7_obj

    @strawberry.field
    def led8(self) -> Optional[LedType]:
        return self.led8_obj

    @strawberry.field
    def led9(self) -> Optional[LedType]:
        return self.led9_obj

    @strawberry.field
    def led10(self) -> Optional[LedType]:
        return self.led10_obj

    @strawberry.field
    def led11(self) -> Optional[LedType]:
        return self.led11_obj

    @strawberry.field
    def led12(self) -> Optional[LedType]:
        return self.led12_obj

@strawberry.type
class DeviceType:
    id: int
    name: str
    owner_id: int
    led_strips: List[LedStripType]
    permanent_token: Optional[str]

    @strawberry.field
    def temporary_token(self) -> Optional['TemporaryTokenType']:
        return self.temporary_token

@strawberry.type
class UserType:
    id: int
    email: str
    active: bool
    fs_uniquifier: str
    roles: List[RoleType]
    devices: List[DeviceType]

@strawberry.type
class TripStopType:
    id: int
    sequence: int
    vehicle_incoming: bool
    stop: StopType
    trip: 'TripType'
    leds: List[LedType]

@strawberry.type
class TripType:
    id: int
    start: StopType
    terminus: StopType
    line: LineType
    trip_count: int
    
@strawberry.type
class TemporaryTokenType:
    id: int
    token: str
    created_at: datetime
    expires_at: Optional[datetime]

# --- Query Root ---
@strawberry.type
class Query:
    @strawberry.field
    def users(self, info: Info) -> List[UserType]:
        with get_db() as db:
            return db.query(User).all()

    @strawberry.field
    def devices(self, info: Info) -> List[DeviceType]:
        with get_db() as db:
            return db.query(Device).all()

    @strawberry.field
    def led_strips(self, info: Info) -> List[LedStripType]:
        with get_db() as db:
            return db.query(LedStrip).all()

    @strawberry.field
    def leds(self, info: Info) -> List[LedType]:
        with get_db() as db:
            return db.query(Led).all()

    @strawberry.field
    def lines(self, info: Info) -> List[LineType]:
        with get_db() as db:
            return db.query(Line).options(joinedload(Line.agency)).all()

    @strawberry.field
    def stops(self, info: Info, name: Optional[str] = None) -> List[StopType]:
        with get_db() as db:
            query = db.query(Stop).options(joinedload(Stop.agency))
            if name:
                query = query.filter(Stop.name == name)
            return query.all()

    @strawberry.field
    def companies(self, info: Info) -> List[AgencyType]:
        with get_db() as db:
            return db.query(Agency).all()

    @strawberry.field
    def roles(self, info: Info) -> List[RoleType]:
        with get_db() as db:
            return db.query(Role).all()
    
    @strawberry.field
    def trips(self, info: Info) -> List[TripType]:
        with get_db() as db:
            return db.query(Trip).all()
    
    @strawberry.field
    def trip_stops(self, info: Info, vehicle_incoming: Optional[bool] = None) -> List[TripStopType]:
        with get_db() as db:
            query = db.query(TripStop)
            if vehicle_incoming is not None:
                query = query.filter(TripStop.vehicle_incoming == vehicle_incoming)
            return query.all()
    
    @strawberry.field
    def temporary_tokens(self, info: Info) -> List[TemporaryTokenType]:
        with get_db() as db:
            return db.query(TemporaryToken).all()



# --- Schema ---
schema = strawberry.Schema(query=Query)
