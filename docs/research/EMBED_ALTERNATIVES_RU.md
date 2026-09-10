# Альтернативы Qwen3-Embedding-4B для массового пересчёта (рус., dim 1024)

Собрано 10.09.2026 по вебу. Способ: прямые запросы к карточкам моделей, статьям и
лидербордам — **поисковик был недоступен** (WebSearch → HTTP 403 «weekly usage limit»,
DuckDuckGo/Bing/Mojeek → captcha), поэтому всё ниже — из первоисточников по известным URL,
а не из подборок. Всё, что я посчитал сам, помечено `[мой расчёт]`.

Контекст задачи (из репозитория, не из веба): боевой эмбеддер — `Qwen3-Embedding-4B`,
`dim=1024` (MRL-обрезка от 2560), OpenAI-совместимый `POST /v1/embeddings`
(`docs/RUNBOOK_DEPLOY.md:638`, `docs/NETWORK.md:81`), колонка `emb FLOAT[1024]`.

---

## ФАКТЫ (таблица с URL)

### Русско/многоязычные модели

| Модель | Параметры | RU/многояз. метрика | dense dim | Скорость | Источник |
|---|---|---|---|---|---|
| **Qwen3-Embedding-4B** (текущая) | 4.02 B (`safetensors.total`=4 021 774 336), 36 слоёв, контекст 32k | MTEB (Multilingual) Mean(task) **69.45**; MTEB (Eng v2) 74.60; C-MTEB 72.27. **RU-замеров нет** (см. «что не нашлось») | 2560 нативно, MRL 32…2560 → **1024 настраивается** | публичных tok/s нет; TEI относит к классу «4.02B (Very Expensive)» | [карточка](https://huggingface.co/Qwen/Qwen3-Embedding-4B), [блог](https://qwenlm.github.io/blog/qwen3-embedding/), [config](https://huggingface.co/Qwen/Qwen3-Embedding-4B/raw/main/config.json), [TEI README](https://github.com/huggingface/text-embeddings-inference#supported-models) |
| **Qwen3-Embedding-0.6B** | 0.596 B (HF API) / 509 M (в таблице TEI), 28 слоёв, 32k | MTEB (Multilingual) **64.33**; MTEB (Eng v2) 70.70; C-MTEB 66.33 | 1024 максимум, MRL 32…1024 | не найдено | [карточка](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) |
| **BGE-M3** (BAAI) | ≈568 M `[мой расчёт: pytorch_model.bin 2 271 145 830 Б fp32 / 4]`, xlm-roberta-large, 24 слоя, 8192 ток. | MTEB (Multilingual), сравнит. таблица Qwen: **59.56**; ruMTEB Average **61.58** (на 09.10.2024); encodechka Mean S **0.787**, Mean S+W 0.696; rusBEIR среднее NDCG@10 **0.5099** `[мой расчёт]` | **1024, фиксированная** (MRL нет) | encodechka: CPU 523.4 / GPU 22.5, размер 2166 MB (единицы и железо в README не указаны) | [карточка](https://huggingface.co/BAAI/bge-m3), [статья](https://arxiv.org/abs/2402.03216), [ruMTEB paper](https://arxiv.org/abs/2408.12503), [encodechka](https://github.com/avidale/encodechka), [rusBEIR](https://huggingface.co/spaces/kaengreg/rusBEIR) |
| **multilingual-e5-large** | 559.9 M, xlm-r, 24 слоя, лимит 512 ток. | MTEB (Multilingual) многояз. среднее **59.58** (Table 4 jina); ruMTEB Average **61.41**; encodechka Mean S **0.78**; rusBEIR **0.5067** `[мой расчёт]` | **1024, фиксированная** | encodechka: CPU 506.8 / GPU 30.8 (самый быстрый GPU-столбец из крупных) | [карточка](https://huggingface.co/intfloat/multilingual-e5-large), [статья](https://arxiv.org/abs/2402.05672), [jina paper](https://arxiv.org/abs/2409.10173) |
| **multilingual-e5-large-instruct** | 559.9 M, 512 ток. | ruMTEB Average **66.03**; MTEB-rus Mean(task) **65.00**; MTEB (Multilingual) 63.22 (таблица Qwen); encodechka Mean S 0.784 | 1024, фиксированная | encodechka: CPU 501.5 / GPU 25.71 | [карточка](https://huggingface.co/intfloat/multilingual-e5-large-instruct), [ruMTEB paper](https://arxiv.org/abs/2408.12503), [USER2](https://huggingface.co/deepvk/USER2-base) |
| **multilingual-e5-base** | 278.0 M, 768 dim, 512 ток. | MTEB-rus Mean(task) 58.34; ruMTEB Average 58.34; encodechka 0.761 | 768, фиксированная (≠1024) | encodechka CPU 130.61 / GPU 14.39 | [карточка](https://huggingface.co/intfloat/multilingual-e5-base), [USER2](https://huggingface.co/deepvk/USER2-base) |
| **jina-embeddings-v3** | 572.3 M, XLM-R 24 слоя + 5 LoRA-адаптеров (<3 % параметров), 8192 ток. | многояз. MTEB в своей разбивке: среднее **64.44** (CF 71.46 / CL 46.71 / PC 76.91 / RR 63.98 / RT 57.98 / STS 69.83), англ. 65.52; MTEB-rus Mean(task) **63.45**; MLDR-rus nDCG@10 **49.67** | **1024 по умолчанию**, MRL до 32 | замеров в найденных источниках нет | [статья](https://arxiv.org/abs/2409.10173), [карточка](https://huggingface.co/jinaai/jina-embeddings-v3), [USER2](https://huggingface.co/deepvk/USER2-base). ⚠️ лицензия **CC BY-NC 4.0** (некоммерческая) |
| **USER-bge-m3** (deepvk) | 359 M (bge-m3 с урезанным словарём 46 166), 24 слоя, 1024, 8192 ток. | encodechka Mean S **0.799** / S+W **0.709** — лучший в таблице encodechka (bge-m3 0.787); MTEB-rus Mean(task) **62.80**; MLDR-rus **58.53** (топ); в rusBEIR не замерялся | **1024, фиксированная** | encodechka: CPU 523.4 / GPU 22.5, размер 1371 MB | [карточка](https://huggingface.co/deepvk/USER-bge-m3), [encodechka](https://github.com/avidale/encodechka), [USER2](https://huggingface.co/deepvk/USER2-base) |
| **USER2-base** (deepvk, 2025) | 149 M, ModernBERT, 8192 ток. | MTEB-rus Mean(task) **61.12** | 768 максимум, MRL [32…768] — **в 1024 не упирается и не дотягивает** | не найдено | [карточка](https://huggingface.co/deepvk/USER2-base) |
| **FRIDA** (SberDevices) | 823 M, FRED-T5 encoder | rusBEIR среднее NDCG@10 **0.5133** `[мой расчёт]` — лучший **нере-ранкер** из 18 строк; заявка карточки: top-1 среди моделей ≤3 B (11.08.26) | d_model **1536** (MRL не заявлен) — **в FLOAT[1024] не влезает** | не найдено | [карточка](https://huggingface.co/ai-forever/FRIDA), [config](https://huggingface.co/ai-forever/FRIDA/raw/main/config.json), [rusBEIR](https://huggingface.co/spaces/kaengreg/rusBEIR) |
| **ru-en-RoSBERTa** (ai-forever) | 404 M, roberta, 24 слоя, лимит 512 ток. | ruMTEB Average **61.77** (второе место среди не-instruct, 09.10.2024); MTEB-rus 61.71; rusBEIR **0.4688** `[мой расчёт]`; MIRACL-rus reranking nDCG@10 56.91 | 1024, фиксированная | в статье: полный прогон ruMTEB ≈ **19 часов на 1×A100 80GB** | [карточка](https://huggingface.co/ai-forever/ru-en-RoSBERTa), [статья](https://arxiv.org/abs/2408.12503) |
| **ruBERT-семейство / DeepPavlov (монолингвальные)** — rubert-tiny2, SBERT-large-nlu-ru, SBERT-large-mt-nlu-ru, ai-forever/ruBert-large, DeepPavlov/rubert-base-cased | 29.4 M (rubert-tiny2, 312 dim, 3 слоя) / 178 M (rubert-base-cased, 768) / остальные — 1024-dim ruBERT-производные (параметры не сверял) | ruMTEB Average: rubert-tiny2 **42.22**, SBERT-large-nlu-ru **45.35**, SBERT-large-mt-nlu-ru **48.72** (против 61.58 у BGE-M3); encodechka Mean S: 0.704 / 0.688 / 0.703 / 0.678 | 312 / 768 / 1024 — по конфигу каждой модели, фиксированные | encodechka: rubert-tiny2 CPU 5.5 / GPU 3.3; sbert_large_mt_nlu_ru CPU 504.5 / GPU 29.7 | [ruMTEB paper](https://arxiv.org/abs/2408.12503), [encodechka](https://github.com/avidale/encodechka), [config ruBert-large](https://huggingface.co/ai-forever/ruBert-large/raw/main/config.json) |

### Общая скорость/размер (единственная найденная публичная таблица скорости)

`encodechka` ([README, лидерборд](https://github.com/avidale/encodechka)) — колонки
`CPU`/`GPU` и `size` (MB). **Единицы, железо и режим в README не описаны**, поэтому
сравнивать можно только строки между собой, а не как абсолют tok/s.

| модель | CPU | GPU | size, MB | Mean S (RU) | dim |
|---|---|---|---|---|---|
| deepvk/USER-bge-m3 | 523.4 | 22.5 | 1371.1 | 0.799 | 1024 |
| BAAI/bge-m3 | 523.4 | 22.5 | 2166.0 | 0.787 | 1024 |
| intfloat/multilingual-e5-large-instruct | 501.5 | 25.71 | 2136.0 | 0.784 | 1024 |
| intfloat/multilingual-e5-large | 506.8 | 30.8 | 2135.9 | 0.780 | 1024 |
| intfloat/multilingual-e5-base | 130.61 | 14.39 | 1061.0 | 0.761 | 768 |
| sentence-transformers/LaBSE | 135.1 | 13.3 | 1796.5 | 0.739 | 768 |
| cointegrated/rubert-tiny2 | 5.5 | 3.3 | 111.4 | 0.704 | 312 |
| ai-forever/sbert_large_mt_nlu_ru | 504.5 | 29.7 | 1628.7 | 0.703 | 1024 |

### Практическое ограничение кейса: dim 1024 и `/v1/embeddings`

| Модель | dim | Настраивается? |
|---|---|---|
| Qwen3-Embedding-4B (текущая) | 2560 → 1024 | **да, MRL 32…2560** (в проекте уже режут до 1024) |
| Qwen3-Embedding-0.6B | 1024 | **да, MRL 32…1024** |
| jina-embeddings-v3 | 1024 | **да, MRL до 32** (заявлено «без потери качества» до 32) |
| USER2-base | 768 | да, MRL [32…768], но **1024 недостижимо** |
| BGE-M3 / USER-bge-m3 / multilingual-e5-large(-instruct) / ru-en-RoSBERTa / SBERT-large | 1024 | **нет, жёстко 1024** |
| multilingual-e5-base / rubert-base-cased | 768 | нет (768 ≠ 1024) |
| FRIDA | 1536 | нет MRL → под `FLOAT[1024]` не подходит без потери/паддинга |

Служить OpenAI-совместимым `POST /v1/embeddings` умеет **Text Embeddings Inference**:
`/v1/embeddings` документирован явно, поддерживаются Qwen3 (в списке есть и 4B, и 0.6B) и
семейство XLM-RoBERTa с absolute positions (BGE-M3, e5). jina-embeddings-v3 в списке
поддерживаемых **не заявлена** (в списке только JinaBERT — это v2) — то есть под неё нужен
свой сервер, а не штатный TEI: [TEI quick tour, раздел OpenAI](https://huggingface.co/docs/text-embeddings-inference/en/quick_tour),
[TEI supported models](https://github.com/huggingface/text-embeddings-inference#supported-models).

---

## КАНДИДАТЫ-СОПЕРНИКИ 4B (и чем подтверждено)

**Реально сопоставимы по качеству (но не по RU-замерам, а по многоязычному MTEB):**

1. **Qwen3-Embedding-0.6B** — тот же класс по размеру, что BGE-M3 (0.596 B против 0.568 B),
   но MTEB (Multilingual) **64.33 против 59.56** у BGE-M3 и 63.22 у mE5-large-instruct;
   dim уже нативно 1024 + MRL. Единственный кандидат, который **одновременно** даёт тот же
   контракт (1024 / MRL / Qwen-семейство / Apache-2.0 / TEI), что и 4B, и снимает ~6.7×
   параметров. Отставание от 4B по MTEB (Multilingual) — 5.1 пункта.
   Подтверждено: официальные карточки [0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
   и [4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B) (одна и та же таблица MTEB).
2. **jina-embeddings-v3** — 572 M, многоязычное среднее **64.44**, англ. 65.52; в статье
   прямо заявлено превосходство над multilingual-e5-large на всех многоязычных задачах и
   превосходство над text-embedding-3-large (65.52 против 64.60 в англ. блоке Table 4).
   Но: **CC BY-NC 4.0** (коммерческое использование — только по договору), TEI её не
   заявляет, а RU-замер есть только один — MTEB-rus 63.45 из чужой карточки.
   Источник: [arXiv 2409.10173](https://arxiv.org/abs/2409.10173), [USER2](https://huggingface.co/deepvk/USER2-base).
3. **USER-bge-m3** — лучший **русско-специфичный** в найденных замерах: encodechka 0.799
   (выше bge-m3 0.787, USER-base 0.772, e5-large 0.78) и MTEB-rus 62.80 при 359 M и 1371 MB
   против 2166 MB у bge-m3. Но dim жёстко 1024 (MRL нет), многоязычного рейтинга нет,
   контекст 8192 (наследие bge-m3). Источник: [карточка](https://huggingface.co/deepvk/USER-bge-m3), [encodechka](https://github.com/avidale/encodechka).
4. **multilingual-e5-large-instruct** — силён именно на русском: ruMTEB Average **66.03**
   (лучшее среди моделей ≤0.6 B в статье ruMTEB), MTEB-rus 65.00 (выше jina-v3 63.45 и
   USER-bge-m3 62.80) — но на многоязычном MTEB 63.22 против 69.45 у 4B и лимит 512 токенов.
   Источник: [ruMTEB paper](https://arxiv.org/abs/2408.12503), [USER2](https://huggingface.co/deepvk/USER2-base).

**Шаг вниз (не соперники 4B по качеству):** BGE-M3 (59.56 многояз. / 61.58 ruMTEB),
multilingual-e5-large (59.58 / 61.41), ru-en-RoSBERTa (61.77 ruMTEB, но rusBEIR 0.4688 —
ниже bge-m3 0.5099 и FRIDA 0.5133), mE5-base и всё с dim 768, **все монолингвальные
ruBERT/DeepPavlov SBERT** (ruMTEB 42.22–48.72 — провал на 13–19 пунктов от BGE-M3),
LaBSE (rusBEIR 0.2806), rubert-tiny2 (быстрая, но 42.22). FRIDA — сильна на RU-поиске
(лучший из нере-ранкеров в rusBEIR), но 1536 dim без MRL, 823 M и 512 токенов.

**Чего эти данные не доказывают:** прямого RU-замера **Qwen3-Embedding-4B и 0.6B** ни в
одном найденном источнике нет. Вывод «4B ≈ или выше e5-large-instruct на русском» опирается
на MTEB (Multilingual) 69.45 против 63.22; на русских задачах порядок может отличаться —
ruMTEB сам показывает, что русские instruct-модели обгоняют многоязычные не-instruct.
Это ключевая дырка в обосновании перехода.

Арифметика по скорости (моя, не замер): 4 021.8 M / 595.8 M = **6.75×** параметров у 4B
против 0.6B при коротком контексте; на длинном контексте разрыв меньше по времени, но больше
по VRAM. Публичного tok/s ни для той, ни для другой модели в вебе не нашлось.

---

## ЧТО НЕ НАШЛОСЬ

1. **RU-замеры Qwen3-Embedding-4B / 0.6B** — ни в карточках, ни в статьях, ни в
   `rusBEIR` (`results.jsonl` этого спейса, 18 записей, — Qwen там нет), ни через
   `datasets-server` HF (отдавал 502 / «Authentication check … failed»). Официальные
   карточки дают только MTEB (Multilingual / Eng v2 / C-MTEB), русского подсчёта нет.
2. **RUSSE** — не найдено ни как задача ruMTEB (в Table 1 перечислены RuBQ 2.0,
   MIRACL/RiaNews, georeview, kinopoisk и т. д.; RUSSE отсутствует), ни как отдельный
   лидерборд в проверенных источниках. Возможно, бенчмарк закрыт/устарел — подтвердить
   не удалось.
3. **Независимые замеры скорости (tok/s, строк/с, latency) для Qwen3-Embedding-\*** —
   ни одного. TEI даёт только качественный класс «Very Expensive»
   ([TEI README](https://github.com/huggingface/text-embeddings-inference#supported-models)),
   цифр нет. Числа encodechka есть, но без единиц, железа и без Qwen.
4. **MLDR/длинный контекст на русском для Qwen3-Embedding-\*** — MTEB-rus/MLDR-rus
   публикуются только для USER-bge-m3 (58.53), USER2 (54.17/51.69), jina-v3 (49.67),
   KaLM-v1.5 (53.75), E5-mistral-7b (52.40) — Qwen отсутствует.
5. **jina-embeddings-v3 по русским задачам по отдельности** — нашлось только агрегированное
   MTEB-rus Mean(task) 63.45 из карточки USER2; своих per-task RU-чисел jina не публикует.
6. **Живой лидерборд ruMTEB/MTEB** — HF-спейсы (`mteb/leaderboard`, `kaengreg/rusBEIR`)
   и datasets-server не отдают данные без JS; по ним сверяться не удалось.
7. **Поиск как таковой** — WebSearch (403, недельная квота), DuckDuckGo, Bing, Mojeek,
   Searx (captcha/пусто). Поэтому источником служат только известные URL первоисточников,
   и список альтернатив ограничен теми, что были названы в задаче + FRIDA/USER2.
