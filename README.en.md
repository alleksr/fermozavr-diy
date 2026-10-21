# Fermozavr DIY

[Русский](README.md)

An open experiment: this winter we build a farm monitoring system that has to work in the field by spring, not on a demonstration bench.

A number on a screen is not yet a measurement. We state the task and the accuracy it requires, test the sensors, and only then publish a shopping list.

## Where to read

The essays are published on [Fermozavr](https://fermozavr.ru). They are not stored in this repository. The articles themselves are in Russian.

- [Project documentation](docs/README.en.md) — station overview, reading format, and decision rules.
- [A smart farm, built by hand: this winter we build the system that goes to the field in spring](https://fermozavr.ru/samodelki/umnaya-ferma-svoimi-rukami-etoy-zimoy-stroim-sistemu-kotoraya-vesnoy-vyydet-v-po)
- [How to join Fermozavr DIY, and what we do next](https://fermozavr.ru/samodelki/kak-prisoedinitsya-k-fermozavr-diy-i-chto-my-budem-delat-dalshe)
- [23.47 °C: the bench and the first shopping list](https://fermozavr.ru/samodelki/23-47-c-stend-i-pervyy-spisok-pokupok)
- [23.47 °C: what the screen is actually showing](https://fermozavr.ru/samodelki/23-47-c-chto-na-samom-dele-pokazyvaet-ekran)
- [What the screen is allowed to say while the sensors are still on the way](https://fermozavr.ru/samodelki/chto-ekran-imeet-pravo-skazat-poka-datchiki-v-puti)
- [The page already opens, the sensors are still on the way](https://fermozavr.ru/samodelki/stranitsa-uzhe-otkryvaetsya-datchiki-eshchyo-v-puti)

## How to join

The form stays open for the whole project: [fermozavr.ru/diy](https://fermozavr.ru/diy).

Discussion is in the [Fermozavr](https://t.me/fermozavr) channel. A comment under a post does not replace the form.

The shopping list for the first bench is in the essay on 23.47 °C. The field-node list comes after the tests.

If a letter is easier, send the same note to [info@fermozavr.ru](mailto:info@fermozavr.ru).

## The page

The first node page already opens on this computer. A sensor is not required: a row can be typed in by hand. From the repository folder:

```
python3 station/server.py
```

Then open `http://127.0.0.1:8321`.

There are no extra libraries. Python 3 itself is enough. This repository has no dependency file, and `pip` installs nothing for this page. On Windows the same command is sometimes named `python`.

## What belongs here

Test protocols, parts lists, schematics, and firmware, once they are ready to repeat. The page this starts from is already in `station/`.
