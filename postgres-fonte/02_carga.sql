-- /dados é a pasta ./data do projeto, montada só para leitura no container.
COPY alunos          FROM '/dados/alunos.csv'          WITH (FORMAT csv, HEADER true);
COPY cursos          FROM '/dados/cursos.csv'          WITH (FORMAT csv, HEADER true);
COPY modulos_aulas   FROM '/dados/modulos_aulas.csv'   WITH (FORMAT csv, HEADER true);
COPY matriculas      FROM '/dados/matriculas.csv'      WITH (FORMAT csv, HEADER true);
COPY historico_aulas FROM '/dados/historico_aulas.csv' WITH (FORMAT csv, HEADER true);
