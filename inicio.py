# %%
"""
FACTOR INVESTING - FATOR QUALIDADE
3º semestre de Administração

Seleção: 27/03/2024
Compra: 28/03/2024
Fim: 01/07/2026

Carteira: 10 melhores ações
Capital: R$ 100.000
Estratégia: Buy and Hold

Score:
40% Rentabilidade
30% Segurança financeira
30% Qualidade dos lucros
"""

from pathlib import Path
import re
import unicodedata
import zipfile

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests


# ==================================================
# 1. CONFIGURAÇÕES
# ==================================================

CORTE = pd.Timestamp("2024-03-27")
INICIO = pd.Timestamp("2024-03-28")
FIM = pd.Timestamp("2026-07-01")

GRUPO = (
    "https://raw.githubusercontent.com/"
    "gabrielmeloboaventura/"
    "Baixa_Volatilidade_Ibovespa/main/dados/"
)

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/"

SAIDA = Path("resultados_qualidade")
CACHE = Path("cache_qualidade")

SAIDA.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

# Classes duplicadas da mesma empresa.
DUPLICADAS = {"BBDC3", "ELET6", "PETR3"}

# Bancos, seguradoras e holding financeira.
FINANCEIRAS = {
    "BBAS3", "BBDC4", "BBSE3", "BPAC11",
    "IRBR3", "ITSA4", "ITUB4", "SANB11"
}

# Ações com preços congelados na base do grupo.
CONGELADAS = {
    "BRFS3", "CRFB3", "SOMA3", "NTCO3",
    "PETZ3", "CIEL3", "GOLL4", "AZUL4", "ELET6"
}


# ==================================================
# 2. DOWNLOAD E LEITURA DOS DADOS
# ==================================================

def baixar(url, nome):

    arquivo = CACHE / nome

    if not arquivo.exists():

        print("Baixando:", nome)

        resposta = requests.get(
            url, timeout=(20, 180)
        )

        resposta.raise_for_status()
        arquivo.write_bytes(resposta.content)

    return arquivo


def csv(url, nome, **opcoes):

    return pd.read_csv(
        baixar(url, nome), **opcoes
    )


def ler_zip(z, nome):

    with z.open(nome) as arquivo:

        return pd.read_csv(
            arquivo,
            sep=";",
            encoding="latin1",
            low_memory=False,
            dtype={"CD_CONTA": str}
        )


def normalizar(df):

    def ajustar(nome):

        nome = unicodedata.normalize(
            "NFKD", nome
        ).encode("ascii", "ignore").decode()

        return re.sub(
            "[^A-Z0-9]+", "_", nome.upper()
        ).strip("_")

    return df.rename(
        columns={c: ajustar(c) for c in df.columns}
    )


def limpar_cnpj(serie):

    return (
        serie.astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(14)
    )


def coluna(df, *opcoes):

    return next(
        (c for c in opcoes if c in df.columns),
        None
    )


# ==================================================
# 3. VINCULAR TICKERS À CVM
# ==================================================

def mapear_tickers():

    # Cadastro oficial da CVM.
    cadastro = normalizar(
        csv(
            CVM + "CAD/DADOS/cad_cia_aberta.csv",
            "cad_cia_aberta.csv",
            sep=";",
            encoding="latin1",
            low_memory=False
        )
    )

    cadastro["CN"] = limpar_cnpj(
        cadastro["CNPJ_CIA"]
    )

    cadastro = (
        cadastro.drop_duplicates("CN")
        .set_index("CN")
    )

    partes = []

    # Formulários cadastrais históricos.
    for ano in (2023, 2024):

        arquivo = baixar(
            CVM + f"DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip",
            f"fca_{ano}.zip"
        )

        with zipfile.ZipFile(arquivo) as z:

            indice = normalizar(
                ler_zip(z, f"fca_cia_aberta_{ano}.csv")
            )

            tabela = normalizar(
                ler_zip(
                    z,
                    f"fca_cia_aberta_valor_mobiliario_{ano}.csv"
                )
            )

        for df in (indice, tabela):

            campo = coluna(
                df, "CNPJ_COMPANHIA", "CNPJ_CIA"
            )

            df["CN"] = limpar_cnpj(df[campo])

            campo = coluna(
                df, "DATA_REFERENCIA", "DT_REFER"
            )

            df["REF"] = pd.to_datetime(
                df[campo], errors="coerce"
            )

            df["VERSAO"] = pd.to_numeric(
                df["VERSAO"], errors="coerce"
            )

        entrega = coluna(
            indice,
            "DT_RECEB",
            "DATA_ENTREGA",
            "DT_ENTREGA"
        )

        if not entrega:
            print(f"FCA {ano}: sem data de entrega.")
            continue

        indice["RECEB"] = pd.to_datetime(
            indice[entrega], errors="coerce"
        )

        # Impede uso de dados posteriores à seleção.
        indice = indice[
            (indice["RECEB"] <= CORTE)
            & (indice["REF"] <= CORTE)
        ]

        tabela = tabela.merge(
            indice[["CN", "REF", "VERSAO", "RECEB"]],
            on=["CN", "REF", "VERSAO"],
            how="inner"
        )

        tabela["ticker"] = (
            tabela["CODIGO_NEGOCIACAO"]
            .astype(str)
            .str.upper()
            .str.strip()
        )

        partes.append(
            tabela[["ticker", "CN", "RECEB"]]
        )

    if not partes:
        raise ValueError(
            "Não foi possível verificar o cadastro histórico."
        )

    mapa = (
        pd.concat(partes)
        .sort_values("RECEB")
        .drop_duplicates("ticker", keep="last")
    )

    mapa = mapa[
        mapa["CN"].isin(cadastro.index)
    ].copy()

    mapa["CD_CVM"] = pd.to_numeric(
        mapa["CN"].map(cadastro["CD_CVM"]),
        errors="coerce"
    )

    return mapa.set_index("ticker")


# ==================================================
# 4. INDICADORES FINANCEIROS
# ==================================================

def indicadores(tabelas, codigo, versao, ano):

    def conta(tipo, numero):

        df = tabelas[tipo]

        dados = df[
            (df["CD_CVM"] == codigo)
            & (df["VERSAO"] == versao)
            & (df["DT_REFER"] == f"{ano}-12-31")
            & (
                df["ORDEM_EXERC"]
                .astype(str)
                .str.upper()
                .isin(["ÚLTIMO", "ULTIMO"])
            )
            & (df["CD_CONTA"].astype(str) == numero)
        ]

        if tipo == "DRE" and "DT_INI_EXERC" in dados:

            dados = dados[
                dados["DT_INI_EXERC"]
                == f"{ano}-01-01"
            ]

        if len(dados) != 1:

            raise ValueError(
                f"{tipo}, conta {numero}: "
                f"{len(dados)} registros"
            )

        linha = dados.iloc[0]

        valor = float(linha["VL_CONTA"])
        escala = str(linha["ESCALA_MOEDA"]).upper()

        if escala not in ("MIL", "UNIDADE"):
            raise ValueError("Escala contábil desconhecida")

        return valor * (1000 if escala == "MIL" else 1)

    # Balanço patrimonial.
    ativo = conta("BPA", "1")
    circulante = conta("BPA", "1.01")
    patrimonio = conta("BPP", "2.03")
    passivo = conta("BPP", "2.01")

    # Demonstração de resultados.
    receita = conta("DRE", "3.01")
    lucro = conta("DRE", "3.11")

    # Fluxo de caixa operacional.
    try:
        caixa = conta("DFC_MI", "6.01")
    except ValueError:
        caixa = conta("DFC_MD", "6.01")

    if min(ativo, patrimonio, passivo, receita) <= 0:
        raise ValueError("Denominador nulo ou negativo")

    if circulante < 0:
        raise ValueError("Ativo circulante negativo")

    return {
        "ROE": lucro / patrimonio,
        "ROA": lucro / ativo,
        "Margem": lucro / receita,
        "Divida": (ativo - patrimonio) / ativo,
        "Liquidez": circulante / passivo,
        "Accruals": (lucro - caixa) / ativo
    }


# ==================================================
# 5. DEMONSTRAÇÕES FINANCEIRAS DA CVM
# ==================================================

def processar_dfps(universo, mapa, exclusoes):

    documentos = {}
    tabelas = {}

    for ano in (2022, 2023):

        arquivo = baixar(
            CVM + f"DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip",
            f"dfp_{ano}.zip"
        )

        with zipfile.ZipFile(arquivo) as z:

            meta = ler_zip(
                z, f"dfp_cia_aberta_{ano}.csv"
            )

            meta["DT_RECEB"] = pd.to_datetime(
                meta["DT_RECEB"], errors="coerce"
            )

            # Somente documentos disponíveis no corte.
            meta = meta[
                (meta["DT_RECEB"] <= CORTE)
                & (meta["DT_REFER"] == f"{ano}-12-31")
            ]

            documentos[ano] = (
                meta.sort_values(["DT_RECEB", "VERSAO"])
                .drop_duplicates("CD_CVM", keep="last")
                .set_index("CD_CVM")
            )

            tabelas[ano] = {}

            for tipo in ("BPA", "BPP", "DRE", "DFC_MI", "DFC_MD"):

                nome = (
                    f"dfp_cia_aberta_{tipo}_con_{ano}.csv"
                )

                if nome not in z.namelist():

                    tabelas[ano][tipo] = pd.DataFrame(
                        columns=["CD_CVM", "VERSAO"]
                    )

                    continue

                df = ler_zip(z, nome)

                df["CD_CVM"] = pd.to_numeric(
                    df["CD_CVM"], errors="coerce"
                )

                df["VERSAO"] = pd.to_numeric(
                    df["VERSAO"], errors="coerce"
                )

                tabelas[ano][tipo] = df[
                    df["CD_CVM"].isin(mapa["CD_CVM"])
                ].copy()

    resultados = []

    for empresa in universo.itertuples(index=False):

        ticker = empresa.ticker

        if ticker in DUPLICADAS:

            motivo = "Classe duplicada"

        elif ticker in FINANCEIRAS:

            motivo = "Instituição financeira: contas incompatíveis"

        elif ticker not in mapa.index:

            motivo = "Sem vínculo ticker/CNPJ na CVM"

        else:

            codigo = mapa.loc[ticker, "CD_CVM"]

            # Prioridade para DFP 2023.
            ano = next(
                (
                    a for a in (2023, 2022)
                    if codigo in documentos[a].index
                ),
                None
            )

            if ano is None:

                motivo = "DFP 2022/2023 indisponível no corte"

            else:

                documento = documentos[ano].loc[codigo]
                versao = documento["VERSAO"]

                try:

                    valores = indicadores(
                        tabelas[ano], codigo, versao, ano
                    )

                    if not np.isfinite(
                        list(valores.values())
                    ).all():

                        raise ValueError("Indicadores inválidos")

                    resultados.append({
                        "ticker": ticker,
                        "empresa": empresa.empresa,
                        "DFP": ano,
                        "recebida": documento["DT_RECEB"],
                        **valores
                    })

                    continue

                except (ValueError, KeyError, TypeError) as erro:

                    motivo = f"DFP {ano} incompleta: {erro}"

        exclusoes.append({
            "ticker": ticker,
            "empresa": empresa.empresa,
            "motivo": motivo
        })

    return pd.DataFrame(resultados).set_index("ticker")


# ==================================================
# 6. SCORE DO FATOR QUALIDADE
# ==================================================

def classificar(df):

    if len(df) < 10:

        raise ValueError(
            f"Apenas {len(df)} empresas válidas."
        )

    notas = pd.DataFrame(index=df.index)

    for nome in (
        "ROE", "ROA", "Margem",
        "Divida", "Liquidez", "Accruals"
    ):

        # Endividamento e accruals: menor é melhor.
        maior_melhor = nome not in (
            "Divida", "Accruals"
        )

        notas[nome] = (
            df[nome].rank(ascending=maior_melhor) - 1
        ) / (len(df) - 1)

    # Mantém os pesos originais do fator.
    df["score"] = 100 * (
        0.40 * notas[["ROE", "ROA", "Margem"]].mean(axis=1)
        + 0.30 * notas[["Divida", "Liquidez"]].mean(axis=1)
        + 0.30 * notas["Accruals"]
    )

    return df.sort_values(
        "score", ascending=False
    )


# ==================================================
# 7. MÉTRICAS DE DESEMPENHO
# ==================================================

def desempenho(valores, retorno_cdi):

    retornos = valores.pct_change().dropna()

    volatilidade = retornos.std(ddof=1)

    acumulado = (
        valores.iloc[-1] / valores.iloc[0] - 1
    )

    anualizado = (
        (1 + acumulado) ** (252 / len(retornos)) - 1
    )

    drawdown = (
        valores / valores.cummax() - 1
    ).min()

    sharpe = (
        (retornos - retorno_cdi.reindex(retornos.index)).mean()
        / volatilidade * np.sqrt(252)
        if volatilidade > 0 else np.nan
    )

    return {
        "Valor final": valores.iloc[-1],
        "Retorno acumulado (%)": acumulado * 100,
        "Retorno anualizado (%)": anualizado * 100,
        "Volatilidade (%)": volatilidade * np.sqrt(252) * 100,
        "Máximo drawdown (%)": drawdown * 100,
        "Sharpe": sharpe
    }


# ==================================================
# 8. EXECUÇÃO PRINCIPAL
# ==================================================

def main():

    print("\nFACTOR INVESTING - FATOR QUALIDADE\n")

    # Universo das 87 ações do Ibovespa.
    universo = csv(
        GRUPO + "universo.csv",
        "universo.csv"
    )

    universo["ticker"] = (
        universo["ticker"].str.upper().str.strip()
    )

    exclusoes = []

    # Identificação e análise contábil.
    mapa = mapear_tickers()

    balancos = processar_dfps(
        universo, mapa, exclusoes
    )

    # Salva exclusões mesmo se houver menos de 10 válidas.
    pd.DataFrame(
        exclusoes,
        columns=["ticker", "empresa", "motivo"]
    ).to_csv(
        SAIDA / "exclusoes.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Ranking e seleção das 10 melhores.
    ranking = classificar(balancos)

    top10 = ranking.head(10).index.tolist()

    # Mesmos preços utilizados pelo grupo.
    precos = csv(
        GRUPO + "precos_ajustados.csv",
        "precos_ajustados.csv",
        parse_dates=["data"]
    ).set_index("data")

    ibovespa = csv(
        GRUPO + "ibovespa.csv",
        "ibovespa.csv",
        parse_dates=["data"]
    ).set_index("data")["ibovespa"].loc[INICIO:FIM]

    cdi = csv(
        GRUPO + "cdi.csv",
        "cdi.csv",
        parse_dates=["data"]
    ).set_index("data")["cdi"]

    if (
        ibovespa.empty
        or ibovespa.index[0] != INICIO
        or ibovespa.index[-1] != FIM
    ):
        raise ValueError("Datas do Ibovespa incompletas.")

    # Alinhamento aos dias reais de pregão.
    acoes = precos.reindex(
        ibovespa.index
    )[top10].apply(
        pd.to_numeric, errors="coerce"
    )

    if acoes.isna().any().any() or (acoes <= 0).any().any():
        raise ValueError("Preços incompletos no Top 10.")

    # CDI: acumula antes de alinhar aos pregões.
    fator_cdi = (
        (1 + cdi).cumprod().shift(1)
        .reindex(ibovespa.index)
    )

    if fator_cdi.isna().any():
        raise ValueError("CDI incompleto.")

    # R$ 100 mil, pesos iguais, sem rebalanceamento.
    curvas = pd.DataFrame(index=ibovespa.index)

    curvas["Quality Top 10"] = (
        100000 * (acoes / acoes.iloc[0]).mean(axis=1)
    )

    curvas["Ibovespa"] = (
        100000 * ibovespa / ibovespa.iloc[0]
    )

    curvas["CDI"] = (
        100000 * fator_cdi / fator_cdi.iloc[0]
    )

    retorno_cdi = curvas["CDI"].pct_change()

    resultado = pd.DataFrame({
        nome: desempenho(curvas[nome], retorno_cdi)
        for nome in curvas.columns
    }).T

    resultado.loc["CDI", "Sharpe"] = 0.0

    # Salvar tabelas.
    ranking.to_csv(
        SAIDA / "ranking_completo.csv",
        encoding="utf-8-sig"
    )

    ranking.head(10).to_csv(
        SAIDA / "ranking_top10.csv",
        encoding="utf-8-sig"
    )

    resultado.to_csv(
        SAIDA / "resultado_backtest.csv",
        encoding="utf-8-sig"
    )

    curvas.to_csv(
        SAIDA / "evolucao.csv",
        encoding="utf-8-sig"
    )

    # Aviso para ações com preços congelados.
    congeladas = sorted(set(top10) & CONGELADAS)

    if congeladas:
        print(
            "\nATENÇÃO: preços congelados:",
            ", ".join(congeladas)
        )

    # Mostrar resultados.
    print("\nTOP 10 - FATOR QUALIDADE\n")

    print(
        ranking[["empresa", "score", "DFP"]]
        .head(10).round(2)
    )

    print("\nDESEMPENHO\n")
    print(resultado.round(3))

    print("\nEmpresas válidas:", len(ranking))
    print("Empresas excluídas:", len(exclusoes))

    # Gráfico 1: ranking.
    ranking["score"].head(10).sort_values().plot.barh(
        title="Top 10 - Fator Qualidade"
    )

    plt.tight_layout()
    plt.savefig(SAIDA / "ranking.png", dpi=160)
    plt.close()

    # Gráfico 2: evolução das carteiras.
    curvas.plot(
        title="Quality x Ibovespa x CDI",
        figsize=(10, 5)
    )

    plt.tight_layout()
    plt.savefig(SAIDA / "evolucao.png", dpi=160)
    plt.close()

    print("\nResultados salvos em:", SAIDA.resolve())


if __name__ == "__main__":
    main()