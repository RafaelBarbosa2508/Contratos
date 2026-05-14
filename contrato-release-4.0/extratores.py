import pdfplumber
import re
from utils import formatar_cnpj, eh_chave_valida, validar_cpf

# ----- FUNÇÕES ABAIXO -----#

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

    # === 1. NOVO BLOCO: MERCADORIA (CT-e) ===
    if "<infcte" in texto_xml_lower:
        # No CT-e o produto fica na tag <proPred> (Produto Predominante)
        produto_cte = re.search(r"<(?:\w+:)?proPred[^>]*>(.*?)</(?:\w+:)?proPred>", texto_xml, re.IGNORECASE)
        if produto_cte and not dados.get("mercadoria"):
            dados["mercadoria"] = produto_cte.group(1).upper()

    # 4. BUSCA DE VOLUME ESPECÍFICO (SOMA de todos os blocos cUnid = 03 no CT-e)
    if "<infcte" in texto_xml_lower:
        blocos_infq = re.findall(r'<infq[^>]*>.*?</infq>', texto_xml_lower, re.DOTALL)
        
        for bloco in blocos_infq:
            if '<cunid>03</cunid>' in bloco or '<cunid>3</cunid>' in bloco:
                match = re.search(r'<qcarga>([\d.]+)</qcarga>', bloco)
                if match:
                    # Agora somamos direto no acumulador principal
                    dados["volume_carregado"] += float(match.group(1))

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

    # --- EXTRAÇÃO DO REMETENTE (UNIFICADA: Prioriza CT-e <rem>, depois NF-e <emit>) ---
    bloco_remetente = None
    tag_endereco_tipo = ""

    # 1. Tenta identificar primeiro o caso de CT-e (<rem>)
    match_rem = re.search(r"<rem>(.*?)</rem>", texto_xml, re.IGNORECASE | re.DOTALL)
    if match_rem:
        bloco_remetente = match_rem.group(1)
        tag_endereco_tipo = "enderReme"
    else:
        # 2. Se não encontrar <rem>, tenta o caso de NF-e (<emit>)
        match_emit = re.search(r"<emit>(.*?)</emit>", texto_xml, re.IGNORECASE | re.DOTALL)
        if match_emit:
            bloco_remetente = match_emit.group(1)
            tag_endereco_tipo = "enderEmit"

    # Se algum dos dois foi encontrado, extraímos os dados
    if bloco_remetente:
        # Nome e CNPJ são tags comuns a ambos os blocos
        nome_xml = re.search(r"<xNome>(.*?)</xNome>", bloco_remetente, re.IGNORECASE)
        cnpj_xml = re.search(r"<CNPJ>(.*?)</CNPJ>", bloco_remetente, re.IGNORECASE)
        
        if nome_xml and not dados.get("remetente_nome"):
            dados["remetente_nome"] = nome_xml.group(1).upper()
        if cnpj_xml and not dados.get("remetente_cnpj"):
            dados["remetente_cnpj"] = formatar_cnpj(cnpj_xml.group(1))

        # Busca o endereço usando a tag dinâmica definida acima
        ender_match = re.search(f"<{tag_endereco_tipo}>(.*?)</{tag_endereco_tipo}>", bloco_remetente, re.IGNORECASE | re.DOTALL)
        if ender_match:
            bloco_ender = ender_match.group(1)
            lgr = re.search(r"<xLgr>(.*?)</xLgr>", bloco_ender, re.IGNORECASE)
            nro = re.search(r"<nro>(.*?)</nro>", bloco_ender, re.IGNORECASE)
            cpl = re.search(r"<xCpl>(.*?)</xCpl>", bloco_ender, re.IGNORECASE)
            bairro = re.search(r"<xBairro>(.*?)</xBairro>", bloco_ender, re.IGNORECASE)
            mun = re.search(r"<xMun>(.*?)</xMun>", bloco_ender, re.IGNORECASE)
            uf = re.search(r"<UF>(.*?)</UF>", bloco_ender, re.IGNORECASE)
            
            # Montagem do endereço formatado
            partes = []
            if lgr: partes.append(lgr.group(1))
            if nro: partes.append(nro.group(1))
            if cpl: partes.append(cpl.group(1))
            if bairro: partes.append(bairro.group(1))
            
            if not dados.get("remetente_end"):
                dados["remetente_end"] = " - ".join(partes).upper()
            
            # Salva a Cidade/UF na variável 'origem' para o relatório
            if mun and uf and not dados.get("origem"):
                dados["origem"] = f"{mun.group(1)} / {uf.group(1)}".upper()

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
    
    # --- NOVA LÓGICA: EXTRAÇÃO DE CNPJ EM xObs (CT-e) ---
    if "<infcte" in texto_xml_lower:
        # Busca o conteúdo da tag xObs
        xobs_match = re.search(r"<xObs>(.*?)</xObs>", texto_xml, re.IGNORECASE | re.DOTALL)
        if xobs_match:
            texto_obs = xobs_match.group(1)
            # Regex para encontrar um CNPJ (com ou sem pontos/traços)
            cnpj_na_obs = re.search(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", texto_obs)
            
            if cnpj_na_obs and not dados.get("transp_cnpj"):
                # Captura o CNPJ e limpa a formatação
                dados["transp_cnpj"] = formatar_cnpj(cnpj_na_obs.group(1))

def extrair_dados_pdf(texto_pdf, dados):
    """Analisa o PDF para identificar se é um Cartão CNPJ ou contém Chaves"""
    texto_upper = texto_pdf.upper()
    
    # Se for Cartão CNPJ, extrai o endereço
    if "COMPROVANTE DE INSCRIÇÃO" in texto_upper and "SITUAÇÃO CADASTRAL" in texto_upper:
        # Se for um cartão CNPJ, extrai o endereço e a Razão Social direto do texto
        endereco_extraido = extrair_endereco_cnpj_card(texto_pdf)
        if endereco_extraido:
            dados["transp_end"] = endereco_extraido
        
        # Tenta pegar a Razão Social que vem logo após o CNPJ no PDF
        rs_match = re.search(r"NOME EMPRESARIAL\s+(.*)", texto_upper)
        if rs_match:
            dados["transp_nome"] = rs_match.group(1).strip()
    
    # Mantemos a busca de chaves no PDF como segurança
    chaves = re.findall(r'\d{44}', texto_pdf)
    for c in chaves:
        if c not in dados["chaves_cte"] and c not in dados["chaves_nfe"]:
            if "DANFE" in texto_upper:
                dados["chaves_nfe"].append(c)
            else:
                dados["chaves_cte"].append(c)

def extrair_endereco_cnpj_card(texto_pdf):
    """Lógica específica para extrair endereço do PDF do Cartão CNPJ da Receita"""
    texto_upper = texto_pdf.upper()
    try:
        # Exemplo simplificado de busca de logradouro no layout da Receita
        logradouro = re.search(r"LOGRADOURO\s+(.*)", texto_upper)
        numero = re.search(r"NÚMERO\s+(.*)", texto_upper)
        bairro = re.search(r"BAIRRO/DISTRITO\s+(.*)", texto_upper)
        municipio = re.search(r"MUNICÍPIO\s+(.*)", texto_upper)
        uf = re.search(r"UF\s+(.*)", texto_upper)
        cep = re.search(r"CEP\s+(.*)", texto_upper)

        if logradouro and municipio:
            end = f"{logradouro.group(1).strip()}, {numero.group(1).strip()} - {bairro.group(1).strip()}. {municipio.group(1).strip()} - {uf.group(1).strip()}. CEP: {cep.group(1).strip()}"
            return end.replace  ("  ", " ")
    except:
        return None
    return None
