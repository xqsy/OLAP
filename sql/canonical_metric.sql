SELECT COUNT(*) AS completed_booking_count
FROM fact_booking
WHERE reservation_status = 'Check-Out';
