import streamlit as st
import time, re, base64
# Importando suas peças modulares
from utils import reiniciar_aplicativo, formatar_moeda, formatar_chave, formatar_cnpj, placa_valida, limpar_valor_formatado
from servicos import buscar_endereco_por_cnpj, gerar_contrato_html, gerar_contrato_servico_html, processar_documentos_fiscais
    
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
        st.success("✅ Documentação identificada! O contrato seguirá para o formato de NFS.")
        
        # Processa os dados extraídos da Nota
        dados = processar_documentos_fiscais(arquivos)

        st.markdown("---")
        st.subheader("📝 Inserção da Nota de Serviço")

        # 1. LINHA DE CONFERÊNCIA (NOTAS E XML LADO A LADO)
        col_n, col_x = st.columns([1, 3])
        with col_n:
            st.text_input("NOTAS FISCAIS", value=" ".join(dados["nfes"]), disabled=True)
        with col_x:
            st.text_input("XML", value=" / ".join([formatar_chave(c) for c in dados["chaves_nfe"]]), disabled=True)
        nfs_manual_input = st.text_input("NÚMERO DA NFS (SERVIÇO)", value="", placeholder="Digite apenas números...")
        # =====================================================================
        # NOVA TRAVA: Bloqueia se estiver vazio OU se houver letras/símbolos
        # =====================================================================
        entrada_limpa = nfs_manual_input.strip()

        if not entrada_limpa:
            st.info("ℹ️ Insira o número da Nota de Serviço para prosseguir.")
            st.stop()

        if not entrada_limpa.isdigit():
            st.error("⚠️ Erro: O campo 'NÚMERO DA NFS' deve conter **apenas números**.")
            st.stop()
        # =====================================================================
    # O código abaixo só vai aparecer na tela DEPOIS que o campo acima for preenchido

        # 2. DADOS DO SUBCONTRATADO (BUSCA AUTOMÁTICA POR CNPJ)
        st.markdown("---")
        st.subheader("🚛 Dados do Subcontratado")

        # 1. Entrada do CNPJ
        cnpj_input = st.text_input("DIGITE O CPF / CNPJ DO SUBCONTRATADO", value=st.session_state.get("transp_cnpj_last", ""))
        cnpj_limpo = re.sub(r'\D', '', cnpj_input)

        # 2. Lógica de Limpeza / Trava se estiver vazio
        if not cnpj_limpo:
            st.session_state.transp_nome = ""
            st.session_state.transp_end = ""
            st.session_state.transp_cnpj_last = ""
            st.info("ℹ️ Por favor, insira o CNPJ para visualizar os dados do subcontratado.")
            st.stop() # Aqui o stop é útil para não mostrar os campos vazios abaixo

        # 3. Bloco de Bloqueados (Filiais Próprias)
        bloqueados = [
            "32368678000118", "32368678000207", "32368678000380",
            "32368678000460", "32368678000541", "32368678000622",
            "32368678000703"
        ]

        if cnpj_limpo in bloqueados:
            st.error("🚫 **BLOQUEADO:** Este CNPJ pertence a uma das filiais da **Rodo Amazônia**. Não é permitido emitir contrato de terceiro para filiais próprias.")
            st.stop()

        # 4. Lógica de Busca Automática (Só dispara se for um CNPJ novo de 14 dígitos)
        if len(cnpj_limpo) == 14 and cnpj_limpo != st.session_state.get("transp_cnpj_last", ""):
            with st.spinner("Buscando dados oficiais..."):
                res = buscar_endereco_por_cnpj(cnpj_limpo)
                if res:
                    st.session_state.transp_nome = res["razao_social"]
                    st.session_state.transp_end = res["endereco"]
                    st.session_state.transp_cnpj_last = cnpj_limpo
                    st.rerun()
                else:
                    st.error("⚠️ CNPJ não localizado na base da Receita.")

        # 5. Exibição Visual (Apenas leitura)
        col_sub1, col_sub2 = st.columns([1, 1])
        with col_sub1:
            st.text_input("RAZÃO SOCIAL", value=st.session_state.get("transp_nome", ""), disabled=True)
        with col_sub2:
            st.text_input("ENDEREÇO", value=st.session_state.get("transp_end", ""), disabled=True)

        # 6. Atualização do dicionário 'dados' para a geração do PDF
        dados["transp_cnpj"] = formatar_cnpj(cnpj_limpo)
        dados["transp_nome"] = st.session_state.get("transp_nome", "")
        dados["transp_end"] = st.session_state.get("transp_end", "")

        # --- DENTRO DO BLOCO DE MOTORISTA E VEÍCULO ---
        if dados.get("transp_nome") and dados.get("transp_end"):
            st.markdown("---")
            st.subheader("🚛 Motorista e Veículo")

            # --- DENTRO DO BLOCO DE MOTORISTA E VEÍCULO ---
            col_mot1, col_mot2 = st.columns([2, 1])
            with col_mot1:
                nome_mot = st.text_input("NOME DO MOTORISTA*", value=dados.get("motorista", "")).upper()
                dados["motorista"] = nome_mot

            with col_mot2:
                cpf_valor_atual = dados.get("cpf_motorista", "")
                cpf_input = st.text_input("CPF DO MOTORISTA*", value=cpf_valor_atual, placeholder="000.000.000-00")
                cpf_limpo = re.sub(r'\D', '', cpf_input) # Limpa apenas números
                dados["cpf_motorista"] = cpf_limpo

            col_v1, col_v2, col_v3 = st.columns(3)
            with col_v1:
                placa_cav = st.text_input("PLACA CAVALO*", value=dados.get("placa_cavalo", ""), placeholder="Ex: OAO7809").upper()
                dados["placa_cavalo"] = placa_cav
            with col_v2:
                p_carreta1 = st.text_input("PLACA CARRETA 1", value=dados.get("placa_carreta1", ""), placeholder="Opcional").upper()
            with col_v3:
                p_carreta2 = st.text_input("PLACA CARRETA 2", value=dados.get("placa_carreta2", ""), placeholder="Opcional").upper()

            # =====================================================================
            # TRAVAS DE VALIDAÇÃO (Agora as variáveis sempre existem)
            # =====================================================================

            # 1. Verifica campos obrigatórios vazios
            if not nome_mot.strip() or not cpf_limpo.strip() or not placa_cav.strip():
                st.warning("⚠️ Os campos marcados com **( * )** são obrigatórios. Por favor, preencha o Nome, CPF e Placa do Cavalo.")
                st.stop()

            # 2. Valida o formato da Placa do Cavalo (OBRIGATÓRIA)
            if not placa_valida(placa_cav):
                st.error(f"❌ A PLACA CAVALO '{placa_cav}' está em um formato inválido. Use o padrão AOT1249 ou AOT1B49.")
                st.stop()

            # 3. Valida CPF (Se não tiver 11 dígitos)
            if len(cpf_limpo) != 11:
                st.error("❌ O CPF deve conter exatamente 11 números.")
                st.stop()

            # 4. Valida Carretas (Apenas se preenchidas)
            v_c1 = p_carreta1.strip()
            if v_c1:
                if not placa_valida(v_c1):
                    st.error(f"❌ A PLACA CARRETA 1 '{v_c1}' está em um formato inválido.")
                    st.stop()
            dados["placa_carreta1"] = v_c1

            v_c2 = p_carreta2.strip()
            if v_c2:
                if not placa_valida(v_c2):
                    st.error(f"❌ A PLACA CARRETA 2 '{v_c2}' está em um formato inválido.")
                    st.stop()
            dados["placa_carreta2"] = v_c2

            # =====================================================================

            # Lógica da Carreta 3 (Processada após todas as validações)
            if p_carreta1 and p_carreta2:
                dados["placa_carreta3"] = f"{p_carreta1} / {p_carreta2}"
            else:
                dados["placa_carreta3"] = p_carreta1 or p_carreta2 or ""

            # --- PAUSA DINÂMICA 2: Só mostra o restante se os campos do motorista/veículo estiverem preenchidos ---
            # Requisitos: Motorista, CPF, Placa Cavalo e pelo menos uma Carreta
            if dados.get("motorista") and dados.get("cpf_motorista") and dados.get("placa_cavalo"):
                
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
                    desconto_txt = st.text_input("DESCONTOS (R$)", value="0,00", key="descontos_nfe")
                    descontos_edit = limpar_valor_formatado(desconto_txt)
                    
                    pedagio_txt = st.text_input("PEDÁGIO (R$)", value=formatar_moeda(dados.get("valor_pedagio", 0.0)))
                    pedagio_edit = limpar_valor_formatado(pedagio_txt)

                # Cálculo e exibição do Valor Líquido (Bloqueado para edição)
                valor_liquido_auto = rendimento_bruto_edit - pedagio_edit - descontos_edit
                st.text_input("VALOR LÍQUIDO FINAL (R$)", value=formatar_moeda(valor_liquido_auto), disabled=True)

                # --- BOTÃO DE GERAR CONTRATO ---
                st.markdown("---")
                if st.button("📄 EMITIR CONTRATO DE SUBCONTRATAÇÃO (NFS)", use_container_width=True):
                    if frete_edit > 0 and volume_edit > 0:
                        with st.spinner("Preparando documento..."):
                            # 1. Atualiza o dicionário de dados com as edições da tela
                            dados["nfs_manual"] = nfs_manual_input
                            dados["mercadoria"] = mercadoria_edit
                            dados["volume_carregado"] = volume_edit 
                            dados["frete_unitario"] = frete_txt    
                            dados["rendimento_bruto"] = rendimento_bruto_edit
                            dados["descontos"] = descontos_edit
                            dados["valor_pedagio"] = pedagio_edit
                            dados["valor_liquido"] = valor_liquido_auto
                            
                            # Define a placa principal (para uso futuro ou nomeação)
                            placa_ref = dados.get("placa_cavalo", "SEM_PLACA")
                            
                            # 2. Gera o HTML usando o template de serviço
                            try:
                                html_contrato = gerar_contrato_servico_html(dados)
                                
                                if html_contrato:
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
                                    
                                    st.success("✅ Contrato gerado! Reiniciando o sistema em 3 segundos...")
                                    time.sleep(3)
                                    reiniciar_aplicativo()
                                    
                            except Exception as e:
                                st.error(f"Erro ao gerar contrato: {e}")
                    else:
                        st.error("⚠️ O relatório não pode ser emitido porque o Frete Unitário ou Volume estão zerados.")
            else:
                st.info("💡 Informe o **Motorista,  CPF e Placa Cavalo** para liberar o fechamento financeiro.")
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
        st.success("✅ Documentação identificada! O contrato seguirá para o formato de CT-E SUBCONTRATADO.")
        # Obtém os valores sugeridos pela leitura automática
        pesos_cte = dados.get("pesos_cte", [])
        pesos_nfe = dados.get("pesos_nfe", [])
        peso_kg_sugerido = sum(pesos_cte) if pesos_cte else sum(pesos_nfe)
        
        try:
            pedagio_sugerido = float(dados.get("valor_pedagio", 0.0))
        except:
            pedagio_sugerido = 0.0

        # --- A SEÇÃO ABAIXO AGORA ESTÁ DENTRO DO 'IF ARQUIVOS' ---
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

        col_mot_cte, col_cpf_cte = st.columns([2, 1])
        with col_mot_cte:
            dados["motorista"] = st.text_input("NOME DO CONDUTOR", value=dados.get("motorista", "")).upper()
        with col_cpf_cte:
            dados["cpf_motorista"] = st.text_input("CPF DO CONDUTOR", value=dados.get("cpf_motorista", ""))

        # Campos do Motorista adicionados ACIMA da Mercadoria
        st.markdown("---")
        st.subheader("📝 Dados Financeiros do Contrato")
        col1, col2 = st.columns(2)
        with col1:
            mercadoria_edit = st.text_input("MERCADORIA", value=dados.get("mercadoria", "Diversos"))
            
            # --- VOLUME EDITÁVEL COM FORMATAÇÃO ---
            volume_inicial = float(dados.get("volume_carregado", 0.0))
            volume_edit = st.number_input("VOLUME/PESO CARREGADO", value=volume_inicial, step=0.001)
            
            frete_txt = st.text_input("FRETE UNITÁRIO (R$/TON)", value="0,00", key="frete_cte")
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
                    try:
                        # Todo o seu código de preenchimento do dicionário e geração do HTML vem aqui
                        dados["valor_tonelada"] = formatar_moeda(frete_edit)
                        valor_liquido_final = rendimento_bruto_edit - pedagio_edit - descontos_edit
                        # 2. Atualiza o dicionário de dados
                        dados["mercadoria"] = mercadoria_edit
                        dados["volume_carregado"] = volume_edit
                        dados["frete_unitario"] = frete_txt
                        dados["rendimento_bruto"] = rendimento_bruto_edit
                        dados["descontos"] = descontos_edit  
                        dados["valor_pedagio"] = pedagio_edit
                        dados["valor_liquido"] = valor_liquido_final

                        # 3. Define a placa de forma segura
                        placa_cavalo = dados.get("placa_cavalo", "SEM_PLACA")
                        dados["veic_placa"] = placa_cavalo
                        nome_arquivo = f"Contrato_{placa_cavalo}.html"
                        
                        # 4. Gera o HTML
                        html_contrato = gerar_contrato_html(dados)
                        
                        # 5. ABRIR RELATÓRIO EM NOVA GUIA
                        if html_contrato:
                            b64 = base64.b64encode(html_contrato.encode()).decode()
                            
                            # JavaScript para abrir nova aba e injetar o HTML
                            js_open_tab = f"""
                            <script>
                                const b64 = '{b64}';
                                const html = decodeURIComponent(escape(window.atob(b64)));
                                const win = window.open("", "_blank");
                                if (win) {{
                                    win.document.write(html);
                                    win.document.close();
                                }} else {{
                                    alert("O navegador bloqueou a abertura da nova guia. Por favor, permita pop-ups para este site.");
                                }}
                            </script>
                            """ 
                            st.components.v1.html(js_open_tab, height=0)
                
                            # --- LÓGICA DE REINÍCIO ---
                            st.success("✅ Contrato gerado! Reiniciando o sistema em 3 segundos...")
                            time.sleep(3)
                            reiniciar_aplicativo()

                    except Exception as e:
                        st.error(f"Erro ao gerar contrato CT-E: {e}")

            elif (frete_edit <= 0):
                st.error("⚠️ O relatório não pode ser emitido porque o Frete Unitário (R$/Ton) não foi informado.")
            else:
                st.error("⚠️ O relatório não pode ser emitido porque o Volume/Peso Carregado não foi informado.")
# Ponto de entrada EXCLUSIVO do Streamlit
if __name__ == "__main__":
    main()