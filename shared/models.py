from sqlalchemy import Table, Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, PrimaryKeyConstraint, ForeignKeyConstraint, DateTime, func
from sqlalchemy.orm import relationship
from flask_security import UserMixin, RoleMixin
from sqlalchemy.orm import backref, joinedload
from datetime import datetime
from shared.db import Base


trip_stop_led_link = Table(
    "trip_stop_led_link",
    Base.metadata,
    Column("trip_stop_id", Integer, ForeignKey("trip_stop.id"), primary_key=True),
    Column("led_id", Integer, ForeignKey("led.id"), primary_key=True),
)

# Define the Role model
class Role(Base, RoleMixin):
    __tablename__ = "role"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True)
    description = Column(String(255))

# Define the User model
class User(Base, UserMixin):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    fs_uniquifier = Column(String(255), unique=True, nullable=False)
    roles = relationship("Role", secondary="user_roles", backref="users")

# Define the UserRoles association table
class UserRoles(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    role_id = Column(Integer, ForeignKey("role.id"))


class ESP32Device(Base):
    __tablename__ = "esp32_device"

    id = Column(Integer, primary_key=True)
    mac_address = Column(String(17), unique=True, nullable=False)
    name = Column(String(100))
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    owner = relationship("User", backref="esp32_devices")
    board_id = Column(Integer, ForeignKey("board.id"))
    board = relationship("Board", backref="esp32_devices")
    test = Column(Boolean, default=False)
    version_hard = Column(String(50)) 
    version_soft = Column(String(50))
    version_firmware = Column(String(50))
    version_updater = Column(String(50))
    last_connected = Column(DateTime)

    registered_at = Column(DateTime, default=datetime.now())
    def to_dict(self):
        return {
            'id': self.id,
            'mac_address': self.mac_address,
            'name': self.name,
            'owner_id': self.owner_id,
            'board_id': self.board_id,
            'registered_at': self.registered_at.isoformat() if self.registered_at else None
        }
        

# Define the Board model
class Board(Base):
    __tablename__ = "board"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    owner = relationship("User", backref="boards")
    svg_path = Column(String(255))
    led_strips = relationship("LedStrip", backref="board")

# Define the LedStrip model
class LedStrip(Base):
    __tablename__ = "led_strip"
    
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("line.id"), nullable=False)
    line_agency_name = Column(String(100), nullable=False)
    order_index = Column(Integer, nullable=False, default=1)
    led_color = Column(String(50), nullable=False, default="red")
    line = relationship(
        "Line",
        backref="led_strips",
        primaryjoin="and_(LedStrip.line_id == Line.id, LedStrip.line_agency_name == Line.agency_name)"
    )

    # LED pointers
    led1 = Column(Integer, ForeignKey("led.id"))
    led2 = Column(Integer, ForeignKey("led.id"))
    led3 = Column(Integer, ForeignKey("led.id"))
    led4 = Column(Integer, ForeignKey("led.id"))
    led5 = Column(Integer, ForeignKey("led.id"))
    led6 = Column(Integer, ForeignKey("led.id"))
    led7 = Column(Integer, ForeignKey("led.id"))
    led8 = Column(Integer, ForeignKey("led.id"))
    led9 = Column(Integer, ForeignKey("led.id"))
    led10 = Column(Integer, ForeignKey("led.id"))
    led11 = Column(Integer, ForeignKey("led.id"))
    led12 = Column(Integer, ForeignKey("led.id"))

    led1_obj = relationship("Led", foreign_keys=[led1], backref=backref("ledstrip1", uselist=False))
    led2_obj = relationship("Led", foreign_keys=[led2], backref=backref("ledstrip2", uselist=False))
    led3_obj = relationship("Led", foreign_keys=[led3], backref=backref("ledstrip3", uselist=False))
    led4_obj = relationship("Led", foreign_keys=[led4], backref=backref("ledstrip4", uselist=False))
    led5_obj = relationship("Led", foreign_keys=[led5], backref=backref("ledstrip5", uselist=False))
    led6_obj = relationship("Led", foreign_keys=[led6], backref=backref("ledstrip6", uselist=False))
    led7_obj = relationship("Led", foreign_keys=[led7], backref=backref("ledstrip7", uselist=False))
    led8_obj = relationship("Led", foreign_keys=[led8], backref=backref("ledstrip8", uselist=False))
    led9_obj = relationship("Led", foreign_keys=[led9], backref=backref("ledstrip9", uselist=False))
    led10_obj = relationship("Led", foreign_keys=[led10], backref=backref("ledstrip10", uselist=False))
    led11_obj = relationship("Led", foreign_keys=[led11], backref=backref("ledstrip11", uselist=False))
    led12_obj = relationship("Led", foreign_keys=[led12], backref=backref("ledstrip12", uselist=False))


# Orders for printed SVG stickers
class Order(Base):
    __tablename__ = "order"

    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board.id"), nullable=False)
    order_details_id = Column(Integer, ForeignKey("order_details.id"), nullable=True)
    svg_path = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    led_colors = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    board = relationship("Board")
    order_details = relationship("OrderDetails", backref="orders")

class GTFSTrip(Base):
    __tablename__ = "gtfs_trip"

    id = Column(String(100), nullable=False)
    trip_id = Column(Integer, ForeignKey("trip.id"), nullable=False)

    # Primary key comlosites
    __table_args__ = (
        PrimaryKeyConstraint("id", "trip_id", name="pk_gtfs_trip_composite"),
    )
    pattern = relationship("Trip", backref="gtfs_mappings")
    
class OrderDetails(Base):
    __tablename__ = "order_details"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True, unique=True)
    address_line1 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="order_details")

    

# Define the Led model (ledstrip specific stop for GUI prupose) 
class Led(Base):
    __tablename__ = "led"
    id = Column(Integer, primary_key=True)
    custom_name = Column(String(100))
    type = Column(String(10), nullable=False) # left/right/central
    # In Led model
    trip_stops = relationship(
        "TripStop",
        secondary="trip_stop_led_link",
        back_populates="leds"
    )

# Define the Line model
class Line(Base):
    __tablename__ = "line"

    id = Column(Integer, primary_key=True)
    #route_id = Column(Integer, nullable=False)
    route_id = Column(String(50), nullable=False)
    short_name = Column(String(10), nullable=False)
    long_name = Column(String(100), nullable=False)
    best_trip_0_id = Column(Integer, ForeignKey("trip.id"), nullable=True)
    best_trip_1_id = Column(Integer, ForeignKey("trip.id"), nullable=True)
    route_type = Column(String(10))
    color = Column(String(7)) # Hex color code
    text_color = Column(String(7)) # Hex color code
    


    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    subagency_id = Column(String(10), nullable=True)
    agency = relationship("Agency", backref="lines")
    
    best_trip_b = relationship(
        "Trip",
        foreign_keys=[best_trip_0_id],
        backref=backref("line_best_trip_0", uselist=False)
    )
    best_trip_f = relationship(
        "Trip",
        foreign_keys=[best_trip_1_id],
        backref=backref("line_best_trip_1", uselist=False)
    )
    subagency = relationship(
        "SubAgency",
        backref="lines",
        foreign_keys=[subagency_id, agency_name],
        overlaps="agency,lines"
    )

    __table_args__ = (
        UniqueConstraint("short_name", "long_name", "agency_name", name="uq_short_long_agency"),
        ForeignKeyConstraint(
            ["subagency_id", "agency_name"],
            ["subagency.id", "subagency.agency_name"],
            name="fk_line_subagency"
        ),
    )

# Define the Stop model
class Stop(Base):
    __tablename__ = "stop"
    stop_id = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    agency = relationship("Agency", backref="stops")

    __table_args__ = (
        PrimaryKeyConstraint("stop_id", "agency_name", name="pk_stopid_agency"),
    )

# Define the Agency model
class Agency(Base):
    __tablename__ = "agency"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    country = Column(String(100), nullable=False)
    
# Define the Agency model
class SubAgency(Base):
    __tablename__ = "subagency"
    id = Column(String(10), nullable=False)
    name = Column(String(100), unique=True, nullable=False)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    agency = relationship("Agency", backref="subagencies")

    __table_args__ = (
        PrimaryKeyConstraint("id", "agency_name", name="pk_subagency_id_agency"),
    )

# Define the trip model ( line + terminus ) 
# trip_count is the number of trips for this line and terminus in trips.txt
class Trip(Base):
    __tablename__ = "trip"

    id = Column(Integer, primary_key=True)
    signature = Column(String(64), nullable=True)

    terminus_stop_id = Column(String, nullable=False)
    terminus_agency_name = Column(String, nullable=False)

    start_stop_id = Column(String, nullable=False)
    start_agency_name = Column(String, nullable=False)

    line_id = Column(Integer, ForeignKey("line.id"), nullable=False)
    line_agency_name = Column(String, nullable=False)

    trip_count = Column(Integer, nullable=False, default=1)
    blacklisted = Column(Boolean, default=False)

    direction = Column(Integer, nullable=False)

    # Constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ["terminus_stop_id", "terminus_agency_name"],
            ["stop.stop_id", "stop.agency_name"]
        ),
        ForeignKeyConstraint(
            ["start_stop_id", "start_agency_name"],
            ["stop.stop_id", "stop.agency_name"]
        ),
    )

    # Relationships
    terminus = relationship(
        "Stop",
        foreign_keys=[terminus_stop_id, terminus_agency_name],
        backref="trips_terminus"
    )
    start = relationship(
        "Stop",
        foreign_keys=[start_stop_id, start_agency_name],
        backref="trips_start"
    )
    line = relationship(
        "Line",
        foreign_keys=[line_id],
        backref="trips"
    )

# Define the trip model ( line + terminus ) 
# trip_count is the number of trips for this line and terminus in trips.txt
class TripStop(Base):
    __tablename__ = "trip_stop"

    id = Column(Integer, primary_key=True)

    trip_id = Column(Integer, ForeignKey("trip.id"), nullable=False)

    stop_stop_id = Column(String, nullable=False)
    stop_agency_name = Column(String, nullable=False)

    vehicle_incoming = Column(Boolean, nullable=False, default=False)
    sequence = Column(Integer, nullable=False)

    # In TripStop model
    leds = relationship(
        "Led",
        secondary="trip_stop_led_link",
        back_populates="trip_stops"
    )   

    # Constraints
    __table_args__ = (
        UniqueConstraint("trip_id", "sequence", name="uq_trip_stop_sequence"),
        ForeignKeyConstraint(
            ["stop_stop_id", "stop_agency_name"],
            ["stop.stop_id", "stop.agency_name"]
        ),
    )

    # Relationships
    trip = relationship("Trip", backref="trip_stops")
    stop = relationship(
        "Stop",
        foreign_keys=[stop_stop_id, stop_agency_name],
        backref="trip_stops"
    )
