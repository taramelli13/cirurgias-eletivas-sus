# Gera o projeto Power BI (.pbip: modelo semântico em TMDL + relatório em PBIR)
# a partir dos CSVs de powerbi/data/. Abra powerbi/cirurgias_eletivas.pbip no
# Power BI Desktop e clique em Atualizar para carregar os dados.
#
# Uso:
#   python scripts/03_gerar_pbip.py

import json
import shutil
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POWERBI_PATH = PROJECT_ROOT / 'powerbi'
DATA_PATH = POWERBI_PATH / 'data'
NOME = 'cirurgias_eletivas'
MODEL_PATH = POWERBI_PATH / f'{NOME}.SemanticModel'
REPORT_PATH = POWERBI_PATH / f'{NOME}.Report'

# Cores da identidade visual da Fin-X (finxapp.com.br)
CORES = {
    'marinho': '#001D3D', 'azul': '#005DA6', 'ciano': '#4EC7F5', 'azul_claro': '#64BED9',
    'cinza': '#54595F', 'cinza_claro': '#E7E7E7', 'fundo': '#F4F8FB', 'branco': '#FFFFFF',
}

# --------------------------------------------------------------------------
# Modelo semântico
# --------------------------------------------------------------------------

M_TIPO = {'string': 'type text', 'int64': 'Int64.Type', 'double': 'type number', 'dateTime': 'type date'}

TABELAS = {
    'fato_cirurgias': [
        ('NumAIH', 'string'), ('Competencia', 'dateTime'), ('DataInternacao', 'dateTime'),
        ('CNES', 'string'), ('CodProcedimento', 'string'), ('CID', 'string'),
        ('Complexidade', 'string'), ('DiasPermanencia', 'int64'), ('DiasUTI', 'int64'),
        ('UsouUTI', 'int64'), ('ValorTotal', 'double'), ('Obito', 'int64'),
        ('Idade', 'int64'), ('Sexo', 'string'),
    ],
    'agg_hospital_procedimento': [
        ('CNES', 'string'), ('CodProcedimento', 'string'), ('Cirurgias', 'int64'),
        ('MediaPermanencia', 'double'), ('MedianaPermanencia', 'double'), ('TaxaUTI', 'double'),
        ('Obitos', 'int64'), ('ValorTotal', 'double'), ('MedianaPares', 'double'),
        ('Comparavel', 'int64'), ('DiasExcedentes', 'double'),
    ],
    'dim_procedimento': [
        ('CodProcedimento', 'string'), ('Procedimento', 'string'), ('PermanenciaSIGTAP', 'double'),
        ('Subgrupo', 'string'), ('FormaOrganizacao', 'string'), ('Grupo', 'string'),
        ('Cirurgias', 'int64'), ('Hospitais', 'int64'), ('ElegivelBenchmark', 'int64'),
        ('MedianaPares', 'double'), ('HospitaisComparados', 'int64'),
    ],
    'dim_hospital': [('CNES', 'string'), ('Hospital', 'string'), ('Municipio', 'string')],
    'dim_calendario': [('Competencia', 'dateTime'), ('Ano', 'int64'), ('MesNum', 'int64'), ('Mes', 'string')],
}

# Colunas que só servem de chave ou de apoio ao cálculo ficam ocultas
OCULTAS = {
    'fato_cirurgias': {'CNES', 'CodProcedimento', 'Competencia', 'NumAIH'},
    'agg_hospital_procedimento': {'CNES', 'CodProcedimento'},
}
ORDENAR_POR = {('dim_calendario', 'Mes'): 'MesNum'}

RELACIONAMENTOS = [
    ('fato_cirurgias.CNES', 'dim_hospital.CNES'),
    ('fato_cirurgias.CodProcedimento', 'dim_procedimento.CodProcedimento'),
    ('fato_cirurgias.Competencia', 'dim_calendario.Competencia'),
    ('agg_hospital_procedimento.CNES', 'dim_hospital.CNES'),
    ('agg_hospital_procedimento.CodProcedimento', 'dim_procedimento.CodProcedimento'),
]

F, A, P = 'fato_cirurgias', 'agg_hospital_procedimento', 'dim_procedimento'
MEDIDAS = [
    ('Cirurgias', f'COUNTROWS ( {F} )', '#,0'),
    ('Hospitais', f'DISTINCTCOUNT ( {F}[CNES] )', '#,0'),
    ('Valor SUS', f'SUM ( {F}[ValorTotal] )', '\\R\\$ #,0'),
    ('Leitos-dia', f'SUM ( {F}[DiasPermanencia] )', '#,0'),
    ('Permanência Média', f'AVERAGE ( {F}[DiasPermanencia] )', '#,0.00'),
    ('Taxa UTI', f'AVERAGE ( {F}[UsouUTI] )', '0.0%'),
    ('Taxa Óbito', f'AVERAGE ( {F}[Obito] )', '0.00%'),
    ('Idade Média', f'AVERAGE ( {F}[Idade] )', '#,0.0'),
    ('% Alta Complexidade', f'DIVIDE ( CALCULATE ( COUNTROWS ( {F} ), {F}[Complexidade] = "Alta" ), [Cirurgias] )', '0.0%'),
    ('Leitos-dia Excedentes', f'SUM ( {A}[DiasExcedentes] )', '#,0'),
    ('Leitos Equivalentes', 'DIVIDE ( [Leitos-dia Excedentes], 365 )', '#,0'),
    ('Permanência Média (Hospital)',
     f'CALCULATE ( DIVIDE ( SUMX ( {A}, {A}[MediaPermanencia] * {A}[Cirurgias] ), SUM ( {A}[Cirurgias] ) ), {A}[Comparavel] = 1 )',
     '#,0.00'),
    ('Mediana dos Pares', f'AVERAGE ( {P}[MedianaPares] )', '#,0.00'),
    ('Permanência SIGTAP', f'AVERAGE ( {P}[PermanenciaSIGTAP] )', '#,0'),
    ('Hospitais Acima do Padrão',
     f'COUNTROWS ( FILTER ( {A}, {A}[Comparavel] = 1 && {A}[MediaPermanencia] > {A}[MedianaPares] ) )', '#,0'),
]


def tag():
    return str(uuid.uuid4())


def tmdl_nome(nome):
    return f"'{nome}'" if any(c in nome for c in " -%()çãéêóíáú") else nome


def tmdl_tabela(nome, colunas):
    linhas = [f'table {nome}', f'\tlineageTag: {tag()}', '']
    for col, tipo in colunas:
        linhas += [f'\tcolumn {col}', f'\t\tdataType: {tipo}']
        if tipo == 'dateTime':
            linhas.append('\t\tformatString: dd/mm/yyyy')
        elif tipo == 'int64':
            linhas.append('\t\tformatString: 0')
        if col in OCULTAS.get(nome, set()):
            linhas.append('\t\tisHidden')
        linhas += [f'\t\tlineageTag: {tag()}',
                   f'\t\tsummarizeBy: {"sum" if tipo in ("int64", "double") else "none"}',
                   f'\t\tsourceColumn: {col}']
        if (nome, col) in ORDENAR_POR:
            linhas.append(f'\t\tsortByColumn: {ORDENAR_POR[(nome, col)]}')
        if tipo == 'dateTime':
            linhas += ['', '\t\tannotation UnderlyingDateTimeDataType = Date']
        linhas += ['', '\t\tannotation SummarizationSetBy = Automatic', '']

    tipos = ', '.join(f'{{"{c}", {M_TIPO[t]}}}' for c, t in colunas)
    linhas += [
        f'\tpartition {nome} = m',
        '\t\tmode: import',
        '\t\tsource =',
        '\t\t\t\tlet',
        f'\t\t\t\t    Fonte = Csv.Document(File.Contents(PastaDados & "{nome}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        '\t\t\t\t    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),',
        f'\t\t\t\t    Tipos = Table.TransformColumnTypes(Cabecalhos, {{{tipos}}}, "en-US")',
        '\t\t\t\tin',
        '\t\t\t\t    Tipos',
        '',
    ]
    return '\n'.join(linhas)


def tmdl_medidas():
    linhas = ['table _Medidas', f'\tlineageTag: {tag()}', '']
    for nome, expr, fmt in MEDIDAS:
        linhas += [f'\tmeasure {tmdl_nome(nome)} = {expr}', f'\t\tformatString: {fmt}',
                   f'\t\tlineageTag: {tag()}', '']
    linhas += ['\tcolumn x', '\t\tisHidden', f'\t\tlineageTag: {tag()}', '\t\tisNameInferred',
               '\t\tsourceColumn: [x]', '', '\tpartition _Medidas = calculated', '\t\tmode: import',
               '\t\tsource = ROW ( "x", BLANK () )', '']
    return '\n'.join(linhas)


def gerar_modelo():
    definicao = MODEL_PATH / 'definition'
    (definicao / 'tables').mkdir(parents=True)
    escrever(MODEL_PATH / 'definition.pbism', json.dumps({'version': '4.2', 'settings': {}}, indent=2))
    escrever(MODEL_PATH / '.platform', plataforma('SemanticModel'))
    escrever(definicao / 'database.tmdl', 'database\n\tcompatibilityLevel: 1606\n')

    tabelas = list(TABELAS) + ['_Medidas']
    modelo = ['model Model', '\tculture: pt-BR', '\tdefaultPowerBIDataSourceVersion: powerBI_V3',
              '\tsourceQueryCulture: en-US', '\tdataAccessOptions', '\t\tlegacyRedirects',
              '\t\treturnErrorValuesAsNull', '',
              # Sem tabelas de data automáticas: o calendário mensal já está no modelo
              'annotation __PBI_TimeIntelligenceEnabled = 0', '',
              f'annotation PBI_QueryOrder = {json.dumps(["PastaDados"] + list(TABELAS))}', '']
    modelo += [f'ref table {t}' for t in tabelas]
    escrever(definicao / 'model.tmdl', '\n'.join(modelo) + '\n')

    # Pasta dos CSVs como parâmetro: troque em Transformar dados > Parâmetros
    # para abrir o projeto em outra máquina.
    pasta = str(DATA_PATH) + '\\'
    escrever(definicao / 'expressions.tmdl',
             f'expression PastaDados = "{pasta}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
             f'\tlineageTag: {tag()}\n\n\tannotation PBI_ResultType = Text\n')

    for nome, colunas in TABELAS.items():
        escrever(definicao / 'tables' / f'{nome}.tmdl', tmdl_tabela(nome, colunas))
    escrever(definicao / 'tables' / '_Medidas.tmdl', tmdl_medidas())

    rel = []
    for origem, destino in RELACIONAMENTOS:
        rel += [f'relationship {tag()}', f'\tfromColumn: {origem}', f'\ttoColumn: {destino}', '']
    escrever(definicao / 'relationships.tmdl', '\n'.join(rel))


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------

VISUAL_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.14.0/schema.json'
PAGE_SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json'


def lit(valor):
    return {'expr': {'Literal': {'Value': valor}}}


def medida(nome):
    return {'field': {'Measure': {'Expression': {'SourceRef': {'Entity': '_Medidas'}}, 'Property': nome}},
            'queryRef': f'_Medidas.{nome}', 'nativeQueryRef': nome}


def coluna(tabela, nome):
    return {'field': {'Column': {'Expression': {'SourceRef': {'Entity': tabela}}, 'Property': nome}},
            'queryRef': f'{tabela}.{nome}', 'nativeQueryRef': nome}


def soma(tabela, nome):
    return {'field': {'Aggregation': {'Expression': {'Column': {'Expression': {'SourceRef': {'Entity': tabela}},
                                                                'Property': nome}}, 'Function': 0}},
            'queryRef': f'Sum({tabela}.{nome})', 'nativeQueryRef': nome}


def titulo(texto):
    return {'title': [{'properties': {'show': lit('true'), 'text': lit(f"'{texto}'")}}]}


def visual(nome, tipo, pos, papeis=None, objetos=None, container=None, ordem=None, filtros=None):
    x, y, w, h = pos
    v = {'visualType': tipo, 'drillFilterOtherVisuals': True}
    if papeis:
        v['query'] = {'queryState': {p: {'projections': proj} for p, proj in papeis.items()}}
        if ordem:
            v['query']['sortDefinition'] = {'sort': ordem, 'isDefaultSort': True}
    if objetos:
        v['objects'] = objetos
    if container:
        v['visualContainerObjects'] = container
    out = {'$schema': VISUAL_SCHEMA, 'name': nome,
           'position': {'x': x, 'y': y, 'z': 0, 'height': h, 'width': w, 'tabOrder': 0}, 'visual': v}
    if filtros:
        out['filterConfig'] = {'filters': filtros}
    return out


def cabecalho(nome, texto, subtitulo):
    paragrafos = [
        {'textRuns': [{'value': texto, 'textStyle': {'fontSize': '22pt', 'fontWeight': 'bold', 'color': CORES['marinho']}}]},
        {'textRuns': [{'value': subtitulo, 'textStyle': {'fontSize': '11pt', 'color': CORES['cinza']}}]},
    ]
    return visual(nome, 'textbox', (20, 12, 1300, 86), objetos={'general': [{'properties': {'paragraphs': paragrafos}}]})


def cartao(nome, nome_medida, pos):
    return visual(nome, 'card', pos, papeis={'Values': [medida(nome_medida)]})


def segmentacao(nome, tabela, col, pos, filtros=None):
    return visual(nome, 'slicer', pos, papeis={'Values': [coluna(tabela, col)]},
                  objetos={'data': [{'properties': {'mode': lit("'Dropdown'")}}]}, filtros=filtros)


def desc(campo):
    return [{'field': campo['field'], 'direction': 'Descending'}]


def filtro_valor(nome, tabela, col, valor):
    ref = {'Column': {'Expression': {'SourceRef': {'Source': 't'}}, 'Property': col}}
    return {'name': nome,
            'field': {'Column': {'Expression': {'SourceRef': {'Entity': tabela}}, 'Property': col}},
            'type': 'Categorical',
            'filter': {'Version': 2, 'From': [{'Name': 't', 'Entity': tabela, 'Type': 0}],
                       'Where': [{'Condition': {'In': {'Expressions': [ref], 'Values': [[{'Literal': {'Value': valor}}]]}}}]}}


def filtro_top(nome, tabela, col, nome_medida, n):
    ref = {'Column': {'Expression': {'SourceRef': {'Source': 'f'}}, 'Property': col}}
    return {'name': nome,
            'field': {'Column': {'Expression': {'SourceRef': {'Entity': tabela}}, 'Property': col}},
            'type': 'TopN',
            'filter': {'Version': 2, 'From': [
                {'Name': 'subquery', 'Expression': {'Subquery': {'Query': {
                    'Version': 2,
                    'From': [{'Name': 'f', 'Entity': tabela, 'Type': 0}, {'Name': 'm', 'Entity': '_Medidas', 'Type': 0}],
                    'Select': [dict(ref, Name='field')],
                    'OrderBy': [{'Direction': 2, 'Expression': {'Measure': {'Expression': {'SourceRef': {'Source': 'm'}}, 'Property': nome_medida}}}],
                    'Top': n}}}, 'Type': 2},
                {'Name': 'f', 'Entity': tabela, 'Type': 0}],
                'Where': [{'Condition': {'In': {'Expressions': [ref], 'Table': {'SourceRef': {'Source': 'subquery'}}}}}]}}


def paginas():
    excedente = medida('Leitos-dia Excedentes')
    perm_hosp = medida('Permanência Média (Hospital)')
    so_comparaveis = filtro_valor('soComparaveis', A, 'Comparavel', '1L')

    largura, gap = 300, 16
    kpis = ['Cirurgias', 'Hospitais', 'Valor SUS', 'Permanência Média', 'Leitos-dia Excedentes', 'Leitos Equivalentes']
    visao_geral = [
        cabecalho('titulo1', 'Cirurgias eletivas no SUS · São Paulo, 2024',
                  'Fonte: SIH/SUS (DATASUS). Leitos-dia excedentes = dias acima da mediana dos hospitais pares, por procedimento.'),
        segmentacao('fComplexidade', F, 'Complexidade', (1500, 20, 400, 70)),
        *[cartao(f'c{i}', m, (20 + i * (largura + gap), 110, largura, 130)) for i, m in enumerate(kpis)],
        visual('gCirurgiasMes', 'lineChart', (20, 260, 930, 800),
               papeis={'Category': [coluna('dim_calendario', 'Mes')], 'Y': [medida('Cirurgias')]},
               container=titulo('Cirurgias eletivas por mês de competência')),
        visual('gTopProcedimentos', 'barChart', (970, 260, 930, 800),
               papeis={'Category': [coluna(P, 'Procedimento')], 'Y': [excedente]},
               container=titulo('Procedimentos com mais leitos-dia excedentes'),
               ordem=desc(excedente), filtros=[filtro_top('top15', P, 'Procedimento', 'Leitos-dia Excedentes', 15)]),
    ]

    cards2 = ['Mediana dos Pares', 'Permanência SIGTAP', 'Hospitais Acima do Padrão', 'Leitos-dia Excedentes']
    variabilidade = [
        cabecalho('titulo2', 'Variabilidade por procedimento',
                  'Escolha um procedimento. Cada ponto é um hospital com pelo menos 20 cirurgias dele no ano.'),
        segmentacao('fProcedimento', P, 'Procedimento', (20, 110, 560, 130),
                    filtros=[filtro_valor('soElegiveis', P, 'ElegivelBenchmark', '1L')]),
        *[cartao(f'p{i}', m, (600 + i * 328, 110, 315, 130)) for i, m in enumerate(cards2)],
        visual('gDispersaoHospitais', 'scatterChart', (20, 260, 930, 800),
               papeis={'Category': [coluna('dim_hospital', 'Hospital')], 'X': [soma(A, 'Cirurgias')], 'Y': [perm_hosp]},
               container=titulo('Volume x permanência média por hospital'), filtros=[so_comparaveis]),
        visual('gHospitaisPermanencia', 'barChart', (970, 260, 930, 800),
               papeis={'Category': [coluna('dim_hospital', 'Hospital')], 'Y': [perm_hosp, medida('Mediana dos Pares')]},
               container=titulo('Hospitais com maior permanência média x mediana dos pares'), ordem=desc(perm_hosp),
               filtros=[so_comparaveis, filtro_top('top20perm', 'dim_hospital', 'Hospital', 'Permanência Média (Hospital)', 20)]),
    ]

    colunas_tabela = [coluna('dim_hospital', 'Hospital'), coluna('dim_hospital', 'Municipio'), excedente,
                      medida('Cirurgias'), medida('Permanência Média'), medida('Taxa UTI'),
                      medida('% Alta Complexidade'), medida('Idade Média'), medida('Taxa Óbito')]
    prioritarios = [
        cabecalho('titulo3', 'Hospitais prioritários',
                  'Excedente não é sinônimo de ineficiência: compare com UTI, complexidade e idade antes de agir.'),
        visual('gTopHospitais', 'barChart', (20, 110, 700, 950),
               papeis={'Category': [coluna('dim_hospital', 'Hospital')], 'Y': [excedente]},
               container=titulo('Top 20 hospitais em leitos-dia excedentes'), ordem=desc(excedente),
               filtros=[filtro_top('top20exc', 'dim_hospital', 'Hospital', 'Leitos-dia Excedentes', 20)]),
        visual('tHospitais', 'tableEx', (740, 110, 1160, 950), papeis={'Values': colunas_tabela},
               container=titulo('Excedente ao lado do perfil de risco do paciente'), ordem=desc(excedente)),
    ]

    return {'visaoGeral': ('Visão geral', visao_geral),
            'variabilidade': ('Variabilidade por procedimento', variabilidade),
            'hospitaisPrioritarios': ('Hospitais prioritários', prioritarios)}


def tema():
    fonte, fonte_negrito = 'Segoe UI', 'Segoe UI Semibold'
    return {
        'name': 'Fin-X SUS',
        'dataColors': [CORES['azul'], CORES['ciano'], CORES['marinho'], CORES['azul_claro'],
                       CORES['cinza'], '#9FB3C8', '#F2A541', '#D1495B'],
        'foreground': CORES['marinho'], 'foregroundNeutralSecondary': CORES['cinza'],
        'background': CORES['branco'], 'backgroundLight': CORES['fundo'], 'tableAccent': CORES['azul'],
        'textClasses': {
            'callout': {'fontFace': fonte_negrito, 'fontSize': 28, 'color': CORES['marinho']},
            'title': {'fontFace': fonte_negrito, 'fontSize': 12, 'color': CORES['marinho']},
            'header': {'fontFace': fonte_negrito, 'fontSize': 12, 'color': CORES['marinho']},
            'label': {'fontFace': fonte, 'fontSize': 10, 'color': CORES['cinza']},
        },
        'visualStyles': {
            '*': {'*': {
                'background': [{'show': True, 'color': {'solid': {'color': CORES['branco']}}, 'transparency': 0}],
                'border': [{'show': True, 'color': {'solid': {'color': CORES['cinza_claro']}}, 'radius': 10}],
                'padding': [{'top': 10, 'bottom': 10, 'left': 14, 'right': 14}],
            }},
            'page': {'*': {
                'background': [{'color': {'solid': {'color': CORES['fundo']}}, 'transparency': 0}],
                'outspace': [{'color': {'solid': {'color': CORES['fundo']}}, 'transparency': 0}],
            }},
            'textbox': {'*': {
                'background': [{'show': False}], 'border': [{'show': False}],
            }},
            'card': {'*': {
                'labels': [{'color': {'solid': {'color': CORES['azul']}}, 'fontSize': 26}],
                'categoryLabels': [{'color': {'solid': {'color': CORES['cinza']}}, 'fontSize': 11}],
            }},
        },
    }


def gerar_relatorio():
    definicao = REPORT_PATH / 'definition'
    (definicao / 'pages').mkdir(parents=True)
    escrever(REPORT_PATH / '.platform', plataforma('Report'))
    escrever(REPORT_PATH / 'definition.pbir',
             json.dumps({'version': '4.0', 'datasetReference': {'byPath': {'path': f'../{NOME}.SemanticModel'}}}, indent=2))
    escrever(definicao / 'version.json', json.dumps({
        '$schema': 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json',
        'version': '2.0.0'}, indent=2))

    recursos = REPORT_PATH / 'StaticResources'
    (recursos / 'RegisteredResources').mkdir(parents=True)
    escrever(recursos / 'RegisteredResources' / 'FinX_SUS.json', json.dumps(tema(), indent=2, ensure_ascii=False))

    versao = {'visual': '2.14.0', 'report': '3.4.0', 'page': '2.3.1'}
    escrever(definicao / 'report.json', json.dumps({
        '$schema': 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json',
        'themeCollection': {'customTheme': {'name': 'FinX_SUS.json', 'reportVersionAtImport': versao,
                                            'type': 'RegisteredResources'}},
        'resourcePackages': [{'name': 'RegisteredResources', 'type': 'RegisteredResources',
                              'items': [{'name': 'FinX_SUS.json', 'path': 'FinX_SUS.json', 'type': 'CustomTheme'}]}],
        'settings': {'useStylableVisualContainerHeader': True, 'defaultDrillFilterOtherVisuals': True,
                     'allowChangeFilterTypes': True, 'useEnhancedTooltips': True,
                     'useDefaultAggregateDisplayName': True},
    }, indent=2))

    pags = paginas()
    for nome_pag, (exibicao, visuais) in pags.items():
        pasta = definicao / 'pages' / nome_pag
        (pasta / 'visuals').mkdir(parents=True)
        escrever(pasta / 'page.json', json.dumps({'$schema': PAGE_SCHEMA, 'name': nome_pag, 'displayName': exibicao,
                                                  'displayOption': 'FitToPage', 'height': 1080, 'width': 1920},
                                                 indent=2, ensure_ascii=False))
        for v in visuais:
            (pasta / 'visuals' / v['name']).mkdir()
            escrever(pasta / 'visuals' / v['name'] / 'visual.json', json.dumps(v, indent=2, ensure_ascii=False))
    escrever(definicao / 'pages' / 'pages.json', json.dumps({
        '$schema': 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json',
        'pageOrder': list(pags), 'activePageName': 'visaoGeral'}, indent=2))
    return sum(len(v) for _, v in pags.values())


def plataforma(tipo):
    return json.dumps({
        '$schema': 'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json',
        'metadata': {'type': tipo, 'displayName': NOME},
        'config': {'version': '2.0', 'logicalId': tag()}}, indent=2)


def escrever(caminho, conteudo):
    caminho.write_text(conteudo, encoding='utf-8')


def main():
    for pasta in (MODEL_PATH, REPORT_PATH):
        if pasta.exists():
            shutil.rmtree(pasta)
    gerar_modelo()
    n_visuais = gerar_relatorio()
    escrever(POWERBI_PATH / f'{NOME}.pbip', json.dumps({
        'version': '1.0', 'artifacts': [{'report': {'path': f'{NOME}.Report'}}],
        'settings': {'enableAutoRecovery': True}}, indent=2))
    print(f'Projeto gerado: powerbi/{NOME}.pbip ({len(TABELAS)} tabelas, {len(MEDIDAS)} medidas, {n_visuais} visuais)')


if __name__ == '__main__':
    main()
