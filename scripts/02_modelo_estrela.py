# Monta o modelo estrela (CSVs) do dashboard Power BI a partir do parquet
# gerado por 01_baixar_sih.py, da tabela SIGTAP e do cadastro CNES.
#
# Uso:
#   python scripts/02_modelo_estrela.py SP 2024
#
# Saída em powerbi/data/: fato_cirurgias, agg_hospital_procedimento,
# dim_procedimento, dim_hospital, dim_calendario.

import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERIM_PATH = PROJECT_ROOT / 'data' / 'interim'
AUX_PATH = PROJECT_ROOT / 'data' / 'aux'
OUT_PATH = PROJECT_ROOT / 'powerbi' / 'data'

# Um procedimento entra no benchmark se tiver volume e hospitais suficientes
# para que a mediana dos pares seja estável.
MIN_CIRURGIAS_PROCEDIMENTO = 300
MIN_HOSPITAIS_PROCEDIMENTO = 10
# Um hospital entra na comparação de um procedimento só com casos suficientes
# para que a média dele não seja ruído.
MIN_CIRURGIAS_HOSPITAL = 20

# Forma de organização 0415-01/0415-02: códigos guarda-chuva (cirurgias
# múltiplas e sequenciais em oncologia). Agrupam cirurgias diferentes e não têm
# permanência definida na SIGTAP, então não são comparáveis entre hospitais.
PREFIXO_GUARDA_CHUVA = '0415'

SEXO = {'1': 'Masculino', '3': 'Feminino'}
COMPLEXIDADE = {'02': 'Média', '03': 'Alta'}


def ler_sigtap():
    with zipfile.ZipFile(AUX_PATH / 'sigtap.zip') as z:
        linhas = z.read('tb_procedimento.txt').decode('latin-1').splitlines()
        grupos = {l[:2]: l[2:102].strip() for l in z.read('tb_grupo.txt').decode('latin-1').splitlines()}
        subgrupos = {l[:4]: l[4:104].strip() for l in z.read('tb_sub_grupo.txt').decode('latin-1').splitlines()}
        formas = {l[:6]: l[6:106].strip() for l in z.read('tb_forma_organizacao.txt').decode('latin-1').splitlines()}

    proc = pd.DataFrame({
        'CodProcedimento': [l[0:10] for l in linhas],
        'Procedimento': [l[10:260].strip().title() for l in linhas],
        'PermanenciaSIGTAP': [int(l[266:270]) for l in linhas],
    })
    # 9999 = permanência não definida na tabela
    proc['PermanenciaSIGTAP'] = proc['PermanenciaSIGTAP'].where(proc['PermanenciaSIGTAP'] < 9999)
    proc['Subgrupo'] = proc['CodProcedimento'].str[:4].map(subgrupos).str.title()
    proc['FormaOrganizacao'] = proc['CodProcedimento'].str[:6].map(formas).str.title()
    proc['Grupo'] = proc['CodProcedimento'].str[:2].map(grupos).str.title()
    return proc


def ler_cnes():
    with zipfile.ZipFile(AUX_PATH / 'cnes_base.zip') as z:
        nome_estab = next(n for n in z.namelist() if n.lower().startswith('tbestabelecimento'))
        nome_mun = next(n for n in z.namelist() if n.lower().startswith('tbmunicipio'))
        estab = pd.read_csv(z.open(nome_estab), sep=';', encoding='latin-1', dtype=str,
                            usecols=['CO_CNES', 'NO_FANTASIA', 'NO_RAZAO_SOCIAL', 'CO_MUNICIPIO_GESTOR'])
        mun = pd.read_csv(z.open(nome_mun), sep=';', encoding='latin-1', dtype=str,
                          usecols=['CO_MUNICIPIO', 'NO_MUNICIPIO'])
    estab = estab.merge(mun, left_on='CO_MUNICIPIO_GESTOR', right_on='CO_MUNICIPIO', how='left')
    return pd.DataFrame({
        'CNES': estab['CO_CNES'].str.zfill(7),
        'Hospital': estab['NO_FANTASIA'].fillna(estab['NO_RAZAO_SOCIAL']).str.strip().str.title(),
        'Municipio': estab['NO_MUNICIPIO'].str.title(),
    }).drop_duplicates('CNES')


def montar_fato(sih):
    competencia = pd.to_datetime(sih['ANO_CMPT'] + '-' + sih['MES_CMPT'] + '-01')
    # COD_IDADE 4 = idade em anos; outros códigos (dias, meses) são menores de 1 ano
    idade = sih['IDADE'].where(sih['COD_IDADE'] == '4', 0)
    return pd.DataFrame({
        'NumAIH': sih['N_AIH'],
        'Competencia': competencia.dt.date,
        'DataInternacao': sih['DT_INTER'].dt.date,
        'CNES': sih['CNES'].str.zfill(7),
        'CodProcedimento': sih['PROC_REA'],
        'CID': sih['DIAG_PRINC'],
        'Complexidade': sih['COMPLEX'].map(COMPLEXIDADE).fillna('Outra'),
        'DiasPermanencia': sih['DIAS_PERM'],
        'DiasUTI': sih['UTI_MES_TO'],
        'UsouUTI': (sih['UTI_MES_TO'] > 0).astype(int),
        'ValorTotal': sih['VAL_TOT'].round(2),
        'Obito': sih['MORTE'],
        'Idade': idade,
        'Sexo': sih['SEXO'].map(SEXO).fillna('Ignorado'),
    })


def benchmark(fato, proc):
    # Média por hospital e procedimento, com volume mínimo
    hp = (fato.groupby(['CNES', 'CodProcedimento'])
              .agg(Cirurgias=('NumAIH', 'size'),
                   MediaPermanencia=('DiasPermanencia', 'mean'),
                   MedianaPermanencia=('DiasPermanencia', 'median'),
                   TaxaUTI=('UsouUTI', 'mean'),
                   Obitos=('Obito', 'sum'),
                   ValorTotal=('ValorTotal', 'sum'))
              .reset_index())

    por_proc = fato.groupby('CodProcedimento').agg(Cirurgias=('NumAIH', 'size'), Hospitais=('CNES', 'nunique'))
    elegivel = ((por_proc['Cirurgias'] >= MIN_CIRURGIAS_PROCEDIMENTO)
                & (por_proc['Hospitais'] >= MIN_HOSPITAIS_PROCEDIMENTO)
                & ~por_proc.index.str.startswith(PREFIXO_GUARDA_CHUVA))
    por_proc['ElegivelBenchmark'] = elegivel

    comparaveis = hp[hp['CodProcedimento'].isin(por_proc.index[elegivel]) & (hp['Cirurgias'] >= MIN_CIRURGIAS_HOSPITAL)]
    # Padrão = mediana das médias dos hospitais pares (o "hospital típico")
    por_proc['MedianaPares'] = comparaveis.groupby('CodProcedimento')['MediaPermanencia'].median()
    por_proc['HospitaisComparados'] = comparaveis.groupby('CodProcedimento').size()
    por_proc['HospitaisComparados'] = por_proc['HospitaisComparados'].fillna(0).astype(int)

    hp = hp.merge(por_proc[['MedianaPares']], left_on='CodProcedimento', right_index=True, how='left')
    hp['Comparavel'] = (hp['CodProcedimento'].isin(comparaveis['CodProcedimento'])
                        & (hp['Cirurgias'] >= MIN_CIRURGIAS_HOSPITAL)).astype(int)
    # Leitos-dia que o hospital liberaria operando na mediana dos pares
    excedente = (hp['MediaPermanencia'] - hp['MedianaPares']).clip(lower=0) * hp['Cirurgias']
    hp['DiasExcedentes'] = np.where(hp['Comparavel'] == 1, excedente, np.nan)

    dim = proc[proc['CodProcedimento'].isin(por_proc.index)].merge(
        por_proc.reset_index(), on='CodProcedimento', how='left')
    dim['ElegivelBenchmark'] = dim['ElegivelBenchmark'].astype(int)
    return hp.round({'MediaPermanencia': 2, 'MedianaPermanencia': 1, 'TaxaUTI': 4,
                     'MedianaPares': 2, 'DiasExcedentes': 1, 'ValorTotal': 2}), dim


def main(uf, ano):
    OUT_PATH.mkdir(parents=True, exist_ok=True)
    sih = pd.read_parquet(INTERIM_PATH / f'sih_eletivas_{uf}{ano}.parquet')
    fato = montar_fato(sih)
    hosp_proc, dim_proc = benchmark(fato, ler_sigtap())

    cnes = ler_cnes()
    dim_hosp = pd.DataFrame({'CNES': fato['CNES'].unique()}).merge(cnes, on='CNES', how='left')
    dim_hosp['Hospital'] = dim_hosp['Hospital'].fillna('CNES ' + dim_hosp['CNES'])

    meses = pd.date_range(f'{ano}-01-01', f'{ano}-12-01', freq='MS')
    nomes = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    calendario = pd.DataFrame({'Competencia': meses.date, 'Ano': meses.year, 'MesNum': meses.month,
                               'Mes': [nomes[m - 1] for m in meses.month]})

    tabelas = {'fato_cirurgias': fato, 'agg_hospital_procedimento': hosp_proc,
               'dim_procedimento': dim_proc, 'dim_hospital': dim_hosp, 'dim_calendario': calendario}
    for nome, tabela in tabelas.items():
        tabela.to_csv(OUT_PATH / f'{nome}.csv', index=False, encoding='utf-8')
        print(f'  {nome}.csv: {len(tabela):,} linhas')

    comp = hosp_proc[hosp_proc['Comparavel'] == 1]
    total = comp['DiasExcedentes'].sum()
    por_hosp = comp.groupby('CNES')['DiasExcedentes'].sum().sort_values(ascending=False)
    print(f'\nProcedimentos no benchmark: {dim_proc["ElegivelBenchmark"].sum()} '
          f'({fato["CodProcedimento"].isin(dim_proc.loc[dim_proc["ElegivelBenchmark"] == 1, "CodProcedimento"]).mean():.1%} das cirurgias)')
    print(f'Leitos-dia excedentes: {total:,.0f} (~{total / 365:,.0f} leitos/ano)')
    print(f'Top 20 hospitais concentram {por_hosp.head(20).sum() / total:.1%} do excedente')
    print(f'Hospitais sem nome no CNES: {(dim_hosp["Hospital"].str.startswith("CNES ")).sum()}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Uso: python scripts/02_modelo_estrela.py UF ANO  (ex.: SP 2024)')
    main(sys.argv[1].upper(), int(sys.argv[2]))
