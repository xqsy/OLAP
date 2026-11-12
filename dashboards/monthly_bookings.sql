SELECT
    toStartOfMonth(dim_date.full_date) AS arrival_month,
    dim_hotel.hotel_code,
    sum(agg_booking_daily.completed_booking_count) AS completed_booking_count
FROM agg_booking_daily
JOIN dim_date ON agg_booking_daily.arrival_date_id = dim_date.date_id
JOIN dim_hotel ON agg_booking_daily.hotel_id = dim_hotel.hotel_id
WHERE 1 = 1
[[AND {{arrival_period}}]]
GROUP BY arrival_month, dim_hotel.hotel_code
ORDER BY arrival_month, dim_hotel.hotel_code;
