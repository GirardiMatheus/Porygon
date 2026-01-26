"""
Nokia TL1 module for OLT management operations.
Provides functions for TL1 connection, ONU provisioning, and configuration.
"""

import os
import sys
import time
from typing import Optional, Tuple, List, Dict, Any
from contextlib import contextmanager

import pexpect
from dotenv import load_dotenv
from utils.log import get_logger

# Constants
DEFAULT_TIMEOUT = 10
CONFIGURATION_WAIT_TIME = 90
STABILIZATION_WAIT_TIME = 3
WIFI_PARAMS_TO_DELETE = ['6', '7', '8', '9']

# Configura o logger para este módulo
logger = get_logger(__name__)

# Carrega variáveis do arquivo .env
load_dotenv()

def countdown_timer(seconds: int) -> None:
    """Display countdown timer with formatted output"""
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        timer = f"\rAguardando: {mins:02d}:{secs:02d}"
        sys.stdout.write(timer)
        sys.stdout.flush()
        time.sleep(1)
    print("\nContinuando...")

def login_olt_tl1(host: str) -> Optional[pexpect.spawn]:
    """Estabelece conexão TL1 com a OLT"""
    try:
        logger.info("Iniciando conexão TL1, obtendo variáveis de ambiente")

        tl1_user = os.getenv('TL1_USER')
        tl1_passwd = os.getenv('TL1_PASSWORD')
        tl1_port = os.getenv('TL1_PORT')
        
        if not all([tl1_user, tl1_passwd, host, tl1_port]):
            logger.error("Erro de configuração TL1: variáveis de ambiente não encontradas")
            raise ValueError("Erro de configuração TL1: variáveis de ambiente não encontradas")
        
        logger.info(f"Conectando TL1, usuário: {tl1_user} | OLT: {host}")
        
        # Conexão TL1
        child = pexpect.spawn(f"ssh {tl1_user}@{host} -p {tl1_port}", 
                                encoding='utf-8', 
                                timeout=30)

        # Verifica resposta do SSH
        index = child.expect([
            "password:", 
            "Are you sure you want to continue connecting", 
            "Permission denied",  
            pexpect.TIMEOUT
        ], timeout=DEFAULT_TIMEOUT)

        if index == 1:
            logger.info("TL1: Primeira conexão - aceitando certificado")
            child.sendline("yes")
            child.expect("password:")
        elif index == 2:
            logger.error("TL1: Falha na autenticação - credenciais inválidas")
            print("❌ Erro: Usuário ou senha inválidos.")
            return None
        elif index == 3:
            logger.error("TL1: Timeout durante conexão SSH")
            print("❌ Erro: Timeout na conexão SSH.")
            return None
        
        logger.info("TL1: Enviando credenciais de acesso")
        child.sendline(tl1_passwd)

        # Aguarda a resposta do login
        login_success = child.expect([
            "Welcome to ISAM", 
            "Permission denied", 
            pexpect.TIMEOUT, 
            pexpect.EOF
        ], timeout=DEFAULT_TIMEOUT)

        if login_success == 1:
            logger.error("TL1: Falha na autenticação após envio da senha")
            print("❌ Erro: Usuário ou senha inválidos.")
            return None
        elif login_success == 2:
            logger.error("TL1: Timeout após envio da senha")
            print("❌ Erro: Timeout na autenticação.")
            return None
        elif login_success == 3:
            logger.error("TL1: Conexão encerrada inesperadamente")
            print("❌ Erro: Conexão encerrada.")
            return None
        elif login_success == 0:
            logger.info("TL1: Login bem-sucedido")
            print("✅ Login efetuado com sucesso")
            
            # Configuração inicial da sessão TL1
            child.sendline("")
            child.expect("<", timeout=5)
            child.sendline('INH-MSG-ALL::ALL:::;')
            child.expect("COMPLD", timeout=DEFAULT_TIMEOUT)
            
            return child

    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Falha na conexão TL1: {str(e)}")
        print(f"❌ Falha na conexão TL1: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado TL1: {str(e)}")
        print(f"❌ Erro inesperado TL1: {str(e)}")
        return None

def auth_bridge_tl1(child: pexpect.spawn, serial: str, vlan: str, name: str, 
                    slot: str, pon: str, position: str, desc2: str) -> bool:
    """Autoriza e configura uma ONT em modo bridge via TL1"""
    try:
        logger.info(f"Provisionando ONT em modo bridge: Serial={serial}, VLAN={vlan}, "
                    f"Nome={name}, Slot={slot}, PON={pon}, Posição={position}, Desc2={desc2}")

        # Autorizar ONT
        cmd = (f'ENT-ONT::ONT-1-1-{slot}-{pon}-{position}::::DESC1="{name}",DESC2="{desc2}",'
                f'SERNUM={serial},PLNDVAR=BRG,SWVERPLND=AUTO,DLSW=AUTO,PLNDCFGFILE1=AUTO,'
                f'DLCFGFILE1=AUTO,OPTICSHIST=ENABLE,VOIPALLOWED=VEIP;')
        logger.info(f"Enviando comando de autorização: {cmd}")
        child.sendline(cmd)
        child.expect("COMPLD", timeout=DEFAULT_TIMEOUT)
        logger.info("Autorização da ONT em modo bridge concluída com sucesso")

        # Unlock da ONT
        unlock_cmd = f"ED-ONT::ONT-1-1-{slot}-{pon}-{position}:::::IS;"
        logger.info(f"Enviando comando de unlock da ONT: {unlock_cmd}")
        child.sendline(unlock_cmd)
        child.expect("COMPLD", timeout=DEFAULT_TIMEOUT)
        logger.info("Unlock da ONT realizado com sucesso")

    except pexpect.exceptions.TIMEOUT as e:
        logger.error(f"Timeout durante autorização/unlock da ONT: {e}")
        print("❌ Timeout ao autorizar ou desbloquear a ONT.")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao autorizar/unlock ONT: {e}")
        print("❌ Erro inesperado ao autorizar ou desbloquear a ONT.")
        return False

    # Aguarda o tempo de configuração
    try:
        logger.info("CONFIGURANDO, aguarde a conclusão em 1,5 minutos...")
        countdown_timer(CONFIGURATION_WAIT_TIME)
        logger.info("Tempo de configuração concluído")
    except Exception as e:
        logger.warning(f"Problema no timer de contagem regressiva: {e}")

    # Comandos adicionais de configuração
    comandos = [
        (f"ENT-ONTCARD::ONTCARD-1-1-{slot}-{pon}-{position}-1:::10_100BASET,1,0::IS;", "ENT-ONTCARD"),
        (f"ENT-LOGPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-1-1:::;", "ENT-LOGPORT"),
        (f"ED-ONTVEIP::ONTVEIP-1-1-{slot}-{pon}-{position}-1-1:::::IS;", "ED-ONTVEIP"),
        (f"SET-QOS-USQUEUE::ONTL2UNIQ-1-1-{slot}-{pon}-{position}-1-1-0::::USBWPROFNAME=HSI_1G_UP;", "SET-QOS-USQUEUE"),
        (f"SET-VLANPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-1-1:::MAXNUCMACADR=32,CMITMAXNUMMACADDR=10;", "SET-VLANPORT (MAC Address)"),
        (f"ENT-VLANEGPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-1-1:::0,{vlan}:PORTTRANSMODE=UNTAGGED;", "ENT-VLANEGPORT"),
        (f"SET-VLANPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-1-1:::DEFAULTCVLAN={vlan};", "SET-VLANPORT (Default VLAN)"),
        ("LOGOFF;", "LOGOFF"),
    ]

    for cmd, descricao in comandos:
        try:
            logger.info(f"Enviando comando {descricao}: {cmd}")
            child.sendline(cmd)
            child.expect("COMPLD", timeout=DEFAULT_TIMEOUT)
            logger.info(f"Comando {descricao} executado com sucesso")
        except pexpect.exceptions.TIMEOUT as e:
            logger.error(f"Timeout ao executar o comando {descricao}: {e}")
            print(f"❌ Timeout no comando {descricao}.")
        except Exception as e:
            logger.error(f"Erro inesperado ao executar o comando {descricao}: {e}")
            print(f"❌ Erro no comando {descricao}.")

    logger.info("✅ Provisionamento da ONT em modo bridge finalizado")
    return True

def auth_router_tl1(child: pexpect.spawn, vlan: str, name: str, desc2: str, 
                    user_pppoe: str, password_pppoe: str, slot: str, pon: str, 
                    position: str, serial_tl1: str) -> bool:
    """Provisiona ONT Router via TL1"""
    try:
        logger.info(f"Iniciando provisionamento da ONT: Slot={slot}, PON={pon}, "
                    f"Posição={position}, Serial={serial_tl1}")

        cmd = (f'ENT-ONT::ONT-1-1-{slot}-{pon}-{position}::::DESC1="{name}",DESC2="{desc2}",'
                f'SERNUM={serial_tl1},PLNDVAR=VEIP_SIP,SWVERPLND=AUTO,DLSW=AUTO,'
                f'PLNDCFGFILE1=AUTO,DLCFGFILE1=AUTO,OPTICSHIST=ENABLE,VOIPALLOWED=VEIP;')

        logger.info(f"Enviando comando de criação da ONT: {cmd}")
        child.sendline(cmd)

        index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT], timeout=DEFAULT_TIMEOUT)
        if index != 0:
            logger.error("Erro ao criar ONT. Resposta inesperada do sistema.")
            print("❌ Erro: Falha ao criar ONT.")
            return False
        
        logger.info("✅ ONT criada com sucesso.")

        # Lista de comandos de configuração
        cmds = [
            (f"ED-ONT::ONT-1-1-{slot}-{pon}-{position}:::::IS;", "Desbloquear ONT"),
            (f"ENT-ONTCARD::ONTCARD-1-1-{slot}-{pon}-{position}-14:::VEIP,1,0::IS;", "Criar VEIP"),
            (f"ENT-LOGPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-14-1:::;", "Criar LOGPORT"),
            (f"ED-ONTVEIP::ONTVEIP-1-1-{slot}-{pon}-{position}-14-1:::::IS;", "Editar VEIP"),
            (f"SET-QOS-USQUEUE::ONTL2UNIQ-1-1-{slot}-{pon}-{position}-14-1-0::::USBWPROFNAME=HSI_1G_UP;", "Configurar USQUEUE"),
            (f"SET-VLANPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-14-1:::MAXNUCMACADR=32,CMITMAXNUMMACADDR=10;", "Configurar VLANPORT"),
            (f"ENT-VLANEGPORT::ONTL2UNI-1-1-{slot}-{pon}-{position}-14-1:::0,{vlan}:PORTTRANSMODE=SINGLETAGGED;", "Configurar VLANEGPORT"),
            (f"ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-1::::PARAMNAME=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.X_CT-COM_WANGponLinkConfig.VLANIDMark,PARAMVALUE={vlan};", "Definir VLAN PPPoE"),
            (f"ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-2::::PARAMNAME=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Username,PARAMVALUE={user_pppoe};", "Definir Usuário PPPoE"),
            (f"ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-3::::PARAMNAME=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.Password,PARAMVALUE={password_pppoe};", "Definir Senha PPPoE"),
        ]

        time.sleep(STABILIZATION_WAIT_TIME)

        for command, description in cmds:
            try:
                logger.info(f"Enviando comando: {description} -> {command}")
                child.sendline(command)

                index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT], timeout=DEFAULT_TIMEOUT)
                if index != 0:
                    logger.error(f"Erro ao {description}. Resposta inesperada.")
                    print(f"❌ Erro: Falha ao {description.lower()}.")
                    return False

                logger.info(f"✅ {description} enviado com sucesso.")

            except pexpect.exceptions.ExceptionPexpect as e:
                logger.error(f"Erro pexpect ao {description}: {str(e)}")
                print(f"❌ Erro de comunicação ao {description.lower()}.")
                return False

            except Exception as e:
                logger.error(f"Erro inesperado ao {description}: {str(e)}")
                print(f"❌ Erro inesperado ao {description.lower()}.")
                return False

        logger.info("✅ Provisionamento concluído com sucesso.")
        countdown_timer(CONFIGURATION_WAIT_TIME)
        return True

    except Exception as e:
        logger.error(f"Erro geral durante o provisionamento da ONT: {str(e)}")
        print("❌ Erro inesperado no provisionamento.")
        return False

def config_wifi(child: pexpect.spawn, slot: str, pon: str, position: str, 
                ssid: str, ssidpassword: str) -> bool:
    """Configure WiFi parameters for ONT"""
    logger.info(f"Dados de WIFI a serem aplicados: SSID={ssid}, Password={ssidpassword}")
    print(f"Dados de WIFI a serem aplicados: SSID={ssid}, Password={ssidpassword}")
    
    success = True

    # Comandos para deletar parâmetros antigos
    for param in WIFI_PARAMS_TO_DELETE:
        try:
            cmd = f"DLT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-{param};"
            child.sendline(cmd)
            child.expect("COMPLD", timeout=3)
            logger.info(f"Parâmetro WiFi {param} removido com sucesso")
        except pexpect.exceptions.TIMEOUT:
            logger.info(f"Parâmetro WiFi {param} não existe para ser removido (ONU possivelmente nova)")
        except Exception as e:
            logger.error(f"Erro ao remover parâmetro WiFi {param}: {str(e)}")

    # Comandos para configurar WiFi
    wifi_commands = [
        (f'ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-6::::'
         f'PARAMNAME=InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID,PARAMVALUE="{ssid}";',
         "SSID do WiFi 2.4G"),
        (f'ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-7::::'
         f'PARAMNAME=InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.PreSharedKey.1.PreSharedKey,PARAMVALUE="{ssidpassword}";',
         "Senha do WiFi 2.4G"),
        (f'ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-8::::'
         f'PARAMNAME=InternetGatewayDevice.LANDevice.1.WLANConfiguration.5.SSID,PARAMVALUE="{ssid}5Ghz";',
         "SSID do WiFi 5GHz"),
        (f'ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-9::::'
         f'PARAMNAME=InternetGatewayDevice.LANDevice.1.WLANConfiguration.5.PreSharedKey.1.PreSharedKey,PARAMVALUE="{ssidpassword}";',
         "Senha do WiFi 5GHz"),
    ]

    for command, description in wifi_commands:
        try:
            child.sendline(command)
            child.expect("COMPLD", timeout=5)
            logger.info(f"✅ {description} configurado com sucesso")
        except pexpect.exceptions.TIMEOUT:
            logger.error(f"❌ Timeout ao configurar {description}")
            success = False
        except Exception as e:
            logger.error(f"❌ Erro ao configurar {description}: {str(e)}")
            success = False

    # Enviar LOGOFF
    try:
        child.sendline('LOGOFF;')
        child.expect("COMPLD", timeout=3)
        logger.info("Comando LOGOFF enviado com sucesso")
    except Exception as e:
        logger.error(f"Erro no comando LOGOFF: {str(e)}")

    return success

def format_tl1_serial(serial: str) -> str:
    """Format serial for TL1 protocol"""
    formatted_serial = serial.strip().upper()
    logger.info(f"Serial formatado para TL1: {formatted_serial}")
    return formatted_serial

def grant_remote_access_wan(child: pexpect.spawn, slot: str, pon: str, position: str, password: str) -> bool:
    """Grant remote access WAN for ONT"""
    try:
        logger.info(f"Iniciando habilitação de acesso remoto WAN para ONU {slot}/{pon}/{position} com a senha {password}")

        # Define comandos
        cmd_enable_remote = (
            f"ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-19::::"
            "PARAMNAME=InternetGatewayDevice.WANDevice.1.WANConnectionDevice.1.WANPPPConnection.1.X_ALU-COM_WanAccessCfg.HttpDisabled,"
            "PARAMVALUE=false;"
        )
        cmd_set_password = (
            f"ENT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-4::::"
            f"PARAMNAME=InternetGatewayDevice.X_Authentication.WebAccount.Password,PARAMVALUE={password};"
        )
        cmd_delete_password = f"DLT-HGUTR069-SPARAM::HGUTR069SPARAM-1-1-{slot}-{pon}-{position}-4;"

        # Habilitar acesso remoto WAN
        logger.info("Enviando comando para habilitar acesso remoto...")
        child.sendline(cmd_enable_remote)
        index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT, pexpect.EOF], timeout=DEFAULT_TIMEOUT)

        if index == 0:
            logger.info(f"✅ Acesso remoto habilitado para ONU {slot}/{pon}/{position}")
        else:
            logger.warning(f"⚠️ Acesso remoto já parece estar habilitado para ONU {slot}/{pon}/{position}")

        time.sleep(2)

        # Configurar senha de acesso remoto
        logger.info("Enviando comando para configurar senha de acesso remoto...")
        child.sendline(cmd_set_password)
        index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT, pexpect.EOF], timeout=DEFAULT_TIMEOUT)

        if index == 0:
            logger.info(f"✅ Senha de acesso remoto configurada com sucesso para ONU {slot}/{pon}/{position}")
            return True
        else:
            logger.error(f"❌ Falha ao configurar senha para ONU {slot}/{pon}/{position}. Tentando corrigir...")

            # Deletar senha antiga e tentar novamente
            logger.info("Enviando comando para deletar senha antiga...")
            child.sendline(cmd_delete_password)
            del_index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT, pexpect.EOF], timeout=DEFAULT_TIMEOUT)

            if del_index == 0:
                logger.info("✅ Senha antiga deletada com sucesso. Tentando reaplicar nova senha...")
                
                child.sendline(cmd_set_password)
                reapply_index = child.expect(["COMPLD", "DENY", pexpect.TIMEOUT, pexpect.EOF], timeout=DEFAULT_TIMEOUT)

                if reapply_index == 0:
                    logger.info(f"✅ Nova senha configurada com sucesso após deletar senha antiga para ONU {slot}/{pon}/{position}")
                    return True
                else:
                    logger.error(f"❌ Falha ao reaplicar senha para ONU {slot}/{pon}/{position} mesmo após deletar senha antiga!")
                    return False
            else:
                logger.error(f"❌ Falha ao deletar senha antiga para ONU {slot}/{pon}/{position}")
                return False

    except pexpect.exceptions.TIMEOUT as e:
        logger.error(f"⏰ Timeout de comunicação TL1 ao configurar ONU {slot}/{pon}/{position}: {str(e)}")
        return False
    except pexpect.exceptions.EOF as e:
        logger.error(f"📴 Conexão encerrada inesperadamente ao configurar ONU {slot}/{pon}/{position}: {str(e)}")
        return False
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"⚡ Erro Pexpect ao configurar ONU {slot}/{pon}/{position}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao configurar ONU {slot}/{pon}/{position}: {str(e)}")
        return False

def reboot_onu(child: pexpect.spawn, slot: str, pon: str, position: str) -> bool:
    """Reinicia uma ONT via TL1"""
    try:
        cmd = f"INIT-SYS::ONT-1-1-{slot}-{pon}-{position}:::6;"
        logger.info(f"Enviando comando de reboot para ONT: {cmd}")
        child.sendline(cmd)
        child.expect("COMPLD", timeout=DEFAULT_TIMEOUT)
        logger.info(f"✅ Comando de reboot enviado com sucesso para a ONT na posição {slot}/{pon}/{position}")
        print("✅ Comando de reboot enviado com sucesso")
        return True
    except pexpect.exceptions.TIMEOUT as e:
        logger.error(f"Timeout ao tentar reiniciar a ONT na posição {slot}/{pon}/{position}: {e}")
        print("❌ Timeout ao reiniciar a ONT")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao tentar reiniciar a ONT na posição {slot}/{pon}/{position}: {e}")
        print("❌ Erro inesperado ao reiniciar a ONT")
        return False
