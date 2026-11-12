-- Each day/hotel must match the detail, including missing or extra groups.
SELECT count() AS mismatched_groups
FROM (
    SELECT arrival_date_id, hotel_id
    FROM (
        SELECT arrival_date_id, hotel_id,
               count() AS detail_count, toUInt64(0) AS summary_count
        FROM fact_booking
        WHERE reservation_status = 'Check-Out'
        GROUP BY arrival_date_id, hotel_id
        UNION ALL
        SELECT arrival_date_id, hotel_id,
               toUInt64(0) AS detail_count, completed_booking_count AS summary_count
        FROM agg_booking_daily
    )
    GROUP BY arrival_date_id, hotel_id
    HAVING sum(detail_count) != sum(summary_count)
);
