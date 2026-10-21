"""Rules for the first Fermozavr node: frost watch and a spray band.

The bars here are the ones written down for the T/RH node: ±0.3 °C and ±3 %RH.
A reading inside the error of a boundary is not treated as a sharp yes or no.
"""

from __future__ import annotations

TEMP_BAR = 0.3
RH_BAR = 3.0
# Above this, humidity is a saturation flag, not a spray-window number.
RH_SATURATION = 95.0
FROST_LOW = 0.0
FROST_HIGH = 2.0
NEAR_ABOVE = 5.0
TREND_MINUTES = 40


def fmt_number(value: float, digits: int) -> str:
    rounded = round(float(value), digits)
    if abs(rounded) < 0.5 * 10 ** (-digits):
        rounded = 0.0
    sign = "−" if rounded < 0 else ""
    body = f"{abs(rounded):.{digits}f}".replace(".", ",")
    return sign + body


def fmt_temp(value: float) -> str:
    return fmt_number(value, 1) + " °C"


def fmt_rh(value: float) -> str:
    return fmt_number(value, 0) + " %"


def temperature_zone(temp: float) -> str:
    if temp < FROST_LOW - TEMP_BAR:
        return "below"
    if temp <= FROST_LOW + TEMP_BAR:
        return "near_zero"
    if temp < FROST_HIGH - TEMP_BAR:
        return "inside"
    if temp <= FROST_HIGH + TEMP_BAR:
        return "near_two"
    return "above"


def trend_of(delta: float | None) -> str:
    if delta is None:
        return "unknown"
    if abs(delta) <= TEMP_BAR:
        return "flat"
    if delta < 0:
        return "down"
    return "up"


def frost_verdict(temp: float, delta: float | None) -> dict[str, str]:
    zone = temperature_zone(temp)
    trend = trend_of(delta)
    title = _frost_title(zone, trend, temp)
    detail = _frost_detail(temp, delta, zone, trend)
    tone = "calm" if zone == "above" and title == "Выше полосы" else "watch"
    return {
        "code": f"{zone}_{trend}",
        "title": title,
        "detail": detail,
        "tone": tone,
    }


def _frost_title(zone: str, trend: str, temp: float) -> str:
    if zone == "below":
        if trend == "down":
            return "Ниже нуля и падает"
        if trend == "up":
            return "Ниже нуля и идёт вверх"
        return "Ниже нуля"
    if zone == "near_zero":
        if trend == "down":
            return "Около нуля и падает"
        return "Около нуля"
    if zone == "inside":
        if trend == "down":
            return "В полосе и падает"
        if trend == "up":
            return "В полосе и идёт вверх"
        if trend == "unknown":
            return "В полосе, хода ещё нет"
        return "В полосе, падения не видно"
    if zone == "near_two":
        if trend == "down":
            return "Около плюс двух и падает"
        return "Около плюс двух"
    if trend == "down" and temp <= NEAR_ABOVE + TEMP_BAR:
        return "Выше полосы, но падает"
    return "Выше полосы"


def _frost_detail(temp: float, delta: float | None, zone: str, trend: str) -> str:
    place = {
        "below": "Это ниже нуля дальше, чем на 0,3 °C.",
        "near_zero": "Это около нуля: при планке ±0,3 °C сам ноль и небольшой плюс здесь неразличимы.",
        "inside": "Это внутри промежутка от 0 до +2 °C, и до обеих границ дальше, чем на 0,3 °C.",
        "near_two": "Это около +2 °C: при планке ±0,3 °C показание может быть ещё внутри полосы или уже выше.",
        "above": "Ночная полоса заморозка: от 0 до +2 °C. Сейчас воздух выше неё.",
    }[zone]
    if trend == "unknown" or delta is None:
        move = "Записи за 40 минут до этой строки нет, поэтому падение не из чего увидеть."
    elif trend == "flat":
        move = (
            f"За 40 минут ход {fmt_temp(delta)}. "
            "Это в пределах планки 0,3 °C, падением такое не считаем."
        )
    elif trend == "down":
        move = f"За 40 минут {fmt_temp(delta)}. Падение больше планки 0,3 °C."
    else:
        move = f"За 40 минут {fmt_temp(delta)}. Температура растёт."
    return f"Сейчас {fmt_temp(temp)}. {place} {move}"


def no_sensor(sensor_ids: list[str]) -> dict[str, str]:
    if not sensor_ids:
        detail = (
            "Строк ещё нет. Стенд и полевой узел присылают их на POST /api/readings. "
            "Пока датчики в пути, строку можно внести вручную внизу страницы."
        )
    else:
        names = ", ".join(sensor_ids)
        detail = (
            f"Уже пишут: {names}. Выберите экземпляр для решения. "
            "Разные модели в одну цифру не усредняем."
        )
    return {
        "code": "no_sensor",
        "title": "Датчик для решения не выбран",
        "detail": detail,
        "tone": "quiet",
    }


def no_reading() -> dict[str, str]:
    return {
        "code": "no_reading",
        "title": "Температуры с выбранного датчика ещё нет",
        "detail": "Решение о заморозке считается по температуре воздуха этого экземпляра.",
        "tone": "quiet",
    }


def sensor_quiet(sensor_id: str, others: list[str]) -> dict[str, str]:
    names = ", ".join(others)
    return {
        "code": "sensor_quiet",
        "title": "Выбранный датчик замолчал",
        "detail": (
            f"{sensor_id} не писал температуру в те минуты, когда писали другие. "
            f"Сейчас есть строки от: {names}. На них решение не переносим."
        ),
        "tone": "quiet",
    }


def stale_verdict(at_time: dict[str, str]) -> dict[str, str]:
    return {
        "code": "stale",
        "title": "Строка устарела",
        "detail": (
            "Последняя температура старше трёх минут. "
            "Для ночи нужна свежая строка: полевой узел пишет раз в минуту."
        ),
        "tone": "quiet",
        "at_time_title": at_time["title"],
        "at_time_detail": at_time["detail"],
    }


def disagreement_verdict(spread: float, *, stale: bool) -> dict[str, str]:
    detail = (
        f"Свежие показания расходятся на {fmt_temp(spread)}. "
        "Планка узла 0,3 °C. Одной температуры воздуха из этого не получается."
    )
    if stale:
        detail += " Строки при этом старше трёх минут."
    return {
        "code": "disagreement",
        "title": "Датчики не сошлись",
        "detail": detail,
        "tone": "watch",
    }


def humidity_disagreement(spread: float) -> dict[str, str]:
    return {
        "code": "disagreement",
        "title": "Датчики влажности не сошлись",
        "detail": (
            f"Свежие показания расходятся на {fmt_rh(spread)}. "
            "Планка узла 3 %. Одну влажность воздуха из этого не получается."
        ),
        "tone": "watch",
    }


def spray_without_air() -> dict[str, str]:
    return {
        "code": "no_air",
        "title": "Полосу обработки сверять не с чем",
        "detail": "Сверять окно обработки можно, когда для решения есть одна температура воздуха.",
        "tone": "quiet",
    }


def spray_blocked() -> dict[str, str]:
    return {
        "code": "disagreement",
        "title": "Полосу обработки сверять нечем",
        "detail": (
            "Температура воздуха с нескольких датчиков не сошлась. "
            "Окно обработки опирается на ту же температуру."
        ),
        "tone": "watch",
    }


def spray_stale() -> dict[str, str]:
    return {
        "code": "stale",
        "title": "Строка для полосы устарела",
        "detail": (
            "Последняя строка старше трёх минут. "
            "Окно обработки смотрят по свежим температуре и влажности."
        ),
        "tone": "quiet",
    }


def spray_verdict(
    temp: float | None,
    rh: float | None,
    temp_min: float | None,
    temp_max: float | None,
    rh_min: float | None,
    rh_max: float | None,
) -> dict[str, str]:
    bounds = (temp_min, temp_max, rh_min, rh_max)
    if any(item is None for item in bounds):
        return {
            "code": "band_incomplete",
            "title": "Полоса обработки не задана",
            "detail": (
                "В требованиях узла это несколько градусов и около 10 % влажности. "
                "Конкретные пороги зависят от работы, в датчике их нет."
            ),
            "tone": "quiet",
        }
    assert temp_min is not None and temp_max is not None
    assert rh_min is not None and rh_max is not None
    if (temp_max - temp_min) <= TEMP_BAR * 2 or (rh_max - rh_min) <= RH_BAR * 2:
        return {
            "code": "band_narrow",
            "title": "Полоса уже погрешности",
            "detail": (
                "Заданная полоса уже планки датчика, ±0,3 °C и ±3 % влажности. "
                "Внутри и снаружи такой полосы показание не различает."
            ),
            "tone": "watch",
        }
    if temp is None:
        return {
            "code": "no_temperature",
            "title": "Температуры для полосы нет",
            "detail": "Полоса задана. Сравнить её пока не с чем.",
            "tone": "quiet",
        }
    if rh is None:
        return {
            "code": "no_humidity",
            "title": "Влажности для полосы нет",
            "detail": (
                f"Температура {fmt_temp(temp)} уже есть. "
                "Окно обработки смотрит ещё и влажность."
            ),
            "tone": "quiet",
        }
    temp_ok = temp_min <= temp <= temp_max
    rh_ok = rh_min <= rh <= rh_max
    band = (
        f"{fmt_number(temp_min, 1)}…{fmt_number(temp_max, 1)} °C и "
        f"{fmt_number(rh_min, 0)}…{fmt_number(rh_max, 0)} %"
    )
    if round(rh) > RH_SATURATION:
        return {
            "code": "near_saturation",
            "title": "Около насыщения",
            "detail": (
                f"Влажность {fmt_rh(rh)}. Выше {fmt_number(RH_SATURATION, 0)} % "
                "процент перестаёт быть решением: это признак насыщения, не окно обработки. "
                f"Полоса задана вами: {band}."
            ),
            "tone": "watch",
        }
    if temp_ok and rh_ok:
        return {
            "code": "inside",
            "title": "Внутри заданной полосы",
            "detail": f"Температура {fmt_temp(temp)}, влажность {fmt_rh(rh)}. Полоса задана вами: {band}.",
            "tone": "calm",
        }
    reasons: list[str] = []
    if temp < temp_min:
        reasons.append(f"температура {fmt_temp(temp)} ниже заданных {fmt_temp(temp_min)}")
    elif temp > temp_max:
        reasons.append(f"температура {fmt_temp(temp)} выше заданных {fmt_temp(temp_max)}")
    if rh < rh_min:
        reasons.append(f"влажность {fmt_rh(rh)} ниже заданных {fmt_rh(rh_min)}")
    elif rh > rh_max:
        reasons.append(f"влажность {fmt_rh(rh)} выше заданных {fmt_rh(rh_max)}")
    return {
        "code": "outside",
        "title": "Вне заданной полосы",
        "detail": f"{'; '.join(reasons)}. Полоса задана вами: {band}.",
        "tone": "watch",
    }
