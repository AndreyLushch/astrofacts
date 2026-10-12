# Руководство для потребителей

Как обращаться к astrofacts из другого сервиса.

## Правила границы

- Только HTTP и JSON. Код astrofacts не импортируется, общих модулей и клиентской библиотеки нет.
- Модели для разбора ответа потребитель пишет у себя — по этому документу или по JSON Schema
  из `GET /openapi.json`. Копировать `schema.py` из этого репозитория в закрытый код нельзя:
  файл под AGPL.
- Сервис слушает `127.0.0.1:8765` на той же машине. Аутентификации нет.

## Запрос

    GET http://127.0.0.1:8765/day?date=2026-10-23&tz=Europe/Moscow&lookahead=6&schema=1

| Параметр | Обязателен | |
|---|---|---|
| `date` | да | локальная дата, `ГГГГ-ММ-ДД`, от 1800-02-01 до 2399-11-30 |
| `tz` | да | таймзона IANA (`Europe/Moscow`); фиксированные смещения не принимаются как замена зоне |
| `lookahead` | нет | окно опережения после конца суток, часы, от 0 до 24; по умолчанию 0 |
| `schema` | нет, но передавайте всегда | версия схемы, под которую написан потребитель; сейчас `1` |

Зачем `lookahead`. Прогноз на завтра, который публикуется вечером, должен знать об аспекте,
точном в 01:00 послезавтра: `lookahead=6` добавит такие события с пометкой `beyond_day: true`.
Запрос «что будет 23-го» от пользователя — обычные сутки, `lookahead` не нужен.

Первый запрос даты считается около 0,2–0,3 с, повторный отдаётся из кеша за миллисекунды.
Кеш живёт в памяти процесса и сбрасывается при перезапуске сервиса.

## Ошибки

Тело ошибки всегда одного вида: `{"error": "<код>", "detail": "<текст>"}`.

| Статус | Код | Что делать |
|---|---|---|
| 409 | `schema_version_mismatch` | сервис отдаёт другую версию схемы (в `supported_schema_versions` — какие); потребителя нужно обновить, повтор не поможет |
| 422 | `missing_parameter`, `invalid_date`, `date_out_of_range`, `unknown_timezone`, `invalid_lookahead` | ошибка в запросе; повтор не поможет |
| нет ответа | — | сервис не запущен; потребитель должен завершить свою операцию ошибкой, а не подставлять выдуманные данные |

Проверка версии: передавайте `schema=1` в запросе **и** сверяйте `schema_version` в ответе.

## Ответ

Сокращённый настоящий ответ на запрос выше (в `bodies`, `houses`, `today` оставлено по два
элемента, в `signs` — один знак из двенадцати):

```json
{
  "schema_version": 1,
  "meta": {
    "date": "2026-10-23",
    "tz": "Europe/Moscow",
    "day_start": "2026-10-23T00:00:00+03:00",
    "day_end": "2026-10-24T00:00:00+03:00",
    "day_length_hours": 24.0,
    "lookahead_hours": 6.0,
    "config_hash": "5f15d2aa7f7e",
    "tzdata_version": "2026c",
    "service_version": "0.1.0"
  },
  "bodies": [
    {
      "body": "sun",
      "sign_at_start": "libra",
      "sign_at_end": "scorpio",
      "retrograde_at_start": false,
      "retrograde_at_end": false
    },
    {
      "body": "moon",
      "sign_at_start": "pisces",
      "sign_at_end": "aries",
      "retrograde_at_start": false,
      "retrograde_at_end": false
    }
  ],
  "moon": {
    "phase": {
      "name": "waxing_gibbous",
      "waxing": true,
      "illumination_pct_start": 87,
      "illumination_pct_end": 93
    },
    "ingress": {
      "from_sign": "pisces",
      "to_sign": "aries",
      "when": {
        "at": "2026-10-23T22:53:00+03:00",
        "beyond_day": false
      }
    },
    "void_of_course": [
      {
        "start": "2026-10-23T06:31:00+03:00",
        "end": "2026-10-23T22:53:00+03:00",
        "starts_before_day": false,
        "ends_after_day": false,
        "sign": "pisces",
        "next_sign": "aries",
        "last_aspect": {
          "body": "mercury",
          "aspect": "trine"
        }
      }
    ],
    "aspects": [
      {
        "body_a": "moon",
        "body_b": "mercury",
        "aspect": "trine",
        "when": {
          "at": "2026-10-23T06:31:00+03:00",
          "beyond_day": false
        },
        "slow_pair": false
      }
    ]
  },
  "exact_aspects": [],
  "ingresses": [
    {
      "body": "sun",
      "from_sign": "libra",
      "to_sign": "scorpio",
      "retrograde": false,
      "when": {
        "at": "2026-10-23T12:37:00+03:00",
        "beyond_day": false
      }
    }
  ],
  "stations": [
    {
      "body": "mercury",
      "direction": "retrograde",
      "sign": "scorpio",
      "when": {
        "at": "2026-10-24T10:12:00+03:00",
        "beyond_day": true
      },
      "days_ahead": 1
    }
  ],
  "lunations": [],
  "background": {
    "sun": {
      "at_start": {
        "sign": "libra",
        "degree": 29
      },
      "at_end": {
        "sign": "scorpio",
        "degree": 0
      }
    },
    "retrograde": [
      "venus",
      "saturn",
      "uranus",
      "neptune"
    ],
    "slow_aspects": [
      {
        "body_a": "uranus",
        "body_b": "neptune",
        "aspect": "sextile",
        "orb_deg": 2.7,
        "state": "applying",
        "generational": true
      },
      {
        "body_a": "uranus",
        "body_b": "pluto",
        "aspect": "trine",
        "orb_deg": 1.9,
        "state": "applying",
        "generational": true
      },
      {
        "body_a": "neptune",
        "body_b": "pluto",
        "aspect": "sextile",
        "orb_deg": 0.8,
        "state": "separating",
        "generational": true
      }
    ]
  },
  "signs": {
    "scorpio": {
      "houses": [
        {
          "body": "sun",
          "house_at_start": 12,
          "house_at_end": 1
        },
        {
          "body": "moon",
          "house_at_start": 5,
          "house_at_end": 6
        }
      ],
      "ruler": {
        "body": "pluto",
        "sign_at_start": "aquarius",
        "sign_at_end": "aquarius",
        "house_at_start": 4,
        "house_at_end": 4,
        "retrograde_at_start": false,
        "retrograde_at_end": false
      },
      "today": [
        {
          "kind": "house_ingress",
          "body": "sun",
          "from_house": 12,
          "to_house": 1,
          "when": {
            "at": "2026-10-23T12:37:00+03:00",
            "beyond_day": false
          },
          "involves_ruler": false
        },
        {
          "kind": "exact_aspect",
          "body_a": "moon",
          "house_a": 6,
          "body_b": "pluto",
          "house_b": 4,
          "aspect": "sextile",
          "when": {
            "at": "2026-10-24T04:21:00+03:00",
            "beyond_day": true
          },
          "slow_pair": false,
          "involves_ruler": true
        }
      ]
    }
  }
}
```

### Общая часть

| Поле | Содержание |
|---|---|
| `meta` | дата, зона, границы суток с офсетами, длина суток (23/24/25 ч), окно опережения, хэш конфигурации расчёта |
| `bodies` | для каждого тела: знак и попятность на начало и конец суток |
| `moon.phase` | название фазы, растёт ли Луна, процент освещённости на начало и конец суток |
| `moon.ingress` | смена знака Луной в эти сутки или `null` |
| `moon.void_of_course` | интервалы Луны без курса, пересекающие сутки; `starts_before_day` / `ends_after_day` показывают, что интервал выходит за их границы |
| `moon.aspects` | точные аспекты Луны |
| `exact_aspects` | точные аспекты остальных пар |
| `ingresses` | смены знака остальными телами |
| `stations` | развороты планет от этих суток на 7 дней вперёд; `days_ahead: 0` — сегодня |
| `lunations` | новолуние или полнолуние в эти сутки, с затмением, если оно есть |
| `background.sun` | знак и целый градус Солнца на начало и конец суток |
| `background.retrograde` | тела в попятном движении на начало суток |
| `background.slow_aspects` | аспекты медленных планет в орбе |

### Проекция на знак: `signs[<знак>]`

| Поле | Содержание |
|---|---|
| `houses` | солярный дом каждого тела на начало и конец суток (знак принят за первый дом) |
| `ruler` | управитель знака: где стоит, в каком доме, попятен ли |
| `today` | события этих суток, разложенные по домам знака; тип события — в поле `kind` |

Виды событий в `today`: `house_ingress` (тело перешло в другой дом), `exact_aspect`,
`station`, `lunation`. Набор полей у каждого вида свой и фиксированный — по `kind` можно
строить проверку.

### Четыре пометки, которые нельзя игнорировать

- **`beyond_day`** — событие случится после конца запрошенных суток. В тексте про «сегодня»
  его нельзя подавать как сегодняшнее.
- **`slow_pair`** — аспект двух медленных планет. Время у него есть, но конфигурация почти
  не меняется несколько суток: писать «в 19:53 произойдёт» про соединение Сатурна с Нептуном —
  ложная точность.
- **`generational`** — фоновый аспект, который держится годами и одинаков изо дня в день.
  Если вставлять его в каждый текст, прогнозы станут неотличимы.
- **`involves_ruler`** — событие затрагивает управителя знака, для этого знака оно весомее.

### Чего в ответе нет

Абсолютных долгот в градусах и аспектов вне орба — намеренно. Положение передаётся знаком
и домом. Если потребителю (в том числе LLM) не хватает данных, их нужно добавить в сервис,
а не вычислять на стороне потребителя.

## Что сверено с внешним источником

| Что | Чем подтверждено |
|---|---|
| Положения тел, моменты ингрессий и аспектов | независимый расчёт (astropy/ERFA, ядро JPL DE432s), расхождение — доли угловой секунды |
| Конвенция Луны без курса и запись времени | вручную с astro-seek.com, две точки (`tests/manual/astroseek.toml`) |
| Затмения 2026 года, мартовское равноденствие 2026 | общеизвестные опубликованные моменты, совпадение до минуты |
| Моменты станций | только две собственные реализации; с внешним источником не сверены |
| Интервал без курса, когда Луна не делает в знаке ни одного аспекта | не сверен; это решение проекта, а не внешняя конвенция |
