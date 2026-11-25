-- Se alguma linha apontar para um registro inexistente, o init falha aqui.
ALTER TABLE modulos_aulas   ADD FOREIGN KEY (curso_id)     REFERENCES cursos (curso_id);
ALTER TABLE matriculas      ADD FOREIGN KEY (aluno_id)     REFERENCES alunos (aluno_id);
ALTER TABLE matriculas      ADD FOREIGN KEY (curso_id)     REFERENCES cursos (curso_id);
ALTER TABLE historico_aulas ADD FOREIGN KEY (matricula_id) REFERENCES matriculas (matricula_id);
ALTER TABLE historico_aulas ADD FOREIGN KEY (aula_id)      REFERENCES modulos_aulas (aula_id);
ANALYZE;
