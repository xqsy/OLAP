-- One fact row = one booking (one record of a fixed source CSV).
CREATE TABLE dim_date (
    date_id INTEGER PRIMARY KEY,
    full_date DATE UNIQUE,
    year SMALLINT,
    quarter SMALLINT,
    month SMALLINT,
    day_of_week SMALLINT
);

CREATE TABLE dim_hotel (
    hotel_sk INTEGER PRIMARY KEY,
    hotel_id INTEGER NOT NULL,
    hotel_code VARCHAR NOT NULL,
    hotel_type VARCHAR NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN NOT NULL,
    UNIQUE (hotel_id, valid_from),
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (is_current = (valid_to IS NULL))
);

CREATE TABLE dim_country (
    country_id INTEGER PRIMARY KEY,
    country_code VARCHAR NOT NULL UNIQUE
);

CREATE TABLE dim_channel (
    channel_id INTEGER PRIMARY KEY,
    market_segment VARCHAR NOT NULL,
    distribution_channel VARCHAR NOT NULL,
    UNIQUE (market_segment, distribution_channel)
);

CREATE TABLE dim_room_type (
    room_type_id INTEGER PRIMARY KEY,
    hotel_id INTEGER NOT NULL,
    room_type_code VARCHAR NOT NULL,
    UNIQUE (hotel_id, room_type_code)
);

CREATE TABLE fact_booking (
    booking_id VARCHAR PRIMARY KEY,
    hotel_sk INTEGER NOT NULL REFERENCES dim_hotel(hotel_sk),
    arrival_date_id INTEGER NOT NULL REFERENCES dim_date(date_id),
    status_date_id INTEGER NOT NULL REFERENCES dim_date(date_id),
    country_id INTEGER NOT NULL REFERENCES dim_country(country_id),
    channel_id INTEGER NOT NULL REFERENCES dim_channel(channel_id),
    reserved_room_type_id INTEGER NOT NULL REFERENCES dim_room_type(room_type_id),
    assigned_room_type_id INTEGER NOT NULL REFERENCES dim_room_type(room_type_id),
    reservation_status VARCHAR,
    is_canceled SMALLINT CHECK (is_canceled IN (0, 1)),
    lead_time INTEGER,
    stays_in_weekend_nights INTEGER,
    stays_in_week_nights INTEGER,
    adults INTEGER,
    children INTEGER,
    babies INTEGER,
    adr DECIMAL(18, 2),
    source_file VARCHAR NOT NULL,
    source_row_number INTEGER NOT NULL CHECK (source_row_number > 0),
    UNIQUE (source_file, source_row_number)
);
