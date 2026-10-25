# Baixa as AIHs reduzidas (SIH/SUS) de um estado e ano e guarda só as
# cirurgias eletivas em parquet.
#
# Uso:
#   python scripts/01_baixar_sih.py SP 2024
#
# Saída: data/interim/sih_eletivas_{UF}{ANO}.parquet

import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd
import pyreaddbc
from dbfread import DBF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / 'data' / 'raw'
INTERIM_PATH = PROJECT_ROOT / 'data' / 'interim'
FTP_URL = 'ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/RD{uf}{aa}{mm}.dbc'

CARATER_ELETIVO = '01'
GRUPO_CIRURGICO = '04'  # grupo 04 da tabela SIGTAP: procedimentos cirúrgicos

COLUNAS = ['N_AIH', 'ANO_CMPT', 'MES_CMPT', 'CNES', 'MUNIC_MOV', 'MUNIC_RES',
           'PROC_REA', 'DIAG_PRINC', 'COMPLEX', 'DT_INTER', 'DT_SAIDA', 'DIAS_PERM',
           'UTI_MES_TO', 'MARCA_UTI', 'VAL_TOT', 'VAL_UTI', 'MORTE', 'IDADE',
           'COD_IDADE', 'SEXO', 'CAR_INT']


def baixar(uf, ano, mes):
    destino = RAW_PATH / f'RD{uf}{ano % 100:02d}{mes:02d}.dbc'
    if not destino.exists():
        url = FTP_URL.format(uf=uf, aa=f'{ano % 100:02d}', mm=f'{mes:02d}')
        print(f'  baixando {url}')
        urllib.request.urlretrieve(url, destino)
    return destino


def ler_dbc(caminho_dbc):
    # pyreaddbc não aceita caminhos com acento, então a conversão roda numa pasta temporária
    with tempfile.TemporaryDirectory() as tmp:
        dbc = Path(tmp) / 'arquivo.dbc'
        dbf = Path(tmp) / 'arquivo.dbf'
        shutil.copy(caminho_dbc, dbc)
        pyreaddbc.dbc2dbf(str(dbc), str(dbf))
        return pd.DataFrame(iter(DBF(str(dbf), encoding='latin-1')))


def filtrar_eletivas(df):
    eletiva = df['CAR_INT'] == CARATER_ELETIVO
    cirurgica = df['PROC_REA'].astype(str).str.startswith(GRUPO_CIRURGICO)
    return df.loc[eletiva & cirurgica, COLUNAS].copy()


def main(uf, ano):
    RAW_PATH.mkdir(parents=True, exist_ok=True)
    INTERIM_PATH.mkdir(parents=True, exist_ok=True)

    meses = []
    for mes in range(1, 13):
        print(f'{uf} {ano}-{mes:02d}')
        df = ler_dbc(baixar(uf, ano, mes))
        eletivas = filtrar_eletivas(df)
        print(f'  {len(df):,} internações -> {len(eletivas):,} cirurgias eletivas')
        meses.append(eletivas)

    sih = pd.concat(meses, ignore_index=True)
    for col in ['DIAS_PERM', 'UTI_MES_TO', 'IDADE']:
        sih[col] = pd.to_numeric(sih[col], errors='coerce').astype('Int64')
    for col in ['VAL_TOT', 'VAL_UTI']:
        sih[col] = pd.to_numeric(sih[col], errors='coerce')
    for col in ['DT_INTER', 'DT_SAIDA']:
        sih[col] = pd.to_datetime(sih[col], format='%Y%m%d', errors='coerce')
    sih['MORTE'] = sih['MORTE'].astype(int)

    saida = INTERIM_PATH / f'sih_eletivas_{uf}{ano}.parquet'
    sih.to_parquet(saida, index=False)
    print(f'\nTotal: {len(sih):,} cirurgias eletivas -> {saida.relative_to(PROJECT_ROOT)}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('Uso: python scripts/01_baixar_sih.py UF ANO  (ex.: SP 2024)')
    main(sys.argv[1].upper(), int(sys.argv[2]))
