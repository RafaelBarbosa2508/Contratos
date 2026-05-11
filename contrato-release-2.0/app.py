import streamlit as st
import pdfplumber
import re
import xml.etree.ElementTree as ET
import requests
import base64
from jinja2 import Environment, FileSystemLoader
import os
import time

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
    
def limpar_valor_formatado(valor_texto):
    """Transforma '1.234,56' em 1234.56 para o Python calcular"""
    try:
        # Remove os pontos de milhar e troca a vírgula pelo ponto decimal
        limpo = str(valor_texto).replace(".", "").replace(",", ".")
        return float(limpo)
    except:
        return 0.0
    
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

def extrair_endereco_cnpj_card(texto_pdf):
    """Extrai o endereço seguindo estritamente o layout do Cartão CNPJ"""
    texto = texto_pdf.upper()
    
    # Dicionário para armazenar as partes do endereço
    end = {}
    
    # Regex específicas para cada campo baseado na imagem do cartão
    campos = {
        "logradouro": r"LOGRADOURO\s*\n?\s*(.*)",
        "numero": r"NÚMERO\s*\n?\s*(.*)",
        "complemento": r"COMPLEMENTO\s*\n?\s*(.*)",
        "cep": r"CEP\s*\n?\s*([\d\.\-]+)",
        "bairro": r"BAIRRO/DISTRITO\s*\n?\s*(.*)",
        "municipio": r"MUNICÍPIO\s*\n?\s*(.*)",
        "uf": r"UF\s*\n?\s*([A-Z]{2})"
    }

    for chave, regex in campos.items():
        match = re.search(regex, texto)
        if match:
            # Pega a primeira linha após a etiqueta e remove espaços
            valor = match.group(1).strip().split('\n')[0].strip()
            # Ignora se o valor capturado for outra etiqueta (campo vazio)
            if any(etiqueta in valor for etiqueta in ["NÚMERO", "COMPLEMENTO", "CEP", "BAIRRO", "UF"]):
                end[chave] = ""
            else:
                end[chave] = valor
        else:
            end[chave] = ""

    # Montagem do endereço formatado
    partes = []
    if end["logradouro"]: partes.append(end["logradouro"])
    if end["numero"]: partes.append(f"Nº {end['numero']}")
    if end["complemento"]: partes.append(end["complemento"])
    if end["bairro"]: partes.append(end["bairro"])
    
    final = ", ".join(partes)
    
    if end["cep"] or end["municipio"]:
        final += f" - CEP: {end['cep']} - {end['municipio']}/{end['uf']}"
        
    return final.strip(", - ")

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

def extrair_dados_pdf(texto_pdf, dados):
    """Extrai informações do PDF com precisão para MDF-e e Volume"""
    texto_upper = texto_pdf.upper()
    # texto_linear mantém quebras de linha em alguns casos para ajudar a Regex 
    # de "Número" a identificar o que está logo abaixo
    texto_linear = texto_upper.replace('\n', ' ')

    if "COMPROVANTE DE INSCRIÇÃO" in texto_upper and "SITUAÇÃO CADASTRAL" in texto_upper:
        # Se for um cartão CNPJ, usa a nova lógica de endereço
        endereco_extraido = extrair_endereco_cnpj_card(texto_pdf)
        if endereco_extraido:
            dados["transp_end"] = endereco_extraido

    # 1. Subcontratação
    sub_match = re.search(r"TRANSPORTE SUBCONTRATADO COM\s+(.*?)\s+CNPJ:\s*([\d\.\-\/]+)", texto_linear)
    if sub_match:
        dados["transp_nome"] = sub_match.group(1).strip()
        dados["transp_cnpj"] = formatar_cnpj(sub_match.group(2).strip())

    # 2. Chaves de Acesso
    chaves_encontradas = re.findall(r'(?<!\d)(?:\d\s*){44}(?!\d)', texto_linear)
    chaves_validas = [re.sub(r'\s', '', c) for c in chaves_encontradas if eh_chave_valida(c)]

    # 3. Tratamento por tipo de documento
    # Procure este bloco dentro do 'if "DANFE" in texto_upper:' e substitua:
    if "DANFE" in texto_upper:
        # Busca o número que aparece no topo do DANFE (campo Nº)
        nfe = re.search(r"N[oO°º\.]*\s*[:.-]?\s*0*(\d{1,9})", texto_upper)
        if nfe:
            num_exato = str(int(nfe.group(1)))
            # Se já houver nota do XML, não faz nada. Se não, adiciona.
            if not dados["nfes"]:
                dados["nfes"].append(num_exato)
        
        # AQUI ESTAVA O ERRO: Removida a linha que extraía números da chave de acesso!
        dados["pdf_chaves_nfe"].extend(chaves_validas)
        
    elif "DACTE" in texto_upper or "CONHECIMENTO DE TRANSPORTE" in texto_upper:
        cte = re.search(r"N[oO°º\.]*\s*[:.-]?\s*0*(\d{1,9})", texto_upper)
        if cte: dados["ctes"].append(str(int(cte.group(1))))
        for c in chaves_validas:
            if c[20:22] == '57': dados["ctes"].append(str(int(c[25:34])))
        dados["pdf_chaves_cte"].extend(chaves_validas)

    elif "MANIFESTO ELETRÔNICO" in texto_upper or "DAMDFE" in texto_upper or "MDF-E" in texto_upper:
        # AJUSTE MDF-E: Foca na palavra "Número" e pega o valor logo abaixo/frente
        # Usamos re.search para pegar apenas a primeira ocorrência (o número principal)
        mdfe = re.search(r"N[ÚU]MERO\s*[:.-]?\s*\n?\s*0*(\d{1,9})", texto_upper)
        if mdfe: 
            dados["mdf_e"] = mdfe.group(1) # Grava o número exato
            dados["mdfes"].append(str(int(mdfe.group(1))))
        
        # Backup por chave de acesso caso o regex de texto falhe
        for c in chaves_validas:
            if c[20:22] == '58': 
                num_chave = str(int(c[25:34]))
                if num_chave not in dados["mdfes"]: dados["mdfes"].append(num_chave)
        
        # Extração de Placas
        texto_placas = texto_upper.split("PLACA", 1)[-1] if "PLACA" in texto_upper else texto_upper
        placas_brutas = re.findall(r"[A-Z]{3}\s*[-]?\s*[0-9]\s*[A-Z0-9]\s*[0-9]{2}", texto_placas)
        placas_limpas = [limpar_placa(p) for p in placas_brutas if not limpar_placa(p).startswith("CEP")]
        placas_unicas = list(dict.fromkeys(placas_limpas))
        if len(placas_unicas) >= 1 and not dados["placa_cavalo"]: dados["placa_cavalo"] = placas_unicas[0]
        if len(placas_unicas) >= 2 and not dados["placa_carreta1"]: dados["placa_carreta1"] = placas_unicas[1]
        if len(placas_unicas) >= 3 and not dados["placa_carreta2"]: dados["placa_carreta2"] = placas_unicas[2]

        # Extração Motorista
        motorista_match = re.search(r"(\d{11})\s+([A-ZÀ-Ÿ\s]+)", texto_upper)
        if motorista_match:
            cpf_encontrado = motorista_match.group(1)
            nome_encontrado = motorista_match.group(2).strip().split('\n')[0] 
            if not dados["cpf_motorista"]: dados["cpf_motorista"] = cpf_encontrado
            if not dados["motorista"] and len(nome_encontrado) > 3: dados["motorista"] = nome_encontrado

    # 5. Peso/Volume (Aplica a normalização que mantém valor cheio ex: 59544)
    peso_matches = re.findall(r"(?:PESO TOTAL|PESO BRUTO|VOLUME CARREGADO|QTD|QUANTIDADE|LITRAGEM).*?([\d]{2,}(?:\.\d{3})*(?:,\d{2,4})?|[\d]{2,}(?:\.\d{2,4}))", texto_linear)
    for peso_str in peso_matches:
        try:
            # Se o volume já foi preenchido pelo XML (qCom), o PDF não sobrescreve
            if dados.get("volume_carregado", 0.0) == 0:
                p_limpo = peso_str.replace('.', '').replace(',', '.') if ',' in peso_str else peso_str
                # Usa a função que você inseriu no topo do código
                peso_float = normalizar_peso_para_ton(p_limpo) 
                dados["volume_carregado"] = peso_float
        except:
            pass

def extrair_dados_xml(texto_xml, dados):
    """Extrai informações direto do XML com precisão para MDF-e e placas específicas"""
    texto_xml_lower = texto_xml.lower()

    def buscar_bloco(tag_pai, xml_texto):
        # Busca <tag>, <nfe:tag>, <cte:tag>, etc.
        pattern = r"<(?:\w+:)?" + tag_pai + r"[^>]*>(.*?)</(?:\w+:)?" + tag_pai + r">"
        match = re.search(pattern, xml_texto, re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else ""

    def buscar_campo(tag, bloco):
        pattern = r"<(?:\w+:)?" + tag + r"[^>]*>(.*?)</(?:\w+:)?" + tag + r">"
        match = re.search(pattern, bloco, re.IGNORECASE)
        return match.group(1) if match else ""
    
    # --- 1. IDENTIFICAÇÃO DA CHAVE E NÚMERO (NF-e) ---
    if "<infnfe" in texto_xml_lower:
        id_match = re.search(r'id=["\'](?:nfe)?(\d{44})["\']', texto_xml_lower)
        if id_match:
            chave_nfe = id_match.group(1)
            if eh_chave_valida(chave_nfe):
                if chave_nfe not in dados["xml_chaves_nfe"]:
                    dados["xml_chaves_nfe"].append(chave_nfe)
                num_nfe = str(int(chave_nfe[25:34]))
                if num_nfe not in dados["nfes"]:
                    dados["nfes"].append(num_nfe)

    # --- 2. MERCADORIA E VOLUME (NF-e) ---
    if "<infnfe" in texto_xml_lower:
        # Mercadoria (xProd)
        produtos = re.findall(r"<(?:\w+:)?xProd[^>]*>(.*?)</(?:\w+:)?xProd>", texto_xml, re.IGNORECASE)
        if produtos and not dados.get("mercadoria"):
            dados["mercadoria"] = produtos[0].upper()

        # Volume (Soma qCom)
        qcom_matches = re.findall(r"<(?:\w+:)?qCom[^>]*>([\d.]+)</(?:\w+:)?qCom>", texto_xml, re.IGNORECASE)
        for val in qcom_matches:
            try: dados["volume_carregado"] += float(val)
            except: pass

    # === NOVO BLOCO: MERCADORIA (CT-e) ===
    if "<infcte" in texto_xml_lower:
        # No CT-e o produto fica na tag <proPred> (Produto Predominante)
        produto_cte = re.search(r"<(?:\w+:)?proPred[^>]*>(.*?)</(?:\w+:)?proPred>", texto_xml, re.IGNORECASE)
        if produto_cte and not dados.get("mercadoria"):
            dados["mercadoria"] = produto_cte.group(1).upper()

    # --- EXTRAÇÃO DO EMITENTE (REMETENTE NA NF-e) ---
    if "<infnfe" in texto_xml_lower:
        # Localiza o bloco <emit>
        emit_match = re.search(r"<rem>(.*?)</rem>", texto_xml, re.IGNORECASE | re.DOTALL)
        if emit_match:
            bloco_emit = emit_match.group(1)
            
            # Captura Nome e CNPJ
            nome_emit = re.search(r"<xNome>(.*?)</xNome>", bloco_emit, re.IGNORECASE)
            cnpj_emit = re.search(r"<CNPJ>(.*?)</CNPJ>", bloco_emit, re.IGNORECASE)
            
            if nome_emit and not dados.get("remetente_nome"):
                dados["remetente_nome"] = nome_emit.group(1).upper()
            
            if cnpj_emit and not dados.get("remetente_cnpj"):
                dados["remetente_cnpj"] = formatar_cnpj(cnpj_emit.group(1))
            
            # Localiza o bloco de endereço <enderEmit>
            ender_match = re.search(r"<enderReme>(.*?)</enderReme>", bloco_emit, re.IGNORECASE | re.DOTALL)
            if ender_match:
                bloco_ender = ender_match.group(1)
                lgr = re.search(r"<xLgr>(.*?)</xLgr>", bloco_ender, re.IGNORECASE)
                nro = re.search(r"<nro>(.*?)</nro>", bloco_ender, re.IGNORECASE)
                cpl = re.search(r"<xCpl>(.*?)</xCpl>", bloco_ender, re.IGNORECASE)
                bairro = re.search(r"<xBairro>(.*?)</xBairro>", bloco_ender, re.IGNORECASE)
                mun = re.search(r"<xMun>(.*?)</xMun>", bloco_ender, re.IGNORECASE)
                uf = re.search(r"<UF>(.*?)</UF>", bloco_ender, re.IGNORECASE)
                
                # Montagem do endereço estruturado
                partes = []
                if lgr: partes.append(lgr.group(1))
                if nro: partes.append(nro.group(1))
                if cpl: partes.append(cpl.group(1))
                if bairro: partes.append(bairro.group(1))
                
                # Extrai a Cidade e UF
                cidade_uf = ""
                if mun and uf:
                    cidade_uf = f"{mun.group(1)} / {uf.group(1)}"
                elif mun:
                    cidade_uf = mun.group(1)
                
                # CORREÇÃO: Salva a cidade diretamente na variável 'origem' que o HTML lê
                if cidade_uf and not dados.get("origem"):
                    dados["origem"] = cidade_uf.upper()
                
                # Salva o endereço isolado (Rua, Número, Complemento, Bairro)
                if not dados.get("remetente_end"):
                    dados["remetente_end"] = " - ".join(partes).upper()

    # 2. DESTINATÁRIO (<dest>)
    dest_bloco = buscar_bloco("dest", texto_xml)
    if dest_bloco:
        dados["destinatario_nome"] = buscar_campo("xNome", dest_bloco).upper()
        cnpj = buscar_campo("CNPJ", dest_bloco) or buscar_campo("CPF", dest_bloco)
        dados["destinatario_cnpj"] = formatar_cnpj(cnpj)
        dados["destinatario_end"] = f"{buscar_campo('xLgr', dest_bloco)}, {buscar_campo('nro', dest_bloco)} - {buscar_campo('xBairro', dest_bloco)}".upper()
        cidade = buscar_campo("xMun", dest_bloco)
        uf = buscar_campo("UF", dest_bloco)
        dados["destino"] = f"{cidade} / {uf}".upper()

    # 3. RECEBEDOR (<receb>)
    receb_bloco = buscar_bloco("receb", texto_xml)
    if receb_bloco:
        cnpj_receb_bruto = buscar_campo("CNPJ", receb_bloco) or buscar_campo("CPF", receb_bloco)
        cnpj_receb_formatado = formatar_cnpj(cnpj_receb_bruto)
        if cnpj_receb_formatado != dados.get("destinatario_cnpj"):
            dados["recebedor_nome"] = buscar_campo("xNome", receb_bloco).upper()
            dados["recebedor_cnpj"] = cnpj_receb_formatado
            dados["recebedor_end"] = f"{buscar_campo('xLgr', receb_bloco)}, {buscar_campo('nro', receb_bloco)} - {buscar_campo('xBairro', receb_bloco)}".upper()
            cidade = buscar_campo("xMun", receb_bloco)
            uf = buscar_campo("UF", receb_bloco)
            dados["recebedor_cidade"] = f"{cidade} / {uf}".upper()
        else:
            dados["recebedor_nome"] = ""
            dados["recebedor_cnpj"] = ""
            dados["recebedor_end"] = ""
            dados["recebedor_cidade"] = ""

    # --- EXTRAÇÃO DO EXPEDIDOR (LOCAL DE RETIRADA NA NF-e) ---
    if "<infnfe" in texto_xml_lower:
        # Localiza o bloco <retirada> conforme o layout da NF-e
        retirada_match = re.search(r"<retirada>(.*?)</retirada>", texto_xml, re.IGNORECASE | re.DOTALL)
        if retirada_match:
            bloco_ret = retirada_match.group(1)
            
            # Captura Nome e CNPJ/CPF do local de retirada
            nome_ret = re.search(r"<xNome>(.*?)</xNome>", bloco_ret, re.IGNORECASE)
            cnpj_ret = re.search(r"<CNPJ>(.*?)</CNPJ>", bloco_ret, re.IGNORECASE) or \
                       re.search(r"<CPF>(.*?)</CPF>", bloco_ret, re.IGNORECASE)
            
            if nome_ret and not dados.get("expedidor_nome"):
                dados["expedidor_nome"] = nome_ret.group(1).upper()
            
            if cnpj_ret and not dados.get("expedidor_cnpj"):
                dados["expedidor_cnpj"] = formatar_cnpj(cnpj_ret.group(1))
            
            # Captura os campos do endereço de retirada
            lgr = re.search(r"<xLgr>(.*?)</xLgr>", bloco_ret, re.IGNORECASE)
            nro = re.search(r"<nro>(.*?)</nro>", bloco_ret, re.IGNORECASE)
            cpl = re.search(r"<xCpl>(.*?)</xCpl>", bloco_ret, re.IGNORECASE)
            bairro = re.search(r"<xBairro>(.*?)</xBairro>", bloco_ret, re.IGNORECASE)
            mun = re.search(r"<xMun>(.*?)</xMun>", bloco_ret, re.IGNORECASE)
            uf = re.search(r"<UF>(.*?)</UF>", bloco_ret, re.IGNORECASE)
            
            # Montagem do endereço (Logradouro, Número - Bairro)
            partes_end = []
            if lgr: partes_end.append(lgr.group(1))
            if nro: partes_end.append(nro.group(1))
            if cpl: partes_end.append(cpl.group(1))
            if bairro: partes_end.append(bairro.group(1))
            
            if partes_end and not dados.get("expedidor_end"):
                dados["expedidor_end"] = " - ".join(partes_end).upper()
                
            # Montagem da Cidade / UF
            if mun and uf and not dados.get("expedidor_cidade"):
                dados["expedidor_cidade"] = f"{mun.group(1)} / {uf.group(1)}".upper()

    # --- 6. MOTORISTA E PLACAS (COM VALIDAÇÃO MATEMÁTICA DE CPF) ---
    bloco_cpl = buscar_bloco("infCpl", texto_xml)
    if bloco_cpl:
        texto_cpl = bloco_cpl.upper()
        
        # A. BUSCA DO NOME (Mesma lógica anterior)
        pos_ini = -1
        for rotulo in ["MOTORISTA", "CONDUTOR", "MOT:", "COND:", "NOME:"]:
            found = texto_cpl.find(rotulo)
            if found != -1:
                pos_ini = found
                break
        
        texto_focado = texto_cpl[pos_ini:] if pos_ini > -1 else texto_cpl

        if not dados.get("motorista"):
            nome_m = re.search(r'(?:MOTORISTA|CONDUTOR|NOME|MOT|COND)[\s.:-]*([A-ZÀ-Ÿ\s]{3,})', texto_focado)
            if nome_m:
                limpo = re.split(r'\b(?:CPF|PLACA|RG|CNPJ|VEICULO|CNH|PL|FONE)\b|\d', nome_m.group(1))[0]
                dados["motorista"] = limpo.strip(' ,.-')

        # B. BUSCA DO CPF COM FILTRO MATEMÁTICO
        if not dados.get("cpf_motorista"):
            # Encontra todos os possíveis números de 11 dígitos ou CPFs formatados no texto focado
            candidatos = re.findall(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b', texto_focado)
            
            for cand in candidatos:
                num_limpo = re.sub(r'\D', '', cand)
                # TESTE REAL: Se passar na conta matemática do CPF, nós assumimos que este é o correto
                if validar_cpf(num_limpo):
                    dados["cpf_motorista"] = num_limpo
                    break # Para na primeira vez que achar um CPF válido

        # C. BUSCA DE PLACAS
        placas_encontradas = re.findall(r'([A-Z]{3}[0-9][A-Z0-9][0-9]{2})', texto_cpl)
        if placas_encontradas:
            if not dados.get("placa_cavalo"): dados["placa_cavalo"] = placas_encontradas[0]
            if len(placas_encontradas) >= 2 and not dados.get("placa_carreta1"): dados["placa_carreta1"] = placas_encontradas[1]
            if len(placas_encontradas) >= 3 and not dados.get("placa_carreta2"): dados["placa_carreta2"] = placas_encontradas[2]

    # Subcontratação
    sub_match = re.search(r"transporte subcontratado com\s+(.*?)\s+cnpj:\s*([\d\.\-\/]+)", texto_xml_lower)
    if sub_match:
        dados["transp_nome"] = sub_match.group(1).strip().upper()
        dados["transp_cnpj"] = formatar_cnpj(sub_match.group(2).strip())

    # --- 2. SEÇÃO DO CT-e (COLETA DE NF-es VINCULADAS) ---
    if "<infcte" in texto_xml_lower:
        # Pega o número do próprio CT-e
        cte = re.search(r"<nCT>(\d+)</nCT>", texto_xml, re.IGNORECASE)
        if cte: dados["ctes"].append(str(int(cte.group(1))))
        
        # COLETA DE NF-es DENTRO DO CT-e (<infDoc> -> <infNFe> -> <chave>)
        # Procuramos todas as chaves de nota fiscal listadas neste CT-e
        chaves_nfe_no_cte = re.findall(r"<chave>(\d{44})</chave>", texto_xml, re.IGNORECASE)
        
        for chave in chaves_nfe_no_cte:
            if eh_chave_valida(chave):
                # Adiciona a chave na lista se não for duplicada
                if chave not in dados["xml_chaves_nfe"]:
                    dados["xml_chaves_nfe"].append(chave)
                
                # Extrai o número da nota (posição 26 a 34 da chave)
                num_nfe = str(int(chave[25:34]))
                if num_nfe not in dados["nfes"]:
                    dados["nfes"].append(num_nfe)

        # Guarda também a chave do próprio CT-e para o histórico
        chaves_do_proprio_cte = re.findall(r'id=["\']cte(\d{44})["\']', texto_xml_lower)
        for c in chaves_do_proprio_cte:
            if eh_chave_valida(c) and c not in dados["xml_chaves_cte"]:
                dados["xml_chaves_cte"].append(c)
        # --- NOVA LÓGICA: EXTRAÇÃO DO REMETENTE NO CT-e ---
        rem_match = re.search(r"<rem>(.*?)</rem>", texto_xml, re.IGNORECASE | re.DOTALL)
        if rem_match:
            bloco_rem = rem_match.group(1)
            
            # Razão Social e CNPJ do Remetente
            nome_rem = re.search(r"<xNome>(.*?)</xNome>", bloco_rem, re.IGNORECASE)
            cnpj_rem = re.search(r"<CNPJ>(.*?)</CNPJ>", bloco_rem, re.IGNORECASE) or \
                    re.search(r"<CPF>(.*?)</CPF>", bloco_rem, re.IGNORECASE)
            
            if nome_rem:
                dados["remetente_nome"] = nome_rem.group(1).upper()
            if cnpj_rem:
                dados["remetente_cnpj"] = formatar_cnpj(cnpj_rem.group(1))
                
            # Endereço do Remetente no CT-e
            ender_rem = re.search(r"<enderRem>(.*?)</enderRem>", bloco_rem, re.IGNORECASE | re.DOTALL)
            if ender_rem:
                b = ender_rem.group(1)
                lgr = re.search(r"<xLgr>(.*?)</xLgr>", b, re.IGNORECASE)
                nro = re.search(r"<nro>(.*?)</nro>", b, re.IGNORECASE)
                bairro = re.search(r"<xBairro>(.*?)</xBairro>", b, re.IGNORECASE)
                mun = re.search(r"<xMun>(.*?)</xMun>", b, re.IGNORECASE)
                uf = re.search(r"<UF>(.*?)</UF>", b, re.IGNORECASE)
                
                # Monta o endereço e a cidade (origem)
                partes = []
                if lgr: partes.append(lgr.group(1))
                if nro: partes.append(nro.group(1))
                if bairro: partes.append(bairro.group(1))
                dados["remetente_end"] = ", ".join(partes).upper()
                
                if mun and uf:
                    dados["origem"] = f"{mun.group(1)} / {uf.group(1)}".upper()
        
    # CT-e
    if "<infcte" in texto_xml_lower:
        cte = re.search(r"<nCT>(\d+)</nCT>", texto_xml, re.IGNORECASE)
        if cte: dados["ctes"].append(str(int(cte.group(1))))
        chaves = re.findall(r'id=["\']cte(\d{44})["\']', texto_xml_lower)
        chaves_v = [c for c in chaves if eh_chave_valida(c)]
        dados["xml_chaves_cte"].extend(chaves_v)
        for c in chaves_v:
            if c[20:22] == '57': dados["ctes"].append(str(int(c[25:34])))

    # === BLOCO DO MDF-e (NOVO MÉTODO DE COLETA DE PLACAS) ===
    if "<infmdfe" in texto_xml_lower:
        mdfe = re.search(r"<nMDF>(\d+)</nMDF>", texto_xml, re.IGNORECASE)
        if mdfe: 
            dados["mdf_e"] = mdfe.group(1)
            dados["mdfes"].append(str(int(mdfe.group(1))))
        
        # 1. Coleta do Cavalo (<veicTracao>)
        tracao_bloco = buscar_bloco("veicTracao", texto_xml)
        if tracao_bloco:
            p_cav = buscar_campo("placa", tracao_bloco)
            if p_cav:
                dados["placa_cavalo"] = p_cav.upper()

        # 2. Coleta dos Reboques (<veicReboque>) - Ordem de leitura
        # Buscamos todos os blocos de reboque presentes no XML
        reboques_blocos = re.findall(r"<(?:\w+:)?veicReboque[^>]*>(.*?)</(?:\w+:)?veicReboque>", texto_xml, re.IGNORECASE | re.DOTALL)
        
        placas_reboque = []
        for bloco in reboques_blocos:
            p_reb = buscar_campo("placa", bloco)
            if p_reb:
                placas_reboque.append(p_reb.upper())

        # Distribuição das placas conforme sua regra de negócio
        if len(placas_reboque) >= 1:
            dados["placa_carreta1"] = placas_reboque[0] # Carreta 1
        
        if len(placas_reboque) >= 2:
            dados["placa_carreta2"] = placas_reboque[1] # Carreta 2
            
            # Se houver uma 3ª carreta (que seria a 4ª placa total), concatena na Carreta 2
            if len(placas_reboque) >= 3:
                dados["placa_carreta2"] += f" / {placas_reboque[2]}"

        # Coleta do Condutor
        condutor_match = re.search(r"<condutor>.*?</condutor>", texto_xml, re.DOTALL | re.IGNORECASE)
        if condutor_match:
            condutor_xml = condutor_match.group(0)
            nome = re.search(r"<xNome>(.*?)</xNome>", condutor_xml, re.IGNORECASE)
            cpf = re.search(r"<CPF>(.*?)</CPF>", condutor_xml, re.IGNORECASE)
            if nome and not dados["motorista"]: dados["motorista"] = nome.group(1).upper()
            if cpf and not dados["cpf_motorista"]: dados["cpf_motorista"] = cpf.group(1)
    
    texto_xml_lower = texto_xml.lower()
    
    # 4. BUSCA DE VOLUME ESPECÍFICO (SOMA de todos os blocos cUnid = 03 no CT-e)
    if "<infcte" in texto_xml_lower:
        blocos_infq = re.findall(r'<infq[^>]*>.*?</infq>', texto_xml_lower, re.DOTALL)
        
        for bloco in blocos_infq:
            if '<cunid>03</cunid>' in bloco or '<cunid>3</cunid>' in bloco:
                match = re.search(r'<qcarga>([\d.]+)</qcarga>', bloco)
                if match:
                    # Agora somamos direto no acumulador principal
                    dados["volume_carregado"] += float(match.group(1))

    # 5. EXTRAÇÃO DO VALE PEDÁGIO (MDF-e: <valePed> -> <disp> -> <vValePed>)
    # Esta é agora a ÚNICA fonte de valor para o pedágio no sistema
    if "<infmdfe" in texto_xml_lower:
        vale_ped_bloco = buscar_bloco("valePed", texto_xml)
        if vale_ped_bloco:
            disp_bloco = buscar_bloco("disp", vale_ped_bloco)
            if disp_bloco:
                valor_ped = buscar_campo("vValePed", disp_bloco)
                if valor_ped:
                    try:
                        # O XML sempre usa ponto decimal (ex: 421.41)
                        dados["valor_pedagio"] = float(valor_ped)
                    except:
                        pass

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
        # ---> A MÁGICA ACONTECE AQUI: "Rebobina" o arquivo para o início <---
        arquivo.seek(0)
        nome_arquivo = arquivo.name.lower() # Pega o nome do arquivo anexado
        if nome_arquivo.endswith(".pdf"):
            try:
                with pdfplumber.open(arquivo) as pdf:
                    texto_pdf = "".join([pagina.extract_text() or "" for pagina in pdf.pages])
                    extrair_dados_pdf(texto_pdf, dados)
            except Exception as e:
                # Trocamos o 'print' por 'st.error' para você ver o erro na tela do site se acontecer!
                st.error(f"Erro ao ler o PDF {nome_arquivo}: {e}")
                
        elif nome_arquivo.endswith(".xml"):
            try:
                # Lemos o arquivo da memória do Streamlit e já passamos para a extração
                texto_xml = arquivo.read().decode('utf-8', errors='ignore')
                extrair_dados_xml(texto_xml, dados)
            except Exception as e:
                st.error(f"Erro ao ler o XML {nome_arquivo}: {e}")
                
    chaves_nfe_definitivas = list(set(dados["xml_chaves_nfe"] + dados["pdf_chaves_nfe"]))
    chaves_cte_definitivas = list(set(dados["xml_chaves_cte"] + dados["pdf_chaves_cte"]))

    # 1. Inicializamos a variável como None para evitar o erro de "não definida"
    endereco_encontrado = None 

    # 2. Só tenta buscar se houver um CNPJ e se o endereço ainda estiver vazio
    if dados.get("transp_cnpj") and not dados.get("transp_end"):
        print(f"Buscando endereço oficial na Receita Federal para o CNPJ: {dados['transp_cnpj']}...")
        endereco_encontrado = buscar_endereco_por_cnpj(dados["transp_cnpj"])
        
        # A verificação deve ficar obrigatoriamente dentro deste IF
        if isinstance(endereco_encontrado, dict):
            # Extrai apenas o texto limpo do dicionário
            dados["transp_end"] = endereco_encontrado.get("endereco", "ENDEREÇO NÃO LOCALIZADO")
            
            # Aproveita para atualizar o nome se estiver vazio
            if not dados.get("transp_nome"):
                dados["transp_nome"] = endereco_encontrado.get("razao_social", "").upper()
                
        elif endereco_encontrado:
            # Se já veio como string, salva direto
            dados["transp_end"] = endereco_encontrado
        else:
            dados["transp_end"] = "ENDEREÇO NÃO LOCALIZADO"

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
    
def main():
    st.set_page_config(page_title="Gerador Rodo Amazônia", layout="centered")
    # Substituímos o st.title por um markdown que proíbe a quebra de texto
    st.markdown("<h2 style='white-space: nowrap; text-align: center;'>🚛 Gerador de Contrato - Rodo Amazônia</h2>", unsafe_allow_html=True)

    # --- INICIALIZAÇÃO DAS VALIDAÇÕES (OBRIGATÓRIOS APENAS XML) ---
    xml_cte_ok = False
    xml_mdf_ok = False
    xml_nfe_ok = False

    # --- INICIALIZAÇÃO DO ESTADO DE SESSÃO (Adicione isso aqui) ---
    if "transp_nome" not in st.session_state:
        st.session_state.transp_nome = ""
    if "transp_end" not in st.session_state:
        st.session_state.transp_end = ""
    if "transp_cnpj_last" not in st.session_state:
        st.session_state.transp_cnpj_last = ""
    
    # --- NOVIDADE: Adicionamos o parâmetro 'key' amarrado ao estado de sessão ---
    # 1. Área de Upload de Arquivos
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    arquivos = st.file_uploader(
        "Anexe os arquivos XML para começar", 
        accept_multiple_files=True, 
        type=["pdf", "xml"], 
        key=f"uploader_principal_{st.session_state.uploader_key}" # <--- A CHAVE AGORA É DINÂMICA!
    )
    
    # --- NOVIDADE: Botão para excluir todos os arquivos ---
    if arquivos:
        if st.button("🗑️ Limpar todos os anexos"):
            st.session_state.uploader_key += 1
            st.rerun() 
    # ------------------------------------------------------

    # Inicializamos as variáveis com valores padrão (vazios)
    dados = {}
    peso_kg_sugerido = 0.0
    pedagio_sugerido = 0.0

# 1. Trava amarela: Aguarda o primeiro upload
    if not arquivos:
        st.warning(
            "📥 **Aguardando o upload dos documentos obrigatórios:**\n\n"
            "• Anexe o **XML da NF-e** para emissão de **Contrato de NFS Subcontratado**.\n\n"
            "• Anexe os **XMLs do CT-e e MDF-e** para emissão de **Contrato CT-e Subcontratado**."
        )
        st.stop()

    # 2. Identificação dos documentos carregados
    # 2. Identificação dos documentos carregados
    for arq in arquivos:
        nome_arq = arq.name.lower()
        try:
            if nome_arq.endswith('.xml'):
                conteudo = arq.getvalue().decode('utf-8', errors='ignore').lower()
                # Identifica CT-e
                if "<cteproc" in conteudo or "<cte " in conteudo:
                    xml_cte_ok = True
                
                # Identifica MDF-e
                if "<mdfeproc" in conteudo or "<mdfe " in conteudo:
                    xml_mdf_ok = True

                # Identifica NF-e (NOVO)
                if "<nfeproc" in conteudo or "<nfe " in conteudo:
                    xml_nfe_ok = True
        except Exception as e:
            st.error(f"Erro ao processar {arq.name}: {e}")

    if xml_nfe_ok and (xml_cte_ok or xml_mdf_ok):
        st.error(
            "⚠️ **CONFLITO DE DOCUMENTOS DETECTADO!**\n\n"
            "O sistema identificou a leitura simultânea de **NF-e** junto com **CT-e/MDF-e**.\n\n"
            "Para evitar erros no layout do relatório, você não pode seguir com os dois parâmetros juntos.\n\n"
            "Por favor, limpe os arquivos anexados e envie **APENAS**:\n\n"
            "• O XML da **NF-e** (Para emitir Contrato NFS Subcontratado)\n\n"
            "**OU**\n\n"
            "• Os XMLs do **CT-e e MDF-e** (Para emitir Contrato CT-e Subcontratado)"
        )
        st.stop() # Mata a execução do programa aqui!
    # =========================================================================

    # --- NOVO FLUXO EXCLUSIVO PARA NOTA FISCAL ---
    if xml_nfe_ok and not xml_cte_ok and not xml_mdf_ok:
        st.info("📄 **Modo de Contrato de Serviço Ativado**")
        
        # Processa os dados extraídos da Nota
        dados = processar_documentos_fiscais(arquivos)
        
        # 1. LINHA DE CONFERÊNCIA (NOTAS E XML LADO A LADO)
        col_n, col_x = st.columns([1, 3])
        with col_n:
            st.text_input("NOTAS FISCAIS", value=" ".join(dados["nfes"]), disabled=True)
        with col_x:
            st.text_input("XML", value=" / ".join([formatar_chave(c) for c in dados["chaves_nfe"]]), disabled=True)

        nfs_manual_input = st.text_input("NÚMERO DA NFS (SERVIÇO)", value="", placeholder="Digite o número da Nota de Serviço aqui...")

        # =====================================================================
        # NOVA TRAVA: Bloqueia a tela até o número da NFS ser preenchido
        # =====================================================================
        if not nfs_manual_input.strip():
            st.warning("⚠️ **Ação Necessária:** Digite o NÚMERO DA NFS acima e aperte 'Enter' (ou clique fora da caixa) para liberar os dados do subcontratado.")
            st.stop() # Mata a renderização da página aqui!
        # =====================================================================

    # O código abaixo só vai aparecer na tela DEPOIS que o campo acima for preenchido

        # 2. DADOS DO SUBCONTRATADO (BUSCA AUTOMÁTICA POR CNPJ)
        st.markdown("---")
        st.subheader("🚛 Dados do Subcontratado")
        
        # Campo único para entrada do CNPJ
        cnpj_input = st.text_input("DIGITE O CPF / CNPJ DO SUBCONTRATADO", value=dados.get("transp_cnpj", ""))
        cnpj_limpo = re.sub(r'\D', '', cnpj_input)
        dados["transp_cnpj"] = formatar_cnpj(cnpj_input)

        # Lista apenas com os números dos CNPJs bloqueados
        bloqueados = [
            "32368678000118", "32368678000207", "32368678000380",
            "32368678000460", "32368678000541", "32368678000622",
            "32368678000703"
        ]
        if cnpj_limpo in bloqueados:
            st.error("🚫 **BLOQUEADO:** Este CNPJ pertence a uma das filiais da **Rodo Amazônia**. Não é permitido emitir contrato de terceiro para filiais próprias nesta etapa.")
            st.stop() # Interrompe o script aqui
    # --- FIM DA VALIDAÇÃO ---

        dados["transp_cnpj"] = formatar_cnpj(cnpj_input)

        # BUSCA: Só dispara se for um CNPJ novo
        if len(cnpj_limpo) == 14 and cnpj_limpo != st.session_state.transp_cnpj_last:
            with st.spinner("Buscando dados oficiais..."):
                res = buscar_endereco_por_cnpj(cnpj_limpo)
                if res:
                    # SALVA NA MEMÓRIA DA SESSÃO
                    st.session_state.transp_nome = res["razao_social"]
                    st.session_state.transp_end = res["endereco"]
                    st.session_state.transp_cnpj_last = cnpj_limpo
                    st.rerun() # Força a atualização para preencher os campos abaixo
                else:
                    st.error("⚠️ CNPJ não localizado.")

        # EXIBIÇÃO: Agora as caixas de texto usam a MEMÓRIA (session_state)
        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            # O 'value' agora puxa do session_state, permitindo que a busca apareça na tela
            nome_editado = st.text_input("RAZÃO SOCIAL", value=st.session_state.transp_nome).upper()
        with col_sub2:
            end_editado = st.text_area("ENDEREÇO", value=st.session_state.transp_end, height=68).upper()

        # ATUALIZA O DICIONÁRIO DADOS: Importante para o contrato final
        dados["transp_nome"] = nome_editado
        dados["transp_end"] = end_editado
        dados["transp_cnpj"] = formatar_cnpj(cnpj_input)

        # --- PAUSA DINÂMICA 1: Só mostra motorista se o subcontratado estiver preenchido ---
        if dados.get("transp_nome") and dados.get("transp_end"):
            
            st.markdown("---")
            st.subheader("🚛 Motorista e Veículo")
            
            col_mot1, col_mot2 = st.columns([2, 1])
            with col_mot1:
                dados["motorista"] = st.text_input("NOME DO MOTORISTA", value=dados.get("motorista", "")).upper()
            with col_mot2:
                dados["cpf_motorista"] = st.text_input("CPF DO MOTORISTA", value=dados.get("cpf_motorista", ""))

            col_v1, col_v2, col_v3 = st.columns(3)
            with col_v1:
                dados["placa_cavalo"] = st.text_input("PLACA CAVALO", value=dados.get("placa_cavalo", "")).upper()
            with col_v2:
                p_carreta1 = st.text_input("PLACA CARRETA 1", value=dados.get("placa_carreta1", "")).upper()
                dados["placa_carreta1"] = p_carreta1
            with col_v3:
                p_carreta2 = st.text_input("PLACA CARRETA 2", value=dados.get("placa_carreta2", "")).upper()
                dados["placa_carreta2"] = p_carreta2

            # Lógica da Carreta 3
            if p_carreta1 and p_carreta2:
                dados["placa_carreta3"] = f"{p_carreta1} / {p_carreta2}"
            else:
                dados["placa_carreta3"] = p_carreta1 or p_carreta2 or ""

            # --- PAUSA DINÂMICA 2: Só mostra o restante se os campos do motorista/veículo estiverem preenchidos ---
            # Requisitos: Motorista, CPF, Placa Cavalo e pelo menos uma Carreta
            if dados.get("motorista") and dados.get("cpf_motorista") and dados.get("placa_cavalo") and dados.get("placa_carreta1"):
                
                # --- DADOS DO REMETENTE ---
                st.markdown("---")
                st.subheader("🏢 Dados do Remetente (Emitente da NF)")
                col_rem1, col_rem2 = st.columns([2, 1])
                with col_rem1:
                    dados["remetente_cnpj"] = st.text_input("CNPJ DO REMETENTE", value=dados.get("remetente_cnpj", ""))
                with col_rem2:
                    dados["remetente_nome"] = st.text_input("RAZÃO SOCIAL DO REMETENTE", value=dados.get("remetente_nome", "")).upper()
                col_rem_end, col_rem_cid = st.columns([2, 1])
                with col_rem_end:
                    dados["remetente_end"] = st.text_area("ENDEREÇO DO REMETENTE", value=dados.get("remetente_end", ""), height=68).upper()
                with col_rem_cid:
                    dados["origem"] = st.text_input("CIDADE / UF (REMETENTE)", value=dados.get("origem", "")).upper()

                # --- DADOS DO DESTINATÁRIO ---
                st.markdown("---")
                st.subheader("🏢 Dados do Destinatário")
                col_dest1, col_dest2 = st.columns([2, 1])
                with col_dest1:
                    dados["destinatario_cnpj"] = st.text_input("CNPJ DO DESTINATÁRIO", value=dados.get("destinatario_cnpj", ""))
                with col_dest2:
                    dados["destinatario_nome"] = st.text_input("RAZÃO SOCIAL DO DESTINATÁRIO", value=dados.get("destinatario_nome", "")).upper()
                col_dest_end, col_dest_cid = st.columns([2, 1])
                with col_dest_end:
                    dados["destinatario_end"] = st.text_input("ENDEREÇO DO DESTINATÁRIO", value=dados.get("destinatario_end", "")).upper()
                with col_dest_cid:
                    dados["destino"] = st.text_input("CIDADE / UF (DESTINATÁRIO)", value=dados.get("destino", "")).upper()

                # --- DADOS DO RECEBEDOR ---
                st.markdown("---")
                st.subheader("🚚 Dados do Recebedor")
                col_rec1, col_rec2 = st.columns([2, 1])
                with col_rec1:
                    dados["recebedor_cnpj"] = st.text_input("CNPJ DO RECEBEDOR", value=dados.get("recebedor_cnpj", ""))
                    
                with col_rec2:
                    dados["recebedor_nome"] = st.text_input("RAZÃO SOCIAL DO RECEBEDOR", value=dados.get("recebedor_nome", "")).upper()
                col_rec_end, col_rec_cid = st.columns([2, 1])
                with col_rec_end:
                    dados["recebedor_end"] = st.text_input("ENDEREÇO DO RECEBEDOR", value=dados.get("recebedor_end", "")).upper()
                with col_rec_cid:
                    dados["recebedor_cidade"] = st.text_input("CIDADE / UF (RECEBEDOR)", value=dados.get("recebedor_cidade", "")).upper()

                # --- DADOS DO EXPEDIDOR ---
                st.markdown("---")
                st.subheader("📍 Dados do Expedidor (Local de Retirada)")
                col_exp1, col_exp2 = st.columns([2, 1])
                with col_exp1:
                    dados["expedidor_cnpj"] = st.text_input("CNPJ DO EXPEDIDOR", value=dados.get("expedidor_cnpj", ""))
                with col_exp2:
                    dados["expedidor_nome"] = st.text_input("RAZÃO SOCIAL DO EXPEDIDOR", value=dados.get("expedidor_nome", "")).upper()
                col_exp_end, col_exp_cid = st.columns([2, 1])
                with col_exp_end:
                    dados["expedidor_end"] = st.text_input("ENDEREÇO DO EXPEDIDOR", value=dados.get("expedidor_end", "")).upper()
                with col_exp_cid:
                    dados["expedidor_cidade"] = st.text_input("CIDADE / UF (EXPEDIDOR)", value=dados.get("expedidor_cidade", "")).upper()

                # --- EDIÇÃO FINANCEIRA E BOTÃO GERAR ---
                st.markdown("---")
                st.subheader("📝 Edição Financeira - Nota de Serviço")
                st.markdown("""
                    <style>
                    /* REMOVE OS BOTÕES + E - DO st.number_input */
                    button[data-testid="stNumberInputStepDown"],
                    button[data-testid="stNumberInputStepUp"] {
                        display: none !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                # --- COLUNAS PARA EDIÇÃO FINANCEIRA ---
                col_fin1, col_fin2 = st.columns(2)
                
                with col_fin1:
                    # Mercadoria extraída do XML
                    mercadoria_edit = st.text_input("MERCADORIA", value=dados.get("mercadoria", "DIVERSOS")).upper()
                    
                    # Volume/Peso (Soma das tags qCom do XML)
                    volume_inicial = float(dados.get("volume_carregado", 0.0))
                    volume_edit = st.number_input("VOLUME / PESO CARREGADO", value=volume_inicial, step=0.001, format="%.3f")
                    
                    # Frete Unitário (Com suporte a várias casas decimais conforme solicitado)
                    frete_txt = st.text_input("FRETE UNITÁRIO (R$/TON)", value="0,00")
                    frete_edit = limpar_valor_formatado(frete_txt)
                    
                with col_fin2:
                    # Cálculo automático do rendimento
                    rendimento_calc = volume_edit * frete_edit
                    
                    # Rendimento Bruto (Editável)
                    rendimento_txt = st.text_input("RENDIMENTO BRUTO (R$)", value=formatar_moeda(rendimento_calc))
                    rendimento_bruto_edit = limpar_valor_formatado(rendimento_txt)
                    
                    # Descontos e Pedágio
                    desconto_txt = st.text_input("DESCONTOS (R$)", value="0,00")
                    descontos_edit = limpar_valor_formatado(desconto_txt)
                    
                    pedagio_txt = st.text_input("PEDÁGIO (R$)", value=formatar_moeda(dados.get("valor_pedagio", 0.0)))
                    pedagio_edit = limpar_valor_formatado(pedagio_txt)

                # Cálculo e exibição do Valor Líquido (Bloqueado para edição)
                valor_liquido_auto = rendimento_bruto_edit - pedagio_edit - descontos_edit
                st.text_input("VALOR LÍQUIDO FINAL (R$)", value=formatar_moeda(valor_liquido_auto), disabled=True)

                # --- BOTÃO DE GERAR CONTRATO ---
                st.markdown("---")
                if st.button("📄 EMITIR CONTRATO DE SUBCONTRATAÇÃO (NFS)", use_container_width=True):
                    html_contrato = gerar_contrato_servico_html(dados)
                    if html_contrato:
                        # Seu código de exibição (b64 e componentes v1)
                        b64 = base64.b64encode(html_contrato.encode('utf-8')).decode()
                    if frete_edit > 0 and volume_edit > 0:
                        with st.spinner("Preparando documento..."):
                            # 1. Atualiza o dicionário de dados com as edições da tela
                            dados["nfs_manual"] = nfs_manual_input
                            dados["mercadoria"] = mercadoria_edit
                            dados["volume_carregado"] = volume_edit # Mantém float para o cálculo no template
                            dados["frete_unitario"] = frete_txt    # Mantém precisão total
                            dados["rendimento_bruto"] = rendimento_bruto_edit
                            dados["descontos"] = descontos_edit
                            dados["valor_pedagio"] = pedagio_edit
                            dados["valor_liquido"] = valor_liquido_auto
                            
                            # Define a placa principal para o nome do arquivo
                            placa_ref = dados.get("placa_cavalo", "SEM_PLACA")
                            
                            # 2. Gera o HTML usando o template de serviço
                            try:
                                html_contrato = gerar_contrato_servico_html(dados)
                                
                                # 3. Injeta o JavaScript para abrir em nova aba
                                b64 = base64.b64encode(html_contrato.encode('utf-8')).decode()
                                js_open_tab = f"""
                                <script>
                                    const b64 = '{b64}';
                                    const html = decodeURIComponent(escape(window.atob(b64)));
                                    const win = window.open("", "_blank");
                                    if (win) {{
                                        win.document.write(html);
                                        win.document.close();
                                    }} else {{
                                        alert("Por favor, permita pop-ups para visualizar o contrato.");
                                    }}
                                </script>
                                """
                                st.components.v1.html(js_open_tab, height=0)
                                # Exibe uma mensagem visual para o usuário não ficar confuso
                                st.success("✅ Contrato gerado! Reiniciando o sistema em 5 segundos...")
                                
                                # O Python "dorme" por 5 segundos
                                time.sleep(5)
                                
                                # Chama a sua função de reset
                                reiniciar_aplicativo()
                            except Exception as e:
                                st.error(f"Erro ao renderizar template: {e}")
                    else:
                        st.error("⚠️ Verifique o Frete e o Volume. Eles não podem ser zero.")
            else:
                st.info("💡 Informe o **Motorista e CPF** para liberar o fechamento financeiro.")
        else:
            st.warning("⚠️ Aguardando a validação do **CNPJ do Subcontratado**...")

        st.stop() # Bloqueia o resto do código (contrato de frete)
    # --- FIM DO FLUXO NF-E ---

    # 3. Verificação de pendências (Apenas XMLs)
    faltando = []
    if not xml_cte_ok: faltando.append("XML do **CT-e** (Conhecimento)")
    if not xml_mdf_ok: faltando.append("XML do **MDF-e** (Manifesto)")

    if faltando:
        st.error("🚫 **Documentos XML Obrigatórios Faltando**")
        for item in faltando:
            st.markdown(f"- {item}")
        st.stop()

    # Se passou, processa os dados normalmente
    dados = processar_documentos_fiscais(arquivos)
    pedagio_sugerido = float(dados.get("valor_pedagio", 0.0))

    if arquivos:
        st.success("✅ Documentação completa identificada! Edição liberada.")
        # Obtém os valores sugeridos pela leitura automática
        pesos_cte = dados.get("pesos_cte", [])
        pesos_nfe = dados.get("pesos_nfe", [])
        peso_kg_sugerido = sum(pesos_cte) if pesos_cte else sum(pesos_nfe)
        
        try:
            pedagio_sugerido = float(dados.get("valor_pedagio", 0.0))
        except:
            pedagio_sugerido = 0.0

        # --- A SEÇÃO ABAIXO AGORA ESTÁ DENTRO DO 'IF ARQUIVOS' ---
        st.markdown("---")
        st.subheader("📝 Dados Financeiros do Contrato")
        st.info("Valores extraídos com sucesso. Você pode ajustar os campos abaixo se necessário.")
        st.markdown("""
            <style>
            /* REMOVE OS BOTÕES + E - DO st.number_input */
            button[data-testid="stNumberInputStepDown"],
            button[data-testid="stNumberInputStepUp"] {
                display: none !important;
            </style>
        """, unsafe_allow_html=True)
        
        # --- DADOS DA CARGA ---
        st.markdown("---")
        st.subheader("📦 Dados do Condutor Responsável")
        # Campos do Motorista adicionados ACIMA da Mercadoria
        col_mot_cte, col_cpf_cte = st.columns([2, 1])
        with col_mot_cte:
            dados["motorista"] = st.text_input("NOME DO CONDUTOR", value=dados.get("motorista", "")).upper()
        with col_cpf_cte:
            dados["cpf_motorista"] = st.text_input("CPF DO CONDUTOR", value=dados.get("cpf_motorista", ""))

        col1, col2 = st.columns(2)
        with col1:
            mercadoria_edit = st.text_input("MERCADORIA", value=dados.get("mercadoria", "Diversos"))
            
            # --- VOLUME EDITÁVEL COM FORMATAÇÃO ---
            volume_inicial = float(dados.get("volume_carregado", 0.0))
            volume_edit = st.number_input("VOLUME/PESO CARREGADO", value=volume_inicial, step=0.001)
            
            frete_txt = st.text_input("FRETE UNITÁRIO (R$/TON)", value="0,00")
            frete_edit = limpar_valor_formatado(frete_txt)
            
        with col2:
            # Cálculo automático do rendimento (usando os valores já limpos)
            rendimento_calc = volume_edit * frete_edit
            
            # --- RENDIMENTO BRUTO EDITÁVEL COM FORMATAÇÃO ---
            rendimento_txt = st.text_input("RENDIMENTO BRUTO (R$)", value=formatar_moeda(rendimento_calc))
            rendimento_bruto_edit = limpar_valor_formatado(rendimento_txt)
            
            desconto_txt = st.text_input("DESCONTOS (R$)", value="0,00")
            descontos_edit = limpar_valor_formatado(desconto_txt)
            
            pedagio_txt = st.text_input("PEDÁGIO (R$)", value=formatar_moeda(pedagio_sugerido))
            pedagio_edit = limpar_valor_formatado(pedagio_txt)

        # Cálculo e exibição do Valor Líquido (Bloqueado para edição)
        valor_liquido_auto = rendimento_bruto_edit - pedagio_edit - descontos_edit
        st.text_input("VALOR LÍQUIDO FINAL (R$)", value=formatar_moeda(valor_liquido_auto), disabled=True)

        st.markdown("---")
        if st.button("🚛 EMITIR CONTRATO DE SUBCONTRATAÇÃO (CT-E)", use_container_width=True):
            if frete_edit > 0 and volume_edit > 0:
                with st.spinner("Gerando contrato..."):
                    # Todo o seu código de preenchimento do dicionário e geração do HTML vem aqui
                    dados["valor_tonelada"] = formatar_moeda(frete_edit)

                # 1. Salva a placa e os cálculos
                valor_liquido_final = rendimento_bruto_edit - pedagio_edit - descontos_edit
                
                # 2. Atualiza o dicionário de dados
                dados["mercadoria"] = mercadoria_edit
                dados["volume_carregado"] = volume_edit
                dados["frete_unitario"] = frete_txt
                dados["rendimento_bruto"] = rendimento_bruto_edit
                dados["descontos"] = descontos_edit  
                dados["valor_pedagio"] = pedagio_edit
                dados["valor_liquido"] = valor_liquido_final

                # 3. Define a placa de forma segura (usa a variável ou 'SEM_PLACA' se não houver)
                placa_cavalo = dados.get("placa_cavalo", "SEM_PLACA")
                dados["veic_placa"] = placa_cavalo
                nome_arquivo = f"Contrato_{placa_cavalo}.html"
                
                # 4. Gera o HTML
                html_contrato = gerar_contrato_html(dados)
                # 5. ABRIR RELATÓRIO EM NOVA GUIA
                b64 = base64.b64encode(html_contrato.encode()).decode()
                
                # JavaScript para abrir nova aba e injetar o HTML
                js_open_tab = f"""
                <script>
                    // Converte base64 de volta para string tratando caracteres especiais (acentos)
                    const b64 = '{b64}';
                    const html = decodeURIComponent(escape(window.atob(b64)));
                    
                    // Abre uma nova aba em branco
                    const win = window.open("", "_blank");
                    
                    if (win) {{
                        // Escreve o conteúdo do contrato na nova aba
                        win.document.write(html);
                        win.document.close();
                    }} else {{
                        // Alerta caso o navegador bloqueie o pop-up
                        alert("O navegador bloqueou a abertura da nova guia. Por favor, permita pop-ups para este site.");
                    }}
                </script>
                """ 
                st.components.v1.html(js_open_tab, height=0)
                # --- NOVA LÓGICA DE REINÍCIO ---
                # Exibe uma mensagem visual para o usuário não ficar confuso
                st.success("✅ Contrato gerado! Reiniciando o sistema em 5 segundos...")
                
                # O Python "dorme" por 5 segundos
                time.sleep(5)
                
                # Chama a sua função de reset
                reiniciar_aplicativo()

            elif (frete_edit <= 0):
                # Mensagem caso o valor seja 0 ou negativo
                st.error("⚠️ O relatório não pode ser emitido porque o Frete Unitário (R$/Ton) não foi informado.")

            else:
                # Mensagem caso o volume seja 0 ou negativo
                st.error("⚠️ O relatório não pode ser emitido porque o Volume/Peso Carregado não foi informado.")
# Ponto de entrada EXCLUSIVO do Streamlit
if __name__ == "__main__":
    main()
