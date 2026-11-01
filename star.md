# Набросок star-схемы

Домен D5 — бронирования. Схема реализована в DuckDB; для З06 выбран отказ от SCD2 и политика SCD1 без истории справочников.

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

- data/raw/H1.csv — Resort Hotel; data/raw/H2.csv — City Hotel. Содержимое исходных файлов сохраняем.
- booking_id — технический ключ из кода H1/H2 и номера записи данных без заголовка. Совпадающие по содержимому строки сохраняем. Повторная загрузка того же сырья не должна создавать дубли.
- hotel_id — постоянный идентификатор и первичный ключ dim_hotel. Факт ссылается на единственную строку отеля по hotel_id. При изменении атрибута по SCD1 старое значение не сохраняется; отчёты за прошлые периоды используют актуальное значение. Полей версий и интервалов действия нет.
- arrival_date_id выводим из ArrivalDateYear, ArrivalDateMonth, ArrivalDateDayOfMonth; status_date_id — из ReservationStatusDate. Один календарь обслуживает обе роли. Главную метрику группируем по дате заезда.
- channel_id соответствует уникальному сочетанию MarketSegment + DistributionChannel; оба признака доступны для группировки.
- room_type_id соответствует паре «отель + код типа номера». Один справочник обслуживает забронированный и назначенный тип. При загрузке обе ссылки должны соответствовать hotel_id бронирования. hotel_id в этом измерении задаёт контекст кода; факт соединяем с каждым справочником напрямую.
- В строках обрезаем пробелы, текстовый NULL распознаём как пропуск. Для неизвестных значений измерений предусматриваем явные строки справочников.
- Статус сохраняем в факте как reservation_status из ReservationStatus; отдельное измерение статуса не создаём.

Для dim_country, dim_channel и dim_room_type исправления выполняем без истории (SCD1). 

