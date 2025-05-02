import pexpect
import os
import time
import csv
import re
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional
from utils.log import get_logger

# Configura o logger para este módulo
logger = get_logger(__name__)

# Carrega variáveis do arquivo .env
load_dotenv()

ssh_userp = os.getenv('SSH_USER_PARKS')
ssh_passwdp = os.getenv('SSH_PASSWORD_PARKS')

def login_ssh(host=None):
    logger.info(f"Conectando ao host: {host}")
    try:
        child = pexpect.spawn(f"ssh {ssh_userp}@{host}", encoding='utf-8', timeout=30)
        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)
        if index == 1:
            child.sendline("yes")
            child.expect("password:")
        child.sendline(ssh_passwdp)
        login_success = child.expect([r"#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            logger.info(f"Conexão estabelecida com sucesso à OLT {host}")
            child.sendline(f"terminal length 0")
            child.expect("#")
            print(f"✅ Conectado com sucesso à OLT {host}")
        else:
            logger.error("Não foi possível autenticar na OLT")
            print("❌ Falha na autenticação")
    
        return child
    
    except pexpect.EOF:
        logger.error("Conexão fechada inesperadamente")
        print("❌ Erro: Conexão foi fechada antes do login.")
        
    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Falha na conexão SSH: {str(e)}"
        logger.error(error_msg)
        print(error_msg)
        return None
        
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        logger.error(error_msg)
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
        logger.error(f"Erro ao listar ONUs não autorizadas: {e}")
        return None

def consult_information(child, serial, max_attempts=20, delay_between_attempts=5):
    try:
        serial = serial.strip().lower()
        logger.info(f"Iniciando consulta para ONU {serial}")

        # Validação do serial
        if len(serial) != 12:
            logger.error(f"Serial inválido: deve ter 12 caracteres (recebido: {serial})")
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
                logger.info(f"Tentativa {attempt}/{max_attempts} - Enviando comando: {comando}")
                
                child.sendline(comando)
                time.sleep(15)
                
                # Padrões para verificação
                patterns = ["#", "% Unknown command", pexpect.TIMEOUT, pexpect.EOF]
                result = child.expect(patterns, timeout=20)
                
                # Tratamento específico para comando desconhecido
                if result == 1: 
                    logger.error("Comando não reconhecido pela OLT")
                    print("\nErro: ONU/ONT não encontrada na OLT selecionada (comando inválido)")
                    return None
                
                elif result != 0: 
                    raise Exception("Timeout ou fim de conexão")
                
                output = child.before.strip()
                logger.debug(f"Resposta bruta recebida: {output[:200]}...")

                # Verificações de resposta
                if "not found" in output.lower():
                    logger.warning(f"ONU {serial} não encontrada na OLT")
                    print("\nAviso: ONU/ONT não encontrada na OLT")
                    return None
                
                if "Serial" in output and "Interface" in output:
                    break

                raise Exception("Resposta incompleta ou inválida")

            except Exception as e:
                logger.warning(f"Falha na tentativa {attempt}: {str(e)}")
                attempt += 1
                if attempt <= max_attempts:
                    time.sleep(delay_between_attempts)
                continue

        if attempt > max_attempts:
            logger.error(f"Falha após {max_attempts} tentativas")
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

        logger.info(f"Consulta concluída para ONU {serial}")
        return data_template

    except Exception as e:
        logger.error(f"Erro crítico: {str(e)}")
        print(f"\nErro crítico: {str(e)}")
        return None

def add_onu_to_pon(child, serial, pon):
    try:
        logger.info(f"Iniciando adição da ONU {serial} na PON {pon}")
        
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
        logger.info(f"onu add serial-number {serial}")
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        time.sleep(10) 
        
        # Verifica se foi bem-sucedido
        if child.before.find("% Serial already exists.") != -1:
            logger.error(f"ONU {serial} já se encontra na PON {pon}")
            return False
        else:
            logger.info(f"ONU {serial} adicionada com sucesso na PON {pon}")
            return True
            
    except Exception as e:
        logger.error(f"Erro durante adição da ONU: {str(e)}")
        return False

def auth_bridge(child, serial, pon, nome, profile, vlan):
    try:
        logger.info(f"Iniciando autorização bridge para ONU {serial} na PON {pon} - Nome: {nome}, Profile: {profile}, VLAN: {vlan}")
        
        # Entrar no modo de configuração
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        logger.info("Modo de configuração acessado com sucesso")
        
        # Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        logger.info(f"Interface gpon1/{pon} acessada com sucesso")
        
        # Configurar alias
        logger.info(f"Configurando alias '{nome}' para ONU {serial}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar alias para ONU {serial}")
        logger.info("Alias configurado com sucesso")
        
        # Configurar profile
        logger.info(f"Configurando profile {profile} para ONU {serial}")
        child.sendline(f"onu {serial} flow {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar profile {profile} para ONU {serial}")
        logger.info("Profile configurado com sucesso")
        
        # Configurar VLAN
        logger.info(f"Configurando VLAN {vlan} para ONU {serial}")
        child.sendline(f"onu {serial} vlan _{vlan} uni-port 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao configurar VLAN {vlan} para ONU {serial}")
        logger.info("VLAN configurada com sucesso")
        
        # Sair das configurações
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        
        # Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        logger.info("Configuração salva com sucesso")
        
        logger.info(f"ONU {serial} autorizada em modo bridge com sucesso - PON: {pon}, Nome: {nome}, Profile: {profile}, VLAN: {vlan}")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao autorizar ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def auth_router_default(child, serial, nome, vlan, pon, profile, login_pppoe, senha_pppoe):
    if not vlan.isdigit():
        raise ValueError(f"VLAN inválida: {vlan}. Deve ser numérica")
    try:
        logger.info(f"Iniciando autenticação no modo roteador para ONU {serial} na PON {pon} - Apelido: {nome}, Perfil: {profile}")
        
        # Entrar no modo de configuração
        logger.info("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar no modo de configuração")
        
        # Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        
        # Definir apelido da ONU
        logger.info(f"Definindo apelido '{nome}' para ONU {serial}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao definir apelido para ONU {serial}")
        
        # Configurar autenticação PPPoE automática
        logger.info("Configurando autenticação automática PPPoE")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar autenticação PPPoE")
        
        # Configurar PPPoE always-on
        logger.info("Configurando PPPoE always-on")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE always-on")
        
        # Habilitar NAT
        logger.info("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        
        # Aplicar perfil de serviço
        logger.info(f"Aplicando perfil de serviço {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao aplicar perfil {profile}")
        
        # Definir credenciais PPPoE
        logger.info("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        
        # Desabilitar FEC upstream
        logger.info("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC upstream")
        
        # Tradução de VLAN
        logger.info(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)
        
        # Sair da configuração
        logger.info("Saindo do modo de configuração")
        child.sendline("exit")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        
        # Salvar configuração
        logger.info("Salvando configuração")
        child.sendline("copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        
        logger.info(f"ONU {serial} autorizada no modo roteador com sucesso")
        return True
        
    except Exception as e:
        error_msg = f"Falha ao autorizar ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def auth_router_121AC(child, serial, pon, nome, profile, vlan):
    try:
        logger.info(f"Iniciando autenticação 121AC para ONU {serial} na PON {pon} - Nome: {nome}, Perfil: {profile}, VLAN: {vlan}")

        # 1. Entrar no modo de configuração
        logger.info("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(5)

        # 2. Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        time.sleep(5)

        # 3. Configurar alias
        logger.info(f"Configurando alias '{nome}'")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(5)

        # 4. Configurar perfil ethernet
        logger.info("Configurando perfil ethernet automático (portas 1-2)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-2")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil ethernet")
        time.sleep(5)

        # 5. Aplicar perfil de fluxo
        logger.info(f"Aplicando perfil de fluxo {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(5)

        # 6. Desabilitar FEC upstream
        logger.info("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC upstream")
        time.sleep(5)

        # 7. Configurar tradução de VLAN
        logger.info(f"Configurando tradução de VLAN _{vlan} para iphost 1")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(5)

        # 8. Sair da configuração
        logger.info("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(5)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(5)

        # 9. Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        logger.info(f"ONU {serial} autorizada com sucesso no perfil 121AC")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação 121AC da ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def auth_router_config2(child, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe):
    try:
        logger.info(f"Iniciando autenticação Config2 para ONU {serial} - PON: {pon}, Nome: {nome}, VLAN: {vlan}")

        # 1. Modo de configuração
        logger.info("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        logger.info(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Perfil Ethernet automático
        logger.info("Configurando perfil Ethernet (portas 1-4)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-4")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil Ethernet")
        time.sleep(2)

        # 5. Configuração PPPoE
        logger.info("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE auto")
        time.sleep(2)

        # 6. PPPoE Always-On
        logger.info("Configurando PPPoE Always-On")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 7. Habilitar NAT
        logger.info("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 8. Aplicar perfil de fluxo
        logger.info(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 9. Credenciais PPPoE (com log seguro)
        logger.info("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 10. Desabilitar FEC upstream
        logger.info("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC")
        time.sleep(2)

        # 11. Tradução de VLAN
        logger.info(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)

        # 12. Sair da configuração
        logger.info("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 13. Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        logger.info(f"Config3 aplicada com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Config3 da ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def auth_router_Fiberlink501Rev2(child, serial, pon, nome, profile, login_pppoe, senha_pppoe):
    try:
        logger.info(f"Iniciando autenticação Fiberlink501Rev2 para ONU {serial} - PON: {pon}, Nome: {nome}")

        # 1. Modo de configuração
        logger.info("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        logger.info(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Perfil Ethernet automático
        logger.info("Configurando perfil Ethernet (portas 1-2)")
        child.sendline(f"onu {serial} ethernet-profile auto-on uni-port 1-2")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar perfil Ethernet")
        time.sleep(2)

        # 5. Aplicar perfil de fluxo
        logger.info(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 6. Configuração PPPoE automática
        logger.info("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE auto")
        time.sleep(2)

        # 7. PPPoE Always-On com timer
        logger.info("Configurando PPPoE Always-On (timer 1200s)")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 1200")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 8. Habilitar NAT
        logger.info("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 9. Credenciais PPPoE (com log seguro)
        logger.info("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 10. Desabilitar FEC upstream
        logger.info("Desabilitando FEC upstream")
        child.sendline(f"onu {serial} upstream-fec disabled")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao desabilitar FEC")
        time.sleep(2)

        # 11. Sair da configuração
        logger.info("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 12. Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        logger.info(f"Fiberlink501Rev2 aplicado com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Fiberlink501Rev2 da ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def auth_router_Fiberlink611(child, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe):
    try:
        logger.info(f"Iniciando autenticação Fiberlink611 para ONU {serial} - PON: {pon}, VLAN: {vlan}")

        # 1. Entrar no modo de configuração
        logger.info("Entrando no modo de configuração")
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        time.sleep(2)

        # 2. Acessar interface GPON
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface GPON {pon}")
        time.sleep(2)

        # 3. Configurar alias
        logger.info(f"Configurando alias: {nome}")
        child.sendline(f"onu {serial} alias {nome}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar alias")
        time.sleep(2)

        # 4. Configurar autenticação PPPoE automática
        logger.info("Configurando autenticação PPPoE automática")
        child.sendline(f"onu {serial} iphost 1 pppoe auth auto")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE automático")
        time.sleep(2)

        # 5. Configurar PPPoE Always-On
        logger.info("Configurando PPPoE Always-On (timer 0)")
        child.sendline(f"onu {serial} iphost 1 pppoe contrigger alwayson idletimer 0")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar PPPoE Always-On")
        time.sleep(2)

        # 6. Habilitar NAT
        logger.info("Habilitando NAT")
        child.sendline(f"onu {serial} iphost 1 pppoe nat enable")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao habilitar NAT")
        time.sleep(2)

        # 7. Aplicar perfil de fluxo
        logger.info(f"Aplicando perfil de fluxo: {profile}")
        child.sendline(f"onu {serial} flow-profile {profile}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao aplicar perfil de fluxo")
        time.sleep(2)

        # 8. Configurar credenciais PPPoE (com log seguro)
        logger.info("Configurando credenciais PPPoE (usuário oculto)")
        child.sendline(f"onu {serial} iphost 1 pppoe username {login_pppoe} password {senha_pppoe}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar credenciais PPPoE")
        time.sleep(2)

        # 9. Configurar tradução de VLAN
        logger.info(f"Configurando tradução de VLAN: _{vlan}")
        child.sendline(f"onu {serial} vlan-translation-profile _{vlan} iphost 1")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao configurar tradução de VLAN")
        time.sleep(2)

        # 10. Sair da configuração
        logger.info("Saindo das configurações")
        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair da interface")
        time.sleep(2)

        child.sendline("exit")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao sair do modo de configuração")
        time.sleep(2)

        # 11. Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("copy r s")
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        time.sleep(10)

        logger.info(f"Fiberlink611 aplicado com sucesso para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Falha na autenticação Fiberlink611 da ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def unauthorized(child, pon, serial):
    try:
        logger.info(f"Iniciando desautorização da ONU {serial} na PON {pon}")
        
        # Entrar no modo de configuração
        child.sendline("configure terminal")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception("Falha ao entrar em modo de configuração")
        
        logger.info(f"Acessando interface gpon1/{pon}")
        child.sendline(f"interface gpon1/{pon}")
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao acessar interface gpon1/{pon}")
        
        # Desautorizar ONU
        logger.info(f"Desautorizando ONU {serial}")
        child.sendline(f"no onu {serial}")
        time.sleep(10)
        if child.expect(["#", "ERROR"], timeout=30) != 0:
            raise Exception(f"Falha ao desautorizar ONU {serial}")
        
        # Salvar configuração
        logger.info("Salvando configuração no OLT")
        child.sendline("do copy r s")
        time.sleep(10)
        if child.expect(["Configuration saved.", "ERROR"], timeout=60) != 0:
            raise Exception("Falha ao salvar configuração")
        
        logger.info(f"ONU {serial} desautorizada com sucesso na PON gpon1/{pon}")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao desautorizar ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def reboot(child, pon, serial):
    try:
        logger.info(f"Iniciando reboot da ONU {serial} na PON {pon}")
        
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

        logger.info(f"Reboot da ONU {serial} concluído com sucesso")
        return True
        
    except Exception as e:
        error_msg = f"Erro ao reiniciar ONU {serial}: {str(e)}"
        logger.error(error_msg)
        return False

def list_onu(child, pon, ip_olt):
    try:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M")
        csv_filename = f"parks_onu_list_{ip_olt.replace('.', '-')}_pon{pon}_{now}.csv"
        csv_path = os.path.join("csv", csv_filename)

        # Envia comando para listar ONUs com modelo
        command = f"show interface gpon1/{pon} onu model"
        child.sendline(command)
        child.expect("#", timeout=10)
        output = child.before.decode() if isinstance(child.before, bytes) else child.before

        matches = []
        for line in output.splitlines():
            if any(x in line.lower() for x in ["serial", "model"]):
                continue
            parts = [p.strip() for p in line.strip().split('|') if p.strip()]
            if len(parts) >= 2:
                serial = parts[0]
                model = parts[1]
                matches.append((serial, model))
            elif len(parts) == 1 and re.match(r"^\w{12}$", parts[0]):
                serial = parts[0]
                model = ""
                matches.append((serial, model))

        if not matches:
            logger.warning("Nenhuma ONU encontrada na PON %s", pon)
            return []

        onu_data = []
        for serial, model in matches:
            # Busca alias da ONU via comando adicional
            command2 = f"show gpon onu {serial} summary"
            child.sendline(command2)
            child.expect("#", timeout=10)
            output2 = child.before.decode() if isinstance(child.before, bytes) else child.before

            alias_match = re.search(r"Alias\s+:\s+(.+)", output2)
            alias = alias_match.group(1).strip() if alias_match else ""

            onu_data.append({
                "serial": serial.strip(),
                "model": model.strip(),
                "alias": alias.strip()
            })

        os.makedirs("csv", exist_ok=True)

        with open(csv_path, mode='w', newline='') as f:
            fieldnames = ['serial', 'model', 'alias']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for onu in onu_data:
                writer.writerow(onu)

        logger.info("%d ONUs processadas e salvas no CSV %s.", len(onu_data), csv_filename)
        return onu_data

    except Exception as e:
        logger.error("Erro ao executar list_onu: %s", str(e))
        return []
