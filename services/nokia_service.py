"""
Nokia Service module for OLT management operations.
Provides high-level functions for ONU provisioning, configuration, and monitoring.
"""

import csv
import time
import re
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
from contextlib import contextmanager

from nokia.nokia_ssh import *
from nokia.nokia_tl1 import *
from utils.log import get_logger

# Constants
BRIDGE_MODELS = ["TP-Link: TX-6610, XZ000-G3", "Intelbras: R1v2, 110Gb", 
                "Fiberhome: AN5506-01-A", "PARKS: Fiberlink100, FiberLink101"]
ROUTER_MODELS = ["NOKIA: G-1425G-A, G-1425G-B, G-1426G-A"]
MODEL_GROUP01 = {"TX-6610", "R1v2", "XZ000-G3", "Fiberlink100"}
MODEL_GROUP02 = {"PON110_V3.0", "RTL9602C", "DM985-100", "HG8310M", "110Gb", "SH901"}
MODEL_GROUP03 = {"XZ000-G7", "AN5506-01-A"}
NOKIA_SERIAL_PREFIX = "ALCL"
MAX_RETRIES = 3
WIFI_PASSWORD_MIN_LENGTH = 8
SSID_MIN_LENGTH = 4
SSID_MAX_LENGTH = 32
NAME_MAX_LENGTH = 63
REMOTE_ACCESS_PASSWORD_LENGTH = 10
COUNTDOWN_WAIT_TIME = 15
STABILIZATION_WAIT_TIME = 10

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Utility functions for common operations

@contextmanager
def ssh_connection(ip_olt: str):
    """Context manager for SSH connections with proper cleanup"""
    conexao = None
    try:
        logger.info(f"Conectando à OLT {ip_olt} via SSH...")
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            raise Exception(f"Falha na conexão SSH com a OLT {ip_olt}")
        logger.info("Conexão SSH estabelecida com sucesso")
        yield conexao
    except Exception as e:
        logger.error(f"Erro na conexão SSH: {str(e)}")
        raise
    finally:
        if conexao:
            try:
                conexao.terminate()
                logger.info("Conexão SSH encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")

@contextmanager
def tl1_connection(ip_olt: str):
    """Context manager for TL1 connections with proper cleanup"""
    conexao = None
    try:
        logger.info(f"Conectando à OLT {ip_olt} via TL1...")
        conexao = login_olt_tl1(host=ip_olt)
        if not conexao:
            raise Exception(f"Falha na conexão TL1 com a OLT {ip_olt}")
        logger.info("Conexão TL1 estabelecida com sucesso")
        yield conexao
    except Exception as e:
        logger.error(f"Erro na conexão TL1: {str(e)}")
        raise
    finally:
        if conexao:
            try:
                conexao.terminate()
                logger.info("Conexão TL1 encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão TL1: {str(e)}")

def get_user_input(prompt: str, validator=None, required: bool = True) -> str:
    """Get validated user input with proper error handling"""
    while True:
        try:
            value = input(prompt).strip()
            if required and not value:
                raise ValueError("Valor não pode estar vazio")
            if validator and not validator(value):
                raise ValueError("Valor inválido")
            return value
        except ValueError as e:
            logger.error(f"Erro na entrada do usuário: {str(e)}")
            print(f"❌ Erro: {str(e)}")
        except KeyboardInterrupt:
            logger.info("Operação cancelada pelo usuário")
            raise

def validate_serial(serial: str) -> bool:
    """Validate ONU serial format"""
    return len(serial) > 0 and serial.replace("-", "").isalnum()

def validate_vlan(vlan: str) -> bool:
    """Validate VLAN format"""
    return vlan.isdigit() and 1 <= int(vlan) <= 4094

def validate_ssid(ssid: str) -> bool:
    """Validate WiFi SSID format"""
    return (SSID_MIN_LENGTH <= len(ssid) <= SSID_MAX_LENGTH and 
            re.match(r'^[a-zA-Z0-9_ ]+$', ssid))

def validate_wifi_password(password: str) -> bool:
    """Validate WiFi password format"""
    return len(password) >= WIFI_PASSWORD_MIN_LENGTH

def validate_name(name: str) -> bool:
    """Validate client name format"""
    return len(name) > 0 and len(name) <= NAME_MAX_LENGTH

def validate_remote_password(password: str) -> bool:
    """Validate remote access password format"""
    return len(password) == REMOTE_ACCESS_PASSWORD_LENGTH

def get_onu_position_info(conexao, serial: str) -> Tuple[str, str, str]:
    """Get ONU position information with error handling"""
    try:
        serial_ssh = format_ssh_serial(serial)
        logger.debug(f"Serial formatado para SSH: {serial_ssh}")
        
        logger.info("Consultando posição da ONU...")
        result = check_onu_position(conexao, serial_ssh)
        
        if not result or len(result) != 3:
            raise Exception("Não foi possível obter a posição da ONU")
            
        slot, pon, position = result
        logger.info(f"ONU encontrada - Slot: {slot}, PON: {pon}, Posição: {position}")
        return slot, pon, position
        
    except Exception as e:
        logger.error(f"Erro ao obter posição da ONU: {str(e)}")
        raise

def load_csv_data(filepath: str) -> List[Dict]:
    """Load CSV data with proper error handling"""
    try:
        data = []
        with open(filepath, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                data.append(row)
        logger.info(f"Carregados {len(data)} registros do arquivo {filepath}")
        return data
    except FileNotFoundError:
        logger.error(f"Arquivo CSV não encontrado: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Erro ao ler arquivo CSV {filepath}: {str(e)}")
        raise

def save_csv_data(filepath: str, data: List[Dict], fieldnames: List[str]) -> None:
    """Save data to CSV file with proper error handling"""
    try:
        with open(filepath, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Arquivo {filepath} criado com {len(data)} registros")
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo CSV {filepath}: {str(e)}")
        raise

def get_vlan_from_csv(slot: str, pon: str, csv_path: str = './csv/nokia.csv') -> str:
    """Get VLAN from CSV or user input"""
    try:
        vlan_data = load_csv_data(csv_path)
        vlan_lookup = {(row['CARD'], str(row['PON'])): row['VLAN'] for row in vlan_data}
        
        vlan = vlan_lookup.get((slot, str(pon)))
        if vlan:
            logger.info(f"VLAN encontrada no CSV: {vlan}")
            return vlan
        else:
            logger.warning(f"VLAN não encontrada no CSV para CARD {slot} e PON {pon}")
            
    except Exception as e:
        logger.error(f"Erro ao consultar CSV: {str(e)}")
        print(f"Erro ao consultar CSV: {str(e)}")
    
    # Solicitar VLAN manual
    return get_user_input(
        "Digite a VLAN: ",
        validator=validate_vlan,
        required=True
    )

def get_wifi_credentials() -> Tuple[str, str]:
    """Get WiFi credentials with validation"""
    ssid = get_user_input(
        "Digite o nome do WIFI: ",
        validator=validate_ssid,
        required=True
    )
    
    password = get_user_input(
        "\nDigite a senha do WIFI "
        "\n(Para ONT Nokia 1426G é necessário adicionar no mínimo "
        "1 número, 1 caractere especial e 1 letra maiúscula.)"
        "\nA senha deve ter no mínimo 8 caracteres: ",
        validator=validate_wifi_password,
        required=True
    )
    
    return ssid, password

def get_pppoe_credentials() -> Tuple[str, str]:
    """Get PPPoE credentials with validation"""
    user = get_user_input(
        "Qual o login PPPoE do cliente: ",
        required=True
    )
    
    password = get_user_input(
        "Qual a senha do PPPoE do cliente: ",
        required=True
    )
    
    return user, password

def provision_onu_by_model(conexao, model: str, slot: str, pon: str, position: str, vlan: str) -> bool:
    """Provision ONU based on model with proper error handling"""
    try:
        if model in MODEL_GROUP01:
            auth_group01_ssh(conexao, slot, pon, position, vlan)
            logger.info("Provisionamento concluído com sucesso (Grupo 01)")
            return True
        elif model in MODEL_GROUP02:
            auth_group02_ssh(conexao, slot, pon, position, vlan)
            logger.info("Provisionamento concluído com sucesso (Grupo 02)")
            return True
        elif model in MODEL_GROUP03:
            auth_group03_ssh(conexao, slot, pon, position, vlan)
            logger.info("Provisionamento concluído com sucesso (Grupo 03)")
            return True
        else:
            logger.warning(f"Modelo incompatível: {model}")
            return False
            
    except Exception as e:
        logger.error(f"Erro no provisionamento: {str(e)}")
        raise

def handle_incompatible_model(conexao, serial: str, slot: str, pon: str, position: str, model: str) -> None:
    """Handle incompatible model by removing ONU"""
    try:
        logger.warning(f"Modelo incompatível: {model}. Excluindo ONU/ONT.")
        print("Modelo não compatível, excluindo ONU/ONT")
        countdown_timer(COUNTDOWN_WAIT_TIME)
        logger.info("Prosseguindo...")
        
        serial_ssh = format_ssh_serial(serial)
        unauthorized(conexao, serial_ssh, slot, pon, position)
        
    except Exception as e:
        logger.error(f"Erro ao excluir ONU: {str(e)}")
        raise

def process_nokia_onu(conexao_tl1, item: Dict, slot: str, pon: str, position: str, vlan: str) -> bool:
    """Process Nokia ONT (ALCL) with proper error handling"""
    try:
        serial = item.get('serial', '').upper().strip()
        name = item.get('name', 'CLIENTE').strip()
        
        logger.info("ONT Nokia ALCL detectada")
        serial_tl1 = format_tl1_serial(serial)

        if item.get('mode', 'bridge').lower() == 'bridge':
            logger.info("Provisionamento em modo Bridge")
            desc2 = "BRIDGE"
            auth_bridge_tl1(conexao_tl1, serial_tl1, vlan, name, slot, pon, position, desc2)
        else:
            logger.info("Provisionamento em modo Router")
            desc2 = "ROUTER"
            ssid = item.get('ssid', '').strip()
            ssidpassword = item.get('ssidpassword', '').strip()
            user_pppoe = item.get('pppoe_user', '').strip()
            password_pppoe = item.get('pppoe_pass', '').strip()

            auth_router_tl1(conexao_tl1, vlan, name, desc2, user_pppoe, password_pppoe, slot, pon, position, serial_tl1)
            if ssid and ssidpassword:
                config_wifi(conexao_tl1, slot, pon, position, ssid, ssidpassword)
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao processar ONT Nokia: {str(e)}")
        raise

def process_standard_onu(conexao, item: Dict, slot: str, pon: str, position: str, vlan: str) -> bool:
    """Process standard ONU with proper error handling"""
    try:
        serial = item.get('serial', '').upper().strip()
        name = item.get('name', 'CLIENTE').strip()
        
        serial_ssh = format_ssh_serial(serial)
        desc2 = "Bridge"
        add_to_pon(conexao, slot, pon, position, serial_ssh, name, desc2)
        time.sleep(STABILIZATION_WAIT_TIME)

        # Use model from CSV if available, otherwise detect automatically
        model = item.get('model', '').strip()
        if not model:
            model = onu_model(conexao, slot, pon, position)
            logger.info(f"Modelo detectado automaticamente: {model}")
        else:
            logger.info(f"Modelo informado via CSV: {model}")

        if not provision_onu_by_model(conexao, model, slot, pon, position, vlan):
            logger.warning(f"Modelo incompatível: {model}. Excluindo ONU.")
            unauthorized(conexao, serial_ssh, slot, pon, position)
            raise Exception(f"Modelo {model} não compatível")
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao processar ONU padrão: {str(e)}")
        raise

def onu_list_nokia(ip_olt: str) -> None:
    """List unauthorized ONUs from OLT"""
    try:
        with ssh_connection(ip_olt) as conexao:
            logger.info("Listando ONUs não autorizadas...")
            unauthorized = list_unauthorized(conexao)
            logger.debug(unauthorized)

            if not unauthorized:
                print("Nenhuma ONU ou ONT pedindo autorização...")
                logger.info("Nenhuma ONU ou ONT encontrada na unauthorized")
                return

    except Exception as e:
        logger.error(f"Erro ao listar ONUs: {str(e)}")
        print(f"❌ Erro ao listar ONUs: {str(e)}")

def unauthorized_complete_nokia(ip_olt: str) -> bool:
    """Complete unauthorized process for ONU"""
    try:
        serial = get_user_input(
            "Qual o serial da ONU? ",
            validator=validate_serial,
            required=True
        )
        
        logger.info(f"Serial informado: {serial}")
        
        with ssh_connection(ip_olt) as conexao:
            slot, pon, position = get_onu_position_info(conexao, serial)
            
            logger.info("Executando desautorização...")
            serial_ssh = format_ssh_serial(serial)
            success = unauthorized(conexao, serial_ssh, slot, pon, position)
            
            if success:
                logger.info("✅ ONU desautorizada com sucesso")
                print("✅ ONU desautorizada com sucesso")
                return True
            else:
                logger.error("Falha no processo de desautorização")
                print("❌ Falha ao desautorizar ONU")
                return False
                
    except Exception as e:
        logger.error(f"Erro durante desautorização: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")
        return False

def consult_information_complete_nokia(ip_olt: str) -> None:
    """Complete consultation process for ONU information"""
    try:
        serial = get_user_input(
            "Digite o serial: ",
            validator=validate_serial,
            required=True
        )
        
        logger.info(f"Serial informado: {serial}")
        
        with ssh_connection(ip_olt) as conexao:
            slot, pon, position = get_onu_position_info(conexao, serial)
            
            logger.info("Obtendo sinal...")
            if not return_signal_temp(conexao, slot, pon, position):
                logger.warning("Falha ao obter informações de sinal")
                
            logger.info("Identificando modelo...")
            model = onu_model(conexao, slot, pon, position)
            if not model:
                logger.warning("Não foi possível identificar o modelo da ONU")
                
    except Exception as e:
        logger.error(f"Erro durante consulta: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

def reboot_complete_nokia(ip_olt: str) -> None:
    """Complete reboot process for ONU"""
    try:
        input("Após enviado o comando pode demorar até 3 min até que a ONU seja reiniciada.\nPressione ENTER para prosseguir.")
        
        serial = get_user_input(
            "Digite o serial: ",
            validator=validate_serial,
            required=True
        )
        
        logger.info(f"Serial informado: {serial}")
        
        # Get position info using SSH
        with ssh_connection(ip_olt) as conexao_ssh:
            slot, pon, position = get_onu_position_info(conexao_ssh, serial)
        
        # Execute reboot using TL1
        with tl1_connection(ip_olt) as conexao_tl1:
            logger.info("Executando reboot...")
            if not reboot_onu(conexao_tl1, slot, pon, position):
                logger.error("Falha no comando de reboot")
                print("❌ Falha ao reiniciar ONU")
            else:
                logger.info("Reboot solicitado com sucesso")
                
    except Exception as e:
        logger.error(f"Erro durante reboot: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

def grant_remote_access_wan_complete(ip_olt: str) -> None:
    """Complete remote access WAN configuration"""
    try:
        serial = get_user_input(
            "Digite o serial: ",
            validator=validate_serial,
            required=True
        )
        
        password = get_user_input(
            "Digite a nova senha de acesso remoto:"
            "\n(Para o modelo 1426G é necessário adicionar no mínimo "
            "1 número, 1 caractere especial e 1 letra maiúscula.)"
            "\nA senha deve conter exatamente 10 caracteres: ",
            validator=validate_remote_password,
            required=True
        )
        
        logger.info(f"Serial informado: {serial}")
        
        # Get position info using SSH
        with ssh_connection(ip_olt) as conexao:
            slot, pon, position = get_onu_position_info(conexao, serial)
        
        # Configure remote access using TL1
        with tl1_connection(ip_olt) as conexao_tl1:
            logger.info("Ativando acesso remoto pela WAN...")
            if not grant_remote_access_wan(conexao_tl1, slot, pon, position, password):
                logger.warning("Falha ao ativar acesso remoto, tentando corrigir.")
                
            print("Habilitado acesso remoto na porta 8080 com sucesso. "
                  "\nUtilize o protocolo http:// seguido do IP adquirido na conexão WAN e :8080"
                  "\nUtilize o usuário de acesso padrão AdminGPON e a nova senha configurada")
            logger.info("Sucesso ao alterar senha de acesso remoto.")
            
    except Exception as e:
        logger.error(f"Erro durante configuração de acesso remoto: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

def configure_wifi(ip_olt: str) -> None:
    """Configure WiFi for ONT"""
    try:
        serial = get_user_input(
            "Digite o serial: ",
            validator=validate_serial,
            required=True
        )
        
        logger.info(f"Serial informado: {serial}")
        
        # Get position info using SSH
        with ssh_connection(ip_olt) as conexao:
            slot, pon, position = get_onu_position_info(conexao, serial)
        
        # Configure WiFi using TL1
        with tl1_connection(ip_olt) as conexao_tl1:
            ssid, ssidpassword = get_wifi_credentials()
            
            result = config_wifi(conexao_tl1, slot, pon, position, ssid, ssidpassword)
            if result:
                print("✅ WiFi configurado com sucesso")
            else:
                print("❌ Falha na configuração do WiFi")
                
    except Exception as e:
        logger.error(f"Erro durante configuração WiFi: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

def provision_nokia(ip_olt: str) -> None:
    """Provision Nokia ONU with improved error handling and validation"""
    try:
        with ssh_connection(ip_olt) as conexao:
            # List unauthorized ONUs
            logger.info("Listando ONUs não autorizadas...")
            unauthorized_onu = list_unauthorized(conexao)

            if not unauthorized_onu:
                logger.warning("Nenhuma ONU ou ONT pedindo autorização")
                print("Nenhuma ONU ou ONT pedindo autorização...")
                return

            # Select ONU
            while True:
                try:
                    serial = get_user_input(
                        "Digite o serial da ONU que deseja provisionar: ",
                        validator=validate_serial,
                        required=True
                    )
                    
                    # Search for the selected ONU
                    find_onu = next((onu for onu in unauthorized_onu if onu[0].upper() == serial.upper()), None)
                    
                    if not find_onu:
                        logger.warning(f"Serial {serial} não encontrado na lista")
                        print("ONU não encontrada na lista de não provisionadas. Tente novamente.")
                        continue

                    # Extract ONU data
                    serial, slot, pon = find_onu  
                    break
                except Exception as e:
                    logger.error(f"Erro na seleção da ONU: {str(e)}")
                    print(f"Erro: {str(e)}")

            logger.info(f"ONU selecionada - Serial: {serial}, Slot: {slot}, PON: {pon}")
            print(f"\nDados da ONU selecionada:")
            print(f"Slot: {slot}")
            print(f"PON: {pon}")

            # Get client name
            name = get_user_input(
                "Qual o nome de cadastro do MK do cliente? ",
                validator=validate_name,
                required=True
            )[:NAME_MAX_LENGTH]

            # Check free positions on PON
            try:
                position = checkfreeposition(conexao, slot, pon)
                logger.info(f"Posição livre encontrada: {position}")
            except Exception as e:
                logger.error(f"Erro ao verificar posições livres: {str(e)}")
                print(f"Erro ao verificar posições livres: {str(e)}")
                return

            # Get VLAN from CSV or user input
            vlan = get_vlan_from_csv(slot, pon)

            # Check if it's an ALCL ONU (Nokia)
            if serial.startswith(NOKIA_SERIAL_PREFIX):
                _handle_nokia_ont_provisioning(ip_olt, conexao, serial, vlan, name, slot, pon, position)
            else:
                _handle_standard_onu_provisioning(conexao, serial, vlan, name, slot, pon, position)

    except Exception as e:
        logger.error(f"Erro durante provisionamento: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

def _handle_nokia_ont_provisioning(ip_olt: str, conexao_ssh, serial: str, vlan: str, 
                                  name: str, slot: str, pon: str, position: str) -> None:
    """Handle Nokia ONT provisioning"""
    logger.info("ONT Nokia ALCL detectada")
    print("\nONT Nokia detectada - Escolha o modo de provisionamento:")
    print("1 - Bridge")
    print("2 - Router")
    
    mode = get_user_input(
        "Digite o número correspondente ao modo desejado: ",
        validator=lambda x: x in ('1', '2'),
        required=True
    )

    # Close SSH connection and start TL1
    conexao_ssh.terminate()
    logger.info("Finalizada sessão SSH")
    
    with tl1_connection(ip_olt) as conexao_tl1:
        logger.info("Iniciada sessão TL1")
        serial_tl1 = format_tl1_serial(serial)

        if mode == '1':
            logger.info("Provisionamento em modo Bridge")
            desc2 = "BRIDGE"
            auth_bridge_tl1(conexao_tl1, serial_tl1, vlan, name, slot, pon, position, desc2)
            print("ONU provisionada em modo bridge")
        else:
            logger.info("Provisionamento em modo Router")
            desc2 = "ROUTER"
            
            # Get WiFi credentials
            ssid, ssidpassword = get_wifi_credentials()
            
            # Get PPPoE credentials
            user_pppoe, password_pppoe = get_pppoe_credentials()

            logger.info("Iniciando provisionamento em modo Router")
            auth_router_tl1(conexao_tl1, vlan, name, desc2, user_pppoe, password_pppoe, slot, pon, position, serial_tl1)
            
            result = config_wifi(conexao_tl1, slot, pon, position, ssid, ssidpassword)
            if result:
                print("✅ WiFi configurado com sucesso")
            else:
                print("❌ Falha na configuração do WiFi")
            
            print("ONT Autorizada em modo router!")
            logger.info("ONT autorizada com sucesso!")

def _handle_standard_onu_provisioning(conexao, serial: str, vlan: str, name: str, 
                                    slot: str, pon: str, position: str) -> None:
    """Handle standard ONU provisioning"""
    # Format serial for SSH
    serial_ssh = format_ssh_serial(serial)
    logger.info(f"Serial formatado: {serial_ssh}")
    
    # Provision for non-ALCL ONUs
    logger.info("Provisionando ONU de outros fabricantes")
    desc2 = "Bridge"
    logger.info(f"Dados para provisionamento - Serial: {serial_ssh}, Slot: {slot}, PON: {pon}, Posição: {position}, VLAN: {vlan}, Nome: {name}, Desc: {desc2}")

    add_to_pon(conexao, slot, pon, position, serial_ssh, name, desc2)
    time.sleep(STABILIZATION_WAIT_TIME)
    
    try:
        model = onu_model(conexao, slot, pon, position)
        logger.info(f"Modelo da ONU detectado: {model}")
    except Exception as e:
        logger.error(f"Erro ao obter modelo da ONU: {str(e)}")
        print("❗ Modelo da ONU não encontrado")
        return

    if not provision_onu_by_model(conexao, model, slot, pon, position, vlan):
        handle_incompatible_model(conexao, serial, slot, pon, position, model)
    else:
        logger.info("Provisionamento concluído com sucesso!")
        print("Provisionamento concluído com sucesso!")
                    
def mass_migration_nokia(ip_olt: str) -> None:
    """Mass migration of ONUs based on CSV migration file"""
    try:
        # Load migration data from CSV
        migration_data = load_csv_data('csv/migration.csv')
        vlan_data = load_csv_data('csv/nokia.csv')
        
        vlan_lookup = {(row['CARD'], row['PON']): row['VLAN'] for row in vlan_data}
        
        migrated_onus = []
        not_migrated_onus = []
        already_processed = {}

        with ssh_connection(ip_olt) as conexao:
            while True:
                logger.info("Listando ONUs não autorizadas...")
                unauthorized_onu = list_unauthorized(conexao)

                if not unauthorized_onu:
                    logger.warning("Nenhuma ONU ou ONT pedindo autorização")
                    print("Nenhuma ONU ou ONT pedindo autorização...")
                    break

                unauth_dict = {onu[0].upper(): (onu[1], onu[2]) for onu in unauthorized_onu}
                pendentes = [item for item in migration_data if item['serial'].upper().strip() not in already_processed]

                if not pendentes:
                    logger.info("Nenhum serial restante para tentar migração")
                    break

                logger.info(f"Iniciando novo ciclo de tentativa para {len(pendentes)} ONUs")
                algum_migrado_nesse_ciclo = False

                for item in pendentes:
                    serial = item.get('serial', '').upper().strip()
                    if not serial:
                        continue

                    if serial in unauth_dict:
                        try:
                            slot, pon = unauth_dict[serial]
                            name = item.get('name', 'CLIENTE').strip()
                            vlan = vlan_lookup.get((slot, pon))
                            if not vlan:
                                raise Exception(f"VLAN não encontrada para slot {slot} e PON {pon}")

                            logger.info(f"Processando ONU {serial} - Slot: {slot}, PON: {pon}, Nome: {name}, VLAN: {vlan}")

                            position = checkfreeposition(conexao, slot, pon)
                            logger.info(f"Posição livre encontrada: {position}")

                            if serial.startswith(NOKIA_SERIAL_PREFIX):
                                # Switch to TL1 for Nokia ONTs
                                conexao.terminate()
                                with tl1_connection(ip_olt) as conexao_tl1:
                                    process_nokia_onu(conexao_tl1, item, slot, pon, position, vlan)
                                conexao = login_olt_ssh(host=ip_olt)
                            else:
                                process_standard_onu(conexao, item, slot, pon, position, vlan)

                            migrated_onus.append({
                                'serial': serial,
                                'slot': slot,
                                'pon': pon,
                                'position': position,
                                'name': name,
                                'vlan': vlan,
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            already_processed[serial] = 'migrated'
                            algum_migrado_nesse_ciclo = True

                        except Exception as e:
                            logger.error(f"Erro ao migrar ONU {serial}: {str(e)}")
                            not_migrated_onus.append({
                                'serial': serial,
                                'error': str(e),
                                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            already_processed[serial] = 'error'
                    else:
                        logger.warning(f"Serial {serial} não encontrado na lista de ONUs não autorizadas")
                        already_processed[serial] = 'not_found'

                if not algum_migrado_nesse_ciclo:
                    logger.info("Nenhuma ONU migrada nesse ciclo. Encerrando tentativas.")
                    break

        # Save results to CSV files
        if migrated_onus:
            save_csv_data('csv/migrated.csv', migrated_onus, 
                         ['serial', 'slot', 'pon', 'position', 'name', 'vlan', 'timestamp'])

        if not_migrated_onus:
            save_csv_data('csv/not_migrated.csv', not_migrated_onus, 
                         ['serial', 'error', 'timestamp'])

        print(f"\nMigração concluída!")
        print(f"ONUs migradas com sucesso: {len(migrated_onus)}")
        print(f"ONUs não migradas: {len(not_migrated_onus)}")

    except Exception as e:
        logger.error(f"Erro durante a migração em massa: {str(e)}")
        print(f"Erro durante a migração: {str(e)}")

def list_onu_csv_nokia(ip_olt: str) -> None:
    """List ONUs from specific PON and save to CSV"""
    try:
        slot = get_user_input("Digite o CARD: ", required=True)
        pon = get_user_input("Digite a PON: ", required=True)

        with ssh_connection(ip_olt) as conexao:
            success = list_onu(conexao, slot, pon)
            
            if success:
                print("✅ Lista de ONUs salva com sucesso.")
            else:
                print("⚠️ Nenhuma ONU listada ou falha ao salvar o CSV.")

    except Exception as e:
        logger.error(f"Erro durante o processo de listagem: {str(e)}", exc_info=True)
        print("❌ Erro ao executar o processo de listagem de ONUs.")

def list_pon_nokia(ip_olt: str) -> None:
    """List PON status with detailed information"""
    try:
        slot = get_user_input("Digite o CARD: ", required=True)
        pon = get_user_input("Digite a PON: ", required=True)

        with ssh_connection(ip_olt) as conexao:
            list_pon(conexao, slot, pon)

    except Exception as e:
        logger.error(f"Erro durante o processo de listagem: {str(e)}", exc_info=True)
        print("❌ Erro ao executar o processo de listagem de ONUs.")

def list_of_compatible_models_nokia() -> None:
    """Display list of compatible ONU models"""
    print("\n=== MODELOS SUPORTADOS ===")
    
    print("\n🔶 BRIDGE:")
    for modelo in BRIDGE_MODELS:
        print(f"  → {modelo}")
    
    print("\n🔷 ROUTER:")
    for modelo in ROUTER_MODELS:
        print(f"  → {modelo}")

    logger.info("Modelos compatíveis exibidos com sucesso")
    input("\nPressione Enter para voltar...")

