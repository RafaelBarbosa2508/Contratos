import re
import streamlit as st

# ----- FUNÇÕES ABAIXO -----#

def reiniciar_aplicativo():
    # 1. Limpa todas as variáveis salvas na sessão
    for key in list(st.session_state.keys()):
        if key != "uploader_key": # Mantemos a chave do uploader para incrementá-la
            del st.session_state[key]
    
    # 2. Incrementa a chave do uploader para forçar o componente a limpar os arquivos
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    st.session_state.uploader_key += 1
    
    # 3. Força o Streamlit a recomeçar do topo
    st.rerun()

def limpar_placa(placa):
    """Remove espaços, traços e garante que fique maiúsculo"""
    return re.sub(r'[\s-]', '', placa).upper()

def formatar_moeda(valor):
    """Formata número (float) para o padrão de moeda brasileiro (ex: 1.234,56)"""
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"
    
def formatar_volume(valor):
    """Formata para 2 casas decimais (ex: 60.451,00)"""
    try:
        # Garante que o valor seja tratado como float para a formatação
        v_float = float(str(valor).replace('.', '').replace(',', '.')) if isinstance(valor, str) else float(valor)
        return f"{v_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor)

def formatar_frete(valor):
    """Retorna o valor exatamente como digitado ou com todas as casas do float"""
    try:
        # Se for string e já tiver vírgula (entrada do usuário), retorna ela mesma
        if isinstance(valor, str) and "," in valor:
            return valor
        # Se for um número, converte para string trocando o ponto pela vírgula
        return str(valor).replace(".", ",")
    except Exception:
        return str(valor)
    
def limpar_valor_formatado(valor_texto: str):
    """Transforma '1.234,56' em 1234.56 para o Python calcular"""
    try:
        # Remove os pontos de milhar e troca a vírgula pelo ponto decimal
        limpo = str(valor_texto).replace(".", "").replace(",", ".")
        return float(limpo)
    except:
        return 0.0
    
def formatar_cpf(cpf):
    # Remove qualquer coisa que não seja número
    numeros = re.sub(r'\D', '', cpf)
    if len(numeros) == 11:
        return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
    return numeros

def formatar_cidade_uf_pdf(texto):
    if not texto or len(texto) < 3: return texto
    texto = texto.strip().upper()
    # Pega tudo exceto os últimos 2 caracteres / Pega os últimos 2 caracteres
    return f"{texto[:-2].strip()} / {texto[-2:]}"

def formatar_chave(chave):
    """Formata a chave de acesso de 44 dígitos em blocos de 4"""
    chave_limpa = re.sub(r'\s', '', chave)
    if len(chave_limpa) == 44:
        return " ".join([chave_limpa[i:i+4] for i in range(0, 44, 4)])
    return chave_limpa

def formatar_cnpj(cnpj):
    if not cnpj: return ""
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    if len(cnpj_limpo) == 14:
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
    elif len(cnpj_limpo) == 11:
        return f"{cnpj_limpo[:3]}.{cnpj_limpo[3:6]}.{cnpj_limpo[6:9]}-{cnpj_limpo[9:]}"
    return cnpj_limpo
    
def validar_cpf(cpf):
    """Valida o CPF usando o algoritmo de dígitos verificadores"""
    cpf = re.sub(r'\D', '', str(cpf))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    
    for i in range(9, 11):
        soma = sum(int(cpf[num]) * ((i + 1) - num) for num in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True

REGEX_PLACA = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
REGEX_CHAVE = re.compile(r'(?<!\d)(?:\d\s*){44}(?!\d)')
def placa_valida(placa):
    if not placa: return False
    # Remove espaços e traços antes de validar
    p = re.sub(r'[\s-]', '', placa).upper()
    # Padrão: 3 letras, 1 número, 1 letra ou número, 2 números (Cobre Tradicional e Mercosul)
    padrao = r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$"
    return bool(re.match(padrao, p))

def normalizar_peso_para_ton(valor):
    """Garante que o valor seja float e converte automaticamente KG para Toneladas"""
    try:
        if isinstance(valor, str):
            valor = valor.strip()
            # Se tiver vírgula e ponto (ex: 59.544,00), remove ponto e troca vírgula por ponto
            if ',' in valor and '.' in valor:
                valor = valor.replace('.', '').replace(',', '.')
            # Se tiver só vírgula (ex: 59544,00), troca por ponto
            elif ',' in valor:
                valor = valor.replace(',', '.')
        
        v_float = float(valor)
        
        # REGRA DE CORREÇÃO (KG para TONELADA):
        # Se o valor for maior que 150 (ex: 59544, 45000), temos certeza absoluta que está em QUILOS.
        # Então, dividimos por 1000 para converter automaticamente para TONELADAS.
        if v_float > 150:
            v_float = v_float / 1000.0
            
        return v_float
    except:
        return 0.0

def eh_chave_valida(chave):
    """Valida se a string é uma chave fiscal brasileira real"""
    chave_limpa = re.sub(r'\s', '', chave)
    if len(chave_limpa) != 44: return False
    if chave_limpa == "0" * 44: return False
    try:
        uf = int(chave_limpa[0:2])
        if not (11 <= uf <= 53): return False
    except:
        return False
    return True

