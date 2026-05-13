\# PROJECT STATUS



\## Название

Городская Пауза



\## Стек

\- FastAPI

\- Aiogram

\- Railway

\- SQLite



\## Архитектура

\- handlers/

\- services/

\- database/

\- static/

\- webapp/



\## Что уже работает

\- Railway deploy

\- Telegram bot

\- FastAPI website

\- Modular structure

\- SQLite init



\## Что осталось

\- Перенос bookings с JSON на SQLite

\- FullCalendar

\- Admin panel

\- Avito sync

\- iCal export/import



\## Главные файлы

\- main.py

\- database/db.py

\- services/booking\_service.py



\## Railway Start Command



```bash

uvicorn main:app --host 0.0.0.0 --port $PORT

```

