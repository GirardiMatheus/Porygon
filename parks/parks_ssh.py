import logging
from dotenv import load_dotenv
import pexpect
import os
import time

def setup_logging():
    """Configura o sistema de logging com rotação de arquivos"""
    logging.basicConfig(
        filename=f"OLT_LOG.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.info("="*50)
    logging.info("Iniciando nova sessão de conexão OLT")
    logging.info("="*50)

def log_interaction(action, details="", level="info"):
    """Função padronizada para registro de logs"""
    message = f"{action.upper()} | {details}"
    if level.lower() == "debug":
        logging.debug(message)
    elif level.lower() == "warning":
        logging.warning(message)
    elif level.lower() == "error":
        logging.error(message)
    else:
        logging.info(message)



# Carrega variáveis do arquivo .env
load_dotenv()
setup_logging()

ssh_userp = os.getenv('SSH_USER_PARKS')
ssh_passwdp = os.getenv('SSH_PASSWORD_PARKS')

def login_ssh(host=None):
    log_interaction(host)
    try:
        child = pexpect.spawn(f"ssh {ssh_userp}@{host}", encoding='utf-8', timeout=30)
        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)
        if index == 1:
            child.sendline("yes")
            child.expect("password:")
        child.sendline(ssh_passwdp)
        login_success = child.expect([r"#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            log_interaction("Conexão estabelecida", f"Conectado à OLT {host}")
            print(f"✅ Conectado com sucesso à OLT {host}")

        else:
            log_interaction("Erro SSH", "Não foi possível autenticar na OLT", "error")
            print("❌ Falha na autenticação")
    
        return child
    
    except pexpect.EOF:
        log_interaction("Erro SSH", "Conexão fechada inesperadamente", "error")
        print("❌ Erro: Conexão foi fechada antes do login.")
        
    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Falha na conexão SSH: {str(e)}"
        log_interaction("Erro SSH", error_msg, "error")
        print(error_msg)
        return None
        
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        log_interaction("Erro geral", error_msg, "error")
        print(error_msg)
        return None


def list_unauthorized(child):
    try:
        # Envia o comando e captura a saída
        child.sendline('show gpon blacklist')
        child.expect('#')
        output = child.before.strip()

        # Dicionário para armazenar os dados
        onu_dict = {}
        
        for line in output.splitlines():
            line = line.strip()
            
            if not line.startswith(('0 |', '1 |', '2 |', '3 |', '4 |', '5 |', '6 |', '7 |', '8 |', '9 |')):
                continue
            
            parts = [part.strip() for part in line.split('|')]
            
            if len(parts) < 3:
                continue
            
            slot, port, serial = parts[0], parts[1], parts[2]
            
            if (not slot.isdigit() or int(slot) > 64 or
                not port.isdigit() or int(port) > 128 or
                not serial or len(serial) < 6 or ' ' in serial):
                continue
            
            # Adiciona ao dicionário: serial como chave, slot e port como valores
            onu_dict[serial] = {
                'slot': slot,
                'pon': port
            }

        return onu_dict if onu_dict else None

    except Exception as e:
        logging.error(f"Erro ao listar ONUs não autorizadas: {e}")
        return None


def consult_information(child, serial, max_attempts=20, delay_between_attempts=5):
    try:
        serial = serial.strip().lower()
        log_interaction(f"Iniciando consulta para ONU {serial}")

        # Validação do serial
        if len(serial) != 12:
            log_interaction(f"Serial inválido: deve ter 12 caracteres (recebido: {serial})", level="ERROR")
            return None

        data_template = {
            "serial": serial,
            "alias": None,
            "model": None,
            "power_level": None,
            "distance_km": None,
            "pon": None,
            "status": None
        }

        comando = f"show gpon onu {serial} summary"
        attempt = 1
        output = None

        while attempt <= max_attempts:
            try:
                log_interaction(f"Tentativa {attempt}/{max_attempts} - Enviando comando: {comando}")
                
                child.sendline(comando)
                time.sleep(15)
                
                # Padrões para verificação
                patterns = ["#", "% Unknown command", pexpect.TIMEOUT, pexpect.EOF]
                result = child.expect(patterns, timeout=20)
                
                # Tratamento específico para comando desconhecido
                if result == 1: 
                    log_interaction("Comando não reconhecido pela OLT", level="ERROR")
                    print("\nErro: ONU/ONT não encontrada na OLT selecionada (comando inválido)")
                    return None
                
                elif result != 0: 
                    raise Exception("Timeout ou fim de conexão")
                
                output = child.before.strip()
                log_interaction(f"Resposta bruta recebida: {output[:200]}...")

                # Verificações de resposta
                if "not found" in output.lower():
                    log_interaction(f"ONU {serial} não encontrada na OLT", level="WARNING")
                    print("\nAviso: ONU/ONT não encontrada na OLT")
                    return None
                
                if "Serial" in output and "Interface" in output:
                    break

                raise Exception("Resposta incompleta ou inválida")

            except Exception as e:
                log_interaction(f"Falha na tentativa {attempt}: {str(e)}", level="WARNING")
                attempt += 1
                if attempt <= max_attempts:
                    time.sleep(delay_between_attempts)
                continue

        if attempt > max_attempts:
            log_interaction(f"Falha após {max_attempts} tentativas", level="ERROR")
            print("\nErro: Limite de tentativas excedido")
            return None

        # Processamento dos dados
        for line in output.splitlines():
            line = line.strip()
            
            if line.startswith("Alias"):
                data_template["alias"] = line.split(":")[1].strip()
            
            elif line.startswith("Interface"):
                data_template["pon"] = line.split(":")[1].strip()

            elif line.startswith("Model"):
                data_template["model"] = line.split(":")[1].strip()
            
            elif line.startswith("Power Level"):
                power_str = line.split(":")[1].strip()
                data_template["power_level"] = power_str.split()[0].strip()
            
            elif line.startswith("Distance"):
                distance_str = line.split(":")[1].strip()
                data_template["distance_km"] = round(int(distance_str.split()[0]) / 1000, 2)
            
            elif line.startswith("Status"):
                status_str = line.split(":")[1].strip()
                data_template["status"] = status_str.split()[0].strip()

        log_interaction(f"Consulta concluída para ONU {serial}")
        return data_template

    except Exception as e:
        log_interaction(f"Erro crítico: {str(e)}", level="ERROR")
        print(f"\nErro crítico: {str(e)}")
        return None


def add_onu_to_pon(child, serial, pon):
    try:
        # Log de interação
        logging.info(f"Iniciando adição da ONU {serial} na PON {pon}")
        
        # Comandos de configuração
        child.sendline("configure terminal")
        child.expect("#")
        time.sleep(5)
        child.sendline(f"interface gpon1/{pon}")
        child.expect("#")
        time.sleep(5)
        child.sendline(f"onu add serial-number {serial}")
        child.expect("#")
        time.sleep(10)
        log_interaction(f"onu add serial-number {serial}")
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        time.sleep(10) 
        
        # Verifica se foi bem-sucedido
        if child.before.find("% Serial already exists.") != -1:
            logging.error(f"ONU {serial} já se encontra na PON {pon}")
            return False
        else:
            logging.info(f"ONU {serial} adicionada com sucesso na PON {pon}")
            return True
            
    except Exception as e:
        logging.error(f"Erro durante adição da ONU: {str(e)}")
        return False

def auth_bridge(child, serial, pon, nome, profile, vlan):
    try:
        log_interaction(f"Iniciando autorização bridge para ONU {serial} na PON {pon} - Nome: {nome}, Profile: {profile}, VLAN: {vlan}")
        
        # Entrar no modo de configuração
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        log_interaction("Modo de configuração acessado com sucesso")
        
        # Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        log_interaction(f"Interface gpon1/{pon} acessada com sucesso")
        
        # Configurar alias
        log_interaction(f"Configurando alias '{nome}' para ONU {serial}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar alias para ONU {serial}")
        log_interaction("Alias configurado com sucesso")
        
        # Configurar profile
        log_interaction(f"Configurando profile {profile} para ONU {serial}")
        child.sendline(f"onu {serial} flow {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar profile {profile} para ONU {serial}")
        log_interaction("Profile configurado com sucesso")
        
        # Configurar VLAN
        log_interaction(f"Configurando VLAN {vlan} para ONU {serial}")
        child.sendline(f"onu {serial} vlan _{vlan} uni-port 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar VLAN {vlan} para ONU {serial}")
        log_interaction("VLAN configurada com sucesso")
        
        # Sair das configurações
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        
        # Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        log_interaction("Configuração salva com sucesso")
        
        log_interaction(f"ONU {serial} autorizada em modo bridge com sucesso - PON: {pon}, Nome: {nome}, Profile: {profile}, VLAN: {vlan}")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao autorizar ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False

def auth_router_default(child, serial, nome, vlan, pon, profile, login_pppoe, senha_pppoe):
    if not vlan.isdigit():
        raise ValueError(f"VLAN inválida: {vlan}. Deve ser numérica")
    try:
        log_interaction(f"Iniciando autenticação no modo roteador para ONU {serial} na PON {pon} - Apelido: {nome}, Perfil: {profile}")
        
        # Entrar no modo de configuração
        log_interaction("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar no modo de configuração")
        
        # Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        
        # Definir apelido da ONU
        log_interaction(f"Definindo apelido '{nome}' para ONU {serial}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao definir apelido para ONU {serial}")
        
        # Configurar autenticação PPPoE automática
        log_interaction("Configurando autenticação automática PPPoE")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar autenticação PPPoE")
        
        # Configurar PPPoE always-on
        log_interaction("Configurando PPPoE always-on")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE always-on")
        
        # Habilitar NAT
        log_interaction("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        
        # Aplicar perfil de serviço
        log_interaction(f"Aplicando perfil de serviço {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao aplicar perfil {profile}")
        
        # Definir credenciais PPPoE
        log_interaction("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        
        # Desabilitar FEC upstream
        log_interaction("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC upstream")
        
        # Tradução de VLAN
        log_interaction(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)
        
        # Sair da configuração
        log_interaction("Saindo do modo de configuração")
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        
        # Salvar configuração
        log_interaction("Salvando configuração")
        child.sendline("copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        
        log_interaction(f"ONU {serial} autorizada no modo roteador com sucesso")
        return True
        
    except Exception as e:
        error_msg = f"Falha ao autorizar ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False
        
    
def auth_router_121AC(child, serial, pon, nome, profile, vlan):
    try:
        log_interaction(f"Iniciando autenticação 121AC para ONU {serial} na PON {pon} - Nome: {nome}, Perfil: {profile}, VLAN: {vlan}")

        # 1. Entrar no modo de configuração
        log_interaction("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(5)

        # 2. Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        time.sleep(5)

        # 3. Configurar alias
        log_interaction(f"Configurando alias '{nome}'")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(5)

        # 4. Configurar perfil ethernet
        log_interaction("Configurando perfil ethernet automático (portas 1-2)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-2")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil ethernet")
        time.sleep(5)

        # 5. Aplicar perfil de fluxo
        log_interaction(f"Aplicando perfil de fluxo {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(5)

        # 6. Desabilitar FEC upstream
        log_interaction("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC upstream")
        time.sleep(5)

        # 7. Configurar tradução de VLAN
        log_interaction(f"Configurando tradução de VLAN _{vlan} para iphost 1")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(5)

        # 8. Sair da configuração
        log_interaction("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(5)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(5)

        # 9. Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        log_interaction(f"ONU {serial} autorizada com sucesso no perfil 121AC")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação 121AC da ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False

def auth_router_config2(child, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe):
    try:
        log_interaction(f"Iniciando autenticação Config2 para ONU {serial} - PON: {pon}, Nome: {nome}, VLAN: {vlan}")

        # 1. Modo de configuração
        log_interaction("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        log_interaction(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Perfil Ethernet automático
        log_interaction("Configurando perfil Ethernet (portas 1-4)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-4")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil Ethernet")
        time.sleep(2)

        # 5. Configuração PPPoE
        log_interaction("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE auto")
        time.sleep(2)

        # 6. PPPoE Always-On
        log_interaction("Configurando PPPoE Always-On")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 7. Habilitar NAT
        log_interaction("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 8. Aplicar perfil de fluxo
        log_interaction(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 9. Credenciais PPPoE (com log seguro)
        log_interaction("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 10. Desabilitar FEC upstream
        log_interaction("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC")
        time.sleep(2)

        # 11. Tradução de VLAN
        log_interaction(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)

        # 12. Sair da configuração
        log_interaction("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 13. Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        log_interaction(f"Config3 aplicada com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Config3 da ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False

def auth_router_Fiberlink501Rev2(child, serial, pon, nome, profile, login_pppoe, senha_pppoe):
    try:
        log_interaction(f"Iniciando autenticação Fiberlink501Rev2 para ONU {serial} - PON: {pon}, Nome: {nome}")

        # 1. Modo de configuração
        log_interaction("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        log_interaction(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Perfil Ethernet automático
        log_interaction("Configurando perfil Ethernet (portas 1-2)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-2")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil Ethernet")
        time.sleep(2)

        # 5. Aplicar perfil de fluxo
        log_interaction(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 6. Configuração PPPoE automática
        log_interaction("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE auto")
        time.sleep(2)

        # 7. PPPoE Always-On com timer
        log_interaction("Configurando PPPoE Always-On (timer 1200s)")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 1200")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 8. Habilitar NAT
        log_interaction("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 9. Credenciais PPPoE (com log seguro)
        log_interaction("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 10. Desabilitar FEC upstream
        log_interaction("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC")
        time.sleep(2)

        # 11. Sair da configuração
        log_interaction("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 12. Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        log_interaction(f"Fiberlink501Rev2 aplicado com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Fiberlink501Rev2 da ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False


def auth_router_Fiberlink611(child, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe):
    try:
        log_interaction(f"Iniciando autenticação Fiberlink611 para ONU {serial} - PON: {pon}, VLAN: {vlan}")

        # 1. Entrar no modo de configuração
        log_interaction("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        log_interaction(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Configurar autenticação PPPoE automática
        log_interaction("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE automático")
        time.sleep(2)

        # 5. Configurar PPPoE Always-On
        log_interaction("Configurando PPPoE Always-On (timer 0)")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 6. Habilitar NAT
        log_interaction("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 7. Aplicar perfil de fluxo
        log_interaction(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 8. Configurar credenciais PPPoE (com log seguro)
        log_interaction("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 9. Configurar tradução de VLAN
        log_interaction(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)

        # 10. Sair da configuração
        log_interaction("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 11. Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        log_interaction(f"Fiberlink611 aplicado com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Fiberlink611 da ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False

def unauthorized(child, pon, serial):
    try:
        log_interaction(f"Iniciando desautorização da ONU {serial} na PON {pon}")
        
        # Entrar no modo de configuração
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        
        log_interaction(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        log_interaction(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        
        # Desautorizar ONU
        log_interaction(f"Desautorizando ONU {serial}")
        child.sendline(f"no onu {serial}")
        time.sleep(10)
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao desautorizar ONU {serial}")
        
        # Salvar configuração
        log_interaction("Salvando configuração no OLT")
        child.sendline("do copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        
        log_interaction(f"ONU {serial} desautorizada com sucesso na PON gpon1/{pon}")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao desautorizar ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False
    
def reboot(child, pon, serial):
    try:
        log_interaction(f"Iniciando reboot da ONU {serial} na PON {pon}")
        
        # Entrar no modo de configuração
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        
        # Acessar interface GPON
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
    
        # Resetar ONU
        child.sendline(f"onu reset {serial}")
        time.sleep(10)
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao resetar ONU {serial}")
        
        # Sair da configuração
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")

        log_interaction(f"Reboot da ONU {serial} concluído com sucesso")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao reiniciar ONU {serial}: {str(e)}"
        log_interaction(error_msg, level="ERROR")
        return False