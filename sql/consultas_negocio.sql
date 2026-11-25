-- Perguntas de negócio respondidas pela camada ouro (rodar no Trino).
-- "Valor de tabela" = soma do preço dos cursos matriculados; a fonte não informa o valor pago.

-- 1. Valor de tabela e matrículas por categoria
SELECT c.categoria, count(*) AS matriculas, sum(f.preco_tabela) AS valor_tabela
FROM hive.ouro.fato_matricula f JOIN hive.ouro.dim_curso c ON f.sk_curso = c.sk_curso
GROUP BY 1 ORDER BY 3 DESC;

-- 2. Matrículas por mês
SELECT t.ano_mes, count(*) AS matriculas
FROM hive.ouro.fato_matricula f JOIN hive.ouro.dim_tempo t ON f.sk_data_matricula = t.sk_data
GROUP BY 1 ORDER BY 1;

-- 3. O que a fonte diz x o que os acessos mostram
SELECT status_fonte, status_calculado, count(*) AS matriculas, round(avg(pct_progresso), 1) AS progresso_medio
FROM hive.ouro.fato_matricula GROUP BY 1, 2 ORDER BY 1, 2;

-- 4. Média de acessos por dia: dia útil, fim de semana e feriado (integra a segunda fonte).
-- O denominador são todos os dias do período com acessos, inclusive os que tiverem zero.
WITH dias AS (
    SELECT t.sk_data, t.tipo_dia, count(f.historico_id) AS acessos
    FROM hive.ouro.dim_tempo t LEFT JOIN hive.ouro.fato_acesso_aula f ON f.sk_data = t.sk_data
    WHERE t.sk_data BETWEEN (SELECT min(sk_data) FROM hive.ouro.fato_acesso_aula)
                        AND (SELECT max(sk_data) FROM hive.ouro.fato_acesso_aula)
    GROUP BY 1, 2)
SELECT tipo_dia, count(*) AS dias, round(avg(acessos), 1) AS acessos_por_dia FROM dias GROUP BY 1 ORDER BY 3 DESC;

-- 5. Os 10 cursos com mais horas assistidas
SELECT c.titulo, c.categoria, round(sum(f.segundos_assistidos) / 3600.0) AS horas
FROM hive.ouro.fato_acesso_aula f JOIN hive.ouro.dim_curso c ON f.sk_curso = c.sk_curso
GROUP BY c.sk_curso, 1, 2 ORDER BY 3 DESC LIMIT 10;

-- 6. Progresso médio por coorte de cadastro
SELECT a.coorte, count(*) AS matriculas, round(avg(f.pct_progresso), 2) AS progresso_medio
FROM hive.ouro.fato_matricula f JOIN hive.ouro.dim_aluno a ON f.sk_aluno = a.sk_aluno
GROUP BY 1 ORDER BY 1;

-- 7. Nota média por posição da aula no curso
SELECT a.ordem_sequencial, count(f.nota_quiz) AS notas, round(avg(f.nota_quiz), 2) AS nota_media
FROM hive.ouro.fato_acesso_aula f JOIN hive.ouro.dim_aula a ON f.sk_aula = a.sk_aula
GROUP BY 1 ORDER BY 1;
