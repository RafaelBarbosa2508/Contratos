import re
import streamlit as st

# Compilamos os padrões de Regex uma única vez no topo para ganhar performance
REGEX_NUMEROS = re.compile(r'\D')
REGEX_LIMPAR_VALOR = re.compile(r'[^\d,.-]')
REGEX_PLACA_PADRAO = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
REGEX_LIMPAR_PLACA = re.compile(r'[\s-]')

# ----- FUNÇÕES DE ESTADO ----- #

def reiniciar_aplicativo():
    """Limpa a sessão e reinicia o uploader"""
    for key in list(st.session_state.keys()):
        if key != "uploader_key":
            del st.session_state[key]
    
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
    st.rerun()

# ----- FUNÇÕES DE LIMPEZA E TRATAMENTO ----- #
def limpar_valor(valor):
    """Transforma qualquer entrada (1.234,56 ou R$ 1234.56) em float puro"""
    if not valor: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    
    v = REGEX_LIMPAR_VALOR.sub('', str(valor))
    if ',' in v and '.' in v: 
        v = v.replace('.', '')
    v = v.replace(',', '.')
    
    try: return float(v)
    except: return 0.0

def limpar_placa(placa):
    if not placa: return ""
    # Remove tudo que NÃO for letra ou número
    return re.sub(r'[^A-Z0-9]', '', str(placa).upper())

# ----- FUNÇÕES DE FORMATAÇÃO ----- #

def formatar_moeda(valor):
    """Aproveita a limpar_valor e formata para padrão PT-BR"""
    v = limpar_valor(valor)
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
def formatar_volume(valor):
    """Otimizada: Agora usa a limpar_valor internamente"""
    v = limpar_valor(valor)
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_frete(valor):
    """Retorna o valor para exibição (ex: 125,50)"""
    v = limpar_valor(valor)
    # Se for inteiro, pode retornar sem casas decimais ou manter padrão
    return str(v).replace(".", ",")

def formatar_cnpj(doc):
    """Formata CPF ou CNPJ de forma unificada"""
    if not doc: return ""
    nums = REGEX_NUMEROS.sub('', str(doc))
    if len(nums) == 14:
        return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
    if len(nums) == 11:
        return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    return nums

def formatar_cidade_uf_pdf(texto):
    if not texto or len(texto) < 3: return texto
    texto = texto.strip().upper()
    return f"{texto[:-2].strip()} / {texto[-2:]}"

def formatar_chave(chave):
    """Formata a chave de acesso em blocos de 4"""
    c = REGEX_NUMEROS.sub('', str(chave))
    if len(c) == 44:
        return " ".join([c[i:i+4] for i in range(0, 44, 4)])
    return c

# ----- FUNÇÕES DE VALIDAÇÃO ----- #

def placa_valida(placa):
    p = limpar_placa(placa)
    # REGEX_PLACA_PADRAO: ^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$
    return bool(REGEX_PLACA_PADRAO.match(p))
    
def validar_cpf(cpf):
    c = REGEX_NUMEROS.sub('', str(cpf))
    if len(c) != 11 or c == c[0] * 11: return False
    for i in range(9, 11):
        soma = sum(int(c[num]) * ((i + 1) - num) for num in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(c[i]): return False
    return True

def eh_chave_valida(chave):
    c = REGEX_NUMEROS.sub('', str(chave))
    if len(c) != 44 or c == "0" * 44: return False
    try:
        return 11 <= int(c[0:2]) <= 53
    except: return False

# ----- REGRAS DE NEGÓCIO ----- #

def normalizar_peso_para_ton(valor):
    v = limpar_valor(valor)
    return v / 1000.0 if v > 150 else v

