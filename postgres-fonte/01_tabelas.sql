-- Schema da fonte (OLTP). As FKs ficam em 03_chaves.sql: validar tudo de uma vez,
-- depois da carga, é mais rápido do que validar linha a linha durante o COPY.
CREATE TABLE alunos (
    aluno_id       INTEGER PRIMARY KEY,
    nome           TEXT    NOT NULL,
    email          TEXT    NOT NULL,
    data_cadastro  DATE    NOT NULL,
    plano_ativo    BOOLEAN NOT NULL
);

CREATE TABLE cursos (
    curso_id             INTEGER PRIMARY KEY,
    titulo               TEXT    NOT NULL,
    categoria            TEXT    NOT NULL,
    carga_horaria_horas  INTEGER NOT NULL,
    preco                NUMERIC(10,2) NOT NULL
);

CREATE TABLE modulos_aulas (
    aula_id           INTEGER PRIMARY KEY,
    curso_id          INTEGER NOT NULL,
    titulo_aula       TEXT    NOT NULL,
    ordem_sequencial  INTEGER NOT NULL,
    duracao_minutos   INTEGER NOT NULL
);

CREATE TABLE matriculas (
    matricula_id      INTEGER PRIMARY KEY,
    aluno_id          INTEGER NOT NULL,
    curso_id          INTEGER NOT NULL,
    data_matricula    DATE    NOT NULL,
    status_conclusao  TEXT    NOT NULL
);

CREATE TABLE historico_aulas (
    historico_id         INTEGER PRIMARY KEY,
    matricula_id         INTEGER   NOT NULL,
    aula_id              INTEGER   NOT NULL,
    data_acesso          TIMESTAMP NOT NULL,
    segundos_assistidos  INTEGER   NOT NULL,
    concluida_flag       BOOLEAN   NOT NULL,
    nota_quiz            NUMERIC(4,2)          -- nula quando a aula não foi concluída
);
