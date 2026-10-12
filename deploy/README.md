# Выкатка

Один скрипт `scripts/deploy.sh` на обоих серверах. Код одинаковый; различаются источник
коммита и то, кто запускает выкатку.

| | Dev | Прод |
|---|---|---|
| Каталог инстанса | `~/deploy/astrofacts-dev` | `/opt/astrofacts` |
| Запуск выкатки | вручную: `scripts/dev.sh deploy` | сам, таймером раз в 5 минут |
| Откуда код | локальный репозиторий, текущий коммит (`HEAD`) | ветка `main` на GitHub (HTTPS, без ключа) |
| Сервис | `astrofacts-dev` | `astrofacts` |
| Адрес | `127.0.0.1:8765` | `127.0.0.1:8765` |

## Как это работает

Каталог инстанса:

```
ephe/                        файлы Swiss Ephemeris, общие для всех релизов
releases/<sha>/              код коммита
venvs/<ключ>/                окружение на версию requirements.lock.txt
current -> releases/<sha>    активный релиз, из него запущен сервис
```

Данных у сервиса нет: ни базы, ни `.env`. Все настройки — в unit-файле.

Шаги одной выкатки:

1. Взять коммит; если он уже активен — выход.
2. Собрать релиз; при изменении `requirements.lock.txt` — новое окружение.
3. Убедиться, что файлы эфемерид на месте и целы; если нет — загрузить (`tools/fetch_ephemeris.py`).
4. Прогнать тесты. Не прошли — релиз удаляется, сервис не трогается.
5. Переключить `current`, перезапустить сервис.
6. 20 секунд наблюдать: сервис активен, не перезапускается и отвечает на `/health`. Иначе — откат.
7. Удалить старые релизы (хранятся последние 5).

Коммит, не прошедший выкатку, повторно не выкатывается до нового коммита (или `--force`).

### Два набора тестов

При выкатке идёт сокращённый набор: сверочные тесты (astropy и ядро JPL) пропускаются, потому
что в окружение сервиса astropy не ставится. Полный набор обязателен на dev:

- `scripts/dev.sh test-full` прогоняет все тесты для `HEAD` без единого пропуска и записывает
  хэш коммита в `.git/astrofacts-full-tests`. При незакоммиченных правках он отказывается
  работать: отметка относится к коммиту, а не к черновику;
- `scripts/dev.sh deploy` и `dry` запускают полный набор сами, если отметки для `HEAD` нет;
- `scripts/deploy.sh` на dev получает `DEPLOY_REQUIRE_STAMP` и не соберёт релиз из коммита
  без отметки, даже если его вызвать в обход `dev.sh`.

На проде этой проверки нет и быть не может (нет astropy). Прод защищает порядок работы:
в `main` попадает только коммит, выкаченный на dev. Технически push непроверенного коммита
в `main` ничто не запрещает.

### Сеть

Сервис в сеть не ходит. Выкатке сеть нужна трижды: получить коммит, поставить зависимости
(только когда меняется `requirements.lock.txt`) и один раз загрузить файлы эфемерид.

Если загрузка эфемерид с сервера недоступна, файлы `sepl_18.se1` и `semo_18.se1` можно положить
в `ephe/` вручную — из https://github.com/aloistr/swisseph/tree/master/ephe. Контрольные суммы
проверяются в любом случае: файл не той версии выкатка и сервис отвергнут.

### pyswisseph

Готового колеса под Python 3.12 на PyPI нет, а компилятора на проде нет и не будет. Колесо
`pyswisseph-2.10.3.2-cp312-cp312-linux_x86_64.whl` собрано заранее; выкатка ищет его в каталоге
`DEPLOY_WHEELS` (по умолчанию `~/wheels`) и из исходников не собирает.

## Команды dev

| Команда | Что делает |
|---|---|
| `scripts/dev.sh test` | тесты черновика в рабочем каталоге |
| `scripts/dev.sh test-full` | полный набор для `HEAD` без пропусков, ставит отметку |
| `scripts/dev.sh deploy` | полный набор (если отметки нет) и выкатка `HEAD` на dev |
| `scripts/dev.sh dry` | то же, но релиз не переключается |
| `scripts/dev.sh rollback` | вернуть предыдущий релиз |
| `scripts/dev.sh status` | активный и предыдущий релизы, состояние сервиса |
| `scripts/dev.sh logs [N]` | журнал сервиса |
| `scripts/dev.sh check` | `/health` работающего сервиса |
| `scripts/dev.sh day ДАТА [TZ] [LOOKAHEAD]` | ответ `/day` |

Выкатывается **коммит**, а не файлы рабочего каталога.

## Установка на dev (один раз, выполняет человек)

Первый релиз уже собран в `~/deploy/astrofacts-dev` (`scripts/dev.sh deploy --no-restart`).

```
# в шаблонах подставляются пользователь, от которого работает сервис, и его домашний каталог
sed -e "s|<USER>|$USER|g" -e "s|<HOME>|$HOME|g" deploy/astrofacts-dev.service \
    | sudo install -m 0644 /dev/stdin /etc/systemd/system/astrofacts-dev.service
sed -e "s|<USER>|$USER|g" deploy/sudoers-astrofacts-dev \
    | sudo install -m 0440 /dev/stdin /etc/sudoers.d/astrofacts-dev
sudo visudo -cf /etc/sudoers.d/astrofacts-dev
sudo systemctl daemon-reload
sudo systemctl enable --now astrofacts-dev
scripts/dev.sh check
```

## Установка на прод (один раз, выполняет человек)

Выполнена 2026-10-12 этими командами; раздел остаётся как инструкция на случай нового сервера.
Перед установкой стоит проверить: Python 3.12 и та же архитектура, что у колеса; свободен
порт 8765; с сервера доступны `github.com`, `raw.githubusercontent.com` и `pypi.org`.

```
# пользователь сервиса и каталог инстанса
sudo useradd --system --home-dir /opt/astrofacts --shell /usr/sbin/nologin astrofacts
sudo mkdir -p /opt/astrofacts/wheels
sudo cp ~/pyswisseph-2.10.3.2-cp312-cp312-linux_x86_64.whl /opt/astrofacts/wheels/

# первый релиз: скрипт берётся из репозитория, дальше он запускается из current
cd /tmp && git clone --depth 1 https://github.com/AndreyLushch/astrofacts.git astrofacts-bootstrap
sudo env HOME=/root DEPLOY_ROOT=/opt/astrofacts \
    DEPLOY_REPO=https://github.com/AndreyLushch/astrofacts.git DEPLOY_REF=main \
    DEPLOY_APP_USER=astrofacts DEPLOY_WHEELS=/opt/astrofacts/wheels \
    /tmp/astrofacts-bootstrap/scripts/deploy.sh --no-restart
rm -rf /tmp/astrofacts-bootstrap

# сервис и таймер выкатки
sudo install -m 0644 /opt/astrofacts/current/deploy/astrofacts.service /etc/systemd/system/
sudo install -m 0644 /opt/astrofacts/current/deploy/astrofacts-deploy.service /etc/systemd/system/
sudo install -m 0644 /opt/astrofacts/current/deploy/astrofacts-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now astrofacts
sleep 3 && curl -s http://127.0.0.1:8765/health    # сервис поднимается около секунды
sudo systemctl start astrofacts-deploy              # пробный запуск: «уже активен — выкатывать нечего»
sudo systemctl enable --now astrofacts-deploy.timer
```

Правки unit-файлов в `/etc` (например, строка `DEPLOY_NOTIFY_CMD`) выкатка не затирает: шаблоны
из `deploy/` копируются в `/etc` только вручную. Обратная сторона — изменение шаблона в
репозитории само на прод не попадает.

Версию базы часовых поясов сервис показывает в `/health` (`tzdata_version`). Она должна
совпадать на dev и проде: обновляется пакетом `tzdata`, после чего сервис нужно перезапустить.

После этого любой push в `main` — выкатка и перезапуск прода в течение ~5 минут.

### Уведомления о выкатке

Своего канала уведомлений у сервиса нет: расчётный слой не должен зависеть от мессенджеров
и прокси. Об исходе выкатки сообщает внешняя команда из `DEPLOY_NOTIFY_CMD` — она лежит вне
этого репозитория и получает текст одним аргументом. Без неё исход виден только
в `journalctl -u astrofacts-deploy`.

Подключение: в `/etc/systemd/system/astrofacts-deploy.service` раскомментировать строку
`Environment=DEPLOY_NOTIFY_CMD=…`, указать путь к своей команде и выполнить
`sudo systemctl daemon-reload`. Проверить команду можно вручную:

```
sudo /путь/к/команде "проверка уведомлений astrofacts"; echo "rc=$?"
```

Неотправленное сообщение выкатку не останавливает.
