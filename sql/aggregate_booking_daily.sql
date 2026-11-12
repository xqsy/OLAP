CREATE TABLE IF NOT EXISTS agg_booking_daily (
    arrival_date_id Int32,
    hotel_id Int32,
    completed_booking_count UInt64
)
ENGINE = MergeTree
ORDER BY (arrival_date_id, hotel_id);

TRUNCATE TABLE agg_booking_daily;

INSERT INTO agg_booking_daily
SELECT arrival_date_id, hotel_id, count() AS completed_booking_count
FROM fact_booking
WHERE reservation_status = 'Check-Out'
GROUP BY arrival_date_id, hotel_id;
