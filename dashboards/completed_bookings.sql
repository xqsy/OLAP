SELECT COUNT(*) AS completed_booking_count
FROM fact_booking
JOIN dim_date ON fact_booking.arrival_date_id = dim_date.date_id
WHERE reservation_status = 'Check-Out'
[[AND {{arrival_period}}]];
