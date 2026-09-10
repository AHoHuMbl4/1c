# Семейство Qwen3-Embedding: официальные замеры, размеры, скорость

Собрано 10.09.2026 по вебу. Вопрос: можно ли перейти с Qwen3-Embedding-4B (bf16, dim 1024,
~1 GPU) на 0.6B ради скорости, не потеряв точность поиска.

Все числа ниже — либо из официальных публикаций Qwen (блог/карточка HF/GitHub/статья),
либо из измерений третьих сторон с указанием стенда. Где число получено арифметикой,
а не замером — это помечено прямо в тексте. Источники — в конце файла.

## ФАКТЫ

Модели: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B),
[4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B),
[8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B) — Apache-2.0, 100+ языков
(русский в списке), 32k контекст, MRL (произвольная размерность), instruction-aware.

| модель | MTEB-multi (Mean Task) | RU-метрика (MTEB, 38 рус. подзадач, среднее) | размер | VRAM (bf16, веса) | скорость | источник-URL |
|---|---|---|---|---|---|---|
| Qwen3-Embedding-0.6B | **64.33** (Retrieval 64.64) | **73.73** | 596M параметров, safetensors 1.19 ГБ; GGUF Q8_0 0.64 ГБ | 1.19 ГБ (замер на стенде: peak 3.875 ГиБ, батч 4 × 5000 ток.) | замер: 48.57 с GPU-forward на 355 документов NarrativeQA (A100, батч 4, max 5000 ток.); замер RU: медиана 22.8 мс на запрос (TEI, локальный GPU) | [blog](https://qwenlm.github.io/blog/qwen3-embedding/) · [HF 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) · [FastE табл. 8](https://arxiv.org/html/2609.08407v1) · [Habr 1010200](https://habr.com/ru/articles/1010200/) |
| Qwen3-Embedding-4B | **69.45** (Retrieval 69.60) | **78.21** | 4.02B параметров, safetensors 8.04 ГБ; GGUF Q4_K_M 2.50 ГБ, Q8_0 4.28 ГБ | 8.04 ГБ (замер на стенде: peak 11.873 ГиБ, те же условия) | замер: 201.31 с GPU-forward на том же корпусе (A100, батч 4, max 5000) | [HF 4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B) · [FastE табл. 8](https://arxiv.org/html/2609.08407v1) |
| Qwen3-Embedding-8B | **70.58** (Retrieval 70.88) | **79.58** | 7.57B параметров, safetensors 15.13 ГБ; GGUF Q4_K_M 4.68 ГБ | 15.13 ГБ | — (в FastE не измерялась) | [HF 8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B) |
| Qwen3-Embedding-0.6B (GGUF) | — | — | Q8_0 **639 МБ**, f16 1198 МБ | — | — | [HF GGUF 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF) |
| Qwen3-Embedding-4B (GGUF) | — | — | Q4_K_M **2497 МБ**, Q8_0 4280 МБ, f16 8050 МБ | — | — | [HF GGUF 4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF) |

Контекст/архитектура (официальная таблица): 0.6B — 28 слоёв, 32K, dim до 1024 (настраивается
32…1024); 4B — 36 слоёв, 32K, dim до 2560 (32…2560); 8B — 36 слоёв, 32K, dim до 4096 (32…4096).
Источник: [Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/), [GitHub QwenLM/Qwen3-Embedding](https://github.com/QwenLM/Qwen3-Embedding).

Размеры весов — из листингов файлов HF (safetensors/GGUF), это точные байты, а не оценка:

| модель | параметров (HF API) | bf16 safetensors | int8 (расчёт = params × 1 байт) | GGUF Q4 |
|---|---|---|---|---|
| 0.6B | 595 776 512 | 1.1916 ГБ | ≈ 0.60 ГБ | нет в репо |
| 4B | 4 021 774 336 | 8.0436 ГБ | ≈ 4.02 ГБ | Q4_K_M 2.497 ГБ |
| 8B | 7 567 295 488 | 15.135 ГБ | ≈ 7.57 ГБ | Q4_K_M 4.677 ГБ |

### Официальные MTEB-таблицы Qwen (полностью, для контекста)

| Модель | MTEB (Multilingual) Mean(Task) | Instruct. Retrieval | Retri. | MTEB (Eng v2) | C-MTEB |
|---|---|---|---|---|---|
| Qwen3-Embedding-0.6B | 64.33 | 5.09 | 64.64 | 70.70 | 66.33 |
| Qwen3-Embedding-4B | 69.45 | 11.56 | 69.60 | 74.60 | 72.27 |
| Qwen3-Embedding-8B | 70.58 | 10.06 | 70.88 | 75.22 | 73.84 |

Источник: [Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/),
[GitHub README](https://github.com/QwenLM/Qwen3-Embedding),
[HF 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B). Для сравнения: BGE-M3 (0.6B) — 59.56,
multilingual-e5-large-instruct (0.6B) — 63.22, gte-Qwen2-7b-instruct — 62.51,
text-embedding-3-large — 58.93.

### Русские числа (MTEB, официальный датасет результатов)

Официального опубликованного текста с агрегатом ruMTEB по моделям Qwen3 не нашлось; числа
ниже посчитаны из официального датасета результатов MTEB
([mteb/results](https://huggingface.co/datasets/mteb/results), parquet `data/train-*`), отобраны
все подзадачи с языком `rus-Cyrl` / подмножеством `ru` / парой `rus_Cyrl-eng_Latn`. Метрика —
то, что публикует MTEB по подзадаче (nDCG@10 для retrieval/reranking, accuracy/Spearman/прочее
для остальных), значения в 0–100.

| подзадача (subset) | 0.6B | 4B | 8B | Δ 4B−0.6B |
|---|---|---|---|---|
| MIRACLRetrievalHardNegatives (ru) | 61.02 | 71.74 | 73.80 | **+10.72** |
| MIRACLRetrievalHardNegatives.v2 (ru) | 62.51 | 71.02 | 73.36 | **+8.51** |
| RiaNewsRetrievalHardNegatives.v2 | 73.45 | 84.42 | 84.89 | **+10.97** |
| RuBQRetrieval | 66.91 | 73.65 | 76.31 | +6.73 |
| MIRACLReranking (ru) | 60.31 | 65.19 | 66.91 | +4.88 |
| RuBQReranking | 65.67 | 72.28 | 73.47 | +6.61 |
| TERRa | 60.68 | 66.63 | 71.33 | +5.95 |
| RuSTSBenchmarkSTS | 84.20 | 88.77 | 89.16 | +4.57 |
| RUParaPhraserSTS | 72.05 | 76.59 | 76.06 | +4.53 |
| STS22 (ru) | 66.21 | 70.14 | 72.63 | +3.93 |
| STS22.v2 (ru) | 69.02 | 72.83 | 74.57 | +3.80 |
| OpusparcusPC (ru) | 89.32 | 93.04 | 93.76 | +3.72 |
| XNLI (ru) | 85.98 | 90.92 | 91.53 | +4.94 |
| MassiveIntentClassification (ru) | 75.36 | 82.56 | 84.01 | +7.20 |
| MassiveScenarioClassification (ru) | 63.93 | 87.66 | 88.67 | **+23.73** |
| KinopoiskClassification | 70.23 | 73.91 | 74.21 | +3.69 |
| RuReviewsClassification | 72.04 | 75.95 | 75.60 | +3.91 |
| GeoreviewClassification | 58.09 | 60.91 | 59.09 | +2.82 |
| HeadlineClassification | 82.50 | 83.55 | 85.41 | +1.04 |
| InappropriatenessClassification | 65.37 | 75.86 | 75.21 | **+10.49** |
| CEDRClassification | 49.88 | 51.01 | 53.05 | +1.13 |
| RuSciBenchGRNTIClassification | 64.95 | 68.20 | 70.68 | +3.25 |
| RuSciBenchOECDClassification | 52.51 | 54.19 | 56.61 | +1.68 |
| SensitiveTopicsClassification | 30.33 | 35.57 | 36.11 | +5.24 |
| GeoreviewClusteringP2P | 66.39 | 76.77 | 78.48 | **+10.38** |
| RuSciBenchGRNTIClusteringP2P | 61.17 | 63.39 | 65.31 | +2.22 |
| RuSciBenchOECDClusteringP2P | 54.01 | 55.06 | 56.36 | +1.04 |
| SIB200ClusteringS2S (rus_Cyrl) | 52.27 | 52.99 | 62.59 | +0.71 |
| Tatoeba (rus-eng) | 92.43 | 93.63 | 94.32 | +1.20 |
| BUCC.v2 (ru-en) | 97.11 | 97.53 | 97.57 | +0.42 |
| FloresBitextMining (rus_Cyrl-eng_Latn) | 99.87 | 100.00 | 100.00 | +0.13 |
| BibleNLPBitextMining (rus_Cyrl-eng_Latn) | 96.88 | 97.92 | 98.44 | +1.04 |
| NTREXBitextMining (rus_Cyrl-eng_Latn) | 98.82 | 99.27 | 99.33 | +0.44 |
| BelebeleRetrieval (rus_Cyrl-rus_Cyrl) | 92.96 | 95.79 | — | +2.83 |
| BelebeleRetrieval (rus_Cyrl-eng_Latn) | 92.55 | 96.20 | 99.08 | +3.64 |
| BelebeleRetrieval (eng_Latn-rus_Cyrl) | 91.48 | 94.86 | 98.50 | +3.38 |
| … (остальные варианты пары rus_Cyrl, см. датасет) | | | | |

В таблице — выжимка (направление `eng→rus` у bitext-задач опущено, полный список — в датасете).
Строка `BelebeleRetrieval (rus_Cyrl-rus_Cyrl)` в итог ниже не входит: у 8B этого подмножества
в датасете нет, то есть сравнить все три модели нечем.

Итог по 38 подзадачам, у которых есть оценка **всех трёх** моделей:

| | 0.6B | 4B | 8B |
|---|---|---|---|
| среднее по 38 подзадачам | 73.73 | **78.21** | **79.58** |
| retrieval (4 подзадачи) | 65.97 | **75.21** | 77.09 |
| STS (5 подзадач) | 76.16 | 80.27 | 81.24 |
| 4B лучше 0.6B в | — | **38 из 38 подзадач** | — |

## РАЗРЫВ 0.6B vs 4B (числами, с источниками)

### 1. Официальные MTEB-агрегаты Qwen (источник: [Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/), [GitHub](https://github.com/QwenLM/Qwen3-Embedding))

| метрика | 0.6B | 4B | разрыв |
|---|---|---|---|
| MTEB Multilingual, Mean(Task) | 64.33 | 69.45 | **+5.12 пункта (+8.0 % отн.)** |
| MTEB Multilingual, Retrieval | 64.64 | 69.60 | +4.96 |
| MTEB Multilingual, Instruct. Retrieval | 5.09 | 11.56 | +6.47 (рост более чем вдвое) |
| MTEB Multilingual, STS | 76.17 | 80.86 | +4.69 |
| MTEB Multilingual, Rerank | 61.41 | 65.08 | +3.67 |
| MTEB Multilingual, Clustering | 52.33 | 57.15 | +4.82 |
| MTEB Eng v2, Mean(Task) | 70.70 | 74.60 | +3.90 |
| C-MTEB, Mean(Task) | 66.33 | 72.27 | +5.94 |

Рядом для ориентира (тот же источник): 8B даёт ещё +1.13 пункта к multilingual-среднему
(70.58 против 69.45), то есть основной прирост покупается на шаге 0.6B → 4B, а не 4B → 8B.

### 2. Русский MTEB: разрыв максимален именно на поиске (источник: посчитано из [mteb/results](https://huggingface.co/datasets/mteb/results))

- среднее по 38 русским подзадачам: **73.73 → 78.21, +4.48 пункта** (медиана +3.70; минимум
  +0.13 на Flores, максимум +23.73 на MassiveScenarioClassification);
- **4B выигрывает у 0.6B во всех 38 подзадачах без исключения**;
- retrieval-подзадачи (MIRACL ru hard-neg ×2, RiaNews hard-neg, RuBQ): **65.97 → 75.21,
  +9.23 пункта** — на русском поиске разрыв в 2 раза больше среднего по всем типам задач;
- reranking (MIRACL ru, RuBQ, TERRa): 62.22 → 68.03, +5.81;
- STS: 76.16 → 80.27, +4.11; classification: 64.26 → 70.02, +5.76; clustering: 58.46 → 62.05, +3.59;
- bitext mining: 96.55 → 97.74, +1.19 (здесь разрыв минимален — задача почти насыщена у обеих).

Вывод по русскому: **на 0.6B теряется в среднем ~4.5 пункта, а на поиске (retrieval) —
~9.2 пункта** относительно 4B. Это не «шум», это систематический сдвиг в одну сторону.

### 3. Измеренная скорость и память на одном стенде (источник: [FastE, arXiv 2609.08407](https://arxiv.org/html/2609.08407v1), таблица 8)

Один A100, length-sorted батч 4, max длина 5000 токенов, корпус NarrativeQA (355 документов),
полный forward без сжатия:

| модель | GPU-forward, с | end-to-end (с токенизацией), с | пиковая память, ГиБ | nDCG@10 |
|---|---|---|---|---|
| 0.6B | **48.57** | **68.36** | **3.875** | 0.45395 |
| 4B | **201.31** | **221.12** | **11.873** | 0.58245 |
| отношение 4B/0.6B | **×4.14** | **×3.23** | **×3.06** | +0.1285 (+28.3 % отн.) |

Это единственное найденное измерение обеих моделей на одной машине в одинаковых условиях.
Оговорка: входы длинные (до 5000 токенов, длина сортирована), на коротких чанках (как в
корпусе 1С) отношение по времени будет ближе к отношению параметров, а экономия памяти
останется той же.

### 4. Локальный запуск на русском: 0.6B быстрый, но на русской таксономии слабее GigaChat

- [Habr «Семантический поиск vs полнотекстовый»](https://habr.com/ru/articles/1010200/),
  10 019 категорий Ozon, 18 запросов, Qwen3-Embedding-0.6B локально через TEI на GPU:
  **медиана 22.8 мс, среднее 21.1 мс, мин 9.0, макс 55.9** на запрос; для сравнения full-text
  PostgreSQL 1.3 мс, GigaChat API 168.3 мс, OpenAI API 274.9 мс. Автор: «Qwen3 на локальном
  GPU в 8× быстрее GigaChat и в 12× быстрее OpenAI».
- Там же по качеству: на русских разговорных запросах («велик», «лекарства», «протекает кран»)
  0.6B проигрывает GigaChat (обучен на русском) и местами OpenAI text-embedding-3-small.

### 5. Русский корпус реального клиента: 0.6B-Q8_0 против 4B-Q4_K_M и 8B-Q4_K_M

[Habr «Embedder для ИТ-крестьянина»](https://habr.com/ru/articles/984520/), 760 чанков реальной
базы клиента, вопросы и оценка — qwen2.5-coder-instruct-32b; Score = (Full + Partial×0.5)/N:

| модель | Score | Full % (полный ответ) | Any % (хоть что-то) | провальных вопросов |
|---|---|---|---|---|
| text-embedding-3-large | 2.125 | 69.3 | 99.9 | 1 |
| Qwen3-Embedding-8B-Q4_K_M | 2.117 | 67.1 | 99.7 | 2 |
| Qwen3-Embedding-4B-Q4_K_M | 2.108 | 67.2 | 99.9 | **1** |
| **Qwen3-Embedding-0.6B-Q8_0** | **2.051** | **68.1** | **99.2** | **6** |
| multilingual-e5-large-instruct | 1.632 | 53.6 | 97.2 | — |
| bge-m3 | 1.628 | 53.9 | 97.0 | — |

Разрыв 0.6B vs 4B на этом корпусе: Score −0.057, Any% −0.7 п.п., но **провальных вопросов
6 против 1** — то есть на большинстве вопросов разницы не видно, а на меньшинстве 0.6B
теряет ответ целиком. Автор статьи: «Модели серии Qwen3-Embedding показали на удивление мало
различия между собой… объём и скорость различаются в разы».

### 6. Кириллица (украинский), вопросно-ответный retrieval: разрыв < 1 пункта

[Qwen Goes Brrr, arXiv 2605.10296](https://arxiv.org/html/2605.10296v1), таблица 2 (retrieval
с фиксированным Qwen3-Reranker-8B, public/private split):

| модель | public | private |
|---|---|---|
| Qwen3-Embedding-8B | 0.9426 | 0.9592 |
| Qwen3-Embedding-0.6B | 0.9370 | 0.9507 |
| Qwen3-Embedding-0.6B, дообученная на 80k + squad | **0.9390** | **0.9581** |

Разрыв 0.6B vs 8B — 0.6–0.9 п.п.; дообучение 0.6B почти закрывает его. Авторы: «если позволяют
вычисления, большая предобученная модель — сильнейший выбор; при жёстких лимитах дообучение
маленькой модели возвращает большую часть разрыва».

### 7. Русский/славянский анализ устойчивости (источник: [arXiv 2608.24477](https://arxiv.org/html/2608.24477v1))

Статья оценивает славянское подмножество MTEB. Qwen3-Embedding там представлен **только 4B и 8B**
(0.6B не оценивалась). По русскому языку (единственный язык с покрытием 8/8 задач, наивысший
ESS 0.49):
- llama-embed-nemotron-8b — лучший по покрытийно-взвешенной согласованности (CW = 0.70);
- **Qwen3-Embedding-8B — второй (CW = 0.65)**;
- **Qwen3-Embedding-4B — устойчиво четвёртый**;
- на pair classification по русскому Qwen3-Embedding-8B — самая переносимо-согласованная
  модель (проверено 15 схемами ранжирования).

Это подтверждает, что 4B/8B — верхняя группа на русском, но числа для 0.6B там нет.

### 8. Предупреждение про серверную обвязку (источник: [issue #221, Hussain0327/amneal](https://github.com/Hussain0327/amneal/issues/221))

Замер 13.08.2026: запросный эмбеддинг одной короткой строки через серверный эндпоинт
(Qwen3-0.6B за Databricks AI Gateway) — **p50 965 мс, p95 1413 мс, n = 17**, при этом батч
по 128 текстов на ингесте того же эндпоинта амортизирует накладные расходы. То есть на коротком
одиночном запросе время определяется не размером модели, а per-request overhead сервера.
Урок для выбора: сравнивать 0.6B и 4B надо на своём батче и своей длине входа, а не по
размеру модели.

### 9. Что это значит арифметически (расчёт, не замер)

- параметров 4.02B против 0.596B — **×6.75**; веса bf16 8.04 ГБ против 1.19 ГБ — **×6.75**;
- размерность вектора 2560 против 1024 — **×2.5 по объёму индекса** и, при прочих равных,
  заметно дороже поиск по индексу (для корпуса ~1.67M строк 4B даёт ~2.5× больше байт
  на вектор, чем 0.6B; это дополнительный, независимый от инференса расход);
- переход 4B → 0.6B с сохранением bf16 освобождает ~6.8 ГБ VRAM (или позволяет уйти на
  int8/GGUF Q8_0 и вовсе на CPU);
- MRL у обеих моделей: 4B можно усечь до 1024 измерений, и тогда останется только выигрыш
  по скорости инференса, но не по объёму индекса. Усечение качества не проверено ни одним
  найденным источником для русского (см. «что не нашлось»).

## ЧТО НЕ НАШЛОСЬ

1. **Официальных чисел скорости/пропускной способности от Qwen нет.** Ни в блоге, ни в
   README GitHub, ни в карточках HF, ни в статье [arXiv 2506.05176](https://arxiv.org/abs/2506.05176)
   нет ни tokens/s, ни latency, ни VRAM (карточка HF отсылает за этим к блогу и GitHub,
   а там этого раздела нет). Всё, что есть по скорости — измерения третьих сторон.
2. **Прямого замера 0.6B против 4B от вендора (vLLM/TEI/llama.cpp/Ollama) не нашлось.**
   Есть только RFC vLLM [#21796](https://github.com/vllm-project/vllm/issues/21796),
   который констатирует, что бенчмарков эмбеддинг-сервинга в vLLM до сих пор нет,
   и харнессы без опубликованных результатов
   ([vllm-embedding-throughput-bench-tr](https://github.com/atahanuz/vllm-embedding-throughput-bench-tr),
   [unstract PR #3](https://github.com/CompleteTech-LLC/unstract/pull/3)).
3. **Опубликованного агрегата ruMTEB (среднее по русскому лидерборду) по моделям Qwen3 нет.**
   Числа в этом файле посчитаны из официального датасета результатов MTEB; проверить их
   можно только повторив выборку (язык `rus-Cyrl` / subset `ru`).
4. **Независимого сравнения 0.6B vs 4B на русских документах нет.** Habr-бенчмарк по судебной
   практике ([1030706](https://habr.com/ru/articles/1030706/), 858 актов, 7 эмбеддеров)
   Qwen3 вообще не включает; статья GigaEmbeddings ([arXiv 2510.22369](https://arxiv.org/html/2510.22369v1))
   сравнивает модели на ruMTEB, но на снимке лидерборда декабря 2024 — Qwen3-Embedding там нет;
   Habr по Ozon использует только 0.6B, без 4B.
5. **Влияния усечения MRL (2560 → 1024) на русский retrieval нет ни в одном источнике.**
   Это самый перспективный компромисс (оставить 4B, урезать вектор), но замеров нет.
6. **Поведения 0.6B на морфологии русского (падежи, словоформы запросов 1С) не измерял никто
   из найденных источников.**
7. **Точных замеров пропускной способности на длине входа ~100–500 токенов нет.** Единственный
   точный замер (FastE) — длины до 5000 токенов и батч 4, что для документов 1С нехарактерно.

## Источники

Официальные:
- [Qwen3 Embedding — блог Qwen](https://qwenlm.github.io/blog/qwen3-embedding/)
- [GitHub QwenLM/Qwen3-Embedding](https://github.com/QwenLM/Qwen3-Embedding)
- [HF Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) · [4B](https://huggingface.co/Qwen/Qwen3-Embedding-4B) · [8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B)
- [HF GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF) · [4B GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-4B-GGUF) · [8B GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF)
- [Технический отчёт, arXiv 2506.05176](https://arxiv.org/abs/2506.05176)
- [Официальный датасет результатов MTEB](https://huggingface.co/datasets/mteb/results) (использован для русских чисел)

Независимые:
- [FastE: Readout-Triggered Token Compression for LLM Embedding Inference, arXiv 2609.08407](https://arxiv.org/html/2609.08407v1) — замеры 0.6B vs 4B: время, память, качество
- [Dataset Scarcity Limits Robust Evaluation of Multilingual Embedding Models (Slavic), arXiv 2608.24477](https://arxiv.org/html/2608.24477v1) — русский/славянский анализ
- [Qwen Goes Brrr: Off-the-Shelf RAG for Ukrainian Multi-Domain Document Understanding, arXiv 2605.10296](https://arxiv.org/html/2605.10296v1) — 0.6B vs 8B на кириллице
- [Habr: Embedder для ИТ-крестьянина](https://habr.com/ru/articles/984520/) — 760 чанков реального клиента, 0.6B/4B/8B
- [Habr: Семантический поиск vs полнотекстовый на 10 000 категорий Ozon](https://habr.com/ru/articles/1010200/) — 0.6B локально, латентность
- [Habr: Бенчмарк 7 эмбеддингов и 4 реранкеров на корпусе судебной практики](https://habr.com/ru/articles/1030706/) — русский юр. корпус, Qwen3 не включён
- [vLLM RFC #21796: Optimize embedding task](https://github.com/vllm-project/vllm/issues/21796)
- [vLLM PR #19260: Support Qwen3 Embedding & Reranker](https://github.com/vllm-project/vllm/pull/19260)
- [ingest/query-асимметрия серверного эндпоинта, issue #221](https://github.com/Hussain0327/amneal/issues/221)
