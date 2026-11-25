-- Validação da camada ouro. Cada consulta devolve: teste, esperado, obtido.
-- A task validar_ouro falha se algum par for diferente. Ela troca {dt} pelo dia da ingestão.

-- 1. Contagens: nada se perde nem se multiplica da prata para a ouro
SELECT 'linhas fato_acesso_aula', (SELECT count(*) FROM hive.prata.historico_aulas), (SELECT count(*) FROM hive.ouro.fato_acesso_aula);
SELECT 'linhas fato_matricula', (SELECT count(*) FROM hive.prata.matriculas), (SELECT count(*) FROM hive.ouro.fato_matricula);
SELECT 'linhas dim_aluno (sem a linha -1)', (SELECT count(*) FROM hive.prata.alunos), (SELECT count(*) FROM hive.ouro.dim_aluno WHERE sk_aluno <> -1);
SELECT 'linhas dim_curso (sem a linha -1)', (SELECT count(*) FROM hive.prata.cursos), (SELECT count(*) FROM hive.ouro.dim_curso WHERE sk_curso <> -1);
SELECT 'linhas dim_aula (sem a linha -1)', (SELECT count(*) FROM hive.prata.aulas), (SELECT count(*) FROM hive.ouro.dim_aula WHERE sk_aula <> -1);
SELECT 'dias em dim_tempo, de 2022 a 2025', (SELECT date_diff('day', DATE '2022-01-01', DATE '2026-01-01')), (SELECT count(*) FROM hive.ouro.dim_tempo);

-- 2. Bronze = prata + quarentena
SELECT 'historico: prata + quarentena = bronze do dia', (SELECT count(*) FROM hive.bronze.historico_aulas WHERE dt_ingestao = '{dt}'), (SELECT (SELECT count(*) FROM hive.prata.historico_aulas) + (SELECT count(*) FROM hive.prata.quarentena_historico_aulas));

-- 3. Chaves: únicas nas dimensões e sem órfãos nos fatos
SELECT 'sk_aluno unica', (SELECT count(*) FROM hive.ouro.dim_aluno), (SELECT count(DISTINCT sk_aluno) FROM hive.ouro.dim_aluno);
SELECT 'sk_curso unica', (SELECT count(*) FROM hive.ouro.dim_curso), (SELECT count(DISTINCT sk_curso) FROM hive.ouro.dim_curso);
SELECT 'sk_aula unica', (SELECT count(*) FROM hive.ouro.dim_aula), (SELECT count(DISTINCT sk_aula) FROM hive.ouro.dim_aula);
SELECT 'orfaos fato_acesso_aula.sk_aluno', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula f LEFT JOIN hive.ouro.dim_aluno d ON f.sk_aluno = d.sk_aluno WHERE d.sk_aluno IS NULL);
SELECT 'desconhecidos fato_acesso_aula.sk_aluno', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula WHERE sk_aluno = -1);
SELECT 'orfaos fato_acesso_aula.sk_curso', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula f LEFT JOIN hive.ouro.dim_curso d ON f.sk_curso = d.sk_curso WHERE d.sk_curso IS NULL);
SELECT 'desconhecidos fato_acesso_aula.sk_curso', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula WHERE sk_curso = -1);
SELECT 'orfaos fato_acesso_aula.sk_aula', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula f LEFT JOIN hive.ouro.dim_aula d ON f.sk_aula = d.sk_aula WHERE d.sk_aula IS NULL);
SELECT 'desconhecidos fato_acesso_aula.sk_aula', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula WHERE sk_aula = -1);
SELECT 'orfaos fato_acesso_aula.sk_data', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_acesso_aula f LEFT JOIN hive.ouro.dim_tempo d ON f.sk_data = d.sk_data WHERE d.sk_data IS NULL);
SELECT 'orfaos fato_matricula.sk_aluno', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_matricula f LEFT JOIN hive.ouro.dim_aluno d ON f.sk_aluno = d.sk_aluno WHERE d.sk_aluno IS NULL);
SELECT 'desconhecidos fato_matricula.sk_aluno', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_matricula WHERE sk_aluno = -1);
SELECT 'orfaos fato_matricula.sk_curso', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_matricula f LEFT JOIN hive.ouro.dim_curso d ON f.sk_curso = d.sk_curso WHERE d.sk_curso IS NULL);
SELECT 'desconhecidos fato_matricula.sk_curso', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_matricula WHERE sk_curso = -1);
SELECT 'orfaos fato_matricula.sk_data_matricula', (SELECT BIGINT '0'), (SELECT count(*) FROM hive.ouro.fato_matricula f LEFT JOIN hive.ouro.dim_tempo d ON f.sk_data_matricula = d.sk_data WHERE d.sk_data IS NULL);

-- 4. Totais preservados
SELECT 'segundos assistidos', (SELECT sum(segundos_assistidos) FROM hive.prata.historico_aulas), (SELECT sum(segundos_assistidos) FROM hive.ouro.fato_acesso_aula);
SELECT 'aulas concluidas (soma das flags)', (SELECT count_if(concluida_flag) FROM hive.prata.historico_aulas), (SELECT count_if(concluida_flag) FROM hive.ouro.fato_acesso_aula);
SELECT 'acessos somados nas matriculas', (SELECT count(*) FROM hive.ouro.fato_acesso_aula), (SELECT sum(total_acessos) FROM hive.ouro.fato_matricula);
SELECT 'preco de tabela: fato x fonte transacional', (SELECT sum(c.preco) FROM fonte.public.matriculas m JOIN fonte.public.cursos c ON m.curso_id = c.curso_id), (SELECT sum(preco_tabela) FROM hive.ouro.fato_matricula);

-- 5. Segunda fonte integrada
SELECT 'feriados marcados em dim_tempo', (SELECT count(*) FROM hive.prata.feriados), (SELECT count(*) FROM hive.ouro.dim_tempo WHERE feriado);
