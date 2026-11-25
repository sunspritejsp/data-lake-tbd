"""Cria (ou atualiza) conexão, datasets, gráficos e dashboards pela API do Superset.

Rodar: docker compose exec superset python /app/projeto/criar_dashboards.py
"""
import json
import os

import requests

URL = "http://localhost:8088/api/v1"
s = requests.Session()
s.headers["Authorization"] = "Bearer " + s.post(f"{URL}/security/login", json={
    "username": "admin", "password": os.environ["SUPERSET_ADMIN_PASSWORD"],
    "provider": "db", "refresh": True}).json()["access_token"]
s.headers["X-CSRFToken"] = s.get(f"{URL}/security/csrf_token/").json()["result"]
s.headers["Referer"] = URL


def chamar(metodo, caminho, **kw):
    r = s.request(metodo, f"{URL}/{caminho}", **kw)
    if not r.ok:
        raise RuntimeError(f"{metodo} {caminho}: {r.status_code} {r.text[:500]}")
    return r.json()


def salvar(recurso, campo, nome, corpo, so_criar=()):
    """Atualiza se já existir um item com esse nome; senão, cria. Devolve o id."""
    q = json.dumps({"filters": [{"col": campo, "opr": "eq", "value": nome}]})
    achados = chamar("GET", f"{recurso}/", params={"q": q})["result"]
    if achados:
        chamar("PUT", f"{recurso}/{achados[0]['id']}", json={k: v for k, v in corpo.items() if k not in so_criar})
        return achados[0]["id"]
    return chamar("POST", f"{recurso}/", json=corpo)["id"]


banco = salvar("database", "database_name", "Lake (Trino)", {
    "database_name": "Lake (Trino)", "sqlalchemy_uri": "trino://superset@trino:8080/hive", "expose_in_sqllab": True})

# ── Datasets: consultas sobre a ouro, com fatos e dimensões já ligados ──────────
# 3600e0 é double: com 3600.0 (decimal), o Trino arredondaria cada linha antes da soma.
SQL = {
    "matriculas": """
        SELECT f.matricula_id, f.sk_aluno, f.status_fonte, f.status_calculado, f.preco_tabela, f.pct_progresso,
               f.aulas_concluidas, f.flag_antes_do_cadastro, f.flag_conclusao_sem_evidencia,
               t.data, CAST(t.ano AS varchar) AS ano, t.ano_mes, c.categoria, c.titulo AS curso, c.faixa_preco
        FROM hive.ouro.fato_matricula f
        JOIN hive.ouro.dim_tempo t ON f.sk_data_matricula = t.sk_data
        JOIN hive.ouro.dim_curso c ON f.sk_curso = c.sk_curso""",
    "acessos": """
        SELECT f.historico_id, f.segundos_assistidos / 3600e0 AS horas, f.pct_assistido, f.concluida_flag, f.nota_quiz,
               t.data, CAST(t.ano AS varchar) AS ano, t.ano_mes, t.dia_semana, t.tipo_dia,
               c.categoria, c.curso_id, c.titulo AS curso, a.ordem_sequencial
        FROM hive.ouro.fato_acesso_aula f
        JOIN hive.ouro.dim_tempo t ON f.sk_data = t.sk_data
        JOIN hive.ouro.dim_curso c ON f.sk_curso = c.sk_curso
        JOIN hive.ouro.dim_aula a ON f.sk_aula = a.sk_aula""",
    "acessos_por_dia": """
        SELECT t.data, CAST(t.ano AS varchar) AS ano, t.tipo_dia, t.nome_feriado, count(f.historico_id) AS acessos
        FROM hive.ouro.dim_tempo t LEFT JOIN hive.ouro.fato_acesso_aula f ON f.sk_data = t.sk_data
        WHERE t.sk_data BETWEEN (SELECT min(sk_data) FROM hive.ouro.fato_acesso_aula)
                            AND (SELECT max(sk_data) FROM hive.ouro.fato_acesso_aula)
        GROUP BY 1, 2, 3, 4""",
    "regras_qualidade": """
        SELECT regra, tabela, descricao, acao, linhas_avaliadas, linhas_afetadas, pct_afetado, dt_ingestao
        FROM hive.qualidade.regras WHERE dt_ingestao = (SELECT max(dt_ingestao) FROM hive.qualidade.regras)""",
    "volumes": """
        SELECT camada, tabela, linhas, dt_ingestao,
               CASE camada WHEN 'bronze' THEN '1. bronze' WHEN 'prata' THEN '2. prata' ELSE '3. ouro' END AS camada_ordem
        FROM hive.qualidade.volumes WHERE dt_ingestao = (SELECT max(dt_ingestao) FROM hive.qualidade.volumes)""",
}
ROTULOS = {
    "regra": "Regra", "tabela": "Tabela", "descricao": "Descrição", "acao": "Ação", "linhas_avaliadas": "Avaliadas",
    "linhas_afetadas": "Afetadas", "pct_afetado": "% afetado", "camada_ordem": "Camada", "linhas": "Linhas",
    "curso_id": "Id", "curso": "Curso", "categoria": "Categoria", "status_fonte": "Status na fonte",
    "status_calculado": "Status calculado",
}
ds = {}
for nome, sql in SQL.items():
    ds[nome] = salvar("dataset", "table_name", nome,
                      {"database": banco, "schema": "ouro", "table_name": nome, "sql": sql},
                      so_criar=("database", "schema", "table_name"))
    chamar("PUT", f"dataset/{ds[nome]}/refresh")
    colunas = chamar("GET", f"dataset/{ds[nome]}")["result"]["columns"]
    chamar("PUT", f"dataset/{ds[nome]}", json={"columns": [
        {"id": c["id"], "column_name": c["column_name"], "verbose_name": ROTULOS.get(c["column_name"])}
        for c in colunas]})


# ── Gráficos ────────────────────────────────────────────────────────────────────
def m(rotulo, sql):
    return {"expressionType": "SQL", "sqlExpression": sql, "label": rotulo, "optionName": "m_" + str(abs(hash(rotulo)))}


def grafico(nome, dataset, tipo, **params):
    base = {"datasource": f"{ds[dataset]}__table", "viz_type": tipo, "adhoc_filters": [], "row_limit": 1000,
            "time_range": "No filter", "color_scheme": "lake", **params}
    return salvar("chart", "slice_name", nome, {
        "slice_name": nome, "viz_type": tipo, "datasource_id": ds[dataset], "datasource_type": "table",
        "params": json.dumps(base)})


def numero(nome, dataset, sql, formato=",d", sub=""):
    return grafico(nome, dataset, "big_number_total", metric=m(nome, sql), y_axis_format=formato, subheader=sub,
                   header_font_size=0.4, subheader_font_size=0.125)


def barras(nome, dataset, eixo, metrica, horizontal=False, formato=",d", maximo=None, valores=True, **extra):
    # `maximo` deixa espaço no fim do eixo para o rótulo da maior barra
    if maximo:
        extra |= {"truncateYAxis": True, "y_axis_bounds": [0, maximo]}
    return grafico(nome, dataset, "echarts_timeseries_bar", x_axis=eixo, metrics=[metrica], groupby=[],
                   orientation="horizontal" if horizontal else "vertical", y_axis_format=formato,
                   show_legend=False, show_value=valores, rich_tooltip=True, truncate_metric=True, **extra)


def tabela(nome, dataset, colunas, **extra):
    return grafico(nome, dataset, "table", query_mode="raw", all_columns=colunas, server_pagination=False,
                   table_timestamp_format="%d/%m/%Y", include_search=False, show_cell_bars=False, **extra)


G = {
    "n_mat": numero("Matrículas", "matriculas", "COUNT(*)"),
    "n_alu": numero("Alunos", "matriculas", "COUNT(DISTINCT sk_aluno)"),
    "n_val": numero("Valor de tabela", "matriculas", "SUM(preco_tabela)", "$,.0f", "soma dos preços dos cursos"),
    "n_hor": numero("Horas assistidas", "acessos", "SUM(horas)", ",.0f"),
    "n_pro": numero("Progresso médio", "matriculas", "AVG(pct_progresso) / 100", ",.1%", "aulas concluídas de 20"),
    "mes": grafico("Matrículas por mês (jun/2025 é parcial)", "matriculas", "echarts_timeseries_line", x_axis="data",
                   time_grain_sqla="P1M", metrics=[m("Matrículas", "COUNT(*)")], groupby=[], y_axis_format=",d",
                   show_legend=False, rich_tooltip=True, x_axis_time_format="%m/%Y", markerEnabled=True, markerSize=8,
                   truncateYAxis=False, y_axis_bounds=[0, None], adhoc_filters=[]),
    "cat": barras("Valor de tabela por categoria", "matriculas", "categoria", m("Valor de tabela", "SUM(preco_tabela)"),
                  horizontal=True, formato="$,.3s", maximo=48_000_000, x_axis_sort="Valor de tabela", x_axis_sort_asc=False),
    "rec": grafico("Status da fonte x status calculado", "matriculas", "table", query_mode="aggregate",
                   groupby=["status_fonte", "status_calculado"],
                   metrics=[m("Matrículas", "COUNT(*)"), m("Progresso", "AVG(pct_progresso) / 100")],
                   order_desc=True, show_cell_bars=False,
                   column_config={"Matrículas": {"d3NumberFormat": ",d"}, "Progresso": {"d3NumberFormat": ",.1%"}}),
    "dia": barras("Média de acessos por dia (feriados: BrasilAPI)", "acessos_por_dia", "tipo_dia",
                  m("Acessos por dia", "AVG(acessos)"), horizontal=True, formato=",.0f", maximo=5_500,
                  x_axis_sort="Acessos por dia", x_axis_sort_asc=False),
    "ord": barras("Horas assistidas por posição da aula no curso", "acessos", "ordem_sequencial",
                  m("Horas", "SUM(horas)"), valores=False, x_axis_sort="ordem_sequencial", x_axis_sort_asc=True,
                  xAxisForceCategorical=True),
    "top": grafico("Cursos com mais horas assistidas", "acessos", "table", query_mode="aggregate",
                   groupby=["curso_id", "curso", "categoria"], metrics=[m("Horas", "SUM(horas)"), m("Acessos", "COUNT(*)")],
                   row_limit=10, order_desc=True, show_cell_bars=False,
                   column_config={"Horas": {"d3NumberFormat": ",.0f"}, "Acessos": {"d3NumberFormat": ",d"}}),
    "q_reg": numero("Regras avaliadas", "regras_qualidade", "COUNT(*)"),
    "q_cri": numero("Regras críticas violadas", "regras_qualidade",
                    "COALESCE(SUM(CASE WHEN acao = 'critica' AND linhas_afetadas > 0 THEN 1 ELSE 0 END), 0)",
                    sub="acima de zero, a execução falha"),
    "q_qua": numero("Linhas em quarentena", "regras_qualidade",
                    "SUM(CASE WHEN acao = 'quarentena' THEN linhas_afetadas ELSE 0 END)"),
    "q_sem": numero("Conclusões sem evidência", "matriculas",
                    "SUM(CASE WHEN flag_conclusao_sem_evidencia THEN 1 ELSE 0 END)",
                    sub="Concluído na fonte, sem 20 aulas concluídas"),
    "q_bar": barras("Linhas afetadas por regra violada", "regras_qualidade", "descricao",
                    m("Linhas afetadas", "SUM(linhas_afetadas)"), horizontal=True, maximo=560_000,
                    x_axis_sort="Linhas afetadas", x_axis_sort_asc=False, adhoc_filters=[{
                        "clause": "WHERE", "expressionType": "SQL", "sqlExpression": "linhas_afetadas > 0",
                        "filterOptionName": "f_afetadas"}]),
    "q_vol": grafico("Linhas por camada e tabela", "volumes", "table", query_mode="raw",
                     all_columns=["camada_ordem", "tabela", "linhas"], order_by_cols=['["camada_ordem", true]'],
                     show_cell_bars=False, column_config={"linhas": {"d3NumberFormat": ",d"}}),
    "q_tab": tabela("Todas as regras da última execução", "regras_qualidade",
                    ["regra", "tabela", "descricao", "acao", "linhas_avaliadas", "linhas_afetadas", "pct_afetado"],
                    order_by_cols=['["regra", true]'],
                    column_config={"linhas_avaliadas": {"d3NumberFormat": ",d"}, "linhas_afetadas": {"d3NumberFormat": ",d"},
                                   "pct_afetado": {"d3NumberFormat": ",.4~f"}}),
}
NOMES = {i["id"]: i["slice_name"] for i in chamar("GET", "chart/", params={"q": json.dumps({"page_size": 100})})["result"]}


# ── Dashboards ──────────────────────────────────────────────────────────────────
def dashboard(titulo, slug, linhas, filtros):
    """linhas: [(altura, [(gráfico, largura), ...]), ...]; a largura total de uma linha é 12."""
    pos = {"DASHBOARD_VERSION_KEY": "v2",
           "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
           "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
           "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": titulo}}}
    for n, (altura, itens) in enumerate(linhas):
        linha = f"ROW-{n}"
        pos["GRID_ID"]["children"].append(linha)
        pos[linha] = {"type": "ROW", "id": linha, "children": [], "parents": ["ROOT_ID", "GRID_ID"],
                      "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for chave, largura in itens:
            cid = f"CHART-{chave}"
            pos[linha]["children"].append(cid)
            pos[cid] = {"type": "CHART", "id": cid, "children": [], "parents": ["ROOT_ID", "GRID_ID", linha],
                        "meta": {"chartId": G[chave], "width": largura, "height": altura, "sliceName": NOMES[G[chave]]}}
    ids = [G[c] for _, itens in linhas for c, _ in itens]
    nativos = [{
        "id": f"NATIVE_FILTER-{coluna}", "name": rotulo, "type": "NATIVE_FILTER", "filterType": "filter_select",
        "targets": [{"datasetId": ds[dataset], "column": {"name": coluna}}],
        "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "searchAllOptions": False,
                          "inverseSelection": False, "defaultToFirstItem": False},
        "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": [G[x] for x in fora]},
        "chartsInScope": [i for i in ids if i not in [G[x] for x in fora]],
        "tabsInScope": [], "description": "",
    } for rotulo, dataset, coluna, fora in filtros]
    meta = {"color_scheme": "lake", "native_filter_configuration": nativos, "cross_filters_enabled": True,
            "refresh_frequency": 0, "expanded_slices": {}, "timed_refresh_immune_slices": [], "label_colors": {n: "#2a78d6" for n in ("Matrículas", "Valor de tabela", "Acessos por dia", "Horas", "Linhas afetadas")},
            "shared_label_colors": {}, "default_filters": "{}", "chart_configuration": {}}
    did = salvar("dashboard", "dashboard_title", titulo, {
        "dashboard_title": titulo, "slug": slug, "published": True,
        "position_json": json.dumps(pos), "json_metadata": json.dumps(meta)})
    for i in ids:
        atuais = {d["id"] for d in chamar("GET", f"chart/{i}")["result"]["dashboards"]}
        chamar("PUT", f"chart/{i}", json={"dashboards": sorted(atuais | {did})})
    return did


dashboard("Cursos online: matrículas e engajamento", "engajamento", [
    (20, [("n_mat", 2), ("n_alu", 2), ("n_val", 3), ("n_hor", 3), ("n_pro", 2)]),
    (50, [("mes", 7), ("cat", 5)]),
    (50, [("rec", 4), ("dia", 4), ("ord", 4)]),
    (50, [("top", 12)]),
], [("Categoria", "matriculas", "categoria", ["dia"]), ("Ano", "matriculas", "ano", [])])

dashboard("Qualidade dos dados do lake", "qualidade", [
    (20, [("q_reg", 3), ("q_cri", 3), ("q_qua", 3), ("q_sem", 3)]),
    (82, [("q_bar", 8), ("q_vol", 4)]),
    (88, [("q_tab", 12)]),
], [])
print(f"ok: {len(ds)} datasets, {len(G)} gráficos, 2 dashboards")
