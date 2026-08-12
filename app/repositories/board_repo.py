from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.orm_models.auth import User
from app.orm_models.board import Board, BoardType, Led, LedStrip
from app.orm_models.price import BoardTypePrice, PriceVersion


class BoardRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Board ────────────────────────────────────────────────────────────────

    def get_boards_for_owner(self, owner_id: int) -> list[Board]:
        return (
            self.db.query(Board)
            .options(
                joinedload(Board.board_type),
                joinedload(Board.led_strips),
                joinedload(Board.esp32_devices),
            )
            .filter_by(owner_id=owner_id, archived=False)
            .all()
        )

    def count_active_boards(self, owner_id: int) -> int:
        return self.db.query(Board).filter_by(owner_id=owner_id, archived=False).count()

    def get_board_by_id(self, board_id: int) -> Board | None:
        return self.db.query(Board).filter_by(id=board_id).first()

    def get_board_with_strips(self, board_id: int) -> Board | None:
        return (
            self.db.query(Board)
            .options(
                joinedload(Board.led_strips)
                .joinedload(LedStrip.leds)
                .joinedload(Led.trip_stops)
            )
            .filter_by(id=board_id)
            .first()
        )

    def get_board_details_full(self, board_id: int) -> Board | None:
        from app.orm_models.gtfs import Line, Trip
        from sqlalchemy.orm import joinedload as jl
        return (
            self.db.query(Board)
            .options(
                jl(Board.board_type),
                joinedload(Board.led_strips).joinedload(LedStrip.line)
                    .joinedload(Line.best_trip_b).joinedload(Trip.terminus),
                joinedload(Board.led_strips).joinedload(LedStrip.line)
                    .joinedload(Line.best_trip_f).joinedload(Trip.terminus),
                joinedload(Board.led_strips).joinedload(LedStrip.leds)
                    .joinedload(Led.trip_stops),
            )
            .filter_by(id=board_id)
            .first()
        )

    def find_duplicate_name(self, owner_id: int, name: str) -> Board | None:
        return (
            self.db.query(Board)
            .filter(
                Board.owner_id == owner_id,
                Board.archived == False,
                func.lower(Board.name) == name.lower(),
            )
            .first()
        )

    def add(self, board: Board) -> Board:
        self.db.add(board)
        self.db.commit()
        self.db.refresh(board)
        return board

    def archive(self, board: Board) -> None:
        board.archived = True
        self.db.commit()

    def delete_cascade(self, board: Board) -> None:
        for strip in board.led_strips:
            for led in strip.leds:
                led.trip_stops.clear()
                self.db.delete(led)
            self.db.delete(strip)
        self.db.delete(board)
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    # ── BoardType ────────────────────────────────────────────────────────────

    def get_board_type_by_id(self, board_type_id: int) -> BoardType | None:
        return self.db.query(BoardType).filter_by(id=board_type_id).first()

    def get_all_board_types(self) -> list[BoardType]:
        return self.db.query(BoardType).all()

    # ── Prices ───────────────────────────────────────────────────────────────

    def get_latest_price_version(self) -> PriceVersion | None:
        return (
            self.db.query(PriceVersion)
            .order_by(PriceVersion.created_at.desc())
            .first()
        )

    def get_prices_for_version(self, version_id: int) -> list[BoardTypePrice]:
        return self.db.query(BoardTypePrice).filter_by(price_version_id=version_id).all()

    def get_price_for_board_type(self, version_id: int, board_type_id: int) -> BoardTypePrice | None:
        return (
            self.db.query(BoardTypePrice)
            .filter_by(price_version_id=version_id, board_type_id=board_type_id)
            .first()
        )
        
    def get_devices_linked_to_board(self, board_id: int):
        from app.orm_models.device import ESP32Device
        return self.db.query(ESP32Device).filter_by(board_id=board_id).all()

    def board_has_orders(self, board_id: int) -> bool:
        from app.orm_models.order import OrderItem
        return self.db.query(OrderItem).filter_by(board_id=board_id).first() is not None
    
    def get_user_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()