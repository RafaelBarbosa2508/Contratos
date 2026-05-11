import streamlit as st
import pdfplumber
import re
import os
import webbrowser
import xml.etree.ElementTree as ET
import requests
import io

def limpar_placa(placa):
    """Remove espaços, traços e garante que fique maiúsculo"""
    return re.sub(r'[\s-]', '', placa).upper()

def formatar_moeda(valor):
    """Formata número (float) para o padrão de moeda brasileiro (ex: 1.234,56)"""
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

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
    """Busca o endereço oficial da Receita Federal usando a BrasilAPI"""
    if not cnpj: 
        return ""
    
    # Limpa o CNPJ mantendo apenas números
    cnpj_limpo = re.sub(r'\D', '', cnpj)
    
    if len(cnpj_limpo) != 14:
        return ""
        
    try:
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        response = requests.get(url, timeout=10) # Aguarda até 10 segundos
        
        if response.status_code == 200:
            dados_cnpj = response.json()
            
            # Monta o endereço: Logradouro, Número - Bairro, Cidade - UF, CEP
            logradouro = dados_cnpj.get('logradouro', '')
            numero = dados_cnpj.get('numero', 'S/N')
            bairro = dados_cnpj.get('bairro', '')
            municipio = dados_cnpj.get('municipio', '')
            uf = dados_cnpj.get('uf', '')
            cep = dados_cnpj.get('cep', '')
            
            endereco_completo = f"{logradouro}, {numero} - {bairro}. {municipio} - {uf}. CEP: {cep}"
            return endereco_completo.upper()
        else:
            print(f"\n[AVISO] Não foi possível encontrar o CNPJ {cnpj} na base de dados.")
            return ""
            
    except requests.exceptions.RequestException as e:
        print(f"\n[ERRO] Falha ao conectar na API de busca de CNPJ: {e}")
        return ""

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

    # 4. Pedágio
    if "VALE PED" in texto_upper:
        if "TOTAL" in texto_upper:
            texto_pos_total = texto_upper.split("TOTAL")[-1]
            match_pedagio = re.search(r"([\d]{1,3}(?:\.\d{3})*,\d{2})", texto_pos_total)
            if match_pedagio:
                valor_str = match_pedagio.group(1).replace('.', '').replace(',', '.')
                dados["valor_pedagio"] = float(valor_str)

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
    """Extrai informações direto do XML com precisão para MDF-e e soma de itens"""
    texto_xml_lower = texto_xml.lower()

    def buscar_bloco(tag_pai, xml_texto):
        match = re.search(r"<(?:\w+:)?" + tag_pai + r"[^>]*>(.*?)</(?:\w+:)?" + tag_pai + r">", xml_texto, re.IGNORECASE | re.DOTALL)
        return match.group(1) if match else ""

    def buscar_campo(tag, bloco):
        match = re.search(r"<(?:\w+:)?" + tag + r"[^>]*>(.*?)</(?:\w+:)?" + tag + r">", bloco, re.IGNORECASE)
        return match.group(1) if match else ""

    # 0. EXTRAÇÃO DA MERCADORIA (<proPred>)
    mercadoria = buscar_campo("proPred", texto_xml)
    if mercadoria:
        dados["mercadoria"] = mercadoria.upper()

    # 1. REMETENTE (<rem>)
    rem_bloco = buscar_bloco("rem", texto_xml)
    if rem_bloco:
        dados["remetente_nome"] = buscar_campo("xNome", rem_bloco).upper()
        cnpj = buscar_campo("CNPJ", rem_bloco) or buscar_campo("CPF", rem_bloco)
        dados["remetente_cnpj"] = formatar_cnpj(cnpj)
        dados["remetente_end"] = f"{buscar_campo('xLgr', rem_bloco)}, {buscar_campo('nro', rem_bloco)} - {buscar_campo('xBairro', rem_bloco)}".upper()
        dados["remetente_cidade"] = buscar_campo("xMun", rem_bloco).upper()

    # 2. DESTINATÁRIO (<dest>)
    dest_bloco = buscar_bloco("dest", texto_xml)
    if dest_bloco:
        dados["destinatario_nome"] = buscar_campo("xNome", dest_bloco).upper()
        cnpj = buscar_campo("CNPJ", dest_bloco) or buscar_campo("CPF", dest_bloco)
        dados["destinatario_cnpj"] = formatar_cnpj(cnpj)
        dados["destinatario_end"] = f"{buscar_campo('xLgr', dest_bloco)}, {buscar_campo('nro', dest_bloco)} - {buscar_campo('xBairro', dest_bloco)}".upper()
        dados["destinatario_cidade"] = buscar_campo("xMun", dest_bloco).upper()

    # 3. RECEBEDOR (<receb>)
    receb_bloco = buscar_bloco("receb", texto_xml)
    if receb_bloco:
        cnpj_receb_bruto = buscar_campo("CNPJ", receb_bloco) or buscar_campo("CPF", receb_bloco)
        cnpj_receb_formatado = formatar_cnpj(cnpj_receb_bruto)
        if cnpj_receb_formatado != dados.get("destinatario_cnpj"):
            dados["recebedor_nome"] = buscar_campo("xNome", receb_bloco).upper()
            dados["recebedor_cnpj"] = cnpj_receb_formatado
            dados["recebedor_end"] = f"{buscar_campo('xLgr', receb_bloco)}, {buscar_campo('nro', receb_bloco)} - {buscar_campo('xBairro', receb_bloco)}".upper()
            dados["recebedor_cidade"] = buscar_campo("xMun", receb_bloco).upper()
        else:
            dados["recebedor_nome"] = ""
            dados["recebedor_cnpj"] = ""
            dados["recebedor_end"] = ""
            dados["recebedor_cidade"] = ""

    # 3.5. EXPEDIDOR (<exped>)
    exped_bloco = buscar_bloco("exped", texto_xml)
    if exped_bloco:
        dados["expedidor_nome"] = buscar_campo("xNome", exped_bloco).upper()
        
        cnpj_exped_bruto = buscar_campo("CNPJ", exped_bloco) or buscar_campo("CPF", exped_bloco)
        dados["expedidor_cnpj"] = formatar_cnpj(cnpj_exped_bruto)
        
        # Monta o endereço do expedidor
        lgr = buscar_campo('xLgr', exped_bloco)
        nro = buscar_campo('nro', exped_bloco)
        bairro = buscar_campo('xBairro', exped_bloco)
        dados["expedidor_end"] = f"{lgr}, {nro} - {bairro}".upper()
        
        dados["expedidor_cidade"] = buscar_campo("xMun", exped_bloco).upper()
    else:
        # Garante que o campo comece vazio se não houver expedidor no XML
        dados["expedidor_nome"] = ""
        dados["expedidor_cnpj"] = ""
        dados["expedidor_end"] = ""
        dados["expedidor_cidade"] = ""

    # Subcontratação
    sub_match = re.search(r"transporte subcontratado com\s+(.*?)\s+cnpj:\s*([\d\.\-\/]+)", texto_xml_lower)
    if sub_match:
        dados["transp_nome"] = sub_match.group(1).strip().upper()
        dados["transp_cnpj"] = formatar_cnpj(sub_match.group(2).strip())

    # === CORREÇÃO CIRÚRGICA PARA NF-e NO XML ===
    if "<infnfe" in texto_xml_lower:
        # 1. Isolamos o bloco <ide> para pegar apenas a identidade DESTA nota
        ide_bloco = buscar_bloco("ide", texto_xml)
        if ide_bloco:
            # 2. Pegamos apenas o número oficial dentro do <ide>
            nfe_match = re.search(r"<nNF>(\d+)</nNF>", ide_bloco, re.IGNORECASE)
            if nfe_match:
                # Limpamos a lista antes para garantir que só tenha ESSA nota
                dados["nfes"] = [str(int(nfe_match.group(1)))]

        # 3. Guardamos as chaves apenas para histórico, sem extrair números delas!
        chaves_encontradas = re.findall(r'id=["\']nfe(\d{44})["\']', texto_xml_lower)
        for c in chaves_encontradas:
            if eh_chave_valida(c) and c not in dados["xml_chaves_nfe"]:
                dados["xml_chaves_nfe"].append(c)
        
    # CT-e
    if "<infcte" in texto_xml_lower:
        cte = re.search(r"<nCT>(\d+)</nCT>", texto_xml, re.IGNORECASE)
        if cte: dados["ctes"].append(str(int(cte.group(1))))
        chaves = re.findall(r'id=["\']cte(\d{44})["\']', texto_xml_lower)
        chaves_v = [c for c in chaves if eh_chave_valida(c)]
        dados["xml_chaves_cte"].extend(chaves_v)
        for c in chaves_v:
            if c[20:22] == '57': dados["ctes"].append(str(int(c[25:34])))

    # MDF-e (Ajustado para pegar apenas o número principal)
    if "<infmdfe" in texto_xml_lower:
        mdfe = re.search(r"<nMDF>(\d+)</nMDF>", texto_xml, re.IGNORECASE)
        if mdfe: 
            dados["mdf_e"] = mdfe.group(1) # Grava o número correto (ex: 99)
            dados["mdfes"].append(str(int(mdfe.group(1))))
        
        chaves = re.findall(r'id=["\']mdfe(\d{44})["\']', texto_xml_lower)
        for c in chaves:
            if eh_chave_valida(c) and c[20:22] == '58':
                num_chave = str(int(c[25:34]))
                if num_chave not in dados["mdfes"]: dados["mdfes"].append(num_chave)
        
        placas = re.findall(r"<placa>([A-Za-z0-9]{7})</placa>", texto_xml, re.IGNORECASE)
        placas_unicas = list(dict.fromkeys([p.upper() for p in placas]))
        if len(placas_unicas) >= 1 and not dados["placa_cavalo"]: dados["placa_cavalo"] = placas_unicas[0]
        if len(placas_unicas) >= 2 and not dados["placa_carreta1"]: dados["placa_carreta1"] = placas_unicas[1]
        if len(placas_unicas) >= 3 and not dados["placa_carreta2"]: dados["placa_carreta2"] = placas_unicas[2]
        
        condutor_match = re.search(r"<condutor>.*?</condutor>", texto_xml, re.DOTALL | re.IGNORECASE)
        if condutor_match:
            condutor_xml = condutor_match.group(0)
            nome = re.search(r"<xNome>(.*?)</xNome>", condutor_xml, re.IGNORECASE)
            cpf = re.search(r"<CPF>(.*?)</CPF>", condutor_xml, re.IGNORECASE)
            if nome and not dados["motorista"]: dados["motorista"] = nome.group(1).upper()
            if cpf and not dados["cpf_motorista"]: dados["cpf_motorista"] = cpf.group(1)

    # 4. BUSCA DE PESO OFICIAL E INTELIGENTE
    if "pesos_nfe" not in dados: dados["pesos_nfe"] = []
    if "pesos_cte" not in dados: dados["pesos_cte"] = []
    
    # Se for CT-e, a tag correta para peso em KG é <qCarga>
    if "<infcte" in texto_xml_lower:
        qcarga = re.search(r"<qCarga>([\d.]+)</qCarga>", texto_xml, re.IGNORECASE)
        if qcarga: 
            dados["pesos_cte"].append(float(qcarga.group(1)))
            
    # Se for NF-e, a tag correta é <pesoB> (Bruto) ou <pesoL> (Líquido)
    elif "<infnfe" in texto_xml_lower:
        peso = re.search(r"<pesoB>([\d.]+)</pesoB>", texto_xml, re.IGNORECASE)
        if not peso:
            peso = re.search(r"<pesoL>([\d.]+)</pesoL>", texto_xml, re.IGNORECASE)
        if peso: 
            dados["pesos_nfe"].append(float(peso.group(1)))

def processar_documentos_fiscais(pasta_arquivos):
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
        "cliente_nome": "", "cliente_cnpj": "", "cliente_ie": "",
        "mercadoria": ""
    }

    for nome_arquivo in os.listdir(pasta_arquivos):
        caminho_completo = os.path.join(pasta_arquivos, nome_arquivo)
        if nome_arquivo.lower().endswith('.pdf'):
            try:
                with pdfplumber.open(caminho_completo) as pdf:
                    texto_pdf = "".join([pagina.extract_text() or "" for pagina in pdf.pages])
                    extrair_dados_pdf(texto_pdf, dados)
            except Exception as e:
                print(f"Erro ao ler o PDF {nome_arquivo}: {e}")
        elif nome_arquivo.lower().endswith('.xml'):
            try:
                with open(caminho_completo, 'r', encoding='utf-8', errors='ignore') as f:
                    texto_xml = f.read()
                    extrair_dados_xml(texto_xml, dados)
            except Exception as e:
                print(f"Erro ao ler o XML {nome_arquivo}: {e}")
                
    chaves_nfe_definitivas = dados["xml_chaves_nfe"] if dados["xml_chaves_nfe"] else dados["pdf_chaves_nfe"]
    chaves_cte_definitivas = dados["xml_chaves_cte"] if dados["xml_chaves_cte"] else dados["pdf_chaves_cte"]

    if dados["transp_cnpj"] and not dados["transp_end"]:
        print(f"Buscando endereço oficial na Receita Federal para o CNPJ: {dados['transp_cnpj']}...")
        endereco_encontrado = buscar_endereco_por_cnpj(dados["transp_cnpj"])
        if endereco_encontrado:
            dados["transp_end"] = endereco_encontrado
        else:
            dados["transp_end"] = "ENDEREÇO NÃO LOCALIZADO"

    dados["nfes"] = list(set(dados["nfes"]))
    dados["ctes"] = list(set(dados["ctes"]))
    dados["mdfes"] = list(set(dados["mdfes"]))
    dados["chaves_nfe"] = list(set(chaves_nfe_definitivas))
    dados["chaves_cte"] = list(set(chaves_cte_definitivas))
    return dados

def gerar_contrato_html(dados, nome_saida="Contrato_Rodo_Amazonia.html"):
    str_nfes = " ".join(dados["nfes"]) if dados["nfes"] else ""
    str_ctes = " ".join(dados["ctes"]) if dados["ctes"] else ""
    str_mdfes = " ".join(dados["mdfes"]) if dados["mdfes"] else ""
    str_chaves_nfe = " / ".join([formatar_chave(c) for c in dados["chaves_nfe"]])
    str_chaves_cte = " / ".join([formatar_chave(c) for c in dados["chaves_cte"]])

    # Formata o volume
    vol_formatado = f"{dados['volume_carregado']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if vol_formatado.endswith(",000"): vol_formatado = vol_formatado.replace(",000", "")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <title>Contrato de Subcontratação - Rodoamazônia</title>
        <style>
            @media print {{
                @page {{ size: A4 landscape; margin: 5mm; }}
                body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            }}
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; font-size: 8pt; margin: 0; padding: 10px; text-transform: uppercase; }}
            table {{ width: 100%; border-collapse: collapse; border: 2px solid black; margin-bottom: 0px; }}
            th, td {{ border: 1px solid black; padding: 3px 4px; text-align: left; vertical-align: middle; }}
            .header-cell {{ border-bottom: 2px solid black; padding: 8px 10px; text-align: center; }}
            .logo-container {{ float: left; text-align: left; width: 25%; }}
            .logo-text {{ font-size: 22pt; font-weight: bold; color: #2E7D32; font-style: italic; margin: 0; letter-spacing: -1px; }}
            .logo-slogan {{ font-size: 8pt; color: #555; font-style: italic; font-weight: bold; padding-left: 5px; }}
            .company-data-container {{ display: inline-block; text-align: center; width: 50%; }}
            .company-data-container p {{ margin: 2px 0; font-size: 10pt; font-weight: normal; text-transform: none; }}
            .company-name {{ font-weight: bold; font-size: 12pt; text-transform: uppercase; }}
            .contract-title {{ text-align: center; font-weight: bold; font-size: 11pt; padding: 6px; }}
            .section-header {{ background-color: black; color: white !important; text-align: center; font-weight: bold; font-size: 10pt; padding: 4px; }}
            .table-no-top-border {{ border-top: none; }}
            .label {{ font-weight: normal; }}
            .col-title {{ font-weight: bold; text-align: center; }}
            .text-red {{ color: red; }}
            .clearfix::after {{ content: ""; clear: both; display: table; }}
        </style>
    </head>
    <body>
        <table>
            <tr>
                <td colspan="2" class="header-cell clearfix">
                    <div class="logo-container">
                        <div class="logo-text">RODO AMAZÔNIA</div>
                        <div class="logo-slogan">Movida pelos desafios.</div>
                    </div>
                    <div class="company-data-container">
                        <p class="company-name">RODOAMAZONIA TRANSPORTE RODOVIÁRIO DE CARGA LTDA</p>
                        <p>Endereço: R. Estrada do Belmont, 10877 - NACIONAL</p>
                        <p>Porto Velho - RO - CEP: 78903-400</p>
                        <p>CNPJ: 32.368.678/0002-07 IE: 5412285</p>
                    </div>
                </td>
            </tr>
            <tr><td colspan="2" class="contract-title">CONTRATO DE SUBCONTRATAÇÃO DE TRANSPORTE</td></tr>
            <tr><td colspan="2" class="section-header">DADOS DO TRANSPORTADOR SUBCONTRATADO</td></tr>
            <tr><td style="width: 30%;">RAZAO SOCIAL DO SUBCONTRATADO:</td><td style="width: 70%;">{dados['transp_nome']}</td></tr>
            <tr><td>CPF / CNPJ:</td><td>{dados['transp_cnpj']}</td></tr>
            <tr><td>ENDEREÇO PROPRIETARIO:</td><td>{dados['transp_end']}</td></tr>
            <tr><td>PLACA CAVALO</td><td>{dados['placa_cavalo']}</td></tr>
            <tr><td>CARRETA 1</td><td>{dados['placa_carreta1']}</td></tr>
            <tr><td>CARRETA 2</td><td>{dados['placa_carreta2']}</td></tr>
            <tr><td>NOME DO MOTORISTA</td><td>{dados['motorista']}</td></tr>
            <tr><td>CPF DO MOTORISTA</td><td>{dados['cpf_motorista']}</td></tr>
        </table>
       
        <table class="table-no-top-border">
            <tr><td colspan="5" class="section-header">SERVIÇO REALIZADO</td></tr>
            
            <tr>
                <td rowspan="4" class="col-title" style="width:15%;">REMETENTE</td>
                <td class="label" style="width:15%;">RAZÃO SOCIAL:</td>
                <td style="width:35%;">{dados['remetente_nome']}</td>
                <td class="label" style="width:15%;">MERCADORIA:</td>
                <td style="width:20%;">{dados.get('mercadoria', '')}</td>
            </tr>
            <tr>
                <td class="label">CPF / CNPJ:</td><td>{dados['remetente_cnpj']}</td>
                <td class="label">VOLUME CARREGADO:</td><td>{vol_formatado}</td>
            </tr>
            <tr>
                <td class="label">ENDEREÇO</td><td>{dados['remetente_end']}</td>
                <td class="label">VALOR / TONELADA:</td><td>R$ {formatar_moeda(dados['valor_tonelada'])}</td>
            </tr>
            <tr>
                <td class="label">CIDADE</td><td>{dados['remetente_cidade']}</td>
                <td class="label">RENDIMENTO BRUTO</td><td>R$ {formatar_moeda(dados['rendimento_bruto'])}</td>
            </tr>
            
            <tr>
                <td colspan="3" style="border-right: none;"></td>
                <td class="label" style="border-left: 1px solid black;">DESCONTOS:</td>
                <td class="text-red">R$ {formatar_moeda(dados['valor_pedagio'])}</td>
            </tr>

            <tr>
                <td rowspan="4" class="col-title">DESTINATÁRIO</td>
                <td class="label">RAZÃO SOCIAL:</td><td>{dados['destinatario_nome']}</td>
                <td class="label">PEDÁGIO:</td><td class="text-red">R$ {formatar_moeda(dados['valor_pedagio'])}</td>
            </tr>
            <tr>
                <td class="label">CPF / CNPJ:</td><td>{dados['destinatario_cnpj']}</td>
                <td class="label">SEST / SENAT (0.0%)</td><td></td>
            </tr>
            <tr>
                <td class="label">ENDEREÇO</td><td>{dados['destinatario_end']}</td>
                <td class="label">INSS (0.0%)</td><td></td>
            </tr>
            <tr>
                <td class="label">CIDADE</td><td>{dados['destinatario_cidade']}</td>
                <td class="label">I.R</td><td></td>
            </tr>

            <tr>
                <td colspan="3" style="border-right: none;"></td>
                <td class="label" style="border-left: 1px solid black;"><b>VALOR LÍQUIDO</b></td>
                <td><b>R$ {formatar_moeda(dados['valor_liquido'])}</b></td>
            </tr>

            <tr>
                <td rowspan="4" class="col-title">RECEBEDOR:</td> 
                <td class="label">RAZAO SOCIAL:</td>
                <td>{dados.get('recebedor_nome', '')}</td>
                <td class="label">TOTAL ADIANTAMENTO:</td>
                <td></td>
            </tr>
            <tr>
                <td class="label">CPF / CNPJ:</td>
                <td>{dados.get('recebedor_cnpj', '')}</td>
                <td class="label">TOTAL DO SALDO</td>
                <td></td>
            </tr>
            <tr>
                <td class="label">ENDEREÇO:</td>
                <td>{dados.get('recebedor_end', '')}</td>
                <td colspan="2"></td>
            </tr>
            <tr>
                <td class="label">CIDADE:</td>
                <td>{dados.get('recebedor_cidade', '')}</td>
                <td colspan="2"></td>
            </tr>

            <tr><td colspan="5" style="height: 12px;"></td></tr>

            <tr>
                <td rowspan="3" class="col-title" style="width:15%;">EXPEDIDOR</td>
                <td class="label" style="width:15%;">RAZÃO SOCIAL</td>
                <td style="width:35%;">{dados['cliente_nome']}</td>
            </tr>
            <tr>
                <td class="label">CPF / CNPJ:</td><td>{dados['cliente_cnpj']}</td>
            </tr>
            <tr>
                <td class="label">INS.ESTADUAL</td><td>{dados['cliente_ie']}</td>
            </tr>
        </table>
        
        <table class="table-no-top-border">
            <tr><td colspan="5" class="section-header">DADOS BANCÁRIOS</td></tr>
            <tr><td colspan="2" class="label">PARCEIRO:</td></tr>
            <tr><td colspan="2" class="label">TIPO DE CONTA:</td></tr>
            <tr><td colspan="2" class="label">BANCO</td></tr>
            <tr><td colspan="2" class="label">AGENCIA:</td></tr>
            <tr><td colspan="2" class="label">CONTA PARCEIRO:</td></tr>
            <tr><td colspan="2" class="label">CONTRATO DE PEDÁGIO</td></tr>
        </table>

        <table class="table-no-top-border">
            <tr><td colspan="3" class="section-header">CONDIÇÕES ESPECIFICAS A ESTE CONTRATO DE TRANSPORTE</td></tr>
            <tr>
                <td style="width: 30%;" class="label">AGENDAMENTO DA DESCARGA PARA:</td>
                <td colspan="2"></td>
            </tr>
            <tr>
                <td class="label">NOTAS FISCAIS</td>
                <td style="width: 20%;">{str_nfes}</td>
                <td style="width: 50%; font-family: monospace;">{str_chaves_nfe}</td>
            </tr>
            <tr>
                <td class="label">CONHECIMENTOS DE TRANSPORTES -CTE</td>
                <td>{str_ctes}</td>
                <td style="font-family: monospace;">{str_chaves_cte}</td>
            </tr>
            <tr>
                <td class="label">MDF-e</td>
                <td colspan="2">{str_mdfes}</td>
            </tr>
        </table>

        <table class="table-no-top-border">
            <tr><td class="section-header">CONDIÇÕES GERAIS DO CONTRATO DE TRANSPORTE</td></tr>
            <tr>
                <td style="padding: 10px; font-size: 7.5pt; text-align: justify; line-height: 1.3;">
                    1- OBRIGATÓRIO O USO DO DISCO DO TACÓGRAFO E DISCO-DIAGRAMA DURANTE TODA A VIAGEM.<br>
                    2- NÃO UTILIZAR QUALQUER TIPO DE ENTORPECENTES E OU BEBIDAS ALCOÓLICAS DURANTE TODA A VIAGEM.<br>
                    3- OBSERVAR E OBEDECER A LIMITES DE VELOCIDADE MAXIMA PERMITIDA POR LEI NO LOCAL EM QUE TRANSITA OU DE ACORDO COM AS CONDIÇÕES DE PISTA E CLIMA APRESENTADAS NO MOMENTO.<br>
                    4- O VEICULO TRANSPORTADOR DEVE ESTAR EM CONDIÇÕES DE TRANSPORTE DE ACORDO COM O TIPO E NATUREZA DA CARGA TRANSPORTADA, INCLUINDO PNEUS, LONA, ETC.<br>
                    5- APÓS QUALQUER PARADA, SEMPRE VISTORIAR O VEICULO ANTES DE REINICIAR A VIAGEM, EVITANDO ASSIM SABOTAGENS.<br>
                    6- OBSERVAR O ESTADO DA CARGA DURANTE A VIAGEM E VERIFICAR SE HOUVE VIOLAÇÃO DE LACRES E EMBALAGENS.<br>
                    7- NÃO REVELAR A NATUREZA DA CARGA, DESTINO E ROTA PARA PESSOAS DESCONHECIDAS.<br>
                    8- PARA CARGAS RASTREADAS: EM TODA E QUALQUER PARADA, O VEICULO DEVERÁ SER BLOQUEADO E O SISTEMA DE RASTREAMENTO DEVERÁ SER MANTIDO O ATIVO DURANTE TODO O PERIODO, TRANSMITINDO A CADA HORA O STATUS DOS SENSORES, ATUADORES E LOCALIZAÇÃO DO VEICULO.<br>
                    9- PROIBIDO DAR CARONA.<br>
                    10- RESPEITE OS INTERVALOS DE DESCANSO ENTRE JORNADAS ESTABELECIDAS POR LEI.<br>
                    11- EM CASO DE ACIDENTE OU FURTO, AVISAR IMEDIATAMENTE A TRANSPORTADORA ATRAVES DO TELEFONE: 92 98119-4151<br>
                    1*- O PAGAMENTO DO SALDO ESTÁ CONDICIONADO AO RECEBIMENTO DOS DOCUMENTOS QUE COMPROVEM O DESCARREGAMENTO.<br><br>
                    DECLARO QUE LI, ENTENDI, ESTOU CIENTE DAS CONDIÇÕES, E ACEITO TODOS OS TERMOS DO CONTRATO BEM COMO OS VALORES E AS CONDIÇÕES ACORDADAS.
                </td>
            </tr>
        </table>
        
        <div style="margin-top: 100px; text-align: center; font-size: 11pt; font-weight: bold;">
            <div style="margin-bottom: 30px;">
                <hr style="border: 1px solid black; width: 60%; margin: 0 auto 5px auto;">
                {dados['transp_nome']}<br>
                <span style="font-weight: normal;">CNPJ: {dados['transp_cnpj']}</span>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content
    
def main():
    st.set_page_config(page_title="Gerador Rodo Amazônia", layout="centered")
    st.title("🚛 Gerador de Contrato - Rodo Amazônia")
    
    # --- NOVIDADE: Controle de sessão para limpar o uploader ---
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    # -----------------------------------------------------------

    # 1. Entrada do Valor/Tonelada na interface visual
    valor_tonelada = st.number_input("Digite o Valor / Tonelada (R$)", min_value=0.0, format="%.2f", step=0.10)
    
    # 2. Upload de Arquivos
    st.write("### Anexe seus documentos abaixo")
    
    # --- NOVIDADE: Adicionamos o parâmetro 'key' amarrado ao estado de sessão ---
    arquivos_enviados = st.file_uploader(
        "Arraste seus PDFs e XMLs aqui", 
        accept_multiple_files=True, 
        type=['pdf', 'xml'],
        key=f"uploader_{st.session_state.uploader_key}"
    )
    
    # --- NOVIDADE: Botão para excluir todos os arquivos ---
    if arquivos_enviados:
        if st.button("🗑️ Limpar todos os anexos"):
            st.session_state.uploader_key += 1
            st.rerun() # Atualiza a página imediatamente limpando a caixa
    # ------------------------------------------------------

    if arquivos_enviados:
        if st.button("Gerar Contrato 📄"):
            with st.spinner('Processando documentos...'):
                
                # Dicionário inicial de dados completo
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
                    "cliente_nome": "", "cliente_cnpj": "", "cliente_ie": "",
                    "mercadoria": ""
                }
                
                # Processamento em Memória
                for arquivo in arquivos_enviados:
                    conteudo = arquivo.read()
                    
                    if arquivo.name.lower().endswith('.pdf'):
                        try:
                            with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
                                texto_pdf = "".join([pagina.extract_text() or "" for pagina in pdf.pages])
                                extrair_dados_pdf(texto_pdf, dados)
                        except Exception as e:
                            st.error(f"Erro ao ler o PDF {arquivo.name}: {e}")
                            
                    elif arquivo.name.lower().endswith('.xml'):
                        try:
                            texto_xml = conteudo.decode('utf-8', errors='ignore')
                            extrair_dados_xml(texto_xml, dados)
                        except Exception as e:
                            st.error(f"Erro ao ler o XML {arquivo.name}: {e}")
                
                # Consolidação das chaves
                chaves_nfe_definitivas = dados["xml_chaves_nfe"] if dados["xml_chaves_nfe"] else dados["pdf_chaves_nfe"]
                chaves_cte_definitivas = dados["xml_chaves_cte"] if dados["xml_chaves_cte"] else dados["pdf_chaves_cte"]
                
                # --- NOVIDADE: RESOLUÇÃO DE PESO INTELIGENTE ---
                pesos_cte = dados.get("pesos_cte", [])
                pesos_nfe = dados.get("pesos_nfe", [])
                peso_xml_final = 0.0

                if pesos_cte:
                    # Se enviou CT-e, ele tem a carga total consolidada (não duplicamos)
                    peso_xml_final = max(pesos_cte) 
                elif pesos_nfe:
                    # Se enviou apenas NF-es (e nenhum CTe), soma todas as notas avulsas
                    peso_xml_final = sum(pesos_nfe)
                
                
                # Se encontrou peso válido no XML, formata para Tonelada e sobrepõe o PDF
                if peso_xml_final > 0:
                    dados["volume_carregado"] = normalizar_peso_para_ton(peso_xml_final)
                # Busca de endereço na Receita Federal (BrasilAPI)
                if dados["transp_cnpj"] and not dados["transp_end"]:
                    st.info(f"Buscando endereço oficial na Receita Federal para o CNPJ: {dados['transp_cnpj']}...")
                    endereco_encontrado = buscar_endereco_por_cnpj(dados["transp_cnpj"])
                    if endereco_encontrado:
                        dados["transp_end"] = endereco_encontrado
                    else:
                        dados["transp_end"] = "ENDEREÇO NÃO LOCALIZADO"

                # Limpeza de dados repetidos
                dados["nfes"] = list(set(dados["nfes"]))
                dados["ctes"] = list(set(dados["ctes"]))
                dados["mdfes"] = list(set(dados["mdfes"]))
                dados["chaves_nfe"] = list(set(chaves_nfe_definitivas))
                dados["chaves_cte"] = list(set(chaves_cte_definitivas))

                # Cálculos Financeiros
                volume_encontrado = dados.get("volume_carregado", 0.0)
                rendimento_bruto = volume_encontrado * valor_tonelada
                valor_pedagio = dados.get("valor_pedagio", 0.0)
                valor_liquido = rendimento_bruto - valor_pedagio
                
                # Atualizando os dados financeiros no dicionário final
                dados["volume_carregado"] = volume_encontrado
                dados["valor_tonelada"] = valor_tonelada
                dados["rendimento_bruto"] = rendimento_bruto
                dados["valor_liquido"] = valor_liquido
                
                # 3. Gerar o HTML
                html_contrato = gerar_contrato_html(dados)
                
                st.success("✅ Contrato gerado com sucesso!")
                
                # Exibir Resumo na Tela para o usuário validar
                st.subheader("Resumo Financeiro")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Volume Total:** {volume_encontrado:.3f} TON")
                    st.write(f"**Valor/Ton:** R$ {formatar_moeda(valor_tonelada)}")
                with col2:
                    st.write(f"**Pedágio:** R$ {formatar_moeda(valor_pedagio)}")
                    st.write(f"**VALOR LÍQUIDO:** R$ {formatar_moeda(valor_liquido)}")

                # 4. Botão de Download do HTML Gerado
                st.download_button(
                    label="⬇️ Baixar Contrato HTML",
                    data=html_contrato,
                    file_name="Contrato_Rodo_Amazonia.html",
                    mime="text/html"
                )

# Ponto de entrada EXCLUSIVO do Streamlit
if __name__ == "__main__":
    main()
