import requests
import streamlit as st
import re, os
import pdfplumber
from jinja2 import Environment, FileSystemLoader
from utils import formatar_chave, formatar_volume, formatar_frete, formatar_moeda
from extratores import extrair_dados_xml,extrair_endereco_cnpj_card

# ----- FUNÇÕES ABAIXO -----#

def processar_documentos_fiscais(arquivos):
    dados = {
        "nfes": [], "ctes": [], "mdfes": [], 
        "pdf_chaves_nfe": [], "pdf_chaves_cte": [],
        "xml_chaves_nfe": [], "xml_chaves_cte": [],
        "chaves_nfe": [], "chaves_cte": [],
        "volume_carregado": 0.0, "valor_pedagio": 0.0, "rendimento_bruto": 0.0, "valor_liquido": 0.0,
        "transp_nome": "", "transp_cnpj": "", "transp_end": "",
        "motorista": "", "cpf_motorista": "", "placa_cavalo": "", "placa_carreta1": "", "placa_carreta2": "",
        "remetente_nome": "", "remetente_cnpj": "", "remetente_end": "", "remetente_cidade": "",
        "destinatario_nome": "", "destinatario_cnpj": "", "destinatario_end": "", "destinatario_cidade": "",
        "recebedor_nome": "", "recebedor_cnpj": "", "recebedor_end": "", "recebedor_cidade": "",
        "expedidor_nome": "", "expedidor_cnpj": "", "expedidor_end": "", "expedidor_cidade": "",
        "mercadoria": ""
    }

    for arquivo in arquivos:
        arquivo.seek(0)
        nome_arquivo = arquivo.name.lower() # Pega o nome do arquivo anexado
        if nome_arquivo.endswith(".xml"):
            try:
                texto_xml = arquivo.read().decode('utf-8', errors='ignore')
                extrair_dados_xml(texto_xml, dados)
            except Exception as e:
                st.error(f"Erro ao ler o XML {nome_arquivo}: {e}")
                
        # Se for PDF, o sistema apenas ignora ou você pode avisar:
        elif nome_arquivo.endswith(".pdf"):
            try:
                with pdfplumber.open(arquivo) as pdf:
                    # Extraímos o texto de todas as páginas
                    texto_pdf = "".join([p.extract_text() or "" for p in pdf.pages])
                    
                    # --- A MÁGICA PARA O CARTÃO CNPJ ---
                    # Se o PDF tiver os termos chaves da Receita Federal:
                    if "COMPROVANTE DE INSCRIÇÃO" in texto_pdf.upper():
                        # Usamos a função de extração que já existe no seu servicos.py
                        endereco = extrair_endereco_cnpj_card(texto_pdf)
                        if endereco:
                            dados["transp_end"] = endereco
                            # Tenta pegar a Razão Social também
                            match_rs = re.search(r"NOME EMPRESARIAL\s+(.*)", texto_pdf.upper())
                            if match_rs:
                                dados["transp_nome"] = match_rs.group(1).strip()
                        st.success(f"✅ Dados do Cartão CNPJ extraídos de: {nome_arquivo}")
            except Exception as e:
                st.error(f"Erro no PDF {nome_arquivo}: {e}")
                
    chaves_nfe_definitivas = list(set(dados["xml_chaves_nfe"] + dados["pdf_chaves_nfe"]))
    chaves_cte_definitivas = list(set(dados["xml_chaves_cte"] + dados["pdf_chaves_cte"]))

    if dados["transp_cnpj"] and not dados["transp_end"]:
        # Tenta buscar na API automaticamente
        resultado_api = buscar_endereco_por_cnpj(dados["transp_cnpj"])
        if resultado_api:
            dados["transp_nome"] = resultado_api["razao_social"]
            dados["transp_end"] = resultado_api["endereco"]

    dados["nfes"] = list(set(dados["nfes"]))
    dados["ctes"] = list(set(dados["ctes"]))
    dados["mdfes"] = list(set(dados["mdfes"]))
    dados["chaves_nfe"] = list(set(chaves_nfe_definitivas))
    dados["chaves_cte"] = list(set(chaves_cte_definitivas))
    return dados

def gerar_contrato_html(dados):
    # (Mantenha as preparações de str_nfes, str_ctes, etc, que você já tem)
    str_nfes = " ".join(dados["nfes"]) if dados.get("nfes") else ""
    str_ctes = " ".join(dados["ctes"]) if dados.get("ctes") else ""
    str_mdfes = " ".join(dados["mdfes"]) if dados.get("mdfes") else ""
    str_chaves_nfe = " / ".join([formatar_chave(c) for c in dados.get("chaves_nfe", [])])
    str_chaves_cte = " / ".join([formatar_chave(c) for c in dados.get("chaves_cte", [])])

    # --- CORREÇÃO DE FORMATAÇÃO ---
    vol_formatado = formatar_volume(dados.get('volume_carregado', 0))
    # Busca a string do frete que foi salva no main
    frete_bruto = dados.get('frete_unitario', '0,00')
    frete_formatado = formatar_frete(frete_bruto)

    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template('template_contrato_cte.html')
        return template.render(
            dados=dados,
            str_nfes=str_nfes,
            str_ctes=str_ctes,
            str_mdfes=str_mdfes,
            str_chaves_nfe=str_chaves_nfe,
            str_chaves_cte=str_chaves_cte,
            vol_formatado=vol_formatado,
            frete_formatado=frete_formatado,
            formatar_moeda=formatar_moeda
        )
    except Exception as e:
        st.error(f"Erro no layout CT-e: {e}")
        return ""

def gerar_contrato_servico_html(dados):
    str_nfes = " ".join(dados["nfes"]) if dados.get("nfes") else ""
    str_chaves = " / ".join([formatar_chave(c) for c in dados.get("chaves_nfe", [])])
    
    # --- 1. BUSCA DOS VALORES COM AS CHAVES CORRETAS ---
    # --- 1. BUSCA DOS VALORES COM A CHAVE CORRETA ---
    volume_bruto = dados.get('volume_carregado', 0)
    # Mudamos de 'valor_tonelada' para 'frete_unitario' para bater com o que vem da tela
    frete_bruto = dados.get('frete_unitario', '0,00')

    # --- 2. FORMATAÇÃO DO VOLUME (2 CASAS DECIMAIS) ---
    vol_formatado = formatar_volume(volume_bruto) # A função formatar_volume agora cuida das 2 casas

    # --- 3. FORMATAÇÃO DO FRETE (PRECISÃO TOTAL) ---
    frete_formatado = formatar_frete(frete_bruto) # A função formatar_frete mantém o que foi digitado
    # --- ADICIONE ESTA LINHA ABAIXO PARA DEFINIR A VARIÁVEL ---
    nfs_numero = dados.get("nfs_manual", "")

    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    try:
        template = env.get_template('template_contrato_nfs.html')
        return template.render(
            dados=dados,
            str_nfes=str_nfes,
            str_chaves_nfe=str_chaves,
            str_nfs=nfs_numero,
            vol_formatado=vol_formatado,       # Variável de texto pronta para uso
            frete_formatado=frete_formatado,   # Variável de texto pronta para uso
            formatar_moeda=formatar_moeda
        )
    except Exception as e:
        st.error(f"Erro ao carregar template_contrato_nfs.html: {e}")
        return ""

@st.cache_data(ttl=86400) # ttl = guarda a memória por 1 dia (86400 segundos)
def buscar_endereco_por_cnpj(cnpj):
    """Busca a Razão Social e o endereço oficial da Receita Federal usando a BrasilAPI"""
    if not cnpj: 
        return None
    
    # Limpa o CNPJ mantendo apenas números
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    
    if len(cnpj_limpo) != 14:
        return None
        
    try:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        response = requests.get(url, timeout=10) # Aguarda até 10 segundos
        
        if response.status_code == 200:
            dados_cnpj = response.json()
            
            # Captura a Razão Social
            razao_social = dados_cnpj.get('razao_social', '').upper()
            
            # Monta o endereço: Logradouro, Número - Bairro, Cidade - UF, CEP
            logradouro = dados_cnpj.get('logradouro', '')
            numero = dados_cnpj.get('numero', 'S/N')
            bairro = dados_cnpj.get('bairro', '')
            municipio = dados_cnpj.get('municipio', '')
            uf = dados_cnpj.get('uf', '')
            cep = dados_cnpj.get('cep', '')
            
            endereco_completo = f"{logradouro}, {numero} - {bairro}. {municipio} - {uf}. CEP: {cep}".upper()
            
            # Retorna os dois dados em um dicionário
            return {
                "razao_social": razao_social,
                "endereco": endereco_completo
            }
        else:
            return None
            
    except requests.exceptions.RequestException:
        return None
    
def consulta_manual_cnpj():
    cnpj = st.session_state.get("transp_cnpj", "")
    # Só dispara se tiver os 14 números
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    if len(cnpj_limpo) == 14:
        with st.spinner("Consultando CNPJ na Receita..."):
            resultado = buscar_endereco_por_cnpj(cnpj_limpo)
            if resultado:
                st.session_state.transp_nome = resultado["razao_social"]
                st.session_state.transp_end = resultado["endereco"]
            else:
                st.error("CNPJ não encontrado ou erro na consulta.")

