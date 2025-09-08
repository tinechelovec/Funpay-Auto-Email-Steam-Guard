# Funpay Auto Email Steam Guard

🔐 Бот для автоматической генерации кодов Steam Guard (из email) на FunPay  
📌 Готов к использованию

## Что из себя представляет бот?

Это Python-скрипт, который:      
✔ Автоматически получает коды Steam Guard из электронной почты  
✔ Можно добавлять более одного аккаунта   
✔ Поддерживает IMAP для чтения писем от Steam  
✔ Автоматически парсит и отправляет коды по запросу  

## Что нужно для работы бота?
1. Установка Python и библиотек
```pip install -r requirements.txt```
2. Привязанный Steam Guard к аккаунту Steam, почта и пароль от почты.
3. Настройка .env
```
FUNPAY_AUTH_TOKEN=golden_key
EMAIL01=mail@gmail.ru
PASSWORD_0=PASSWORD_0
COMMAND_0=!код
DAILY_LIMIT_0=любые
PERIOD_HOURS_0=любые
```

По всем багам, вопросам и предложеням пишите в [Issues](https://github.com/tinechelovec/Funpay-Auto-Email-Steam-Guard/issues) или в [Telegram](https://t.me/tinechelovec)

Другие боты и плагины [Channel](https://t.me/by_thc)
