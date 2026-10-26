-- Executed by etl/load_duckdb.py in the session containing TEMP raw_booking.
-- raw_booking contains accepted records; rejected records are logged separately.
-- NULL expected = informational count; otherwise actual must equal expected.
WITH checks AS (
    SELECT 'fact_booking rows' AS check_name, count(*) AS actual,
           (SELECT count(*) FROM raw_booking) AS expected FROM fact_booking
    UNION ALL
    SELECT 'source ' || r.source_file || ' rows',
           (SELECT count(*) FROM fact_booking f WHERE f.source_file = r.source_file), count(*)
    FROM raw_booking r GROUP BY r.source_file
    UNION ALL
    SELECT 'completed bookings (Check-Out)', count(*),
           (SELECT count(*) FROM raw_booking WHERE reservation_status = 'Check-Out')
    FROM fact_booking WHERE reservation_status = 'Check-Out'
    UNION ALL
    SELECT 'source ' || r.source_file || ' Check-Out',
           (SELECT count(*) FROM fact_booking f
            WHERE f.source_file = r.source_file AND f.reservation_status = 'Check-Out'),
           count(*) FILTER (WHERE r.reservation_status = 'Check-Out')
    FROM raw_booking r GROUP BY r.source_file
    UNION ALL
    SELECT 'dim_date rows', count(*),
           (SELECT coalesce(date_diff('day', min(d), max(d)) + 2, 1)
            FROM (SELECT arrival_date AS d FROM raw_booking UNION ALL SELECT status_date FROM raw_booking))
    FROM dim_date
    UNION ALL
    SELECT 'dim_hotel rows', count(*),
           (SELECT count(DISTINCT hotel_id) + 1 FROM raw_booking) FROM dim_hotel
    UNION ALL
    SELECT 'dim_country rows', count(*),
           (SELECT count(*) FROM (SELECT coalesce(country_code, 'UNKNOWN') FROM raw_booking
                                  UNION SELECT 'UNKNOWN')) FROM dim_country
    UNION ALL
    SELECT 'dim_channel rows', count(*),
           (SELECT count(*) FROM (
               SELECT coalesce(market_segment, 'UNKNOWN'), coalesce(distribution_channel, 'UNKNOWN')
               FROM raw_booking UNION SELECT 'UNKNOWN', 'UNKNOWN')) FROM dim_channel
    UNION ALL
    SELECT 'dim_room_type rows', count(*),
           (SELECT count(*) FROM (
               SELECT hotel_id, coalesce(reserved_room_type, 'UNKNOWN') FROM raw_booking
               UNION SELECT hotel_id, coalesce(assigned_room_type, 'UNKNOWN') FROM raw_booking
               UNION SELECT hotel_id, 'UNKNOWN' FROM raw_booking UNION SELECT 0, 'UNKNOWN'))
    FROM dim_room_type
    UNION ALL
    SELECT 'fact rows with NULL keys', count(*), 0 FROM fact_booking
    WHERE booking_id IS NULL OR hotel_sk IS NULL OR arrival_date_id IS NULL OR status_date_id IS NULL
       OR country_id IS NULL OR channel_id IS NULL
       OR reserved_room_type_id IS NULL OR assigned_room_type_id IS NULL
    UNION ALL
    SELECT 'fact rows with NULL required values', count(*), 0 FROM fact_booking
    WHERE reservation_status IS NULL OR is_canceled IS NULL OR lead_time IS NULL
       OR stays_in_weekend_nights IS NULL OR stays_in_week_nights IS NULL
       OR adults IS NULL OR babies IS NULL
    UNION ALL
    SELECT 'fact rows with invalid numeric ranges', count(*), 0 FROM fact_booking
    WHERE lead_time < 0 OR stays_in_weekend_nights < 0 OR stays_in_week_nights < 0
       OR adults < 0 OR children < 0 OR babies < 0
    UNION ALL
    SELECT 'fact rows with invalid status', count(*), 0 FROM fact_booking
    WHERE reservation_status NOT IN ('Check-Out', 'Canceled', 'No-Show')
    UNION ALL
    SELECT 'raw rows with missing or old dates', count(*), 0 FROM raw_booking
    WHERE arrival_date IS NULL OR status_date IS NULL
       OR arrival_date < DATE '2000-01-01' OR status_date < DATE '2000-01-01'
    UNION ALL
    SELECT 'dimension rows with NULL primary keys',
           (SELECT count(*) FROM dim_date WHERE date_id IS NULL)
         + (SELECT count(*) FROM dim_hotel WHERE hotel_sk IS NULL)
         + (SELECT count(*) FROM dim_country WHERE country_id IS NULL)
         + (SELECT count(*) FROM dim_channel WHERE channel_id IS NULL)
         + (SELECT count(*) FROM dim_room_type WHERE room_type_id IS NULL), 0
    UNION ALL
    SELECT 'fact rows with missing dimension references', count(*), 0
    FROM fact_booking f
    LEFT JOIN dim_hotel h ON f.hotel_sk = h.hotel_sk
    LEFT JOIN dim_date a ON f.arrival_date_id = a.date_id
    LEFT JOIN dim_date s ON f.status_date_id = s.date_id
    LEFT JOIN dim_country c ON f.country_id = c.country_id
    LEFT JOIN dim_channel ch ON f.channel_id = ch.channel_id
    LEFT JOIN dim_room_type r ON f.reserved_room_type_id = r.room_type_id
    LEFT JOIN dim_room_type ar ON f.assigned_room_type_id = ar.room_type_id
    WHERE h.hotel_sk IS NULL OR a.date_id IS NULL OR s.date_id IS NULL OR c.country_id IS NULL
       OR ch.channel_id IS NULL OR r.room_type_id IS NULL OR ar.room_type_id IS NULL
    UNION ALL
    SELECT 'room types from a different hotel', count(*), 0
    FROM fact_booking f JOIN dim_hotel h USING (hotel_sk)
    JOIN dim_room_type r ON r.room_type_id = f.reserved_room_type_id
    JOIN dim_room_type a ON a.room_type_id = f.assigned_room_type_id
    WHERE r.hotel_id <> h.hotel_id OR a.hotel_id <> h.hotel_id
    UNION ALL
    SELECT 'overlapping hotel versions', count(*), 0
    FROM dim_hotel a JOIN dim_hotel b ON a.hotel_id = b.hotel_id AND a.hotel_sk < b.hotel_sk
    WHERE (b.valid_to IS NULL OR a.valid_from < b.valid_to)
      AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
    UNION ALL
    SELECT 'hotel version outside arrival date', count(*), 0
    FROM fact_booking f JOIN dim_hotel h USING (hotel_sk)
    JOIN dim_date d ON d.date_id = f.arrival_date_id
    WHERE d.full_date < h.valid_from OR d.full_date >= h.valid_to
    UNION ALL
    SELECT 'duplicate booking IDs', count(*) - count(DISTINCT booking_id), 0 FROM fact_booking
    UNION ALL
    SELECT 'unknown country bookings', count(*),
           (SELECT count(*) FROM raw_booking WHERE country_code IS NULL OR country_code = 'UNKNOWN')
    FROM fact_booking WHERE country_id = 0
    UNION ALL
    SELECT 'NULL children preserved', count(*) FILTER (WHERE children IS NULL),
           (SELECT count(*) FROM raw_booking WHERE children IS NULL) FROM fact_booking
)
SELECT check_name, actual, expected FROM checks ORDER BY check_name;
