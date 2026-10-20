-- Вопрос 1 из паспорта: как меняется количество состоявшихся
-- бронирований по месяцам заезда в каждом отеле?
SELECT
    d.year,
    d.month,
    h.hotel_code,
    COUNT(*) AS completed_booking_count
FROM fact_booking AS f
JOIN dim_date AS d ON f.arrival_date_id = d.date_id
JOIN dim_hotel AS h ON f.hotel_sk = h.hotel_sk
WHERE f.reservation_status = 'Check-Out'
GROUP BY d.year, d.month, h.hotel_code
ORDER BY d.year, d.month, h.hotel_code;

-- Вопрос 2 из паспорта: какие каналы и рыночные сегменты дают
-- больше состоявшихся бронирований? Окно считает долю от всех
-- состоявшихся бронирований и место сочетания сегмента и канала.
WITH channel_counts AS (
    SELECT
        ch.market_segment,
        ch.distribution_channel,
        COUNT(*) AS completed_booking_count
    FROM fact_booking AS f
    JOIN dim_channel AS ch ON f.channel_id = ch.channel_id
    WHERE f.reservation_status = 'Check-Out'
    GROUP BY ch.market_segment, ch.distribution_channel
)
SELECT
    market_segment,
    distribution_channel,
    completed_booking_count,
    ROUND(
        100.0 * completed_booking_count
        / SUM(completed_booking_count) OVER (),
        2
    ) AS share_pct,
    DENSE_RANK() OVER (
        ORDER BY completed_booking_count DESC
    ) AS channel_rank
FROM channel_counts
ORDER BY completed_booking_count DESC,
         market_segment,
         distribution_channel
LIMIT 10;

-- Вопрос 3 из паспорта: из каких стран больше состоявшихся
-- бронирований? UNKNOWN не является страной. Считаем бронирования,
-- а не уникальных людей или сумму числа гостей в номерах.
SELECT
    c.country_code,
    COUNT(*) AS completed_booking_count
FROM fact_booking AS f
JOIN dim_country AS c ON f.country_id = c.country_id
WHERE f.reservation_status = 'Check-Out'
  AND c.country_code <> 'UNKNOWN'
GROUP BY c.country_code
ORDER BY completed_booking_count DESC, c.country_code
LIMIT 10;
