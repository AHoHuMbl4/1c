# Qwen3-Embedding-0.6B против 4B: практические свидетельства (веб-разведка)

Дата сбора: 10.09.2026. Вопрос владельца: можно ли уйти с 4B (dim 1024, bf16, одна GPU)
на 0.6B, чтобы массовый пересчёт векторов шёл быстрее, **при условии, что качество поиска
не падает**.

Короткий вывод по собранному: **условие «качество не падает» на русском не выполняется.**
На официальных прогонах MTEB (`embeddings-benchmark/results`) 0.6B проигрывает 4B на всех
11 русскоязычных задачах, в среднем −5.5 пункта, а на трёх русских retrieval-задачах —
−8.7 пункта (nDCG@10). Ускорение при этом реально и велико, но упирается не в GPU, а в CPU
на стороне сервера.

Инструменты: прямой веб-доступ через HTTP (WebSearch недоступен — исчерпана недельная квота;
Reddit и поисковики отдают 403/JS-челлендж, поэтому Reddit читался через архив
Arctic Shift JSON API). Всё, что ниже, — с URL; где источник описывает *план* замера, а не
сам замер, это помечено — по индексации GitHub таких «agent-written» issue много.

---

## СВИДЕТЕЛЬСТВА

| Источник | Что пробовали | Результат | URL |
|---|---|---|---|
| MTEB results repo (`embeddings-benchmark/results`), прогоны Qwen3-Embedding-0.6B и -4B | 11 русскоязычных задач MTEB v2 (retrieval, reranking, STS, clustering, classification, bitext) | 0.6B ниже 4B **на всех 11**; средняя разница −5.5 пункта, на трёх русских retrieval — −8.7 | https://github.com/embeddings-benchmark/results/tree/main/results/Qwen__Qwen3-Embedding-0.6B |
| HF model card, таблица MTEB(Multilingual) | Официальные прогоны 0.6B / 4B / 8B | Mean(Task): 0.6B 64.33 · 4B 69.45 · 8B 70.58. Retrieval: 64.64 / 69.60 / 70.88. C-MTEB: 66.33 / 72.27 / 73.84 | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B |
| Reddit r/LocalLLaMA, «Tested 14 embedding models on Thai» (16.03.2026, A100, MTEB на 15 тайских задачах) | 14 моделей на тайском | Qwen3-Embedding-4B 74.41 · **0.6B 69.08** (−5.3) · bge-m3 64.77 · jina-v5-text-nano 66.85 | https://reddit.com/r/LocalLLaMA/comments/1rv3y4o/ |
| То же, лидерборд (LANTA, A100 40GB, MTEB 2.10) | полные таблицы по задачам тайского | интерактив с разбивкой по задачам; в тексте предупреждение: 7B+ модели падают по OOM на 40 ГБ | https://anusoft.github.io/thai-mteb-leaderboard/ |
| Reddit r/LocalLLaMA, «rom $5/query to free memory» (28.02.2026) | 5 эмбеддеров на **реальных двуязычных рус/англ. данных** (7178 сообщений чата) | Qwen3-Embedding-0.6B — **0.56**, ниже nomic-embed-text v1.5 (84 МБ, 0.69) и EmbeddingGemma-300M (0.60). Автор: «самая маленькая и старая модель победила с большим отрывом на многоязычных разговорных данных» | https://reddit.com/r/LocalLLaMA/comments/1rgtsa3/ |
| GitHub issue QwenLM/Qwen3-Embedding #182 (MSMARCO, англ.) | 0.6B на MSMARCO passages | MRR@10 ≈ **31**; мейнтейнер: у 8B 36.8, «у 0.6B будет только ниже» | https://github.com/QwenLM/Qwen3-Embedding/issues/182 |
| GitHub issue #82 (reranker 0.6B vs 4B, неангл.) | recall@10 на хинди / индонезийском / тайском | Qwen3-Reranker-0.6B **хуже** bge-reranker-v2-m3 на hi и th; 4B лучше 0.6B везде (hi 78.99 vs 72.04). Комментарий сообщества: «0.6B с дефолтной инструкцией действительно хуже v2-m3, но при хорошо подобранной инструкции результат сильно растёт» | https://github.com/QwenLM/Qwen3-Embedding/issues/82 |
| Qwen blog, таблицы MTEB-R/CMTEB-R/MMTEB-R (reranker) | Qwen3-Reranker-0.6B vs 4B на ретриве, поднятом 0.6B-эмбеддером | 65.80 vs 69.76 (MTEB-R), 71.31 vs 75.94 (CMTEB-R), 66.36 vs 72.74 (MMTEB-R) | https://qwenlm.github.io/blog/qwen3-embedding/ |
| GitHub PR ArthurVardevanyan/HomeLab #703 (прод-деплой, сент. 2026) | Выбор модели в домашнем/прод-контуре: llama.cpp + llama-swap, `--parallel 16`, ctx 16384, LiteLLM-лимит 960 req/min | Выбрана **4B**, а не 0.6B; в обсуждении PR прямо сравнение «70.58 MTEB vs 64.6» — то есть размер выбирали по MTEB, а не по скорости | https://github.com/ArthurVardevanyan/HomeLab/pull/703 |
| GitHub SGLang issue #31891 (бенчмарк, 2026) | Qwen3-Embedding-0.6B, `/v1/embeddings`, A6000 и H200 NVL | См. раздел «Производительность» — это кейс «малая модель + несколько реплик на одной GPU» | https://github.com/sgl-project/sglang/issues/31891 |
| Reddit r/LocalLLaMA, ARK Zurich (07.03.2026) | 0.6B как «память» приложения на M2 Pro, Ollama/Metal | «<25 ms на эмбеддинг», ~0.4 ГБ резидентно; качество не измерялось | https://reddit.com/r/LocalLLaMA/comments/1rmz1u7/ |
| HF discussion #61 | 0.6B на мобильном (Snapdragon 865), квантование | «180+ t/s», 350 МБ в квантованном виде, лучший результат для арабо-англ. мобильного RAG «в этом размере» (заявление вендора, не независимый замер) | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/discussions/61 |
| GitHub issue QwenLM/Qwen3-Embedding #60 | Массовый прогон 1 436 116 строк, 0.6B, sentence-transformers | Автор: «очень медленно»; чисел в issue нет, ответа от мейнтейнера нет (пометка: **план/проблема без замера**) | https://github.com/QwenLM/Qwen3-Embedding/issues/60 |
| GitHub issues `locke1979/OpenNICF` #101, #107 | Парное сравнение 0.6B и 4B на одном корпусе (326 док. / 190 запросов), метрики Recall/MRR/nDCG + латентность | Это **задание на замер**, не результат; опубликованных чисел в issue нет (пометка: **не замер**) | https://github.com/locke1979/OpenNICF/issues/107 |
| GitHub PR CompleteTech-LLC/unstract #3, PR 0nepixel1/mnemosyne #1 | Матрица бенчмарков 0.6B/4B/8B через TEI (CPU/GPU), немецко-англ. smoke-тест | Опять **план/инфраструктура** без итоговых чисел; у mnemosyne только фикстура 8/8 на ранге 1 (слишком мала, чтобы что-то доказывать) | https://github.com/CompleteTech-LLC/unstract/pull/3 |

### MTEB, русскоязычные задачи: 0.6B против 4B (main_score)

Источник — официальный репозиторий результатов MTEB, прогоны `mteb==2.3.2`, ревизии
`Qwen__Qwen3-Embedding-0.6B@b22da49` и `Qwen__Qwen3-Embedding-4B@636cd9b`
(файлы `results/<модель>/<ревизия>/<задача>.json`). Язык отобран по `languages == rus-Cyrl`.

| Задача (тип) | 0.6B | 4B | Δ |
|---|---|---|---|
| RuBQRetrieval (retrieval) | 0.6691 | 0.7365 | −0.0673 |
| RiaNewsRetrievalHardNegatives.v2 (retrieval) | 0.7345 | 0.8442 | −0.1097 |
| MIRACLRetrievalHardNegatives.v2, ru (retrieval) | 0.6251 | 0.7102 | −0.0851 |
| RuBQReranking (reranking) | 0.6567 | 0.7228 | −0.0661 |
| RuSTSBenchmarkSTS (STS) | 0.8420 | 0.8877 | −0.0457 |
| RUParaPhraserSTS (STS) | 0.7205 | 0.7659 | −0.0453 |
| GeoreviewClusteringP2P (clustering) | 0.6639 | 0.7677 | −0.1038 |
| RuReviewsClassification (classification) | 0.7204 | 0.7595 | −0.0391 |
| RuSciBenchGRNTIClusteringP2P | 0.6117 | 0.6339 | −0.0222 |
| RuSciBenchOECDClusteringP2P | 0.5401 | 0.5506 | −0.0104 |
| Tatoeba, rus↔eng (bitext mining) | 0.9243 | 0.9363 | −0.0120 |

Средняя разница по одиннадцати задачам −5.5 пункта; по трём retrieval-задачам −8.7 пункта.
Ни на одной русской задаче 0.6B не выигрывает.

Для контекста — официальные таблицы HF: MTEB(Multilingual) Mean(Task) 64.33 против 69.45
(−5.1), MTEB(Eng v2) 70.70 против 74.60 (−3.9), C-MTEB 66.33 против 72.27 (−5.9).
То есть разрыв на русском **не меньше**, чем в среднем и на английском.

---

## ПРОИЗВОДИТЕЛЬНОСТЬ

Все числа — с чужого железа и из разных контуров, **прямого замера «0.6B и 4B на одной
машине, один рантайм» в открытых источниках найти не удалось** (см. «ЧТО НЕ НАШЛОСЬ»).

**0.6B, SGLang, одна GPU (главный найденный замер; это ровно кейс «малая модель + больше
потоков»).** SGLang issue #31891: Qwen3-Embedding-0.6B, `/v1/embeddings`, входы по 50
токенов, `--max-concurrency 64` на реплику, 2048 промптов на реплику, равный бюджет ядер
(16) на все плечи, три прогона на плечо.

| Плечо | RTX A6000 | 2×H200 NVL (одна GPU) |
|---|---|---|
| одна реплика, 16 ядер | 816.2 req/s | 573.0 req/s |
| DP2 + MPS | 1283.9 req/s (1.57×) | 908.3 req/s (1.59×) |
| **DP3 + MPS** | **1490.4 req/s (1.83×)** | **1507.1 req/s (2.63×)** |
| DP2 без MPS (time-slicing) | 1135.6 req/s (1.39×) | 1038.6 req/s (1.81×) |

Вывод авторов, важный для нас: **на коротких входах 0.6B упирается не в GPU, а в CPU**
(GPU SM-active ~33 %), поэтому «больше процессов на той же карте» даёт 1.6–2.6×, и это
дешевле, чем любая смена модели. Оговорка авторов: абсолютные числа между машинами
несравнимы, сравнимы только формы масштабирования.
URL: https://github.com/sgl-project/sglang/issues/31891

**4B, прод-инстанс.** PR HomeLab #703: llama.cpp/llama-swap, `--parallel 16`,
ctx-size 16384, «до 16 одновременных embedding-запросов с 16K-контекстом», 16–28 ГБ VRAM
на GPU, выгрузка после 5 мин простоя; LiteLLM-лимит 960 req/min (16 r/s) выставлен «под
ёмкость --parallel 16». URL: https://github.com/ArthurVardevanyan/HomeLab/pull/703

**4B, массовый пересчёт.** Reddit r/LocalLLaMA (12.03.2026): Qwen3-Embedding-4B —
«~6 минут на 10k векторов» на A100 80GB, `batch_size=32` (≈28 векторов/с); там же второе
4B-эмбеддер при тех же условиях — ~45 мин на 10k. URL:
https://reddit.com/r/LocalLLaMA/comments/1rrs24q/

**0.6B, малые контуры.** <25 мс на эмбеддинг (Ollama, Metal, M2 Pro, заметки приложения);
«180+ t/s» на Snapdragon 865 в квантованном виде (заявление вендора).
URL: https://reddit.com/r/LocalLLaMA/comments/1rmz1u7/ ·
https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/discussions/61

**Обратный пример: 0.6B, но с накладными расходами.** Issue Hussain0327/amneal #221
(Databricks-эндпоинт): p50 запросного эмбеддинга на 0.6B — **965 мс** на одну короткую
строку, при этом TTFT 120B-генератора — 527 мс. Автор: время уходит на per-request
накладные, а не на вычисления. URL: https://github.com/Hussain0327/amneal/issues/221

**Про регрессии рантаймов (влияет на любой размер):** vLLM issue #52630 — «~18 % регрессии
throughput пулинга начиная с torch 2.11 (vLLM ≥ 0.20.0)»;
https://github.com/vllm-project/vllm/issues/52630. TEI: расхождение векторов между
sentence-transformers и TEI лечится только TEI ≥ 1.8.3
(https://github.com/QwenLM/Qwen3-Embedding/issues/171).

**Наш собственный ориентир (для сверки, не из веба):** при 1.67M строк переход 4B→0.6B
по параметрам даёт ≈6.7× меньше FLOPs на документ, но реальное ускорение массового
пересчёта ограничено тем, что упирается в CPU/токенизацию (см. SGLang выше) и в те же
~4.3K токенов на 1С-представления.

---

## СЛАБОСТИ 0.6B

1. **Русский ретрив — минус ~9 пунктов nDCG@10 против 4B** (таблица выше, официальные
   прогоны MTEB). Это самая тяжёлая часть деградации; на «лёгких» ru-задачах
   (классификация, кластеризация научных текстов) разрыв 1–2 пункта.
2. **Инструкция обязательна, и её формат строгий.** Запросы кодируются как
   `Instruct: {задача}\nQuery: {запрос}`, документы — без инструкции. В карточке модели:
   без инструкции падение ретрива на 1–5 %. Рекомендация Qwen — писать инструкции
   **на английском**, даже для многоязычных задач. Неверный формат — тихая просадка
   (issue #82: 0.6B-reranker «не лучше v2-m3» именно из-за формата; лечится подбором
   инструкции).
   https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/discussions/29 ·
   https://github.com/QwenLM/Qwen3-Embedding/issues/82
3. **Matryoshka / усечение размерности.** `is_matryoshka` отсутствует в `config.json`,
   и vLLM/agent-scope отвечают 400: `does not support matryoshka representation`. Лечится
   флагом `--hf_overrides '{"is_matryoshka": true}'`, но качество усечённых размерностей
   никто в отчётах не сверял.
   https://github.com/QwenLM/Qwen3-Embedding/issues/188, #177, #85, #140
4. **Длинный контекст = всплески памяти.** Issue #154: на контекстах >8k при `bsz=1`
   всплески, **16k не влезает в 40 ГБ VRAM**; автор и комментатор подтверждают, что это
   у всех размеров Qwen3-Embedding (0.6B, 4B, 8B). Наш корпус — представления 1С, длинные
   тексты там обычны.
   https://github.com/QwenLM/Qwen3-Embedding/issues/154
5. **Опечатки/OOV → всплеск VRAM и OOM.** HF discussion #38: на правильно написанных
   запросах память стабильна, на опечатках — резкий рост, вплоть до CUDA OOM на A10 (24 ГБ)
   и отказа обслуживать последующие батчи. Для живого поиска это риск.
   https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/discussions/38
6. **NaN-эмбеддинги с HTTP 200 (молчаливая порча индекса).** TEI, образ cuda-1.9 +
   flash-attn на Turing/T4: «100 % NaN-векторов», сервер при этом пишет Success и отдаёт
   200. Аналогично llama.cpp на Volta (sm_70) с Qwen3-Embedding-8B: один «плохой» вход
   вешает сервер, и **все последующие** запросы возвращают NaN до перезапуска.
   https://github.com/huggingface/text-embeddings-inference/pull/896 ·
   https://github.com/ggml-org/llama.cpp/issues/26044
7. **Недетерминизм между рантаймами/версиями.** Issue #189: один и тот же вход на разных
   версиях vLLM даёт cosine < 1.0 — при массовом пересчёте это несравнимые пространства
   векторов (наши индексы придётся пересобирать целиком, половинчатый переход невозможен).
   https://github.com/QwenLM/Qwen3-Embedding/issues/189
8. **EOS/PAD-тонкость.** В Qwen3 `pad_token_id == eos_token_id == 151643`; пулинг
   last-token, `padding_side='left'`. Ошибка настройки даёт другой вектор без ошибки.
   https://github.com/QwenLM/Qwen3-Embedding/issues/122, #54
9. **Доменная чувствительность.** Ни в одном найденном источнике нет замеров на
   корпоративных/справочных русских текстах (1С). Косвенный сигнал — история про
   MSMARCO (#182) и тайский лидерборд: 0.6B «почти догоняет 4B» на одних типах задач
   и отстаёт на 5–11 пунктов на других; заранее предсказать, как будет на нашем домене,
   по вебу нельзя.

---

## ЧТО НЕ НАШЛОСЬ

1. **Прямого замера throughput 0.6B против 4B на одном железе, одном рантайме,
   одинаковых входах** — не нашлось ни в GitHub, ни в Reddit-архиве, ни в блогах.
   Все числа выше сняты на разном железе и в разных контурах, сравнивать их между собой
   нельзя. Это дыра, которую закрывает только собственный замер (например, TEI или vLLM
   на нашей GPU, один корпус, оба размера, vec/s и прогон на том же наборе запросов).
2. **Русскоязычного прод-отчёта именно про 0.6B** — нет. Единственный найденный русский
   замер: двуязычный (рус/англ.) тест на 7178 сообщениях чата, где 0.6B проиграл
   nomic-embed-text v1.5 (84 МБ) и EmbeddingGemma-300M — то есть даже не 4B.
3. **Свидетельств, что 0.6B + reranker догоняет 4B-одного на русском** — нет. Наоборот:
   reranker 0.6B на трёх неанглийских языках оказался хуже bge-reranker-v2-m3 (#82),
   а в официальной таблице Qwen Reranker-0.6B отстаёт от 4B на 3.9–6.4 пункта (MTEB-R /
   CMTEB-R / MMTEB-R). Схема «дешёвый эмбеддер + дешёвый реранкер» на русском нигде
   не подтверждена числами.
4. **Русских лидербордов с 0.6B**: ruMTEB как отдельного публичного лидерборда с
   Qwen3-Embedding найти не удалось; числа пришлось брать из агрегированного
   `embeddings-benchmark/results` (это тот же источник, что кормит MTEB-лидерборд).
5. **Замеров на домене 1С / справочно-нормативных русских текстах** — нет ни по одной
   модели.
6. **Инструментальные ограничения сбора** (важно для оценки полноты):
   `WebSearch` отключён по квоте (HTTP 403 «weekly usage limit»); reddit.com, old.reddit.com
   и публичные redlib-зеркала отдают 403/JS-челлендж; DuckDuckGo, Mojeek, Brave, Ecosia,
   Qwant, searx.be — 403/челлендж/captcha. Поиск фактически шёл через GitHub Search API
   (лимит 60 req/час — по ходу сборки исчерпан, часть запросов пришлась на raw-URL),
   архив Reddit Arctic Shift (жёсткий rate-limit) и прямые URL HF/GitHub. Возможен
   недоучёт: англоязычные блоги и часть Reddit-тредов остались непрочитанными, а русские
   площадки (Habr и др.) отдают контент только JS-рендером и не читались вовсе.
7. **Не проверено**: качество 0.6B с русскоязычной инструкцией (все найденные рецепты —
   с английской), и поведение на усечённых размерностях (768/512) применительно к русскому.
