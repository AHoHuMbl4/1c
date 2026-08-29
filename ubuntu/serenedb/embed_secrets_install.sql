-- Один секрет эмбеддера: имя и значения — psql -v (не в командной строке shell).
-- Вызывается из embed_secrets_install.sh в цикле по EMBED_HOSTS + qwen.
CREATE OR REPLACE SECRET :"sec_name" (
  TYPE openai,
  api_key :'api_key',
  base_url :'base_url',
  embeddings_path :'embed_path'
);
