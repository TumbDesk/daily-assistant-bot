"""Travel management for vacation weather in the agenda."""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select

from database import TravelTrip, get_session
from services.i18n_util import LocalizedError
from services.timezone_util import now


@dataclass(frozen=True)
class TravelTripDTO:
    destination: str
    latitude: float
    longitude: float
    start_date: date
    end_date: date


class TravelService:
    def add_trip(
        self,
        user_id: str,
        destination: str,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> TravelTrip:
        if end_date < start_date:
            raise LocalizedError("err_trip_end_before_start")

        with get_session() as session:
            trip = TravelTrip(
                user_id=user_id,
                destination=destination.strip(),
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
            )
            session.add(trip)
            session.flush()
            session.refresh(trip)
            return self._detach_trip(session, trip)

    def get_active_trip(
        self, user_id: str, on_date: date | None = None
    ) -> TravelTripDTO | None:
        today = on_date or now().date()

        with get_session() as session:
            row = session.scalars(
                select(TravelTrip)
                .where(TravelTrip.user_id == user_id)
                .where(TravelTrip.start_date <= today)
                .where(TravelTrip.end_date >= today)
                .order_by(TravelTrip.start_date.desc())
                .limit(1)
            ).first()

            if row is None:
                return None

            return TravelTripDTO(
                destination=row.destination,
                latitude=row.latitude,
                longitude=row.longitude,
                start_date=row.start_date,
                end_date=row.end_date,
            )

    def _detach_trip(self, session, trip: TravelTrip) -> TravelTrip:
        session.expunge(trip)
        return trip

    def list_trips(self, user_id: str) -> list[TravelTrip]:
        with get_session() as session:
            rows = list(
                session.scalars(
                    select(TravelTrip)
                    .where(TravelTrip.user_id == user_id)
                    .order_by(TravelTrip.start_date.asc())
                ).all()
            )
            for row in rows:
                session.expunge(row)
        return rows

    def get_trip(self, user_id: str, trip_id: int) -> TravelTrip | None:
        with get_session() as session:
            trip = session.scalar(
                select(TravelTrip)
                .where(TravelTrip.id == trip_id)
                .where(TravelTrip.user_id == user_id)
            )
            if trip is None:
                return None
            return self._detach_trip(session, trip)

    def delete_trip(self, user_id: str, trip_id: int) -> bool:
        with get_session() as session:
            trip = session.scalar(
                select(TravelTrip)
                .where(TravelTrip.id == trip_id)
                .where(TravelTrip.user_id == user_id)
            )
            if trip is None:
                return False
            session.delete(trip)
            return True

    def update_trip(
        self,
        user_id: str,
        trip_id: int,
        *,
        destination: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TravelTrip:
        with get_session() as session:
            trip = session.scalar(
                select(TravelTrip)
                .where(TravelTrip.id == trip_id)
                .where(TravelTrip.user_id == user_id)
            )
            if trip is None:
                raise LocalizedError("err_trip_not_found")

            if destination is not None:
                trip.destination = destination.strip()
            if latitude is not None:
                trip.latitude = latitude
            if longitude is not None:
                trip.longitude = longitude
            if start_date is not None:
                trip.start_date = start_date
            if end_date is not None:
                trip.end_date = end_date

            if trip.end_date < trip.start_date:
                raise LocalizedError("err_trip_end_before_start")

            session.flush()
            session.refresh(trip)
            return self._detach_trip(session, trip)


_travel_service: Optional[TravelService] = None


def get_travel_service() -> TravelService:
    global _travel_service
    if _travel_service is None:
        _travel_service = TravelService()
    return _travel_service
