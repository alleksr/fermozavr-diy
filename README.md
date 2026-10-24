# Fermozavr DIY

[English](README.en.md)

Открытый эксперимент: зимой собираем систему мониторинга фермы, которая весной должна работать в поле, а не на демонстрационном столе.

Цифра на экране сама по себе ещё не измерение. Сначала формулируем задачу и требования к точности, потом проверяем датчики и только после этого публикуем список покупок.

## Где читать

Тексты цикла выходят на [Фермозавре](https://fermozavr.ru). В этот репозиторий статьи не кладутся.

- [Документация проекта](docs/README.md) — устройство станции, формат показаний и правила решений.
- [ESP32 на столе. Готовим подключение к нашему дашборду](https://fermozavr.ru/samodelki/esp32-na-stole-gotovim-podklyuchenie-k-nashemu-dashbordu)
- [Умная ферма своими руками: этой зимой строим систему, которая весной выйдет в поле](https://fermozavr.ru/samodelki/umnaya-ferma-svoimi-rukami-etoy-zimoy-stroim-sistemu-kotoraya-vesnoy-vyydet-v-po)
- [Как присоединиться к Fermozavr DIY и что мы будем делать дальше](https://fermozavr.ru/samodelki/kak-prisoedinitsya-k-fermozavr-diy-i-chto-my-budem-delat-dalshe)
- [23,47 °C: стенд и первый список покупок](https://fermozavr.ru/samodelki/23-47-c-stend-i-pervyy-spisok-pokupok)
- [23,47 °C: что на самом деле показывает экран](https://fermozavr.ru/samodelki/23-47-c-chto-na-samom-dele-pokazyvaet-ekran)
- [Что экран имеет право сказать, пока датчики в пути](https://fermozavr.ru/samodelki/chto-ekran-imeet-pravo-skazat-poka-datchiki-v-puti)
- [Страница уже открывается, датчики ещё в пути](https://fermozavr.ru/samodelki/stranitsa-uzhe-otkryvaetsya-datchiki-eshchyo-v-puti)

## Как присоединиться

Анкета открыта всё время проекта: [fermozavr.ru/diy](https://fermozavr.ru/diy).

Обсуждение идёт в канале [«Фермозавр»](https://t.me/fermozavr). Комментарий под постом не заменяет анкету.

Перечень для стенда первого опыта опубликован в статье про 23,47 °C. Список полевого узла появится после испытаний.

Если удобнее письмо, тот же рассказ можно отправить на [info@fermozavr.ru](mailto:info@fermozavr.ru).

## Страница

Первая страница узла уже открывается на этом компьютере. Датчик для неё не нужен: строку можно вписать руками. В папке репозитория:

```
python3 station/server.py
```

Адрес после запуска: `http://127.0.0.1:8321`.

Отдельных библиотек нет. Нужен сам Python 3, файл зависимостей в репозитории не лежит, и `pip` здесь ничего не устанавливает. На Windows та же команда иногда называется `python`.

Запись с ESP32 лежит в `firmware/fermozavr_recorder/`. Одна сборка отдаёт ту же строку по USB, по Wi‑Fi или по Bluetooth. Пока датчик не ответил числом, в журнал ничего не пишется. Как включить путь: [документация станции](docs/station.md).

## Что будет здесь

Протоколы испытаний, перечни деталей и схемы — по мере того, как они станут готовы к повторению. Страница лежит в `station/`, запись с платы — в `firmware/fermozavr_recorder/`.
