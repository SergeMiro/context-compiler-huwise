# Context Compiler — план разработки для ИИ-агента (v4, 09.11.2026)

Заменяет v3 и `context-compiler-design.md`. Документ написан так, чтобы ИИ-агент (Claude Code, Codex)
мог взять его и строить проект задача за задачей без дополнительных вопросов. Демо — собеседование
с командой Context в Huwise, **пятница 13.11, 10:00**.

---

## 0. Что строим (одним абзацем)

Сервис, который берёт портал данных Huwise/Opendatasoft (Explore API v2.1), компилирует каждый набор
в короткую **карточку контекста** для ИИ-агента, раскладывает их в Elasticsearch (поиск) и Neo4j
(связи между наборами), отдаёт агентам через **MCP-сервер** с тремя инструментами и **доказывает
цифрами** на контрольных вопросах, что агент с карточками отвечает лучше, чем с «голым» доступом.
Цикл улучшения предлагает правки карточек и оставляет только те, после которых оценка не упала.

Портал для разработки и демо: `data.education.gouv.fr` (Минобразования Франции, работает на Huwise).

## 1. Правила для агента-исполнителя

1. Репозиторий `SergeMiro/context-compiler-huwise` (public). На VPS единственная рабочая копия —
   `/home/sergiy_prod/context-compiler-huwise`. Не клонировать в другие папки.
2. Перед каждой задачей: `git status`. Чужие незакоммиченные правки не трогать.
3. Ветки: `prod` (стабильная, по умолчанию на GitHub) ← `preprod` (проверенная) ← `dev` (интеграция) ←
   `feat/t<N>-<имя>` (одна задача). Задача делается в своей ветке от `dev`; каждый законченный кусок
   функционала — коммит `T<N>: <что сделано>` и push. Готовая задача — `git merge --no-ff` в `dev`, push,
   ветку задачи удалить. В конце каждого этапа (§12) `dev` → `preprod` → `prod` только fast-forward,
   после зелёного `manage.py test` на `preprod`. Коммит только при зелёных тестах.
4. Минимум кода. Не добавлять слоёв, опций и абстракций, которых нет в этом плане. Новая зависимость —
   только из списка §4.
5. **На горячем пути (MCP-инструменты) нет вызовов LLM.** LLM вызывается только командами `eval` и `improve`.
6. **Модель не выбрана.** Никаких имён провайдеров и моделей в коде. Только адаптер §6 с переменными
   окружения. Пока модель не задана, всё, что требует LLM, тестируется на `FakeLLM`.
7. Тесты не ходят в сеть: Explore API — через записанные фикстуры; ES и Neo4j — живые контейнеры
   на 127.0.0.1 (тесты помечены и используют отдельные индекс/портал `test-*`, за собой чистят).
8. Секретов в git нет. `.env` в `.gitignore`, в репозитории — `.env.example`.
9. Задача закрыта, когда выполнены **все** её критерии приёмки из этого плана, и результат проверки
   (вывод команды) записан в тело коммита.
10. Если критерий не выполняется за разумное время — не обходить, а записать в `NOTES.md`
    («что не вышло, почему, что пробовал») и перейти к следующей задаче, если она не зависит от этой.

## 2. Факты о Explore API (проверены 09.11 на живом портале)

| Факт | Следствие для кода |
|---|---|
| `GET /api/explore/v2.1/catalog/exports/json` отдаёт **весь каталог одним запросом**: 314 наборов, 6 976 полей, 527 КБ, ~1 с | полный скан = 1 запрос; на 5000 порталов = 5000 запросов |
| `GET /catalog/datasets?where=modified>'2026-11-05'&order_by=modified asc&limit=100&offset=…` работает | инкрементальный скан по курсору `Portal.scan_cursor` |
| В `select` нельзя писать `metas.default.modified` → ошибка; можно `select=dataset_id,modified` | в инкременте выбирать плоские имена |
| Ответы сжаты gzip | `httpx` распаковывает сам; в curl нужен `--compressed` |
| Заголовки `X-RateLimit-Limit: 50000`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (сутки, на домен) | сканер читает `Remaining` и останавливается, если < 10 % лимита |
| `cache-control: public, max-age=60` | кешировать ответы `query` не дольше 60 с |
| Плохой ODSQL → HTTP 400 `{"error_code":"ODSQLError","message":"…Unknown field: foo…"}` | валидатор — первая линия, API — вторая; ошибку API отдавать агенту как есть |
| `metas.default`: title, description (**HTML**), theme[], keyword[], license, publisher, modified, update_frequency, records_count, federated, source_domain, source_dataset | description чистить от HTML |
| `fields[]`: name, label, type, description (часто `null`) | у полей описания почти всегда пустые — это и есть дыра, которую закрывает карточка |
| Частые ключи: `uai` (79 наборов), `code_academie` (68), `code_departement` (59), `code_region` | связи наборов через ключи |
| **`code_departement` хранится как `'021'`, а не `'21'`** (Côte-d'Or) | идеальный пример для демо: «голый» агент пишет `'21'` и получает 0 |
| `select=count(*) as n` без `group_by` возвращает странные повторы | число строк брать как `total_count` при `limit=0` |
| Из 8 федеративных наборов ни у одного нет `source_domain` | на этом портале lineage из метаданных пустой; DERIVED_FROM — только ручной (`Transformation`) |

Контрольная проверка: `fr-en-annuaire-education`, `where=code_departement='021' and type_etablissement='Collège' and statut_public_prive='Public'` → `total_count = 58`.

## 3. Архитектура

```
ХОЛОДНЫЙ ПУТЬ (команды / Celery; здесь и только здесь бывает LLM)
  Explore API ─scan─▶ Portal · Dataset · Field  (БД — единственный источник правды)
                          │ compile (детерминированно)
                          ▼
                       Card (версии)  ◀── kept ContextEdit
                          │ project
             ┌────────────┼──────────────┐
             ▼            ▼              ▼
          ES `cards`   Neo4j          export: llms.txt + <id>.md
  eval:    EvalCase → агент (LLM) → EvalRun/EvalResult
  improve: провалы → LLM предлагает ContextEdit → compile → eval → kept | reverted

ГОРЯЧИЙ ПУТЬ (MCP, без LLM, без записи в БД кроме ToolCall)
  find_dataset(question)  → ES (filter+routing по порталу) → короткие карточки top-5
  explain_dataset(id)     → полная карточка + связи из Neo4j
  query(id, odsql)        → валидатор → Explore API (ключ клиента насквозь, limit ≤ 100)
```

Границы модулей (агент их не нарушает):
- `sources/explore.py` знает только HTTP и модели. Не знает ES/Neo4j/LLM.
- `context/compile.py` читает модели, пишет `Card`. Не знает HTTP/ES/Neo4j.
- `projections/es.py`, `projections/graph.py` читают `Card`/`Field`, пишут в свой стор. Перестраиваются с нуля командой.
- `tools.py` — три функции горячего пути. MCP-сервер и eval-агент вызывают **одни и те же** функции.
- `llm.py` — единственное место с HTTP к модели.

## 4. Стек и зависимости

Python 3.12, `.venv` в корне репозитория. База: Django 5.2.19, djangorestframework 3.16.1,
elasticsearch 8.19.3, neo4j 5.28.8. Контейнеры (только 127.0.0.1): ES 8.15.3 (:9200), Neo4j 5.26 (:7687) — `docker-compose.yml`.

Добавить (закрепить точные версии в `requirements.txt`, все пакеты — с версией старше двух недель):
- `httpx` — клиент Explore API и LLM-адаптер;
- `mcp` — официальный Python SDK (FastMCP, транспорт streamable HTTP);
- `celery` — фоновые задачи, брокер **RabbitMQ** (как у Huwise);
- `mysqlclient` — драйвер **MariaDB** (как у Huwise; нужны `libmariadb-dev` и `pkg-config`);
- больше ничего. Токены считаем приближённо (`len(text) // 4`), YAML не нужен (JSON), HTML чистим `html.parser` из stdlib.

Стек — строго технологии Huwise: Django/DRF, MariaDB 11.4, Celery + RabbitMQ 4.1, Elasticsearch 8, Neo4j 5.
Redis не используем: блокировки — `GET_LOCK` в MariaDB, кеш карточек — в процессе.
Свободной памяти на VPS ~8 ГБ, стенд занимает ~2,2 ГБ.

## 5. Структура кода (итог)

```
context-compiler-huwise/
  requirements.txt  .env.example  NOTES.md  README.md
  context/            settings.py (читает env), urls.py, celery.py
  catalog/            models.py (Portal, Dataset, Field, Transformation), admin.py, tests/
  sources/            explore.py (ExploreSource), keys.py (словарь ключей и PII-полей)
  ctx/                models.py (Card, ContextEdit, ToolCall), compile.py, export.py, admin.py
  projections/        es.py, graph.py
  tools.py            find_dataset / explain_dataset / query + odsql.py (валидатор)
  llm.py              адаптер + FakeLLM
  evals/              models.py (EvalCase, EvalRun, EvalResult), agent.py, runner.py, improve.py,
                      golden/education.json, admin.py
  mcpserver.py        FastMCP-обёртка над tools.py
  */management/commands/  scan, compile, project, export_llms, golden_refresh, eval, improve, mcp, bench
  tests/fixtures/     catalog-education.json (обрезанный экспорт: 15 наборов), records-*.json
```

Приложение `ctx`, а не `context`: имя `context` уже занято пакетом настроек.

## 6. LLM-адаптер (модель выберем потом)

`llm.py`, ~60 строк:

```python
class LLMNotConfigured(RuntimeError): ...

def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0) -> dict:
    """OpenAI-совместимый POST {CTXC_LLM_BASE_URL}/chat/completions. Возвращает message (content, tool_calls)."""
```

- Переменные: `CTXC_LLM_BASE_URL`, `CTXC_LLM_API_KEY`, `CTXC_LLM_MODEL`, `CTXC_LLM_TIMEOUT=60`.
  Любой из первых трёх пуст → `LLMNotConfigured("задайте CTXC_LLM_* в .env")`.
- Ретраи: 3 попытки на 429/5xx с паузой 2/4/8 с. Остальные ошибки — наверх.
- Каждый вызов пишет в лог: модель, токены (`usage`), мс. Без текста сообщений.
- `FakeLLM(script: list[dict])` — отдаёт заранее заданные ответы по очереди; подменяется в тестах
  через `override_settings(CTXC_LLM="fake")` или аргумент функции.
- Формат tool calling — OpenAI (`tools=[{"type":"function","function":{…}}]`). Почти все провайдеры
  его поддерживают; если выбранная модель не умеет — это решение принимает владелец проекта, не агент.

## 7. Задачи

Формат каждой: **цель → что сделать → критерии приёмки → тесты**. Порядок — по номерам.
Оценка времени — для агента с работающим окружением.

### T0. Окружение (30 мин)
- `requirements.txt` с точными версиями (текущие 4 пакета + httpx, mcp, celery, mysqlclient); установить в `.venv`.
- `docker-compose.yml`: MariaDB (127.0.0.1:3307, init даёт права на `test_ctxc`), RabbitMQ (:5673), ES (:9200), Neo4j (:7687), у всех healthcheck.
- `settings.py` читает env (`os.environ.get` с дефолтами для стенда): `ES_URL`, `NEO4J_URL`, `NEO4J_AUTH`,
  `DB_*`, `CELERY_BROKER_URL`, `CTXC_LLM_*`, `CTXC_SCAN_BUDGET_PCT=5`. `.env.example` со всеми ключами, `.env` в `.gitignore`.
- Подключить `django.contrib.admin`, `sessions`, `messages`, `staticfiles`, шаблоны — понадобятся в T14.

Приёмка: `manage.py check` без ошибок; `docker compose ps` — 3 контейнера healthy; старые тесты зелёные.

### T1. Модели и миграции (1 ч)
Проект с нуля: миграции генерируются под MariaDB. `Transformation` — ручной lineage.

| Модель | Поля | Ограничения |
|---|---|---|
| `Portal` | `domain` (unique), `title`, `scan_cursor` (datetime, null), `llm_budget_per_day` (int, 50), `created_at` | |
| `Dataset` | `portal` FK, `dataset_id`, `title`, `description` (чистый текст), `themes` JSON, `keywords` JSON, `license`, `publisher`, `update_frequency`, `records_count`, `modified`, `federated`, `source_domain`, `source_dataset`, `raw_metas` JSON | unique (`portal`, `dataset_id`); index (`portal`, `modified`) |
| `Field` | `dataset` FK, `name`, `label`, `type`, `description`, `sample_values` JSON (≤ 10), `is_key`, `is_pii` | unique (`dataset`, `name`) |
| `Transformation` | как сейчас (`source`, `target`, `kind`) | |
| `Card` (ctx) | `dataset` FK, `version`, `short`, `full`, `tokens_short`, `tokens_full`, `content_hash`, `created_at` | unique (`dataset`, `version`) |
| `ContextEdit` (ctx) | `dataset` FK, `kind` (`description`/`synonyms`/`query_template`/`note`), `before`, `after`, `source` (`llm`/`human`), `status` (`proposed`/`kept`/`reverted`/`rejected`), `eval_before` JSON, `eval_after` JSON, `rationale`, `created_at`, `decided_at` | |
| `ToolCall` (ctx) | `portal` FK, `tool`, `ms`, `ok`, `error_code`, `ts` | index (`portal`, `ts`); текст запроса не хранить |
| `EvalCase` (evals) | `portal` FK, `slug` (unique в портале), `question`, `expected_dataset`, `reference_odsql` JSON (`select`, `where`, `group_by`), `expected_value`, `tolerance` (0.05), `tags` JSON | |
| `EvalRun` (evals) | `portal`, `mode` (`naked`/`compiled`), `model`, `card_versions` JSON, `metrics` JSON, `started_at`, `finished_at` | |
| `EvalResult` (evals) | `run` FK, `case` FK, `found_dataset`, `odsql_valid_first_try`, `answer`, `answer_ok`, `steps`, `ms`, `tokens`, `transcript` JSON | |

Приёмка: `makemigrations --check` пуст; `migrate` на чистой БД проходит; тест на уникальность (`portal`, `dataset_id`).

### T2. Сканер `ExploreSource` (2 ч)
- `ExploreSource(domain, api_key=None)`: `full()` — 1 запрос `catalog/exports/json`; `since(cursor)` — постраничный
  `catalog/datasets?where=modified>'…'&order_by=modified asc`, затем для изменившихся — `catalog/datasets/{id}` (поля).
- `scan(portal, full=False)`: если `scan_cursor` пуст или `full` → полный скан; иначе инкремент.
  Upsert `Dataset` и `Field` в одной транзакции на набор; при полном скане удалить наборы, которых больше нет.
  Курсор = максимум `modified` из ответа, обновляется **после** коммита.
- HTML описаний → текст (`html.parser`), схлопнуть пробелы, обрезать до 4 000 символов.
- `keys.py`: `KEY_FIELDS` = `uai`, `identifiant_de_l_etablissement` (→ `uai`), `code_commune`, `code_insee`,
  `code_postal`, `code_departement`, `code_academie`, `code_region`, `code_region_academique`, `siret`, `siren`, `annee`,
  `rentree_scolaire`; `PII_PATTERNS` = `nom`, `prenom`, `email`, `mail`, `telephone`, `tel`, `adresse`, `fax`, `date_naissance`
  (`nom_etablissement` и `nom_commune` — **не** PII: проверять целым словом, белый список).
- Примеры значений: только для `is_key` или полей `text` с кардинальностью < 50 (запрос
  `records?select=<f>,count(*)&group_by=<f>&order_by=count(*) desc&limit=10`); только для наборов, где
  поле новое или `modified` вырос; никогда для `is_pii`. Бюджет: не больше `CTXC_SCAN_BUDGET_PCT` от
  `X-RateLimit-Limit`; при `Remaining` < 10 % — остановиться и записать в лог.
- Команда `manage.py scan <domain> [--full] [--no-samples]`, печатает: наборов новых/изменённых/удалённых, полей, запросов, секунд.

Приёмка (живой прогон): `scan data.education.gouv.fr --full` → 314 наборов (± новые), ~6 976 полей, < 120 с
с примерами; повторный `scan` без `--full` делает ≤ 3 запросов, если ничего не менялось.
Тесты (фикстуры, `httpx.MockTransport`): полный скан создаёт N наборов; инкремент обновляет только изменившиеся;
удалённый набор исчезает при полном; HTML вычищен; PII-поле не получает примеров; курсор не двигается при ошибке.

### T3. Компиляция карточек (2 ч)
`ctx/compile.py`, функция `compile_dataset(ds) -> Card | None` (None — если текст не изменился, сравнение по `content_hash`).

Короткая карточка (≤ 400 токенов) — шаблон строго такой:
```
## {dataset_id} — {title}
{1–2 предложения: description, обрезанный по предложению}
{records_count} строк · обновлён {modified:%d.%m.%Y} ({update_frequency}) · {license} · {publisher}
Ключи: {is_key поля через запятую}
Поля: {до 12 полей: name (label)}
Синонимы: {из kept ContextEdit kind=synonyms}
```
Полная (≤ 1 500 токенов): всё из короткой + каждое поле `name · type · label · description · примеры`,
шаблоны ODSQL (из `query_template`), заметки (`note`, например «code_departement — три цифры: '021'»),
связи (заполняет `explain_dataset` из Neo4j на лету, в карточке не хранить), ограничения (limit ≤ 100).

Бюджет: при превышении резать поля в порядке: сначала оставить ключи, поля из шаблонов и заметок, затем по
порядку в схеме; последняя строка `… ещё N полей: explain_dataset`.
Команда `manage.py compile <domain>` → «скомпилировано X, без изменений Y».

Приёмка: все 314 наборов скомпилированы; `max(tokens_short) ≤ 400`, `max(tokens_full) ≤ 1500`;
повторный `compile` даёт «без изменений 314».
Тесты: детерминизм (два прогона — один hash); бюджет на наборе с 71 полем; kept-правка попадает в карточку,
reverted — нет; PII-примеров в карточке нет.

### T4. Проекция в Elasticsearch (1,5 ч)
Переиспользовать подход из текущего `catalog/search.py` (версионный индекс + алиас). Индекс `cards`:
`portal` keyword, `dataset_id` keyword, `title` text(french)^3, `synonyms` text(french)^3, `keywords` text^2,
`description` text(french), `field_labels` text(french), `themes` keyword, `modified` date, `short` (не индексируется, `index: false`).
- Запись и поиск — всегда с `routing=portal.domain`; запрос всегда с `filter: term portal`.
- `project_es(portal)` — полная пересборка через алиас; `upsert_es(card)` — одна карточка.
- `search(portal, q, k=5)` → `[{dataset_id, title, score, short}]`; `multi_match` `best_fields` + `fuzziness: AUTO`.

Приёмка: `project` по 314 карточкам < 10 с; запрос «collèges publics Côte-d'Or» даёт `fr-en-annuaire-education` в top-3.
Тесты: изоляция тенантов (два портала, одинаковый текст — поиск по A не видит B); пересборка не теряет алиас.

### T5. Проекция в Neo4j (1,5 ч)
Модель графа — **линейная по размеру**, без попарных рёбер:
`(:Dataset {portal, dataset_id, title})-[:HAS_KEY]->(:Key {name})`, `(:Dataset)-[:DERIVED_FROM {kind}]->(:Dataset)`.
«Можно соединить» = два шага через общий `Key`, а не ребро на каждую пару (на `uai` это 79 рёбер вместо 3 081).
- Ограничения: unique (`portal`, `dataset_id`) на `:Dataset`, unique `name` на `:Key`.
- `project_graph(portal)`: `UNWIND` пакетами по 500, `MERGE`, параметры, удалить узлы портала, которых нет в БД.
- `joinable(portal, dataset_id, limit=10)` → наборы с общими ключами, отсортированы по числу общих ключей.
- `lineage(portal, dataset_id)` → upstream/downstream глубиной ≤ 5 (код из текущего `graph.py`).

Приёмка: `fr-en-annuaire-education` → не меньше 10 связанных наборов по `uai`/`code_departement`; запрос < 50 мс.
Тесты: изоляция порталов; идемпотентность (два `project_graph` — то же число узлов и рёбер).

### T6. Валидатор ODSQL (2 ч)
`tools/odsql.py`, функция `validate(fields: set[str], params: dict) -> dict` (возвращает очищенные параметры
или бросает `ODSQLRejected(reason)`). Полный парсер ODSQL не писать.
- Разрешённые ключи: `select`, `where`, `group_by`, `order_by`, `limit`, `offset`. Остальное — отказ.
- Токенизатор: строки в одинарных кавычках (с `\'`), числа, идентификаторы, операторы, скобки, запятые.
- Идентификатор, который не ключевое слово ODSQL (`and or not in like is null as asc desc count sum avg min max
  year month day date_format search suggest within_distance in_bbox now true false distinct`) и не вызов функции,
  обязан быть в `fields` или быть алиасом из `select … as x`. Иначе — `unknown field: X; известные похожие: …` (difflib, 3 варианта).
- Запрещено: `;`, комментарии `--`/`/*`, обратные кавычки, длина параметра > 1 000 символов.
- `limit` по умолчанию 20, максимум 100; `offset` ≤ 10 000.

Приёмка/тесты (таблица ≥ 20 случаев): валидный count, `group_by`, `like`, `in (…)`; поле с ошибкой в имени →
подсказка; `' or 1=1 --`; `limit=10000` → 100; лишний параметр `apikey`; поле из другого набора; строка с
экранированной кавычкой внутри (не ломает токенизатор).

### T7. Инструменты и MCP-сервер (2,5 ч)
`tools.py` — три функции, они же — инструменты агента в eval:
- `find_dataset(portal, question, k=5)` → `[{dataset_id, title, short}]`.
- `explain_dataset(portal, dataset_id)` → `full` + `joinable` + `lineage`. Неизвестный id → ошибка с похожими id.
- `query(portal, dataset_id, params, api_key=None)` → валидатор → `GET …/records` → `{total_count, results}`.
  Ошибка API (`ODSQLError`) возвращается агенту текстом. Таймаут 10 с.
- Каждый вызов пишет `ToolCall` (tool, ms, ok, error_code). Кеш карточек — `functools.lru_cache` по
  (`dataset_id`, `version`); `shortcut:` кеш в процессе; при нескольких серверах — общий кеш (их выбор).

«Голый» набор для сравнения (как 4 общих инструмента их MCP) — в том же файле, только для eval:
`naked_search(portal, question)` → title + первые 300 символов описания (ES по `title`/`description`, без синонимов и полей);
`naked_get(portal, dataset_id)` → сырые `raw_metas` + список полей name/type; `naked_query` — `query` **без** валидатора.

`mcpserver.py`: FastMCP, транспорт streamable HTTP, `127.0.0.1:8796`. Портал — из заголовка `X-Domain`
(как у Huwise), иначе аргумент `portal`; `X-Apikey` — насквозь в `query`, не логировать, не хранить.
Rate limit на портал: 10 вызовов/с (token bucket в памяти; `shortcut:` общий счётчик при нескольких серверах).
Команда `manage.py mcp`.

Приёмка: скрипт-клиент на `mcp` SDK перечисляет 3 инструмента и проходит сценарий
«найти → объяснить → посчитать коллежи» → 58. `manage.py bench <domain>` (200 вызовов `find`/`explain`):
p95 `find` < 100 мс, `explain` < 50 мс — вывод в коммит.
Тесты: портал из заголовка важнее аргумента; чужой портал не видит наборов; `ToolCall` без текста запроса.

### T8. Экспорт `llms.txt` (40 мин)
`manage.py export_llms <domain> <out_dir>` → `llms.txt` (заголовок портала, по строке на набор: `- [title](datasets/<id>.md): первое предложение`)
и `datasets/<id>.md` (полная карточка). Детерминированно.
Приёмка: 314 файлов + `llms.txt`; повторный экспорт не меняет ни байта. Тест на 3 наборах.

### T9. Celery (1 ч)
`context/celery.py`, брокер RabbitMQ. Задачи: `scan_portal(domain)` → после коммита (`transaction.on_commit`) →
`compile_portal` → `project_portal` (ES + Neo4j только для изменившихся карточек). Блокировка «один скан на портал»
через `SELECT GET_LOCK('scan:<domain>', 0)` в MariaDB (снимается сам при обрыве соединения). `acks_late=True`, ретраи с backoff на сетевые ошибки.
Beat: `scan_all` раз в час ставит `scan_portal` для каждого портала с разносом по минутам (hash домена % 60).
В тестах `CELERY_TASK_ALWAYS_EAGER=True`.
Приёмка: `celery -A context worker -B` + `scan_portal.delay('data.education.gouv.fr')` → в логе цепочка из 3 задач;
второй одновременный запуск пропущен блокировкой. Тест на блокировку.

### T10. LLM-адаптер (40 мин)
По §6. Тесты: без env → `LLMNotConfigured`; `FakeLLM` отдаёт tool_call и текст; ретрай на 429 (через `httpx.MockTransport`).

### T11. Контрольные вопросы (2 ч)
`evals/golden/education.json`, **30 вопросов по-французски**, как спросил бы живой человек. Для каждого:
`slug`, `question`, `expected_dataset`, `reference_odsql`, `tolerance`, `tags`
(`count`, `filter`, `group`, `join-key`, `synonym`, `trap`). Ожидаемое значение **не писать руками**:
`manage.py golden_refresh <domain>` выполняет `reference_odsql` через API и записывает `expected_value`
(число = `total_count` при `limit=0` или значение агрегата).

Состав: 10 простых подсчётов, 8 с фильтром по коду (`'021'`, академия Dijon), 6 с синонимами
(«bahut», «établissements du second degré», «IPS» → индекс социальной позиции), 4 «ловушки», где
похожий набор неверен (`fr-en-ips-ecoles-ap2022` против `fr-en-ips-lycees-ap2022`, `fr-en-indicateurs-de-resultat-des-lycees-gt_v2`
против старой версии), 2 вопроса, на которые на портале **нет** данных (ожидаемый ответ — «нет данных»).

Первые вопросы (для образца):
1. «Combien de collèges publics en Côte-d'Or ?» → `fr-en-annuaire-education`, `where: code_departement='021' and type_etablissement='Collège' and statut_public_prive='Public'` → 58.
2. «Combien d'écoles en France ?» → `fr-en-annuaire-education`, `where: type_etablissement='Ecole'`.
3. «Quel est l'IPS moyen des lycées de l'académie de Dijon ?» → `fr-en-ips-lycees-ap2022`.
4. «Combien d'élèves en CPGE par sexe ?» → `fr-en-effectifs-etudiants-cpge-par-annee-et-par-sexe`.

Приёмка: `golden_refresh` проходит по всем 28 вопросам с данными без ошибок API; у каждого `expected_value` не пустой;
исполнитель вручную открыл 5 случайных и проверил смысл (записать в коммит).

### T12. Агент и прогон оценок (2,5 ч)
`evals/agent.py`: свой цикл без фреймворков, ≤ 80 строк. Системный промпт короткий (FR): «отвечай только по данным
портала, сначала найди набор, потом посчитай; если данных нет — скажи "pas de données"». До 6 шагов, `temperature=0`.
Режим `compiled` — инструменты `find_dataset`/`explain_dataset`/`query`; `naked` — `naked_search`/`naked_get`/`naked_query`.
Модель и промпт одни и те же.

`evals/runner.py`, `manage.py eval <domain> --mode naked|compiled|both [--cases slug,slug]`:
- проверка ответа **детерминированная**: из последнего ответа извлечь число (FR-формат: `1 234,5`) и сравнить с
  `expected_value` ± `tolerance`; для «нет данных» — признак отказа; LLM-судья не используется;
- `found_dataset` = последний набор, к которому был `query`;
- метрики: верный набор, валидный ODSQL с первой попытки, верный ответ, медиана/p95 мс, шагов на вопрос, токены;
- вывод — таблица markdown в stdout и в `EvalRun.metrics`; транскрипты в `EvalResult`.

Приёмка: на `FakeLLM` полный прогон 30 × 2 проходит без исключений; с реальной моделью (когда владелец задаст `CTXC_LLM_*`) —
таблица «naked / compiled» записана в `NOTES.md`.
Тесты: извлечение числа из FR-текста; агент останавливается на 6 шагах; метрики считаются на фиктивных результатах.

### T13. Цикл улучшения (2 ч)
`evals/improve.py`, `manage.py improve <domain> [--mode propose|auto] [--max-edits 10]` — алгоритм:
1. Последний `compiled` прогон → провалившиеся случаи, сгруппировать по `expected_dataset`.
2. На группу: одно обращение к LLM с полной карточкой, вопросами, транскриптами провала → ответ строго JSON
   `{kind, after, rationale}` одной правки (`synonyms`/`description`/`query_template`/`note`). Невалидный JSON → пропуск.
3. Создать `ContextEdit(status=proposed)`. В режиме `propose` — остановиться, ждать человека (T14).
4. В режиме `auto` или после одобрения: применить → `compile_dataset` → `upsert_es` → прогнать
   **провалившиеся + 10 случайных прошедших** (контроль регрессий).
5. Верных ответов больше и ни один прошедший не упал → `kept`; иначе → `reverted`, карточка откатывается к предыдущей версии.
6. Бюджет: не больше `Portal.llm_budget_per_day` вызовов LLM в сутки.
7. Итог в stdout: «предложено N · оставлено K · откатано R · верных ответов X → Y».

Приёмка: на `FakeLLM` сценарий «провал → правка `note` про `'021'` → перепрогон → kept» и сценарий с регрессией → reverted.
Тесты на оба сценария и на бюджет.

### T14. Django admin (1,5 ч)
- `Dataset` (поиск, фильтр по порталу/теме, поля inline только для чтения), `Card` (только чтение, обе версии текста).
- `ContextEdit`: список с фильтром по статусу; страница — `difflib.HtmlDiff` между `before` и `after`;
  действия «Одобрить» (запускает шаги 4–5 из T13 синхронно для одной правки) и «Отклонить».
- `EvalRun`: метрики таблицей, ссылка на результаты. Админ — только по логину (`createsuperuser`), на 127.0.0.1.

Приёмка: в браузере (Neo, `browser: local`) видно diff предложенной правки и кнопку одобрения; одобрение меняет статус.

### T15. README, демо, репетиция (1,5 ч)
- `README.md`: что это, запуск с нуля одной последовательностью команд, архитектура (§3), масштаб (§8),
  безопасность (§9), что сознательно не сделано (§10).
- `DEMO.md`: сценарий на 5 минут (§11) с точными командами и ожидаемым выводом.
- Прогон «с нуля»: `docker compose down -v && up -d` → migrate → scan → compile → project → eval → improve — без ручных правок.

## 8. Масштаб: 3 000–5 000 порталов

| Что | Цифра | Решение в коде |
|---|---|---|
| Наборов / полей | ~750 000 / ~15 млн | индексы (`portal`, `modified`), (`dataset`, `name`); MariaDB с первого дня; масштаб — реплики на чтение |
| Скан | полный: 1 запрос/портал; инкремент: 1–3 запроса/портал/час → ~15 000 запросов/час на парк | Celery, разнос по минутам, блокировка на портал, бюджет ≤ 5 % дневного лимита портала |
| ES | ~750 000 карточек, единицы ГБ | один индекс, `routing=portal` — поиск по порталу бьёт в один шард |
| Neo4j | ~750 000 `Dataset` + сотни `Key`; рёбра линейны числу полей-ключей | модель через `Key`, без попарных рёбер |
| Горячий путь | 1 запрос ES + кеш | MCP без состояния → горизонтально; кеш карточек в процессе; общий кеш при > 1 сервере |
| LLM | только офлайн | бюджет вызовов на портал в сутки |

От 1 портала к 5 000 код не меняется: меняются БД, число воркеров, кеш и шарды.

## 9. Безопасность

- Изоляция тенантов: портал в каждом запросе к БД, ES (`filter` + `routing`), Neo4j (`portal` в `MATCH`). Тесты в T4, T5, T7.
- Ключ клиента (`X-Apikey`) только насквозь в Explore API: не пишется в БД, логи, `ToolCall`.
- Валидатор ODSQL по белому списку полей; `limit ≤ 100`; только чтение.
- PII-поля: без примеров значений, не попадают в карточки; LLM видит только метаданные и агрегаты.
- Rate limit на портал в MCP; бюджет скана; бюджет LLM.
- MCP и admin слушают только 127.0.0.1 на стенде. Правки контекста аудируются (`ContextEdit`: кто, когда, до/после).

## 10. Сознательно не делаем (и почему)

| Не делаем | Почему |
|---|---|
| LLM на горячем пути | задержка, цена, недетерминизм; думает агент-клиент |
| Отдельный IR-формат | модели Django и есть промежуточное представление |
| Векторы / эмбеддинги | добавить, только если оценка покажет провал поиска (`find` не находит набор в top-5) |
| Второй LLM-проверяющий | проверка детерминированная + человек в admin |
| LangChain / LangGraph | цикл агента — 80 строк |
| Jev / внешний «decision» API | на горячем пути LLM нет, офлайн нет задачи, где классификатор лучше точной проверки |
| Глоссарий как отдельная сущность | синонимы — правки карточки; глоссарий портала — когда будут их данные |
| pip-пакет `ctxc` | после собеседования, если будет смысл |
| Адаптеры OpenAPI/Snowflake | точка расширения — интерфейс `ExploreSource.full()/since()` |

## 11. Сценарий демо (5 минут)

1. `manage.py scan data.education.gouv.fr --full` → «314 наборов, ~7 000 полей, N запросов, M с».
2. Карточка `fr-en-annuaire-education` в admin: коротко, с ключами, свежестью и лицензией.
3. Вопрос «Combien de collèges publics en Côte-d'Or ?» в двух режимах. `naked`: агент пишет `'21'` или ищет не тот
   набор. `compiled`: заметка про `'021'` → 58 с первой попытки.
4. Таблица 30 вопросов «naked / compiled» + p95 инструментов.
5. `improve --mode propose` → diff в admin → «Одобрить» → перепрогон → `kept`.
6. `explain_dataset` со связями из Neo4j по `uai`; `llms.txt`.
7. Фраза про масштаб из §8.

## 12. Порядок и дни

| Когда | Задачи | Линия отсечения |
|---|---|---|
| Пн 09.11 вечер | T0, T1, T2 | данные портала в БД |
| Вт 10.11 | T3, T4, T5, T6, T7 | MCP отвечает «58» — **минимум для демо** |
| Ср 11.11 | T8, T9, T10, T11, T12 | таблица naked/compiled (нужна выбранная модель) |
| Чт 12.11 | T13, T14, T15, репетиция | improve + admin; если не успеваем — diff в консоли |

Решения за владельцем: **модель для eval/improve** (до утра среды, иначе T12 и T13 остаются на `FakeLLM`).

## 13. Проверка всего проекта перед пятницей

```bash
cd ~/context-compiler-huwise && docker compose up -d
.venv/bin/python manage.py test                      # все тесты зелёные
.venv/bin/python manage.py scan data.education.gouv.fr --full
.venv/bin/python manage.py compile data.education.gouv.fr
.venv/bin/python manage.py project data.education.gouv.fr
.venv/bin/python manage.py bench data.education.gouv.fr        # p95 find < 100 мс
.venv/bin/python manage.py eval data.education.gouv.fr --mode both
.venv/bin/python manage.py improve data.education.gouv.fr --mode auto --max-edits 5
```
