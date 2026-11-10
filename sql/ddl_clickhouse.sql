CREATE TABLE IF NOT EXISTS dim_date (
    date_id Int32,
    full_date Nullable(Date),
    year Nullable(Int16),
    quarter Nullable(Int16),
    month Nullable(Int16),
    day_of_week Nullable(Int16)
)
ENGINE = MergeTree
ORDER BY date_id;

CREATE TABLE IF NOT EXISTS dim_hotel (
    hotel_id Int32,
    hotel_code String,
    hotel_type String
)
ENGINE = MergeTree
ORDER BY hotel_id;

CREATE TABLE IF NOT EXISTS dim_country (
    country_id Int32,
    country_code String
)
ENGINE = MergeTree
ORDER BY country_id;

CREATE TABLE IF NOT EXISTS dim_channel (
    channel_id Int32,
    market_segment String,
    distribution_channel String
)
ENGINE = MergeTree
ORDER BY channel_id;

CREATE TABLE IF NOT EXISTS dim_room_type (
    room_type_id Int32,
    hotel_id Int32,
    room_type_code String
)
ENGINE = MergeTree
ORDER BY room_type_id;

CREATE TABLE IF NOT EXISTS fact_booking (
    booking_id String,
    hotel_id Int32,
    arrival_date_id Int32,
    status_date_id Int32,
    country_id Int32,
    channel_id Int32,
    reserved_room_type_id Int32,
    assigned_room_type_id Int32,
    reservation_status Nullable(String),
    is_canceled Nullable(Int16),
    lead_time Nullable(Int32),
    stays_in_weekend_nights Nullable(Int32),
    stays_in_week_nights Nullable(Int32),
    adults Nullable(Int32),
    children Nullable(Int32),
    babies Nullable(Int32),
    adr Nullable(Decimal(18, 2)),
    source_file String,
    source_row_number Int32
)
ENGINE = MergeTree
ORDER BY (arrival_date_id, hotel_id, booking_id);
