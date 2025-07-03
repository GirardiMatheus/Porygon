"""
Main module for OLT management system.
Provides menu-driven interface for Nokia and Parks OLT operations.
"""

import os
import time
from typing import Optional, Dict, Tuple, Callable, Any
from dataclasses import dataclass

from dotenv import load_dotenv
from services.parks_service import *
from services.nokia_service import *
from utils.log import get_logger

# Constants
VENDOR_NOKIA = "nokia"
VENDOR_PARKS = "parks"
EXIT_OPTION = "0"
BACK_OPTION = "B"
MODELS_OPTION = "6"
SLEEP_SHORT = 1
SLEEP_MEDIUM = 2

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Carrega variáveis de ambiente
load_dotenv()

@dataclass
class OLTConfiguration:
    """Configuration for OLT instances"""
    name: str
    ip: Optional[str]
    vendor: str

class OLTManager:
    """Manages current OLT connection and vendor type"""
    
    def __init__(self) -> None:
        self.current_olt: Optional[str] = None
        self.vendor_type: Optional[str] = None
        logger.info("OLTManager inicializado")

    def set_olt(self, ip: str, vendor: str) -> None:
        """Configura a OLT atual e seu fabricante"""
        self.current_olt = ip
        self.vendor_type = vendor.lower()
        logger.info(f"OLT configurada: {ip} ({vendor})")

    def is_olt_selected(self) -> bool:
        """Verifica se uma OLT está selecionada"""
        return self.current_olt is not None

    def clear_olt(self) -> None:
        """Limpa a OLT atual"""
        logger.info(f"Limpando OLT atual: {self.current_olt}")
        self.current_olt = None
        self.vendor_type = None

def clear_screen() -> None:
    """Limpa a tela do console"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_menu(title: str, options: Dict[str, Any]) -> str:
    """Exibe um menu e retorna a escolha do usuário"""
    clear_screen()
    print(f"\n{title}")
    for key, value in options.items():
        description = value[0] if isinstance(value, tuple) else value
        print(f"[{key}] {description}")
    choice = input("\nINSIRA A OPÇÃO DESEJADA: ").strip()
    logger.debug(f"Menu '{title}' - Opção selecionada: {choice}")
    return choice

def get_olt_configurations(vendor: str) -> Dict[int, OLTConfiguration]:
    """Get OLT configurations for a specific vendor"""
    configurations = {
        VENDOR_PARKS: {
            1: OLTConfiguration("LAB_Parks", os.getenv('LAB_IP_PARKS'), VENDOR_PARKS),
            2: OLTConfiguration("BACAXA 01", os.getenv('BACAXA_IP_01'), VENDOR_PARKS),
            3: OLTConfiguration("BACAXA 02", os.getenv('BACAXA_IP_02'), VENDOR_PARKS),
            4: OLTConfiguration("SAMBE", os.getenv('SAMBE_IP_01'), VENDOR_PARKS)
        },
        VENDOR_NOKIA: {
            1: OLTConfiguration("LAB_Nokia", os.getenv('LAB_IP'), VENDOR_NOKIA),
            2: OLTConfiguration("NOKIA_INOA", os.getenv('INOA_IP'), VENDOR_NOKIA),
            3: OLTConfiguration("NOKIA_ITAIPUACU", os.getenv('ITAIPUACU_IP'), VENDOR_NOKIA),
            4: OLTConfiguration("NOKIA_NITEROI", os.getenv('NITEROI_IP'), VENDOR_NOKIA),
            5: OLTConfiguration("NOKIA_BACAXA", os.getenv('BACAXA_IP'), VENDOR_NOKIA),
            6: OLTConfiguration("NOKIA_SAMPAIO", os.getenv('SAMPAIO_IP'), VENDOR_NOKIA),
            7: OLTConfiguration("NOKIA_SAQUAREMA", os.getenv('SAQUAREMA_IP'), VENDOR_NOKIA)
        }
    }
    return configurations.get(vendor, {})

def get_olt_connection(manager: OLTManager, vendor: str) -> bool:
    """Obtém a conexão com a OLT selecionada"""
    configurations = get_olt_configurations(vendor)
    
    if not configurations:
        logger.error(f"Nenhuma configuração encontrada para o vendor: {vendor}")
        print("❌ Vendor não suportado!")
        return False

    while True:
        menu_options = {}
        for key, config in configurations.items():
            menu_options[str(key)] = (config.name, config.ip)
        menu_options[BACK_OPTION] = "Voltar"
        
        choice = show_menu(f"Escolha a OLT {vendor.upper()} desejada:", menu_options)

        if choice.upper() == BACK_OPTION:
            logger.info("Retornando ao menu anterior")
            return False

        try:
            choice_int = int(choice)
            if choice_int in configurations:
                config = configurations[choice_int]
                if config.ip:
                    manager.set_olt(config.ip, vendor)
                    logger.info(f"OLT selecionada: {config.name} ({config.ip})")
                    print(f"✅ OLT {config.name} selecionada com sucesso!")
                    time.sleep(SLEEP_SHORT)
                    return True
                else:
                    logger.warning(f"IP não configurado para a OLT: {config.name}")
                    print(f"❌ IP não configurado para a OLT: {config.name}")
            else:
                logger.warning(f"Opção inválida no menu de OLTs: {choice}")
                print("❌ Opção inválida!")
        except ValueError:
            logger.warning(f"Entrada inválida no menu de OLTs: {choice}")
            print("❌ Opção inválida!")
        
        time.sleep(SLEEP_SHORT)

def get_vendor_menu_options() -> Dict[str, Dict[str, Tuple[str, Optional[Callable]]]]:
    """Get menu options for each vendor"""
    return {
        'parks': {
            '1': ("Provisionar ONU", provision),
            '2': ("Desautorizar ONU", unauthorized_complete),
            '3': ("Listar ONU/ONT pedindo autorização", onu_list),
            '4': ("Consultar Informações da ONU/ONT", consult_information_complete),
            '5': ("Reiniciar ONU/ONT", reboot_complete),
            '6': ("Lista de modelos compatíveis", list_of_compatible_models),
            '7': ("Criar csv para migração ou divisão de pon", list_onu_csv_parks),
            '0': ("Voltar ao menu anterior", None)
        },
        'nokia': {
            '1': ("Provisionar ONU", provision_nokia),
            '2': ("Desautorizar ONU", unauthorized_complete_nokia),
            '3': ("Listar ONU/ONT pedindo autorização", onu_list_nokia),
            '4': ("Consultar Informações da ONU/ONT", consult_information_complete_nokia),
            '5': ("Reiniciar ONU/ONT", reboot_complete_nokia),
            '6': ("Lista de modelos compatíveis", list_of_compatible_models_nokia),
            '7': ("Habilitar acesso remoto pela WAN", grant_remote_access_wan_complete),
            '8': ("Configurar WIFI", configure_wifi),
            '9': ("Listar ONU na PON", list_pon_nokia),
            '10': ("Migração em massa", mass_migration_nokia),
            '11': ("Criar csv para migração ou divisão de PON", list_onu_csv_nokia),
            '0': ("Voltar ao menu anterior", None)
        }
    }

def execute_vendor_function(manager: OLTManager, function: Callable, choice: str) -> None:
    """Execute vendor-specific function with proper error handling"""
    try:
        if choice == MODELS_OPTION:
            # Models function doesn't need OLT IP
            function()
            input("\nPressione Enter para continuar...")
            return

        if not manager.current_olt:
            print("❌ Nenhuma OLT selecionada!")
            logger.warning("Tentativa de executar ação sem OLT definida")
            time.sleep(SLEEP_SHORT)
            return

        logger.info(f"Executando função: {function.__name__}")
        function(ip_olt=manager.current_olt)
        logger.info(f"Concluído: {function.__name__}")
        input("\nPressione Enter para continuar...")

    except Exception as e:
        logger.error(f"Erro na execução da função {function.__name__}: {str(e)}", exc_info=True)
        print(f"❌ Erro na operação: {str(e)}")
        time.sleep(SLEEP_MEDIUM)

def handle_vendor_menu(manager: OLTManager, vendor: str) -> None:
    """Menu específico para cada fabricante"""
    menu_options = get_vendor_menu_options()
    
    if vendor not in menu_options:
        logger.error(f"Vendor não suportado: {vendor}")
        print(f"❌ Vendor {vendor} não suportado!")
        return

    while True:
        choice = show_menu(f"MENU {vendor.upper()}", menu_options[vendor])
        logger.info(f"Menu {vendor.upper()} - Opção selecionada: {choice}")

        if choice == EXIT_OPTION:
            logger.info("Retornando ao menu anterior")
            return

        if choice in menu_options[vendor]:
            function = menu_options[vendor][choice][1]
            if function:
                execute_vendor_function(manager, function, choice)
            else:
                logger.warning(f"Função não implementada para opção: {choice}")
                print("❌ Função não implementada!")
                time.sleep(SLEEP_SHORT)
        else:
            print("❌ Opção inválida!")
            logger.warning(f"Opção inválida no menu do fabricante: {choice}")
            time.sleep(SLEEP_SHORT)

def main() -> None:
    """Função principal do sistema"""
    logger.info("Sistema iniciado")
    manager = OLTManager()

    vendor_options = {
        '1': "NOKIA",
        '2': "PARKS",
        '0': "Sair"
    }

    try:
        while True:
            choice = show_menu("Escolha o fabricante:", vendor_options)
            logger.info(f"Fabricante selecionado: {choice}")

            if choice == '0':
                logger.info("Sistema encerrado pelo usuário")
                print("Saindo...")
                break

            if choice in vendor_options:
                vendor = vendor_options[choice].lower()
                if get_olt_connection(manager, vendor):
                    handle_vendor_menu(manager, vendor)
            else:
                logger.warning(f"Opção inválida de fabricante: {choice}")
                print("Opção inválida!")
                time.sleep(SLEEP_SHORT)

    except KeyboardInterrupt:
        logger.info("Sistema encerrado pelo usuário via KeyboardInterrupt")
        print("\nEncerrando programa...")
    except Exception as e:
        logger.critical(f"Erro grave: {str(e)}", exc_info=True)
        print(f"Erro inesperado: {str(e)}")
    finally:
        logger.info("Sistema encerrado")

if __name__ == "__main__":
    main()
