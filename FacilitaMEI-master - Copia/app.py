from datetime import date, datetime
from io import BytesIO
import json
import math
import os

import calendar
import requests
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = "troque-esta-chave-em-producao"
API_URL = "http://localhost:3000"

# ----------------------------------------------------------------
# Constantes Globais e Opções
# ----------------------------------------------------------------

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TIPOS_LANC = ["Entrada", "Saída"]
CATEGORIAS_LANC = ["Vendas", "Infraestrutura", "Fornecedores", "Pessoal", "Utilidades", "Manutenção", "Impostos", "Outros"]
FORMAS_LANC = ["Pix", "Cartão", "Boleto", "TED", "Transferência", "Débito automático", "Dinheiro"]

OPCOES = {
    "tipo_pessoa": ["Pessoa física", "Pessoa jurídica"],
    "status": ["Ativo", "Inativo"],
    "uf": ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
           "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
           "SP", "SE", "TO"],
    "forma_pagamento": ["Pix", "Boleto", "Cartão de crédito", "Cartão de débito", "Transferência", "Dinheiro"],
    "prazo_pagamento": ["À vista", "7 dias", "15 dias", "30 dias", "45 dias", "60 dias"],
    "categoria_receita": ["Vendas", "Serviços", "Comissões", "Outras receitas"],
}

OPCOES_PRODUTO = {
    "categoria": ["Cafés e grãos", "Bebidas", "Acessórios", "Doces e salgados", "Outros"],
    "unidade": ["Unidade (un)", "Quilo (kg)", "Grama (g)", "Litro (l)", "Pacote (pct)", "Caixa (cx)"],
    "status": ["Ativo", "Inativo"],
}

# ----------------------------------------------------------------
# Filtros do Jinja2
# ----------------------------------------------------------------

@app.template_filter("brl")
def brl(valor):
    """Formata 1234.5 como R$ 1.234,50"""
    if valor is None:
        valor = 0.0
    texto = f"{abs(float(valor)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"

@app.template_filter("num")
def num(valor):
    """Formata 1234.5 como 1.234,50 (sem o R$)"""
    if valor is None:
        valor = 0.0
    return f"{abs(float(valor)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@app.template_filter("brls")
def brls(valor):
    """Como 'brl', mas mostra o sinal de menos nos valores negativos."""
    if valor is None:
        valor = 0.0
    val_float = float(valor)
    return ("− " if val_float < 0 else "") + brl(abs(val_float))

@app.template_filter("mil")
def mil_filtro(v):
    return _mil(v)

# ----------------------------------------------------------------
# Funções Auxiliares de Apoio e Sessão
# ----------------------------------------------------------------

def _empresa_id():
    """Retorna o ID da empresa logada na sessão atual (ou None)."""
    usr = session.get("usuario")
    return usr.get("id") if isinstance(usr, dict) else None

def _limpar_valor(val_str):
    """Converte valores formatados como 'R$ 42,90' ou '42.90' em float."""
    if not val_str:
        return 0.0
    digitos = "".join(ch for ch in str(val_str) if ch.isdigit() or ch in (",", "."))
    if "," in digitos:
        digitos = digitos.replace(".", "").replace(",", ".")
    try:
        return float(digitos)
    except ValueError:
        return 0.0

def _mil(v):
    if v == 0:
        return "0"
    texto = f"{abs(v) / 1000:.1f}".replace(".", ",")
    if texto.endswith(",0"):
        texto = texto[:-2]
    return ("−" if v < 0 else "") + texto + " mil"

def _mil1(v):
    return ("−" if v < 0 else "") + f"{abs(v) / 1000:.1f}".replace(".", ",") + " mil"

def _qtd(n):
    return f"{n} lançamento" + ("" if n == 1 else "s")

def _escala(lo, hi):
    lo, hi = min(lo, 0), max(hi, 0)
    if hi == lo:
        hi = lo + 1000
    for passo in (500, 1000, 2000, 2500, 4000, 5000, 10000, 20000, 25000, 40000, 50000, 100000, 200000, 500000):
        base = math.floor(lo / passo) * passo
        topo = math.ceil(hi / passo) * passo
        if (topo - base) / passo <= 5:
            break
    return base, topo, passo

def _meses_disponiveis(movimentos):
    if not movimentos:
        return []
    return sorted({m["data"][:7] for m in movimentos if "data" in m and len(m["data"]) >= 7})

def _periodo(mes):
    try:
        ano, n = map(int, mes.split("-"))
        return f"01–{calendar.monthrange(ano, n)[1]:02d} {MESES_ABREV[n - 1]} {ano}"
    except Exception:
        return mes

def _filtros(movimentos):
    meses = _meses_disponiveis(movimentos)
    mes_padrao = meses[-1] if meses else date.today().strftime("%Y-%m")

    mes = request.args.get("mes", mes_padrao)
    if meses and mes not in meses:
        mes = mes_padrao

    cat = request.args.get("categoria", "")
    if cat not in CATEGORIAS_LANC:
        cat = ""

    opcoes_meses = [(m, _periodo(m)) for m in meses]
    return mes, cat, opcoes_meses

def _filtrar(movimentos, mes, cat):
    return [
        m for m in movimentos
        if m.get("data", "").startswith(mes) and (not cat or m.get("categoria") == cat)
    ]

def _saldo_antes(movimentos, mes, saldo_inicial=0.0):
    saldo = saldo_inicial
    for m in movimentos:
        if m.get("data", "")[:7] < mes:
            saldo += float(m["valor"]) if m.get("tipo") == "Entrada" else -float(m["valor"])
    return round(saldo, 2)

def _semanas(mes, movs):
    try:
        ano, n = map(int, mes.split("-"))
        ultimo = calendar.monthrange(ano, n)[1]
        abrev = MESES_ABREV[n - 1]
    except Exception:
        return []

    faixas = [(1, 7), (8, 14), (15, 21), (22, 28)]
    if ultimo >= 29:
        faixas.append((29, ultimo))

    semanas = []
    for ini, fim in faixas:
        da_semana = [
            m for m in movs
            if m.get("data") and len(m["data"]) >= 10 and ini <= int(m["data"][8:10]) <= fim
        ]
        semanas.append({
            "rotulo": f"{ini:02d}–{fim:02d} {abrev}",
            "fim": f"{fim:02d} {abrev}",
            "entradas": round(sum(float(m["valor"]) for m in da_semana if m.get("tipo") == "Entrada"), 2),
            "saidas": round(sum(float(m["valor"]) for m in da_semana if m.get("tipo") == "Saída"), 2),
        })
    return semanas

def _totais(movs):
    ent = round(sum(float(m["valor"]) for m in movs if m.get("tipo") == "Entrada"), 2)
    sai = round(sum(float(m["valor"]) for m in movs if m.get("tipo") == "Saída"), 2)
    qtd_ent = sum(1 for m in movs if m.get("tipo") == "Entrada")
    return ent, sai, round(ent - sai, 2), qtd_ent, len(movs) - qtd_ent

def montar_grafico(rotulos, saldos):
    if not saldos:
        return {"pontos": [], "linha": "", "area": "", "grades": []}

    x0, x1, y_topo, y_base = 52, 424, 24, 170
    base, topo, passo = _escala(min(saldos), max(saldos))
    passo_x = (x1 - x0) / max(len(saldos) - 1, 1)

    def y_de(v):
        return y_base - ((v - base) / max(topo - base, 1)) * (y_base - y_topo)

    pontos = [
        {"x": round(x0 + i * passo_x, 1), "y": round(y_de(v), 1), "rotulo": rotulos[i], "valor": _mil1(v)}
        for i, v in enumerate(saldos)
    ]
    linha = " ".join(f"{p['x']},{p['y']}" for p in pontos)
    y_zero = round(y_de(0), 1)
    area = f"{x0},{y_zero} {linha} {x1},{y_zero}"
    grades = [{"y": round(y_de(v), 1), "rotulo": _mil(v)} for v in range(base, topo + 1, passo)]
    return {"pontos": pontos, "linha": linha, "area": area, "grades": grades}

def _obter_dados_api(empresa_id):
    movimentos = []
    vencimentos = []
    if not empresa_id:
        return movimentos, vencimentos

    try:
        r = requests.get(f"{API_URL}/movimentacoes", params={"empresa_id": empresa_id}, timeout=3)
        if r.status_code == 200:
            movimentos = r.json()
    except Exception as e:
        print(f"API Node offline (movimentacoes): {e}")

    try:
        r = requests.get(f"{API_URL}/vencimentos", params={"empresa_id": empresa_id}, timeout=3)
        if r.status_code == 200:
            vencimentos = r.json()
    except Exception as e:
        print(f"API Node offline (vencimentos): {e}")

    return movimentos, vencimentos

# ----------------------------------------------------------------
# Autenticação e Início
# ----------------------------------------------------------------

@app.route("/")
def index():
    return render_template("inicio.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    email = ""
    erro = None
    aviso = request.args.get("aviso")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "")

        try:
            resposta = requests.post(
                f"{API_URL}/login",
                json={"email": email, "senha": senha},
                timeout=10,
            )
            dados = resposta.json()
        except requests.exceptions.RequestException:
            erro = "Não foi possível conectar ao servidor. Tente novamente."
        except ValueError:
            erro = "Resposta inválida do servidor."
        else:
            if resposta.status_code == 200:
                usr = dados.get("usuario", {})
                session["usuario"] = {
                    "id": usr.get("id"),
                    "nome": usr.get("nome", "Usuário MEI"),
                    "cpf_cnpj": usr.get("cpf_cnpj", ""),
                    "email": usr.get("email", email),
                }
                return redirect(url_for("visao_geral"))
            erro = dados.get("erro", "Erro ao realizar login.")

    return render_template("login.html", email=email, erro=erro, aviso=aviso)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/registro")
def pagina_registro():
    return render_template("registro.html", erro=None)

@app.route("/registrar", methods=["POST"])
def registrar():
    nome = request.form.get("nome", "").strip()
    documento = request.form.get("documento", "").strip()
    email = request.form.get("email", "").strip()
    senha = request.form.get("senha", "")
    confirmar_senha = request.form.get("confirmar_senha", "")

    if senha != confirmar_senha:
        return render_template("registro.html", erro="As senhas não coincidem.")

    try:
        resposta = requests.post(
            f"{API_URL}/cadastro",
            json={"nome": nome, "cpf_cnpj": documento, "email": email, "senha": senha},
            timeout=10,
        )
        dados = resposta.json()
    except requests.exceptions.RequestException:
        return render_template("registro.html", erro="Não foi possível conectar ao servidor. Tente novamente.")
    except ValueError:
        return render_template("registro.html", erro="Resposta inválida do servidor.")

    if resposta.status_code == 201:
        flash("Registro concluído! Sua conta foi criada.", "sucesso")
        return redirect(url_for("login", aviso="registrado"))

    return render_template("registro.html", erro=dados.get("erro", "Erro ao realizar cadastro."))

# ----------------------------------------------------------------
# Visão Geral / Painel
# ----------------------------------------------------------------

@app.route("/visao-geral")
@app.route("/painel")
def visao_geral():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    movimentos, vencimentos = _obter_dados_api(empresa_id)
    mes, cat, opcoes_meses = _filtros(movimentos)
    movs_filtrados = _filtrar(movimentos, mes, cat)
    semanas = _semanas(mes, movs_filtrados)
    ent, sai, res_op, qtd_ent, qtd_sai = _totais(movs_filtrados)

    inicial = 0.0 if cat else _saldo_antes(movimentos, mes)
    final = round(inicial + res_op, 2)
    abrev = MESES_ABREV[int(mes[5:7]) - 1] if len(mes) >= 7 else ""

    if cat:
        nota_saldo = f"Somente {cat}"
    elif inicial > 0:
        pct = (final - inicial) / inicial * 100
        nota_saldo = ("+" if pct >= 0 else "−") + f"{abs(pct):.1f}".replace(".", ",") + f"% desde 01 {abrev}"
    else:
        nota_saldo = "Sem saldo inicial para comparar"

    if ent > 0:
        margem = res_op / ent * 100
        nota_margem = "Margem de " + ("−" if margem < 0 else "") + f"{abs(margem):.1f}".replace(".", ",") + "% sobre as entradas"
    else:
        nota_margem = "Sem entradas no período"

    kpis = [
        {"rotulo": "Saldo da categoria" if cat else "Saldo em caixa", "valor": final,
         "tom": "out" if final < 0 else "", "nota": nota_saldo},
        {"rotulo": "Entradas do mês", "valor": ent, "tom": "in", "nota": _qtd(qtd_ent)},
        {"rotulo": "Saídas do mês", "valor": sai, "tom": "out", "nota": _qtd(qtd_sai)},
        {"rotulo": "Resultado operacional", "valor": res_op, "tom": "out" if res_op < 0 else "", "nota": nota_margem},
    ]

    maior = max([s["entradas"] for s in semanas] + [s["saidas"] for s in semanas] + [0])
    _, topo, passo = _escala(0, maior)

    recentes = sorted(movs_filtrados, key=lambda m: m.get("data", ""), reverse=True)[:5]
    lancamentos_fmt = [
        {"data": f"{m['data'][8:10]}/{m['data'][5:7]}/{m['data'][:4]}" if len(m.get("data", "")) >= 10 else m.get("data", ""),
         "descricao": m.get("descricao", ""), "categoria": m.get("categoria", ""),
         "tipo": m.get("tipo", ""), "valor": m.get("valor", 0)}
        for m in recentes
    ]

    p = {
        "kpis": kpis,
        "semanas": semanas,
        "escala": {"topo": topo, "ticks": list(range(topo, -1, -passo))},
        "vencimentos": [v for v in vencimentos if not cat or v.get("categoria") == cat],
        "lancamentos": lancamentos_fmt,
        "total_registros": len(movs_filtrados),
    }

    return render_template("visao_geral.html", p=p, mes=mes, categoria=cat, meses=opcoes_meses, categorias=CATEGORIAS_LANC)

# ----------------------------------------------------------------
# Fluxo de Caixa
# ----------------------------------------------------------------

@app.route("/fluxo-de-caixa")
def fluxo_caixa():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    movimentos, _ = _obter_dados_api(empresa_id)
    mes, cat, opcoes_meses = _filtros(movimentos)
    movs_filtrados = _filtrar(movimentos, mes, cat)
    semanas = _semanas(mes, movs_filtrados)
    abrev = MESES_ABREV[int(mes[5:7]) - 1] if len(mes) >= 7 else ""
    ent, sai, res_op, qtd_ent, qtd_sai = _totais(movs_filtrados)

    inicial = 0.0 if cat else _saldo_antes(movimentos, mes)
    saldos = [inicial]
    for s in semanas:
        saldos.append(round(saldos[-1] + s["entradas"] - s["saidas"], 2))
    final = saldos[-1]
    rotulos = [f"01 {abrev}"] + [s["fim"] for s in semanas]

    if cat:
        nota_ini, nota_fim = f"Somente {cat}", "Acumulado no período"
    else:
        nota_ini = f"em 01 {abrev}"
        if inicial > 0:
            pct = (final - inicial) / inicial * 100
            nota_fim = ("+" if pct >= 0 else "−") + f"{abs(pct):.1f}".replace(".", ",") + "% no período"
        else:
            nota_fim = "Sem saldo inicial para comparar"

    kpis = [
        {"rotulo": "Saldo inicial", "valor": inicial, "tom": "", "nota": nota_ini},
        {"rotulo": "Total de entradas", "valor": ent, "tom": "in", "nota": _qtd(qtd_ent)},
        {"rotulo": "Total de saídas", "valor": sai, "tom": "out", "nota": _qtd(qtd_sai)},
        {"rotulo": "Saldo final", "valor": final, "tom": "out" if final < 0 else "", "nota": nota_fim},
    ]

    alertas = []
    if not movs_filtrados:
        alertas.append({"tom": "info", "texto": "Nenhum lançamento encontrado para este filtro."})
    else:
        folha = sum(float(m["valor"]) for m in movs_filtrados if m.get("tipo") == "Saída" and m.get("categoria") == "Pessoal")
        if not cat and sai > 0 and folha > 0:
            pct = f"{folha / sai * 100:.1f}".replace(".", ",")
            alertas.append({"tom": "aviso", "texto": f"Folha representa {pct}% das saídas. Acompanhe o limite planejado."})
        negativas = [s["rotulo"] for s in semanas if s["entradas"] - s["saidas"] < 0]
        if not negativas:
            texto = "Nenhuma semana fechou com resultado negativo."
        elif len(negativas) == 1:
            texto = f"A semana {negativas[0]} fechou com resultado negativo."
        else:
            texto = "As semanas " + ", ".join(negativas[:-1]) + " e " + negativas[-1] + " fecharam com resultado negativo."
        alertas.append({"tom": "info", "texto": texto})

    f = {
        "kpis": kpis,
        "resultado": res_op,
        "alertas": alertas,
        "semanas": [s["rotulo"] for s in semanas],
        "linhas": [],
        "grafico": montar_grafico(rotulos, saldos)
    }

    return render_template("fluxo_caixa.html", f=f, grafico=f["grafico"],
                           mes=mes, categoria=cat, meses=opcoes_meses, categorias=CATEGORIAS_LANC)

# ----------------------------------------------------------------
# Produtos (Listagem, Cadastro, Edição e Exclusão)
# ----------------------------------------------------------------

def _extrair_dados_produto(f, empresa_id):
    return {
        "empresa_id": empresa_id,
        "nome": f.get("nome", "").strip(),
        "sku": f.get("sku", "").strip(),
        "categoria": f.get("categoria", ""),
        "descricao": f.get("descricao", "").strip(),
        "preco": _limpar_valor(f.get("preco")),
        "custo": _limpar_valor(f.get("custo")),
        "estoque_inicial": int(float(f.get("estoque_inicial") or 0)),
        "unidade": f.get("unidade", ""),
        "estoque_minimo": int(float(f.get("estoque_minimo") or 0)),
        "status": f.get("status", "Ativo"),
    }

@app.route("/produtos")
def produtos():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    lista_produtos = []
    try:
        resp = requests.get(f"{API_URL}/produtos", params={"empresa_id": empresa_id}, timeout=3)
        if resp.status_code == 200:
            lista_produtos = resp.json()
    except Exception as e:
        print(f"API Node offline (produtos): {e}")

    ativos = sum(1 for item in lista_produtos if item.get("status") == "Ativo")
    estoque_baixo = sum(
        1 for item in lista_produtos
        if int(item.get("estoque_inicial") or 0) <= int(item.get("estoque_minimo") or 0)
    )

    return render_template(
        "produtos.html",
        produtos=lista_produtos,
        total_produtos=len(lista_produtos),
        ativos=ativos,
        estoque_baixo=estoque_baixo,
        aviso=request.args.get("aviso"),
    )

@app.route("/produtos/novo", methods=["GET", "POST"])
def novo_produto():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        dados_produto = _extrair_dados_produto(request.form, empresa_id)
        try:
            resp = requests.post(f"{API_URL}/produtos", json=dados_produto, timeout=5)
            if resp.status_code == 201:
                return redirect(url_for("produtos", aviso="salvo"))
        except Exception as e:
            print(f"Erro ao salvar produto na API: {e}")

    return render_template("cadastro_produto.html", p={}, op=OPCOES_PRODUTO, editando=False)

@app.route("/produtos/editar/<int:produto_id>", methods=["GET", "POST"])
def editar_produto(produto_id):
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        dados_produto = _extrair_dados_produto(request.form, empresa_id)
        try:
            resp = requests.put(f"{API_URL}/produtos/{produto_id}", json=dados_produto, timeout=5)
            if resp.status_code == 200:
                return redirect(url_for("produtos", aviso="editado"))
        except Exception as e:
            print(f"Erro ao atualizar produto na API: {e}")

    produto_atual = {}
    try:
        resp = requests.get(
            f"{API_URL}/produtos/{produto_id}",
            params={"empresa_id": empresa_id},
            timeout=3,
        )
        if resp.status_code == 200:
            produto_atual = resp.json()
        else:
            return redirect(url_for("produtos"))
    except Exception as e:
        print(f"Erro ao carregar produto para edição: {e}")
        return redirect(url_for("produtos"))

    return render_template("cadastro_produto.html", p=produto_atual, op=OPCOES_PRODUTO, editando=True)

@app.route("/produtos/excluir/<int:produto_id>", methods=["POST"])
def excluir_produto(produto_id):
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    try:
        resp = requests.delete(
            f"{API_URL}/produtos/{produto_id}",
            params={"empresa_id": empresa_id},
            timeout=5,
        )
        if resp.status_code == 200:
            return redirect(url_for("produtos", aviso="excluido"))
    except Exception as e:
        print(f"Erro ao excluir produto na API: {e}")

    return redirect(url_for("produtos"))

@app.route("/produtos/cancelar")
def cancelar_produto():
    return redirect(url_for("produtos", aviso="cancelado"))

# ----------------------------------------------------------------
# Clientes (Listagem, Cadastro e Edição)
# ----------------------------------------------------------------

def _extrair_dados_cliente(f, empresa_id):
    return {
        "empresa_id": empresa_id,
        "nome": f.get("nome", "").strip(),
        "tipo_pessoa": f.get("tipo_pessoa", ""),
        "documento": f.get("documento", "").strip(),
        "telefone": f.get("telefone", "").strip(),
        "email": f.get("email", "").strip(),
        "status": f.get("status", "Ativo"),
        "cep": f.get("cep", "").strip(),
        "logradouro": f.get("logradouro", "").strip(),
        "numero": f.get("numero", "").strip(),
        "complemento": f.get("complemento", "").strip(),
        "bairro": f.get("bairro", "").strip(),
        "cidade": f.get("cidade", "").strip(),
        "uf": f.get("uf", ""),
        "forma_pagamento": f.get("forma_pagamento", ""),
        "prazo_pagamento": f.get("prazo_pagamento", ""),
        "limite_credito": _limpar_valor(f.get("limite_credito")),
        "categoria_receita": f.get("categoria_receita", ""),
        "observacoes": f.get("observacoes", "").strip(),
    }

@app.route("/clientes")
def clientes():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    lista_clientes = []
    try:
        resp = requests.get(f"{API_URL}/clientes", params={"empresa_id": empresa_id}, timeout=3)
        if resp.status_code == 200:
            lista_clientes = resp.json()
    except Exception as e:
        print(f"API Node offline (clientes): {e}")

    ativos = sum(1 for item in lista_clientes if item.get("status") == "Ativo")
    inativos = len(lista_clientes) - ativos

    return render_template(
        "clientes.html",
        clientes=lista_clientes,
        total_clientes=len(lista_clientes),
        ativos=ativos,
        inativos=inativos,
        aviso=request.args.get("aviso"),
    )

@app.route("/clientes/novo", methods=["GET", "POST"])
def novo_cliente():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        dados_cliente = _extrair_dados_cliente(request.form, empresa_id)
        try:
            resp = requests.post(f"{API_URL}/clientes", json=dados_cliente, timeout=5)
            if resp.status_code == 201:
                return redirect(url_for("clientes", aviso="salvo"))
        except Exception as e:
            print(f"Erro ao salvar cliente na API: {e}")

    return render_template("cadastro_cliente.html", c={}, op=OPCOES, editando=False)

@app.route("/clientes/editar/<int:cliente_id>", methods=["GET", "POST"])
def editar_cliente(cliente_id):
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    if request.method == "POST":
        dados_cliente = _extrair_dados_cliente(request.form, empresa_id)
        try:
            resp = requests.put(f"{API_URL}/clientes/{cliente_id}", json=dados_cliente, timeout=5)
            if resp.status_code == 200:
                return redirect(url_for("clientes", aviso="editado"))
        except Exception as e:
            print(f"Erro ao atualizar cliente na API: {e}")

    cliente_atual = {}
    try:
        resp = requests.get(
            f"{API_URL}/clientes/{cliente_id}",
            params={"empresa_id": empresa_id},
            timeout=3,
        )
        if resp.status_code == 200:
            cliente_atual = resp.json()
        else:
            return redirect(url_for("clientes"))
    except Exception as e:
        print(f"Erro ao carregar cliente para edição: {e}")
        return redirect(url_for("clientes"))

    return render_template("cadastro_cliente.html", c=cliente_atual, op=OPCOES, editando=True)

@app.route("/clientes/cancelar")
def cancelar_cliente():
    return redirect(url_for("clientes", aviso="cancelado"))

# ----------------------------------------------------------------
# Lançamentos (Listagem, Criação e Exclusão)
# ----------------------------------------------------------------

@app.route("/lancamentos")
def lancamentos():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    movimentos, _ = _obter_dados_api(empresa_id)
    ent, sai, res, q_ent, q_sai = _totais(movimentos)
    l = {
        "total_registros": len(movimentos),
        "totais": {"entradas": ent, "saidas": sai, "saldo": res},
        "itens": movimentos,
    }
    return render_template(
        "lancamentos.html", l=l, tipos=TIPOS_LANC, cats=CATEGORIAS_LANC,
        formas=FORMAS_LANC, hoje=date.today().isoformat(),
    )

@app.route("/lancamentos/novo", methods=["POST"])
def novo_lancamento():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    f = request.form
    tipo = f.get("tipo", "")
    descricao = f.get("descricao", "").strip()
    valor = _limpar_valor(f.get("valor"))

    try:
        data_obj = datetime.strptime(f.get("data", ""), "%Y-%m-%d")
        data_str = data_obj.strftime("%Y-%m-%d")
    except ValueError:
        data_str = None

    if not descricao or tipo not in TIPOS_LANC or valor <= 0 or data_str is None:
        return redirect(url_for("lancamentos"))

    try:
        requests.post(
            f"{API_URL}/movimentacoes",
            json={
                "empresa_id": empresa_id,
                "data": data_str,
                "tipo": tipo,
                "categoria": f.get("categoria", ""),
                "forma": f.get("forma", ""),
                "valor": valor,
                "descricao": descricao,
            },
            timeout=5,
        )
    except Exception as e:
        print(f"Erro ao enviar lançamento para API: {e}")

    return redirect(url_for("lancamentos", aviso="salvo"))

@app.route("/lancamentos/excluir/<int:lancamento_id>", methods=["POST"])
def excluir_lancamento(lancamento_id):
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    try:
        resp = requests.delete(
            f"{API_URL}/movimentacoes/{lancamento_id}",
            params={"empresa_id": empresa_id},
            timeout=5,
        )
        if resp.status_code == 200:
            return redirect(url_for("lancamentos", aviso="excluido"))
    except Exception as e:
        print(f"Erro ao excluir lançamento na API: {e}")

    return redirect(url_for("lancamentos"))

# ----------------------------------------------------------------
# Relatórios e Exportação
# ----------------------------------------------------------------

def _montar_relatorio(empresa_id):
    movimentos, _ = _obter_dados_api(empresa_id)
    mes, cat, opcoes_meses = _filtros(movimentos)
    movs_filtrados = _filtrar(movimentos, mes, cat)

    try:
        ano, n = map(int, mes.split("-"))
        ultimo = calendar.monthrange(ano, n)[1]
        abrev = MESES_ABREV[n - 1]
    except Exception:
        ultimo = 30
        abrev = ""

    faixas = [(1, 7), (8, 14), (15, 21), (22, 28)]
    if ultimo >= 29:
        faixas.append((29, ultimo))

    semanas_rotulos = [f"{ini:02d}–{fim:02d} {abrev}".upper() for ini, fim in faixas]

    def _valores_semanais(lista_movs):
        vals = []
        for ini, fim in faixas:
            soma = sum(
                float(m["valor"])
                for m in lista_movs
                if m.get("data") and len(m["data"]) >= 10 and ini <= int(m["data"][8:10]) <= fim
            )
            vals.append(round(soma, 2))
        return vals, round(sum(vals), 2)

    linhas = []

    # 1. Entradas
    linhas.append({"rotulo": "Entradas", "tipo": "secao", "tom": "in"})
    movs_ent = [m for m in movs_filtrados if m.get("tipo") == "Entrada"]
    cats_ent = sorted({m.get("categoria") or "Outros" for m in movs_ent})
    for c_nome in cats_ent:
        vals, tot = _valores_semanais([m for m in movs_ent if (m.get("categoria") or "Outros") == c_nome])
        linhas.append({
            "rotulo": c_nome,
            "valores": vals,
            "total": tot,
            "tipo": "",
            "tom": "",
        })

    vals_ent, tot_ent = _valores_semanais(movs_ent)
    linhas.append({
        "rotulo": "Total de entradas",
        "valores": vals_ent,
        "total": tot_ent,
        "tipo": "subtotal",
        "tom": "in",
    })

    # 2. Saídas
    linhas.append({"rotulo": "Saídas", "tipo": "secao", "tom": "out"})
    movs_sai = [m for m in movs_filtrados if m.get("tipo") == "Saída"]
    cats_sai = sorted({m.get("categoria") or "Outros" for m in movs_sai})
    for c_nome in cats_sai:
        vals, tot = _valores_semanais([m for m in movs_sai if (m.get("categoria") or "Outros") == c_nome])
        linhas.append({
            "rotulo": c_nome,
            "valores": vals,
            "total": tot,
            "tipo": "",
            "tom": "",
        })

    vals_sai, tot_sai = _valores_semanais(movs_sai)
    linhas.append({
        "rotulo": "Total de saídas",
        "valores": vals_sai,
        "total": tot_sai,
        "tipo": "subtotal",
        "tom": "out",
    })

    # 3. Resultado operacional
    vals_res = [round(e - s, 2) for e, s in zip(vals_ent, vals_sai)]
    tot_res = round(tot_ent - tot_sai, 2)
    linhas.append({
        "rotulo": "Resultado operacional",
        "valores": vals_res,
        "total": tot_res,
        "tipo": "resultado",
        "tom": "in" if tot_res >= 0 else "out",
    })

    agora = datetime.now()
    atualizado_em = f"{agora.day:02d} {MESES_ABREV[agora.month - 1]} {agora.year}, {agora.strftime('%H:%M')}"

    return {
        "mes": mes,
        "categoria": cat,
        "meses": opcoes_meses,
        "periodo_texto": _periodo(mes),
        "semanas": semanas_rotulos,
        "linhas": linhas,
        "atualizado_em": atualizado_em,
        "tem_movimentos": len(movs_filtrados) > 0,
    }

@app.route("/relatorios")
def relatorios():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    dados = _montar_relatorio(empresa_id)
    f = {
        "semanas": dados["semanas"],
        "linhas": dados["linhas"],
    }

    return render_template(
        "relatorios.html",
        f=f,
        mes=dados["mes"],
        categoria=dados["categoria"],
        meses=dados["meses"],
        categorias=CATEGORIAS_LANC,
        atualizado_em=dados["atualizado_em"],
        tem_movimentos=dados["tem_movimentos"],
    )

def gerar_excel(empresa_id, nome_empresa):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        return "Biblioteca 'openpyxl' não instalada. Execute: pip install openpyxl", 500

    dados = _montar_relatorio(empresa_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório Financeiro"

    ws["A1"] = f"Relatório Financeiro — {nome_empresa}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Período: {dados['periodo_texto']} | Gerado em {dados['atualizado_em']}"

    cabecalho = ["Descrição"] + dados["semanas"] + ["Total"]
    ws.append([])
    ws.append(cabecalho)

    header_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
    for cell in ws[4]:
        cell.font = Font(bold=True)
        cell.fill = header_fill

    for linha in dados["linhas"]:
        if linha["tipo"] == "secao":
            ws.append([linha["rotulo"].upper()])
            ws[ws.max_row][0].font = Font(bold=True)
            continue
        row = [linha["rotulo"]] + linha["valores"] + [linha["total"]]
        ws.append(row)
        if linha["tipo"] in ("subtotal", "resultado"):
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max(max_len + 4, 14)

    arquivo = BytesIO()
    wb.save(arquivo)
    arquivo.seek(0)
    return send_file(
        arquivo,
        as_attachment=True,
        download_name=f"relatorio-{dados['mes']}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def gerar_pdf(empresa_id, nome_empresa):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return "Biblioteca 'reportlab' não instalada. Execute: pip install reportlab", 500

    dados = _montar_relatorio(empresa_id)
    estilos = getSampleStyleSheet()
    arquivo = BytesIO()
    doc = SimpleDocTemplate(arquivo, pagesize=landscape(A4), topMargin=30, bottomMargin=30)

    elementos = [
        Paragraph(f"Relatório Financeiro — {nome_empresa}", estilos["Heading2"]),
        Paragraph(f"Período: {dados['periodo_texto']} · Atualizado em {dados['atualizado_em']}", estilos["Normal"]),
        Spacer(1, 16),
    ]

    tabela_dados = [["Descrição"] + dados["semanas"] + ["Total"]]
    for linha in dados["linhas"]:
        if linha["tipo"] == "secao":
            tabela_dados.append([linha["rotulo"].upper()] + [""] * (len(dados["semanas"]) + 1))
            continue
        formatador = brls if linha["tipo"] == "resultado" else brl
        valores_fmt = [formatador(v) for v in linha["valores"]]
        tabela_dados.append([linha["rotulo"]] + valores_fmt + [formatador(linha["total"])])

    tabela = Table(tabela_dados, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    elementos.append(tabela)
    doc.build(elementos)
    arquivo.seek(0)
    return send_file(
        arquivo,
        as_attachment=True,
        download_name=f"relatorio-{dados['mes']}.pdf",
        mimetype="application/pdf",
    )

@app.route("/relatorios/exportar/<formato>")
def exportar_relatorio(formato):
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    usr = session.get("usuario") or {}
    nome_empresa = usr.get("nome") or PERFIL.get("nome", "Empresa MEI")

    if formato == "excel":
        return gerar_excel(empresa_id, nome_empresa)
    if formato == "pdf":
        return gerar_pdf(empresa_id, nome_empresa)
    abort(404)

# ----------------------------------------------------------------
# Perfil, Configurações (Isoladas por Empresa) e Geral
# ----------------------------------------------------------------

app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
PASTA_UPLOADS = os.path.join(app.root_path, "static", "uploads")
ARQ_DADOS = os.path.join(app.root_path, "dados_usuario.json")
EXT_FOTO = {"png", "jpg", "jpeg", "webp", "gif"}

def _ler_dados():
    try:
        with open(ARQ_DADOS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def _gravar_perfil():
    dados = _ler_dados()
    dados["perfil"] = PERFIL
    with open(ARQ_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

_salvo = _ler_dados()

PERFIL = {"nome": "Usuário MEI", "cargo": "Administrador", "foto": None, "versao": 0, **_salvo.get("perfil", {})}

CONFIG_PADRAO = {
    "telefone": "",
    "periodo": "Mês atual",
    "antecedencia": "5",
    "alerta_vencimento": True,
    "resumo_semanal": False,
    "alerta_estoque": True,
}
OPCOES_CONFIG = {
    "periodo": ["Mês atual", "Últimos 30 dias", "Trimestre atual", "Ano atual"],
    "antecedencia": ["1", "3", "5", "7", "15"],
}

def _prefs_empresa(empresa_id):
    dados = _ler_dados()
    por_empresa = dados.get("empresas", {})
    return {**CONFIG_PADRAO, **por_empresa.get(str(empresa_id), {})}

def _salvar_prefs_empresa(empresa_id, novas_prefs):
    dados = _ler_dados()
    por_empresa = dados.get("empresas", {})
    por_empresa[str(empresa_id)] = novas_prefs
    dados["empresas"] = por_empresa
    with open(ARQ_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

@app.context_processor
def injetar_usuario():
    usr = session.get("usuario")
    nome = usr["nome"] if usr and usr.get("nome") else PERFIL["nome"]
    cargo = "Empresário MEI" if usr else PERFIL["cargo"]
    iniciais = "".join(p[0] for p in nome.split()[:2]).upper() or "?"
    agora = datetime.now()
    atualizado_em = f"{agora.day:02d} {MESES_ABREV[agora.month - 1]} {agora.year}, {agora.strftime('%H:%M')}"
    return {
        "usuario": {**PERFIL, "nome": nome, "cargo": cargo, "iniciais": iniciais},
        "atualizado_em": atualizado_em,
    }

def _apagar_foto():
    if PERFIL["foto"]:
        try:
            os.remove(os.path.join(app.root_path, "static", PERFIL["foto"]))
        except OSError:
            pass
        PERFIL["foto"] = None
        PERFIL["versao"] += 1

@app.route("/perfil", methods=["POST"])
def salvar_perfil():
    nome = request.form.get("nome", "").strip()
    if nome:
        PERFIL["nome"] = nome[:60]
        if "usuario" in session:
            session["usuario"]["nome"] = nome[:60]
            session.modified = True

    if request.form.get("remover_foto"):
        _apagar_foto()

    arquivo = request.files.get("foto")
    if arquivo and arquivo.filename:
        ext = arquivo.filename.rsplit(".", 1)[-1].lower()
        if ext in EXT_FOTO:
            _apagar_foto()
            os.makedirs(PASTA_UPLOADS, exist_ok=True)
            arquivo.save(os.path.join(PASTA_UPLOADS, f"avatar.{ext}"))
            PERFIL["foto"] = f"uploads/avatar.{ext}"
            PERFIL["versao"] += 1

    _gravar_perfil()
    destino = urlparse(request.referrer or "").path or url_for("visao_geral")
    return redirect(f"{destino}?aviso=salvo")

@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    empresa_id = _empresa_id()
    if not empresa_id:
        return redirect(url_for("login"))

    prefs = _prefs_empresa(empresa_id)

    if request.method == "POST":
        f = request.form
        empresa_nome = f.get("empresa", "").strip()
        cnpj = f.get("cnpj", "").strip()
        email = f.get("email", "").strip()

        try:
            resp = requests.put(
                f"{API_URL}/empresa/{empresa_id}",
                json={"nome": empresa_nome, "cnpj": cnpj, "email": email},
                timeout=5,
            )
            if resp.status_code == 200 and "usuario" in session:
                session["usuario"]["nome"] = empresa_nome
                session["usuario"]["cpf_cnpj"] = cnpj
                session["usuario"]["email"] = email
                session.modified = True
        except Exception as e:
            print(f"Erro ao atualizar empresa na API: {e}")

        prefs["telefone"] = f.get("telefone", "").strip()
        if f.get("periodo") in OPCOES_CONFIG["periodo"]:
            prefs["periodo"] = f["periodo"]
        if f.get("antecedencia") in OPCOES_CONFIG["antecedencia"]:
            prefs["antecedencia"] = f["antecedencia"]
        for campo in ("alerta_vencimento", "resumo_semanal", "alerta_estoque"):
            prefs[campo] = campo in f

        _salvar_prefs_empresa(empresa_id, prefs)
        return redirect(url_for("configuracoes", aviso="salvo"))

    usr = session.get("usuario") or {}
    dados_empresa = {
        "nome": usr.get("nome", ""),
        "cnpj": usr.get("cpf_cnpj", ""),
        "email": usr.get("email", ""),
    }

    try:
        resp = requests.get(f"{API_URL}/empresa/{empresa_id}", timeout=3)
        if resp.status_code == 200:
            dados_empresa = resp.json()
    except Exception as e:
        print(f"API Node offline (empresa): {e}")

    cfg = {
        "empresa": dados_empresa.get("nome", ""),
        "cnpj": dados_empresa.get("cnpj", ""),
        "email": dados_empresa.get("email", ""),
        **prefs,
    }
    return render_template("configuracoes.html", cfg=cfg, op=OPCOES_CONFIG)

@app.route("/configuracoes/cancelar")
def cancelar_configuracoes():
    return redirect(url_for("configuracoes", aviso="cancelado"))

@app.route("/ajuda")
def ajuda():
    return render_template("ajuda.html")

# ----------------------------------------------------------------
# Execução do Servidor
# ----------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)