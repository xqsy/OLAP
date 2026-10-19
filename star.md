# Набросок star-схемы

Приложение к [паспорту витрины](passport.md) для З02. Домен D5 — бронирования. Это проектируемая схема; загрузка H1/H2 и создание новых таблиц ещё не выполнены.

**Одна строка fact_booking = одно бронирование.** Загружаем все статусы, главная метрика считает только reservation_status = 'Check-Out'.

Всего шесть таблиц: один факт и пять измерений. Стрелки показывают внешние ключи из факта; каждой строке справочника может соответствовать много бронирований.

```mermaid
flowchart LR
    F["fact_booking<br/>booking_id — PK<br/>hotel_id, country_id, channel_id<br/>arrival_date_id, status_date_id<br/>reserved_room_type_id, assigned_room_type_id<br/>reservation_status, is_canceled<br/>lead_time, adr<br/>stays_in_weekend_nights, stays_in_week_nights<br/>adults, children, babies<br/>source_file, source_row_number"]
    H["dim_hotel<br/>hotel_id — PK<br/>hotel_code, hotel_type"]
    D["dim_date<br/>date_id — PK<br/>full_date, year, quarter, month<br/>day_of_week"]
    C["dim_country<br/>country_id — PK<br/>country_code"]
    CH["dim_channel<br/>channel_id — PK<br/>market_segment<br/>distribution_channel"]
    R["dim_room_type<br/>room_type_id — PK<br/>hotel_id, room_type_code"]
    F -->|hotel_id| H
    F -->|arrival_date_id| D
    F -->|status_date_id| D
    F -->|country_id| C
    F -->|channel_id| CH
    F -->|reserved_room_type_id| R
    F -->|assigned_room_type_id| R
```

## Источники и ключи

- data/H1.csv — Resort Hotel; data/H2.csv — City Hotel. Планируемое размещение сырья — data/raw/hotel/; содержимое файлов сохраняем.
- booking_id — технический ключ из кода H1/H2 и номера записи данных без заголовка. Совпадающие по содержимому строки сохраняем. Повторная загрузка того же сырья не должна создавать дубли.
- arrival_date_id выводим из ArrivalDateYear, ArrivalDateMonth, ArrivalDateDayOfMonth; status_date_id — из ReservationStatusDate. Один календарь обслуживает обе роли. Главную метрику группируем по дате заезда.
- channel_id соответствует уникальному сочетанию MarketSegment + DistributionChannel; оба признака доступны для группировки.
- room_type_id соответствует паре «отель + код типа номера». Один справочник обслуживает забронированный и назначенный тип. При загрузке обе ссылки должны соответствовать отелю бронирования. hotel_id в этом измерении задаёт контекст кода; факт соединяем с каждым справочником напрямую.
- В строках обрезаем пробелы, текстовый NULL распознаём как пропуск. Для неизвестных значений измерений предусматриваем явные строки справочников.
- Статус сохраняем в факте как reservation_status из ReservationStatus; отдельное измерение статуса не создаём.

## Главная метрика

```sql
SELECT COUNT(*) AS completed_booking_count
FROM fact_booking
WHERE reservation_status = 'Check-Out';
```

Количество бронирований не равно количеству людей, комнат или ночей. Справочники не содержат версий SCD2; обоснование и ограничения — в [cut.md](cut.md).
