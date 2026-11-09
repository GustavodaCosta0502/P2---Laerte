# %%
r"""
FACTOR INVESTING - FATOR QUALIDADE
Projeto de programacao: 10 empresas, 2 carteiras, 6 graficos e HTML.
Formacao: 02/05/2024 | Fim: 01/07/2026.
CVM DFP 2023: apenas versoes recebidas ate 30/04/2024.
Executar no terminal: .\.venv\Scripts\python.exe inicio_qualidade_700.py
Ou executar a celula # %% no Jupyter do VS Code.
"""

from pathlib import Path
from io import BytesIO
from datetime import datetime
import os
import ssl
import sys
import tempfile
import time
import zipfile
import certifi
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ============================================================
# 1. CONFIGURACOES DO ESTUDO
# ============================================================
try:
    PASTA = Path(__file__).resolve().parent
except NameError:
    PASTA = Path.cwd()  # notebook sem arquivo .py associado
# Pasta nova: preserva todos os resultados de versoes anteriores.
SAIDA = PASTA / "resultados_qualidade"
CACHE = PASTA / "cache_qualidade"
SAIDA.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)
FORMACAO = "2024-05-02"
LIMITE_DFP = "2024-04-30"
FIM = "2026-07-01"
CAPITAL = 10_000.0
TOKEN_BRAPI = os.getenv("TOKEN_BRAPI", "")
# Universo definido antes de consultar os retornos do backtest.
# O criterio foi representar diferentes setores, nao escolher vencedores.
# Codigo CVM evita confusao entre empresas de nomes parecidos.
EMPRESAS = {
    "WEGE3": ("WEG", "Industria", 5410),
    "VALE3": ("Vale", "Mineracao", 4170),
    "PETR4": ("Petrobras", "Petroleo", 9512),
    "ABEV3": ("Ambev", "Bebidas", 23264),
    "SUZB3": ("Suzano", "Papel e celulose", 13986),
    "RENT3": ("Localiza", "Locacao", 19739),
    "RADL3": ("Raia Drogasil", "Farmacias", 5258),
    "VIVT3": ("Telefonica Brasil", "Telecom", 17671),
    "TOTS3": ("TOTVS", "Tecnologia", 19992),
    "LREN3": ("Lojas Renner", "Varejo", 8133),
}
# Cores coerentes entre os graficos e o relatorio.
AZUL = "#142C49"
VERDE = "#168F7A"
LARANJA = "#D9854B"
OURO = "#CDA452"
CINZA = "#8797A7"
FUNDO = "#F7F9FC"
CORES = {
    "Quality": VERDE,
    "Low Quality": LARANJA,
    "Ibovespa": AZUL,
    "CDI": OURO,
}
# Dado que sera mostrado no relatorio (fonte efetivamente usada).
FONTES_PRECOS = {}
ORIGEM_CDI = ""

def configurar_graficos():
    """Configura os graficos usando fontes do Windows."""

    from matplotlib import font_manager

    # Procura uma fonte instalada no Windows
    fontes = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]

    fonte_escolhida = None

    for arquivo in fontes:
        if arquivo.exists():
            font_manager.fontManager.addfont(str(arquivo))
            fonte_escolhida = font_manager.FontProperties(
                fname=str(arquivo)
            ).get_name()
            break

    if fonte_escolhida is None:
        raise RuntimeError(
            "Nenhuma fonte compativel foi encontrada no Windows."
        )

    plt.rcParams.update({
        "font.family": fonte_escolhida,
        "font.size": 10,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#DDE4EC",
        "axes.labelcolor": AZUL,
        "text.color": AZUL,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": "#DFE6EE",
        "savefig.facecolor": "white",
    })

# ============================================================
# 2. CONEXAO SEGURA E DEMONSTRACOES DA CVM
# ============================================================
def preparar_certificados():
    """Aproveita certificados do Windows, sem desativar a verificacao SSL."""
    if os.name != "nt":
        return
    try:
        conteudo = Path(certifi.where()).read_text(encoding="utf-8")
        for certificado, tipo, _ in ssl.enum_certificates("ROOT"):
            if tipo == "x509_asn":
                conteudo += "\n" + ssl.DER_cert_to_PEM_cert(certificado)
        arquivo = Path(tempfile.gettempdir()) / "certificados_quality.pem"
        arquivo.write_text(conteudo, encoding="utf-8")
        os.environ["REQUESTS_CA_BUNDLE"] = str(arquivo)
        os.environ["CURL_CA_BUNDLE"] = str(arquivo)
    except Exception as erro:
        print("Aviso: certificados do Windows nao foram unidos:", erro)

def baixar_dfp():
    """Usa a DFP original de 2023 que ja pode existir no projeto."""
    arquivo = PASTA / "dfp_cia_aberta_2023.zip"
    if arquivo.exists() and zipfile.is_zipfile(arquivo):
        print("CVM: arquivo DFP 2023 recuperado do computador.")
        return arquivo
    url = (
        "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/"
        "dfp_cia_aberta_2023.zip"
    )
    print("CVM: baixando demonstracoes financeiras de 2023...")
    resposta = requests.get(url, timeout=(15, 120))
    resposta.raise_for_status()
    if not zipfile.is_zipfile(BytesIO(resposta.content)):
        raise ValueError("A CVM nao devolveu um arquivo ZIP valido.")
    arquivo.write_bytes(resposta.content)
    return arquivo

def ler_csv_cvm(zip_aberto, nome):
    """Le somente o CSV solicitado, dentro do ZIP da CVM."""
    with zip_aberto.open(nome) as entrada:
        return pd.read_csv(entrada, sep=";", encoding="latin1", low_memory=False)

def ler_conta(tabela, codigo):
    """Seleciona uma unica conta do exercicio de 2023."""
    linhas = tabela[
        (tabela["CD_CONTA"].astype(str) == codigo)
        & (tabela["ORDEM_EXERC"].astype(str).str.upper()
           .str.contains("ÚLTIMO|ULTIMO", regex=True))
        & (pd.to_datetime(tabela["DT_FIM_EXERC"], errors="coerce")
           == pd.Timestamp("2023-12-31"))
    ]
    if len(linhas) != 1:
        raise ValueError(f"Conta {codigo}: {len(linhas)} registros; esperado 1.")
    linha = linhas.iloc[0]
    valor = pd.to_numeric(linha["VL_CONTA"], errors="coerce")
    if not np.isfinite(valor):
        raise ValueError(f"Conta {codigo} com valor ausente ou invalido.")
    escala = str(linha.get("ESCALA_MOEDA", "")).strip().upper()
    if escala not in ("", "MIL", "UNIDADE"):
        raise ValueError(f"Escala monetaria nao reconhecida: {escala}")
    return float(valor) * (1000 if escala == "MIL" else 1)

def carregar_balancos():
    """Apura seis indicadores usando somente DFPs disponiveis ate abril."""
    arquivo = baixar_dfp()
    with zipfile.ZipFile(arquivo) as z:
        indice = ler_csv_cvm(z, "dfp_cia_aberta_2023.csv")
        indice["DT_RECEB"] = pd.to_datetime(indice["DT_RECEB"])
        indice["DT_REFER"] = pd.to_datetime(indice["DT_REFER"])
        # Primeiro exclui versoes que so apareceram depois da formacao.
        indice = indice[
            (indice["DT_RECEB"] <= pd.Timestamp(LIMITE_DFP))
            & (indice["DT_REFER"] == pd.Timestamp("2023-12-31"))
        ].sort_values(["DT_RECEB", "VERSAO"])
        grupos = ["BPA", "BPP", "DRE", "DFC_MI", "DFC_MD"]
        dados = {
            grupo: ler_csv_cvm(z, f"dfp_cia_aberta_{grupo}_con_2023.csv")
            for grupo in grupos
        }
        empresas = {}
        for ticker, (nome, setor, codigo_cvm) in EMPRESAS.items():
            documentos = indice[indice["CD_CVM"] == codigo_cvm]
            if documentos.empty:
                raise ValueError(f"{ticker}: DFP nao disponivel em 30/04/2024.")
            doc = documentos.iloc[-1]
            versao = int(doc["VERSAO"])
            tabelas = {}
            for grupo, tabela in dados.items():
                tabelas[grupo] = tabela[
                    (tabela["CD_CVM"] == codigo_cvm)
                    & (tabela["VERSAO"] == versao)
                    & (tabela["DT_REFER"].astype(str).str[:10] == "2023-12-31")
                ]
            ativo = ler_conta(tabelas["BPA"], "1")
            ativo_c = ler_conta(tabelas["BPA"], "1.01")
            patrimonio = ler_conta(tabelas["BPP"], "2.03")
            passivo_c = ler_conta(tabelas["BPP"], "2.01")
            receita = ler_conta(tabelas["DRE"], "3.01")
            lucro = ler_conta(tabelas["DRE"], "3.11")
            fluxo = None
            for grupo in ("DFC_MI", "DFC_MD"):
                if not tabelas[grupo].empty:
                    try:
                        fluxo = ler_conta(tabelas[grupo], "6.01")
                        break
                    except ValueError:
                        continue
            if fluxo is None:
                raise ValueError(f"{ticker}: fluxo de caixa operacional ausente.")
            if min(ativo, patrimonio, receita, passivo_c) <= 0:
                raise ValueError(f"{ticker}: denominador nao positivo.")
            if ativo - patrimonio < 0:
                raise ValueError(f"{ticker}: passivo total negativo.")
            empresas[ticker] = {
                "Empresa": nome,
                "Setor": setor,
                "ROE": lucro / patrimonio,
                "ROA": lucro / ativo,
                "Margem liquida": lucro / receita,
                "Endividamento": (ativo - patrimonio) / ativo,
                "Liquidez corrente": ativo_c / passivo_c,
                "Accruals": (lucro - fluxo) / ativo,
                "Data DFP": doc["DT_RECEB"].strftime("%d/%m/%Y"),
                "Versao DFP": versao,
            }
            print(f"  {ticker}: DFP v{versao}, recebida {empresas[ticker]['Data DFP']}")
    return pd.DataFrame.from_dict(empresas, orient="index")

# ============================================================
# 3. RANKING DO FATOR QUALIDADE
# ============================================================

def fazer_ranking(balancos):
    """Pondera rentabilidade (40%), seguranca (30%), lucros (30%)."""
    indicadores = [
        "ROE", "ROA", "Margem liquida", "Endividamento",
        "Liquidez corrente", "Accruals",
    ]
    if len(balancos) != 10:
        raise ValueError("O trabalho precisa das 10 empresas escolhidas.")
    if not np.isfinite(balancos[indicadores].to_numpy(dtype=float)).all():
        raise ValueError("Ha indicadores ausentes ou nao numericos na DFP.")
    notas = pd.DataFrame(index=balancos.index)
    for coluna in indicadores:
        # Para Endividamento e Accruals, menor e melhor.
        maior_melhor = coluna not in ("Endividamento", "Accruals")
        posicao = balancos[coluna].rank(method="average", ascending=maior_melhor)
        notas[coluna] = (posicao - 1) / (len(balancos) - 1) * 100
    ranking = balancos.copy()
    ranking["Score rentabilidade"] = notas[
        ["ROE", "ROA", "Margem liquida"]
    ].mean(axis=1)
    ranking["Score seguranca"] = notas[
        ["Endividamento", "Liquidez corrente"]
    ].mean(axis=1)
    ranking["Score lucros"] = notas["Accruals"]
    ranking["Score"] = (
        0.40 * ranking["Score rentabilidade"]
        + 0.30 * ranking["Score seguranca"]
        + 0.30 * ranking["Score lucros"]
    )
    ranking = ranking.sort_values("Score", ascending=False, kind="stable")
    ranking.insert(0, "Posicao", np.arange(1, 11))
    return ranking

# ============================================================
# 4. COTACOES E CDI
# ============================================================
def preco_yahoo(ticker):
    """Precos diarios ajustados (Yahoo Finance) para todo o backtest."""
    simbolo = "^BVSP" if ticker == "IBOV" else ticker + ".SA"
    historico = yf.Ticker(simbolo).history(
        start=FORMACAO, end="2026-07-02", auto_adjust=True, actions=False
    )
    if historico.empty or "Close" not in historico:
        raise ValueError(f"Sem cotacoes do Yahoo para {ticker}.")
    serie = historico["Close"].astype(float).copy()
    serie.index = pd.to_datetime(serie.index).tz_localize(None).normalize()
    return serie

def preco_brapi(ticker):
    """Alternativa opcional caso o Yahoo nao retorne determinada acao."""
    if not TOKEN_BRAPI or ticker == "IBOV":
        raise ValueError("Sem token brapi (ou indice nao atendido).")
    resposta = requests.get(
        f"https://brapi.dev/api/quote/{ticker}",
        params={"token": TOKEN_BRAPI, "range": "5y", "interval": "1d"},
        timeout=(10, 40),
    )
    resposta.raise_for_status()
    historico = pd.DataFrame(resposta.json()["results"][0]["historicalDataPrice"])
    if "adjustedClose" not in historico:
        raise ValueError(f"brapi sem preco ajustado: {ticker}.")
    datas = (
        pd.to_datetime(historico["date"], unit="s", utc=True)
        .dt.tz_convert("America/Sao_Paulo")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    return pd.Series(historico["adjustedClose"].values, index=datas, dtype=float)

def carregar_precos():
    """Alinha todas as acoes sem inventar cotacoes por preenchimento."""
    series = {}
    for ticker in [*EMPRESAS, "IBOV"]:
        try:
            serie = preco_yahoo(ticker)
            origem = "Yahoo Finance"
        except Exception as erro:
            print(f"  Aviso {ticker}: Yahoo falhou ({erro}).")
            serie = preco_brapi(ticker)
            origem = "brapi"
        serie = serie.loc[FORMACAO:FIM].sort_index()
        serie = serie.loc[~serie.index.duplicated(keep="last")]
        if serie.empty or serie.isna().any() or (serie <= 0).any():
            raise ValueError(f"{ticker}: preco faltante, nulo ou negativo.")
        FONTES_PRECOS[ticker] = origem
        series[ticker] = serie
        print(f"  {ticker}: {len(serie)} pregões - {origem}")
    tabela = pd.concat(series, axis=1).sort_index()
    dias_incompletos = tabela.index[tabela.isna().any(axis=1)]
    if len(dias_incompletos) > 3:
        raise ValueError(
            f"Foram encontrados {len(dias_incompletos)} dias sem todas as cotacoes."
        )
    if len(dias_incompletos):
        print(f"  Aviso: {len(dias_incompletos)} datas incompletas removidas.")
    tabela = tabela.dropna()
    if tabela.empty or tabela.index[0] != pd.Timestamp(FORMACAO):
        raise ValueError("Falta cotacao da data de formacao.")
    if tabela.index[-1] != pd.Timestamp(FIM):
        raise ValueError("Falta cotacao da data final.")
    if tabela.pct_change().abs().gt(0.65).any().any():
        raise ValueError("Variacao diaria extrema: verificar eventos societarios.")
    return tabela

def interpretar_cdi(dados):
    """Converte os valores do SGS 12 (% ao dia) em retorno decimal."""
    datas = pd.to_datetime(dados["data"], dayfirst=True)
    numeros = pd.to_numeric(
        dados["valor"].astype(str).str.replace(",", ".", regex=False),
        errors="raise",
    ) / 100
    serie = pd.Series(numeros.to_numpy(dtype=float), index=datas).sort_index()
    if serie.index.has_duplicates or serie.isna().any():
        raise ValueError("SGS 12 retornou datas duplicadas ou valores ausentes.")
    return serie

def usar_cdi_legado(datas):
    """Recupera CDI REAL de um CSV que o programa anterior ja produziu."""
    antigo = PASTA / "resultados" / "curvas_investimento.csv"
    if not antigo.exists():
        return None
    tabela = pd.read_csv(antigo, sep=";", decimal=",", index_col=0, parse_dates=True)
    if "CDI" not in tabela:
        return None
    valores = tabela["CDI"].astype(float)
    if valores.empty or not np.isclose(valores.iloc[0], CAPITAL):
        return None
    serie = valores.pct_change()
    serie.iloc[0] = 0.0
    if serie.reindex(datas).isna().any():
        return None
    print("  CDI: aproveitando serie real salva pelo projeto anterior.")
    return serie

def carregar_cdi(datas):
    """Usa cache local, CSV real de execucao anterior ou API do BCB."""
    global ORIGEM_CDI
    arquivo = CACHE / "cdi_sgs12.csv"
    serie = None
    if arquivo.exists():
        cache = pd.read_csv(arquivo)
        serie = interpretar_cdi(cache)
        if serie.reindex(datas[1:]).isna().any():
            serie = None
        else:
            ORIGEM_CDI = "Banco Central SGS 12 (cache da API)"
            print("  CDI: carregado do cache local.")
    if serie is None:
        serie = usar_cdi_legado(datas)
        if serie is not None:
            ORIGEM_CDI = "SGS 12 via CSV do backtest anterior"
    if serie is None:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
        for tentativa in range(1, 4):
            try:
                print(f"  CDI: Banco Central, tentativa {tentativa}/3...")
                resposta = requests.get(
                    url,
                    params={
                        "formato": "json", "dataInicial": "02/05/2024",
                        "dataFinal": "01/07/2026",
                    },
                    timeout=(10, 45),
                )
                resposta.raise_for_status()
                serie = interpretar_cdi(pd.DataFrame(resposta.json()))
                ORIGEM_CDI = "Banco Central SGS 12 (API)"
                # Grava os percentuais reais para execucoes futuras.
                pd.DataFrame({
                    "data": serie.index.strftime("%d/%m/%Y"),
                    "valor": serie.values * 100,
                }).to_csv(arquivo, index=False)
                break
            except (requests.RequestException, ValueError, KeyError) as erro:
                print(f"  Falha ao consultar CDI: {erro}")
                time.sleep(2)
    if serie is None:
        raise ConnectionError(
            "Sem CDI. Tente novamente com internet ou use um cache real do BCB."
        )
    alinhado = serie.reindex(datas).copy()
    alinhado.iloc[0] = 0.0  # compra no fechamento do primeiro dia
    if alinhado.isna().any() or (alinhado.abs() > 0.01).any():
        raise ValueError("CDI incompleto ou com valores diarios suspeitos.")
    return alinhado

# ============================================================
# 5. CARTEIRAS, RISCO E DESEMPENHO
# ============================================================
def carteira_buy_hold(precos, acoes):
    """Cada acao recebe a mesma parcela inicial; nao ha rebalanceamento."""
    desempenho_individual = precos[acoes] / precos[acoes].iloc[0]
    return CAPITAL * desempenho_individual.mean(axis=1)

def calcular_metricas(curva, cdi):
    """Retorno total, anual, volatilidade, Sharpe e maior queda."""
    retornos = curva.pct_change().dropna()
    taxa_dia = cdi.reindex(retornos.index)
    if taxa_dia.isna().any() or len(retornos) < 2:
        raise ValueError("Dados insuficientes para indicadores de risco.")
    total = curva.iloc[-1] / curva.iloc[0] - 1
    anual = (1 + total) ** (252 / len(retornos)) - 1
    vol_dia = retornos.std(ddof=1)
    vol_ano = vol_dia * np.sqrt(252)
    sharpe = (
        (retornos - taxa_dia).mean() / vol_dia * np.sqrt(252)
        if vol_dia > 0 else np.nan
    )
    drawdown = (curva / curva.cummax() - 1).min()
    return {
        "Retorno total (%)": total * 100,
        "Retorno anual (%)": anual * 100,
        "Volatilidade (%)": vol_ano * 100,
        "Max. drawdown (%)": drawdown * 100,
        "Sharpe": sharpe,
        "Valor final (R$)": curva.iloc[-1],
    }

def calcular_contribuicao(precos, ranking):
    """A soma das contribuicoes deve ser igual ao retorno da carteira."""
    selecionadas = ranking.index[:5].tolist()
    retornos = (precos[selecionadas].iloc[-1] /
                precos[selecionadas].iloc[0] - 1) * 100
    return pd.DataFrame({
        "Empresa": ranking.loc[selecionadas, "Empresa"],
        "Score": ranking.loc[selecionadas, "Score"],
        "Peso inicial (%)": 20.0,
        "Retorno individual (%)": retornos,
        "Contribuicao (p.p.)": retornos / 5,
    })

def analisar_sensibilidade(precos, ranking, cdi):
    """Examina a concentracao sem escolher o melhor resultado depois."""
    resultados = {}
    for n in (3, 5, 7):
        ativos = ranking.index[:n].tolist()
        curva = carteira_buy_hold(precos, ativos)
        resultados[f"Top {n}"] = calcular_metricas(curva, cdi)
    return pd.DataFrame(resultados).T

def testar_calculos():
    """Testes pequenos que independem da internet e dos dados do mercado."""
    precos = pd.DataFrame({
        "A": [100.0, 110.0, 120.0],
        "B": [100.0, 90.0, 80.0],
    })
    curva = carteira_buy_hold(precos, ["A", "B"])
    assert np.isclose(curva.iloc[0], CAPITAL)
    assert np.isclose(curva.iloc[-1], CAPITAL)
    # Com pesos iguais na COMPRA, e nao recalibrados a cada pregao.
    assert np.isclose(curva.iloc[1], CAPITAL)

# ============================================================
# 6. GRAFICOS (APARECEM TAMBEM NO JUPYTER)
# ============================================================

def salvar_figura(fig, nome):
    fig.savefig(SAIDA / nome, dpi=190, bbox_inches="tight")
    if "ipykernel" in sys.modules:
        plt.show()
    plt.close(fig)

def titulo(ax, texto, subtitulo=""):
    ax.set_title(texto, loc="left", fontsize=16, fontweight="bold", pad=26)
    if subtitulo:
        ax.text(0, 1.02, subtitulo, transform=ax.transAxes,
                fontsize=9, color="#6B7B8A", va="bottom")
    ax.set_axisbelow(True)

def grafico_evolucao(curvas):
    fig, ax = plt.subplots(figsize=(12, 5.6))
    for nome in ("Quality", "Low Quality", "Ibovespa", "CDI"):
        espessura = 2.8 if nome == "Quality" else 1.9
        ax.plot(curvas.index, curvas[nome], color=CORES[nome],
                lw=espessura, label=nome,
                linestyle="--" if nome == "CDI" else "-")
    ax.axhline(CAPITAL, color="#BAC6D1", lw=1, linestyle=":")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: "R$ " + f"{v:,.0f}".replace(",", ".")))
    ax.grid(axis="y", alpha=0.7)
    titulo(ax, "Quanto R$ 10 mil teriam se tornado?",
           "Carteiras e referencias | maio de 2024 a julho de 2026")
    ax.legend(frameon=False, loc="upper left", ncol=4)
    fig.autofmt_xdate()
    fig.tight_layout()
    salvar_figura(fig, "01_evolucao.png")

def grafico_ranking(ranking):
    ordem = ranking.sort_values("Score")
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    cores = [VERDE if t in ranking.index[:5] else "#BAC5D0" for t in ordem.index]
    ax.barh(ordem.index, ordem["Score"], color=cores, height=0.66)
    for i, nota in enumerate(ordem["Score"]):
        ax.text(nota + 1.4, i, f"{nota:.1f}", va="center", fontweight="bold")
    ax.set_xlim(0, 110)
    ax.set_xlabel("Score de qualidade | escala relativa de 0 a 100")
    ax.grid(axis="x", alpha=0.45)
    titulo(ax, "Ranking do fator qualidade",
           "Verde: cinco empresas selecionadas para a carteira Quality")
    fig.tight_layout()
    salvar_figura(fig, "02_ranking.png")

def grafico_retorno(resultados):
    nomes = ["Quality", "Low Quality", "Ibovespa", "CDI"]
    valores = resultados.loc[nomes, "Retorno total (%)"]
    fig, ax = plt.subplots(figsize=(9.5, 5.1))
    barras = ax.bar(nomes, valores, color=[CORES[n] for n in nomes], width=0.56)
    ax.bar_label(barras, fmt="%+.1f%%", padding=5, fontsize=11, fontweight="bold")
    ax.axhline(0, color="#9BA9B7", lw=1)
    ax.set_ylabel("Retorno acumulado (%)")
    ax.grid(axis="y", alpha=0.5)
    ax.margins(y=0.22)
    titulo(ax, "Rentabilidade acumulada",
           "Mesmo periodo e capital inicial para as quatro alternativas")
    fig.tight_layout()
    salvar_figura(fig, "03_retorno.png")

def grafico_risco(resultados):
    nomes = ["Quality", "Low Quality", "Ibovespa"]
    pos = np.arange(3)
    vol = resultados.loc[nomes, "Volatilidade (%)"].to_numpy()
    quedas = -resultados.loc[nomes, "Max. drawdown (%)"].to_numpy()
    fig, ax = plt.subplots(figsize=(9.8, 5.1))
    b1 = ax.bar(pos - 0.18, vol, 0.36, color=VERDE, label="Volatilidade anual")
    b2 = ax.bar(pos + 0.18, quedas, 0.36, color=AZUL,
                label="Maior queda (valor absoluto)")
    ax.bar_label(b1, fmt="%.1f%%", padding=4)
    ax.bar_label(b2, fmt="%.1f%%", padding=4)
    ax.set_xticks(pos, nomes)
    ax.set_ylabel("Percentual (%)")
    ax.legend(frameon=False, ncol=2)
    ax.grid(axis="y", alpha=0.5)
    ax.margins(y=0.22)
    titulo(ax, "Risco observado no periodo",
           "Valores menores representam oscilacoes ou quedas mais moderadas")
    fig.tight_layout()
    salvar_figura(fig, "04_risco.png")

def grafico_contribuicao(contribuicao):
    dados = contribuicao["Contribuicao (p.p.)"].sort_values()
    fig, ax = plt.subplots(figsize=(9.3, 4.8))
    cores = [VERDE if v >= 0 else LARANJA for v in dados]
    barras = ax.barh(dados.index, dados.values, color=cores, height=0.58)
    ax.bar_label(barras, fmt="%+.1f p.p.", padding=4, fontsize=10)
    ax.axvline(0, color="#91A0AE", lw=1)
    ax.grid(axis="x", alpha=0.45)
    ax.margins(x=0.22)
    titulo(ax, "Quem ajudou ou prejudicou a carteira?",
           "Contribuicao de cada ativo ao retorno total da Quality")
    fig.tight_layout()
    salvar_figura(fig, "05_contribuicao.png")

def grafico_sensibilidade(sensibilidade):
    nomes = ["Top 3", "Top 5", "Top 7"]
    valores = sensibilidade.loc[nomes, "Retorno total (%)"]
    fig, ax = plt.subplots(figsize=(9, 4.9))
    barras = ax.bar(nomes, valores, color=["#87BDB3", VERDE, "#B5D4CD"], width=0.55)
    ax.bar_label(barras, fmt="%+.1f%%", padding=5, fontweight="bold")
    ax.axhline(0, color="#91A0AE", lw=1)
    ax.set_ylabel("Retorno acumulado (%)")
    ax.grid(axis="y", alpha=0.5)
    ax.margins(y=0.25)
    titulo(ax, "Concentracao da carteira",
           "Top 3, Top 5 e Top 7 | pesos iguais no momento da compra")
    fig.tight_layout()
    salvar_figura(fig, "06_sensibilidade.png")

def criar_graficos(ranking, curvas, resultados, contribuicao, sensibilidade):
    configurar_graficos()
    grafico_evolucao(curvas)
    grafico_ranking(ranking)
    grafico_retorno(resultados)
    grafico_risco(resultados)
    grafico_contribuicao(contribuicao)
    grafico_sensibilidade(sensibilidade)

# ============================================================
# 7. TABELAS, RELATORIO E APRESENTACAO
# ============================================================
def salvar_csv(tabela, nome):
    """Gera CSV em formato facil de abrir no Excel brasileiro."""
    tabela.to_csv(SAIDA / nome, sep=";", decimal=",", encoding="utf-8-sig")

def tabela_html(tabela):
    return tabela.to_html(
        classes="dados", border=0, na_rep="—",
        float_format=lambda x: f"{x:,.2f}",
    )

def montar_relatorio(ranking, resultados, contribuicao, sensibilidade):
    """Relatorio de uma pagina longa, com imagens locais e conclusao automatica."""
    q = resultados.loc["Quality", "Retorno total (%)"]
    b = resultados.loc["Low Quality", "Retorno total (%)"]
    ibov = resultados.loc["Ibovespa", "Retorno total (%)"]
    cdi = resultados.loc["CDI", "Retorno total (%)"]
    grupo_q = ", ".join(ranking.index[:5])
    grupo_b = ", ".join(ranking.index[5:])
    diferenca = q - b
    arquivos = [
        "01_evolucao.png", "02_ranking.png", "03_retorno.png",
        "04_risco.png", "05_contribuicao.png", "06_sensibilidade.png",
    ]
    figuras = "\n".join(
        f'<img src="{nome}" alt="Grafico {i+1}">'
        for i, nome in enumerate(arquivos)
    )
    fontes = pd.DataFrame.from_dict(FONTES_PRECOS, orient="index", columns=["Fonte de cotacoes"])
    fontes.loc["CDI", "Fonte de cotacoes"] = ORIGEM_CDI
    conclusao = (
        f"A carteira Quality retornou {q:+.2f}%, contra {b:+.2f}% da Low Quality "
        f"(diferenca de {diferenca:+.2f} pontos percentuais). "
        f"O Ibovespa registrou {ibov:+.2f}% e o CDI, {cdi:+.2f}%. "
        "Esses numeros descrevem somente o intervalo estudado e nao provam "
        "que o fator tera o mesmo desempenho em outros periodos."
    )
    css = """
    body{margin:0;background:#f7f9fc;color:#142c49;font:15px/1.6 Arial,sans-serif}
    header{background:#142c49;color:white;padding:46px 6%}
    header h1{margin:0;font-size:34px;letter-spacing:-.7px}
    header p{margin:10px 0 0;color:#c1d2e1}
    main{max-width:1080px;margin:auto;padding:24px}
    section{background:white;border:1px solid #edf1f5;border-radius:14px;
            box-shadow:0 5px 20px #142c4909;margin:20px 0;padding:26px 30px}
    h2{font-size:21px;margin:0 0 14px} p{margin:10px 0;color:#344b61}
    .indicadores{display:grid;grid-template-columns:repeat(4,1fr);gap:13px}
    .cartao{background:#edf7f4;border-radius:10px;padding:18px}
    .cartao small{display:block;color:#52687a}.cartao strong{font-size:26px;color:#168f7a}
    .dados{border-collapse:collapse;width:100%;display:block;overflow-x:auto;font-size:13px}
    .dados td,.dados th{padding:9px 11px;border-bottom:1px solid #e8edf2;
                        text-align:right;white-space:nowrap}
    .dados th{background:#f0f4f8} img{display:block;width:100%;height:auto;margin:20px 0}
    .nota{padding:14px 17px;border-left:4px solid #cda452;background:#fcf8ed}
    footer{padding:24px;text-align:center;color:#6c7b88;font-size:12px}
    @media(max-width:720px){.indicadores{grid-template-columns:repeat(2,1fr)}
      section{padding:16px}header h1{font-size:26px}}
    """
    html = f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Factor Investing | Fator Qualidade</title><style>{css}</style></head>
<body><header><h1>Factor Investing | Fator Qualidade</h1>
<p>10 empresas brasileiras · 02/05/2024 até 01/07/2026 · Capital hipotetico R$ 10.000</p>
</header><main>
<section><h2>Resultados principais</h2><div class="indicadores">
<div class="cartao"><small>Quality</small><strong>{q:+.1f}%</strong></div>
<div class="cartao"><small>Low Quality</small><strong>{b:+.1f}%</strong></div>
<div class="cartao"><small>Ibovespa</small><strong>{ibov:+.1f}%</strong></div>
<div class="cartao"><small>CDI</small><strong>{cdi:+.1f}%</strong></div>
</div></section>
<section><h2>Objetivo e metodologia</h2>
<p>A hipotese e que empresas mais lucrativas, financeiramente seguras e com maior
conversao do lucro em caixa possam apresentar resultados mais favoraveis.</p>
<p>Os dados financeiros vieram das DFPs consolidadas de 2023, nas versoes
entregues ate 30/04/2024. O score atribui 40% a rentabilidade (ROE, ROA, margem),
30% a seguranca (endividamento, liquidez) e 30% a qualidade dos lucros (accruals).</p>
<p><b>Quality:</b> {grupo_q}.<br><b>Low Quality:</b> {grupo_b}.</p>
<p>As carteiras foram iniciadas com cinco acoes e 20% por ativo, sem rebalanceamento.
O universo foi escolhido intencionalmente por diversidade setorial, sem utilizar
retornos posteriores a formacao da carteira.</p></section>
<section><h2>Ranking fundamentalista</h2>
{tabela_html(ranking[["Empresa", "Setor", "ROE", "ROA", "Margem liquida", "Endividamento", "Liquidez corrente", "Accruals", "Score"]])}</section>
<section><h2>Retorno e risco</h2>{tabela_html(resultados)}</section>
<section><h2>Graficos do estudo</h2>{figuras}</section>
<section><h2>Contribuicao por empresa</h2>{tabela_html(contribuicao)}</section>
<section><h2>Teste de concentracao</h2><p>Comparamos as carteiras Top 3, Top 5 e
Top 7 para observar o efeito do numero de acoes, sem escolher a vencedora
com conhecimento dos resultados futuros.</p>{tabela_html(sensibilidade)}</section>
<section><h2>Fontes utilizadas</h2>{tabela_html(fontes)}</section>
<section><h2>Conclusao e limites</h2><p>{conclusao}</p>
<p class="nota"><b>Limites:</b> apenas dez empresas e uma unica formacao;
selecao intencional; risco de atualizacoes nos precos ajustados; resultados
sem impostos ou custos de transacao; indicadores contabeis podem conter
itens extraordinarios; Ibovespa tem metodologia propria de retorno total.</p>
<p>Este relatorio e educacional e nao recomenda comprar ou vender acoes.</p></section>
</main><footer>Gerado em {datetime.now():%d/%m/%Y %H:%M} · Python + CVM + Yahoo/brapi + Banco Central</footer>
</body></html>"""
    destino = SAIDA / "relatorio.html"
    destino.write_text(html, encoding="utf-8")
    return destino

def mostrar_no_jupyter(ranking, resultados):
    """Exibe tambem as tabelas no painel interativo do VS Code."""
    if "ipykernel" not in sys.modules:
        return
    from IPython.display import display
    print("\nRanking de qualidade:")
    display(ranking[["Empresa", "Score", "Score rentabilidade",
                     "Score seguranca", "Score lucros"]].round(2))
    print("\nResultados do backtest:")
    display(resultados.round(2))

# ============================================================
# 8. PROGRAMA PRINCIPAL
# ============================================================
def main():
    preparar_certificados()
    testar_calculos()
    print("\n1/4 | Consultando balancos historicos...")
    ranking = fazer_ranking(carregar_balancos())
    carteira_quality = ranking.index[:5].tolist()
    carteira_low = ranking.index[5:].tolist()
    print("\nQuality:", ", ".join(carteira_quality))
    print("Low Quality:", ", ".join(carteira_low))
    print("\n2/4 | Buscando precos e CDI...")
    precos = carregar_precos()
    cdi = carregar_cdi(precos.index)
    curvas = pd.DataFrame({
        "Quality": carteira_buy_hold(precos, carteira_quality),
        "Low Quality": carteira_buy_hold(precos, carteira_low),
        "Ibovespa": CAPITAL * precos["IBOV"] / precos["IBOV"].iloc[0],
        "CDI": CAPITAL * (1 + cdi).cumprod(),
    })
    resultados = pd.DataFrame({
        nome: calcular_metricas(curvas[nome], cdi) for nome in curvas
    }).T
    resultados.loc["CDI", "Sharpe"] = np.nan
    contribuicao = calcular_contribuicao(precos, ranking)
    if not np.isclose(
        contribuicao["Contribuicao (p.p.)"].sum(),
        resultados.loc["Quality", "Retorno total (%)"], atol=1e-6,
    ):
        raise AssertionError("Contribuicoes individuais nao fecham com a carteira.")
    sensibilidade = analisar_sensibilidade(precos, ranking, cdi)
    print("\n3/4 | Gravando tabelas e gerando os graficos...")
    salvar_csv(ranking, "ranking.csv")
    salvar_csv(resultados, "resultado.csv")
    salvar_csv(contribuicao, "contribuicao.csv")
    salvar_csv(sensibilidade, "sensibilidade.csv")
    salvar_csv(curvas, "evolucao.csv")
    criar_graficos(ranking, curvas, resultados, contribuicao, sensibilidade)
    relatorio = montar_relatorio(ranking, resultados, contribuicao, sensibilidade)
    print("\n4/4 | CONCLUIDO!")
    print(resultados.round(2).to_string())
    print("\nRelatorio HTML:", relatorio)
    mostrar_no_jupyter(ranking, resultados)

if __name__ == "__main__":
    try:
        main()
    except PermissionError as erro:
        print("\nNao foi possivel gravar algum arquivo. Feche-o no Excel e tente novamente.")
        print("Detalhe:", erro)
        raise
    except Exception as erro:
        print("\nExecucao interrompida para nao apresentar resultado incompleto.")
        print(type(erro).__name__ + ":", erro)
        raise
# %%
