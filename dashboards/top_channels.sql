SELECT
    concat(dim_channel.market_segment, ' / ', dim_channel.distribution_channel) AS channel,
    count() AS completed_booking_count
FROM fact_booking
JOIN dim_channel ON fact_booking.channel_id = dim_channel.channel_id
JOIN dim_date ON fact_booking.arrival_date_id = dim_date.date_id
WHERE reservation_status = 'Check-Out'
[[AND {{arrival_period}}]]
GROUP BY dim_channel.market_segment, dim_channel.distribution_channel
ORDER BY completed_booking_count DESC, channel
LIMIT 10;
