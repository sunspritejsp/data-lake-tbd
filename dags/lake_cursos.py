"""DAG do data lake: bronze -> prata -> ouro, com portões de qualidade entre as camadas."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task, task_group

FUSO = pendulum.timezone("America/Maceio")
# Dia da ingestão: fim do intervalo de dados. Não muda se a task for reexecutada.
DT = "{{ data_interval_end.in_timezone('America/Maceio').to_date_string() }}"
EXECUCAO = "{{ run_id }}"
TABELAS = ["alunos", "cursos", "modulos_aulas", "matriculas", "historico_aulas", "feriados"]


@dag(
    dag_id="lake_cursos",
    description="Postgres e BrasilAPI -> bronze -> prata -> ouro",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 11, 1, tz=FUSO),
    catchup=False,
    max_active_runs=1,       # as camadas prata e ouro são substituídas a cada execução
    max_active_tasks=3,      # limite de memória da máquina
    default_args={"owner": "engenharia-dados", "retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["medalhao"],
    doc_md=__doc__,
)
def lake_cursos():

    @task_group
    def bronze():
        @task
        def ingerir(tabela, dt, execucao):
            from pipeline import bronze
            return bronze.ingerir(tabela, dt, execucao)

        @task
        def registrar():
            from pipeline.catalogo import registrar
            for tabela in TABELAS:
                registrar("bronze", tabela, "dt_ingestao")

        [ingerir.override(task_id=t)(t, DT, EXECUCAO) for t in TABELAS] >> registrar()

    @task_group
    def prata():
        @task
        def preparar(dt):
            from pipeline import qualidade
            qualidade.iniciar(dt)

        @task
        def cadastros(dt, execucao):
            from pipeline import prata
            prata.cadastros(dt, execucao)

        @task
        def historico(dt, execucao):
            from pipeline import prata
            prata.historico(dt, execucao)

        @task
        def matriculas(dt, execucao):
            from pipeline import prata
            prata.matriculas(dt, execucao)

        # sem retry: repetir não muda o resultado de uma regra violada
        @task(retries=0)
        def portao_de_qualidade(dt):
            from pipeline import qualidade
            return qualidade.verificar(dt)

        (preparar(DT) >> cadastros(DT, EXECUCAO) >> historico(DT, EXECUCAO)
         >> matriculas(DT, EXECUCAO) >> portao_de_qualidade(DT))

    @task_group
    def ouro():
        @task
        def construir(tabela):
            from pipeline import ouro
            return getattr(ouro, tabela)()

        @task(retries=0)
        def validar(dt):
            from pipeline import ouro
            return len(ouro.validar(dt))

        @task
        def medir_volumes(dt):
            from pipeline import qualidade
            qualidade.medir_volumes(dt)

        dims = [construir.override(task_id=t)(t) for t in ("dim_aluno", "dim_curso", "dim_aula", "dim_tempo")]
        fatos = [construir.override(task_id=t)(t) for t in ("fato_matricula", "fato_acesso_aula")]
        fim = validar(DT)
        for fato in fatos:
            dims >> fato >> fim
        fim >> medir_volumes(DT)

    bronze() >> prata() >> ouro()


lake_cursos()
