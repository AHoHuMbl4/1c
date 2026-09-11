# Карта M3: места, где тракт решает за человека (2026-09-11)

Линза: всё, что тракт **молча** выбирает за человека (меру, сущность, период, ветку, пул, сортировку-победителя) вместо меню из вики-подписей — вне формулы №15. Догадка = дефект (п.12 TARGET). Код только читался: `ubuntu/serenedb/ask/z*.py`, `ubuntu/serenedb/serene_ask.py`, `ubuntu/serenedb/ask_choice_mem.py` (память, зовётся из z14/z20).

`serene_ask.py` — загрузчик зон, **выбора за человека нет** (строки 1–48: `load_all` + `main`).

| место | файл:строки | условие срабатывания | что выбирается молча | вред (какой ответ искалечивает) | замена по формуле | риск |
|---|---|---|---|---|---|---|
| prefer_entity_for_sales + cold-lift | `z11_sales.py:236-339`; зов `z20:2229`, `2660-2662`, `3272-3273` | `sales_sum_intent` или `sales_rank_engaged`; есть document_/письма → lift register; пусто + allow_cold → любой `accumulationregister_%` с written_by | Регистр движений (score Количество+Всего, имя «реализац/продаж») в голове пула; документы и «книга/НДС» выкидываются | Wiki/BM25 могли выбрать документ/книгу; ответ идёт с чужого src (деньги vs книга НДС) | Меню вики-подписей при ≥2 src; cold-lift — **убрать** (ступень 2/вики) | critical |
| sales_canon_src → sales_canon_locked | `z11:371-383`; lock `z20:1278`, `4083-4086`; уважение `z21:671-673` | После выбора src: sum/rank sales и `src == sales_canon_src(...)` | Фиксация одного accumulationregister_* как «канон» | Обходит вики-каскад (`wiki_primary` сразу возвращает locked); развилка схлопывается | Не lockать; неоднозначность → меню вики | critical |
| sales_canon_force_pool | `z11:638-646`; зов `z20:3276-3278`, `3378-3379` | `diag.sales_canon_locked` (или мёртвые catalog/stock/register_locked) | `picked=arb_pool=[locked]`, `doubt=False` | Clarify/соперники невозможны — ответ «как будто одно прочтение» | Убрать force; меню при >1 | critical |
| sales_money / force_money / sales_measure_canon | `z11:386-414`, `613-635`, `521-576`; применение `z20:4230-4265`, `4326-4332` | sales_sum (не superlative-rank) или rank×sales; нет measure_pick | Мера «Всего/сумм» или «Количество» по эвристикам/алиасам | «Сколько продали» → деньги вместо qty (или наоборот на топе); чужое поле | Меню классов money\|qty из вики/алиасов (`measure_class_alts` уже есть путь role_ask) | critical |
| INTENT_SAMPLES majority / _merge_intents | `z01:889-890`; `z02:588-623`, `669-672` | Каждый вопрос; пока lead < INTENT_LEAD — до 5 прогонов; победитель по счёту, tie → первый | kind, terms, measure, want, period, action_* | Разный kind → другой пул/число (замер в комментарии: 18/58 расходятся) | При distinct>1 по kind/measure/period — меню вики-вариантов разбора, не голосование | critical |
| _intent_text: список → первый | `z02:39-50`, `430-434` | Модель вернула kind/measure как list | Первый непустой элемент; остальные только в `parse.fixed` | Альтернативы рода/меры отбрасываются без меню | Меню из всех элементов списка | high |
| assumed-период LLM + exempt sales | `z02:549-561`; clarify-гейт `z20:1715-1743` (`sales_sum`/`canon_claims` → False); apply `z20:1873+`, `1972-1998` | Период в intent, год не в цифрах вопроса → `parse.assumed`; длинное окно — clarify **кроме** продаж | Окно «год назад→сегодня» и т.п. применяется к отбору | Пустой/чужой итог при живых данных вне окна (ACCEPTANCE_UT №28) | Всегда меню окон из вики/period_readings; снять exempt для sales | critical |
| prefer_window_leader (mtd/wtd) | `z03:373-393`, `581-611`; diag `z20:1896-1903` | ≥2 period_readings; нет prefer_form | Лидер MTD/WTD (или readings[0]); полный месяц/неделя — только соперник детектора | Число за «месяц» = MTD, не календарный месяц | Меню подписей окон (уже в fork B) **до** ответа, не лидер молча | high |
| period_form_from_question first-hit | `z03:427-437`, `_apply_period_form_window:475-510` | Фраза из `period_relative_forms` (meta/json) ⊆ вопроса | Первый совпавший form_id | «неделя» → wtd vs full_week vs prev_week без спроса | Меню form_id с вики-подписями | high |
| fork_leader_class defaults | `z13:79-134`; outcome B `z13:491-500` | Исход B, picked_src в нескольких классах | Предпочтение mtd/wtd; day_basis=`calendar_days`; amount_basis=`doc_amount` | Ответ по одной оси, вторая только в options (если labels есть) | Не выбирать лидера: все ветки в меню вики-подписей, либо A только при 1 классе | high |
| prefer_mute_computed_over_clarify | `z13:446-474`; зов `z20:~3839` | ASK_ATOM_TERMINAL; mute-лидер computed; figures соперников пусты | Ответ по picked_src без entity-clarify | Молчаливый src при живых пустых соперниках | Меню src с вики-labels | medium |
| pick_measure → rerank победитель | `z16:589-634` | word есть, measure_choice='rerank' | `ranked[0]` (+ base-prefix эвристика) | Неверная величина на верной сущности (замер 30.07 суммы) | how='ask' → меню подписей мер | high |
| unresolved_quantity → names[0] | `z16:415-435` | want/sum без measure; totals не ambiguous | Первая мера из списка | Случайное поле при равных итогах | Меню мер / вики | medium |
| prefer_entity_for_rank | `z10:428-491`; зов `z20:2228` | rank + productish слова в q/kind + ≥2 cands | Lift register / document выше tabpart | Рейтинг с чужого носителя | Меню вики при нескольких носителях | high |
| prefer_entity_for_catalog_count + hardcode имён | `z11:759-794`; зов `z20:2230`, `2660`, `3274` | `catalog_count_question` / kind→catalog | `cats[0]` или hardcode `catalog_номенклатура`/`nomenclature`/`товары`… | «Сколько в прайсе» → конкретный catalog без меню | Меню catalog_* из вики | high |
| rank_axis_resolve ordered[0] | `z10:233-295` (273, 284) | >2 оси; rerank дал порядок | Топ rerank как ось GROUP BY | Топ по клиенту вместо товара (и наоборот) | ≥2 правдоподобные → меню осей (частично есть для ровно 2) | high |
| sales_rank_product_axis / qty vs money | `z11:452-610`; `z20:4238-4259` | rank×sales; product catalog axis или фразы «лучше всего продавалось» | qty vs money без спроса, если не оба живы+без имени | Чужой лидер топа | role_ask / меню классов | high |
| event_kind_catalog_expand_pool | `z05:478-518`; зов `z20:2223-2227` | event+count + axis/kind | Дописывает catalog + document/register holders в пул | Сам по себе не выбирает ответ; раздувает пул перед prefer/wiki | **Оставить как техника** обогащения пула для ступени 2–3; вред только в связке с prefer/lock | low (тех) |
| entity_form_expand_pool / axis_on_sales score | `z05:455-475`, `1042-1071` | F-path / distinct | Sales-holder с max `_sales_register_score` | Форма счёта на «канон»-регистре | Меню форм/носителей | medium |
| entity_form_rolling_year | `z05:521-531`, gate `534-552` | event+count, нет окна / assumed | origin=assumed rolling_12m | Distinct за «год» без спроса | Меню периодов | high |
| event_filter_pool | `z05:1005-1008`; `z20:3250-3254`, `2666` | event_path + K6R | Сужает arb_pool до «движений»; при len==1 — doubt=False | Одно движение остаётся без меню | Если после фильтра >1 — меню; =1 ок | medium |
| K6R.apply_to_candidates reorder | `z20:2246-2258` | K6R включён | Перестановка cands по answer_fit_v2 | Меняет, кого видит wiki/LLM первым | Техника ранжирования **если** финал — wiki clarify; вред если берёт [0] без меню | medium / неясно |
| writer_pair / signals_disagree | `z20:3149-3169`, `3221-3269` | writer документ↔регистр; top_by_question ∉ picked | Добавляет соперника в круг (часто → clarify) | Само по себе не победитель; при совпадении чисел — ответ без спроса | Оставить как заведение неоднозначности; ти-брейк «числа равны → согласие» — проверить отдельно | low (тех) / medium (tie) |
| ask_choice_mem apply | `ask_choice_mem.py:161-183`; `z20:5810-5835` | ASK_MEMORY_APPLY=1 + user + ambiguous out + hit | Повторный прогон с trusted src/measure из памяти | Меню не показывают; «помню: …» | Только после явного remember; при неоднозначности всё равно меню, память — подсказка | medium (флаг) |
| apply_prior_period | `z20:1777-1803` | Текущий период пуст/канон-догадка; prior задан текстом | Копирует period (+assumed-метки) из prior | Диалог наследует окно без подтверждения | Уточнить / меню, если вопрос сам период не назвал | medium |
| period_zero_why → want=sum | `z11:810-819`; `z20:3217-3220`, `1934-1937` | «почему»+«ноль/воскресенье» + sales | about/list → sum + period_empty path | Обходит coverage; навязывает sales-канон | Убрать догадку want; меню | medium |
| canon_claims_question | `z16:359-375` | sales_sum / sales_canon_intent / catalog_count | Объявляет «канон забрал вопрос» → kind_unsupported не режет | Маскирует отсутствие kind в корпусе продажами | Ступень 2 вики, не канон | medium |
| fork outcome A (1 class) | `z20:3231`, `3557` | classes==1 | Ответ единственного класса | Ок по формуле (одно прочтение) | **Оставить** | keep |
| seal_clarify / decision tickets | `z14:409-461` | kind clarify/figures с options | Не выбирает — сериализует выбор человека | — | **Оставить** (ступень 5) | keep |
| prefer_entity_for_stock / filter_stock_* | `z12:868+`, `1080-1094` | Функции живы; в `z20` маршруте **не зовутся** (изъятие 11.09; тест `test_final_stock_route_filters_absent`) | Были: balance-register в голове | Сейчас в HTTP-пути — мёртвый код | Не возвращать; снос функций — отдельный шаг | n/a (мертво в route) |
| catalog_count_locked / stock_canon_locked / register_count_locked | ссылки `z20`/`_bootstrap`/`z16`; **присваиваний в текущем z20 нет** (кроме sales_canon_locked) | Только чтение diag | Ранние замки вырезаны 01.09 («один путь» wiki) | Мёртвые ветки force_pool OR; путаница аудита | Вычистить мёртвые OR / bootstrap-патчи | low (долг) |
| _sales_register_score / sales_noncanon / _is_product_catalog | `z11:74-89`, `688-713` | Внутри prefer/canon | Победа по score и подстрокам имени src | Привязка к именованию базы (п.0) | Вики-подписи + структура meta, без «реализац» в коде | high (п.0) |

---

## (а) Что сносить в первую очередь (частота × вред)

1. **Пакет sales-канона сущности:** `prefer_entity_for_sales` + cold-lift + `sales_canon_locked` + `sales_canon_force_pool` + уважение lock в `z21` — срабатывает на почти каждый вопрос «продали/выручка/оборот»; полностью подменяет ступени 2–4.
2. **Канон меры продаж:** `sales_force_money_measure` / `sales_money_measure` / `sales_measure_canon` в `z20:4230+` — после src молча ставит деньги/qty; прямой вред числа.
3. **INTENT_SAMPLES голосование + `_intent_text` first-of-list** — на **каждый** вопрос; тихое ветвление kind/terms/period до вики.
4. **Assumed-период с exempt для sales** (`period_assumed_needs_clarify` → False на sales) + **prefer_window_leader mtd/wtd** — период без меню; продажи особенно опасны.
5. **prefer_entity_for_catalog_count** (+ hardcoded `catalog_номенклатура`…) и **prefer_entity_for_rank** — перестановка пула до wiki.
6. **pick_measure rerank-победитель** и **rank_axis_resolve ordered[0]** при >2 осях — молчаливая мера/ось.
7. **fork_leader_class** дефолты осей W/day/amount — лидер ответа B без спроса по форме окна.
8. **Память apply** (`ASK_MEMORY_APPLY`) — реже, но полностью схлопывает меню.
9. **Мёртвый stock/catalog lock + orphan prefer_stock** — не бьёт прод-путь сейчас; вычистить, чтобы не вернуть.

Не сносить как «выбор за человека»: `event_kind_catalog_expand_pool` / расширение пула без lock; `seal_clarify`/билеты; fork A при одном классе; writer_pair как *добавление* соперника (не победитель).

---

## (б) Слова домена / каноны в коде (п.0 TARGET — привязка)

| зона | что зашито |
|---|---|
| `z11_sales.py:15-18,30-35` | продаж/торг/выруч/sale/revenue; продали/наторговали/sold… |
| `z11:41-60,627-634` | лучше/хуже всего, топ, лидер, сравни, сотрудник/зарплат… |
| `z11:79-88,307` | количество/всего/ндс/книга/реализац/продаж/sale в **именах src/мер** |
| `z11:463-469` | «лучше всего», «топ продаж», «что … продава…» |
| `z11:700-713,789-791` | установкацен/номенклатур/товар/product; hardcode `catalog_номенклатура`… |
| `z11:752-755,816-818` | прайс/номенклатур; почему/ноль/воскресен |
| `z10_rank.py:72-84` | больше всего/топ/лидер/рейтинг/какой товар… |
| `z10:435-436` | товар/номенклатур/product в prefer_rank |
| `z16:323-326,354` | напиши/стих…; сколько/выруч/продаж/остат/заказ |
| `z02` / `z16` question_expects | те же учётные маркеры |
| `z03` | form_id wtd/mtd/prev_week… (структура ок); фразы — из meta/json (данные), first-hit — выбор |
| `z12` | остатки/склад — доменные эвристики (route изъят, код жив) |
| `z13` | `_WINDOW_LEADER_FORMS`, `_DAY_BASIS_LEADER_DEFAULT`, `_AMOUNT_BASIS_LEADER_DEFAULT` |

---

## (в) Неясные места (честно)

1. **K6R.answer_fit_v2 reorder** — перестановка кандидатов: техника поиска или скрытый ти-брейк до wiki? Нужен замер: берётся ли когда-либо `cands[0]` в обход wiki clarify.
2. **Ти-брейк «числа совпали → не clarify»** (`answers_diverge` / writer_pair_proven) — согласие по числу vs разные src с одинаковым итогом: формула требует меню подписей или допускает «одно число»?
3. **`catalog_count_locked` / `stock_canon_locked` / `register_count_locked`** — в текущем `z20` присваиваний нет; bootstrap всё ещё патчит ветки под них. Живой путь lockает только `sales_canon_locked`. Полный след lock→force на складе/прайсе **не подтверждён** чтением текущего файла.
4. **fork label-kind:** `fork_labels_of` / `fork_labels_covering` читают вики-подписи из БД — это **правильная** ступень 4; вред только в `fork_leader_class`, который заранее выбирает, *какая* ветка в тексте ответа.
5. **Shadow-память** (`attach_choice_memory` без APPLY) — в diag only; на ответ не влияет (не дефект M3, пока APPLY выкл).
6. **Связка expand_pool + prefer_sales:** expand сам по себе техника; вред — когда expanded register тут же становится lock/головой.

---

Источник фактов: чтение дерева `/srv/1c/ubuntu/serenedb/ask/` на 2026-09-11; сервер/БД не трогались; кроме этого файла ничего не менялось.
