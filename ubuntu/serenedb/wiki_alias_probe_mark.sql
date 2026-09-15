\set ON_ERROR_STOP on
-- Пометка исхода разведения в probe (ok/failed + версия генератора).
-- Ключ — слово + отпечаток набора сущностей (как INSERT в collision_round).
-- Доки: Sql › Statements › UPDATE.
UPDATE :probe_table
SET result = :'result', gen_ver = :'gen_ver'
WHERE alias = :'word' AND entities_fp = :'fp';
