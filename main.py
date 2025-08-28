"""
Main module for OLT management system.
Provides menu-driven interface for Nokia and Parks OLT operations.
"""

import os
import time
import json
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

# Carrega configuração do JSON
with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

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
    """Get OLT configurations for a specific vendor from config.json"""
    vendor_data = CONFIG["vendors"].get(vendor, {})
    olts = vendor_data.get("olts", [])
    result = {}
    for idx, olt in enumerate(olts, start=1):
        ip = os.getenv(olt["env_ip"])
        result[idx] = OLTConfiguration(olt["name"], ip, vendor)
    return result

def save_config():
    """Salva o CONFIG atualizado no arquivo config.json"""
    with open(os.path.join(os.path.dirname(__file__), "config.json"), "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, indent=2, ensure_ascii=False)

def add_olt_to_config(vendor: str):
    """Adiciona uma nova OLT ao config.json"""
    name = input("Nome da nova OLT: ").strip()
    env_ip = input("Nome da variável de ambiente do IP (ex: NOVA_OLT_IP): ").strip()
    if not name or not env_ip:
        print("❌ Nome e variável de ambiente são obrigatórios.")
        time.sleep(SLEEP_SHORT)
        return
    # Verifica duplicidade
    olts = CONFIG["vendors"][vendor]["olts"]
    if any(olt["name"] == name or olt["env_ip"] == env_ip for olt in olts):
        print("❌ Já existe uma OLT com esse nome ou variável de ambiente.")
        time.sleep(SLEEP_SHORT)
        return
    olts.append({"name": name, "env_ip": env_ip})
    save_config()
    print(f"✅ OLT '{name}' cadastrada. Configure a variável de ambiente '{env_ip}' para o IP.")
    time.sleep(SLEEP_SHORT)

def remove_olt_from_config(vendor: str):
    """Remove uma OLT do config.json"""
    olts = CONFIG["vendors"][vendor]["olts"]
    if not olts:
        print("Nenhuma OLT cadastrada para remover.")
        time.sleep(SLEEP_SHORT)
        return
    print("\nOLTs cadastradas:")
    for idx, olt in enumerate(olts, start=1):
        print(f"[{idx}] {olt['name']} ({olt['env_ip']})")
    try:
        idx = int(input("Digite o número da OLT para remover: ").strip())
        if 1 <= idx <= len(olts):
            removed = olts.pop(idx - 1)
            save_config()
            print(f"✅ OLT '{removed['name']}' removida.")
        else:
            print("❌ Opção inválida.")
    except ValueError:
        print("❌ Entrada inválida.")
    time.sleep(SLEEP_SHORT)

def get_olt_connection(manager: OLTManager, vendor: str) -> bool:
    """Obtém a conexão com a OLT selecionada"""
    while True:
        configurations = get_olt_configurations(vendor)
        menu_options = {}
        for key, config in configurations.items():
            menu_options[str(key)] = (config.name, config.ip)
        menu_options["A"] = "Cadastrar nova OLT"
        menu_options["R"] = "Remover OLT"
        menu_options[BACK_OPTION] = "Voltar"
        
        choice = show_menu(f"Escolha a OLT {vendor.upper()} desejada:", menu_options)

        if choice.upper() == BACK_OPTION:
            logger.info("Retornando ao menu anterior")
            return False
        if choice.upper() == "A":
            add_olt_to_config(vendor)
            continue
        if choice.upper() == "R":
            remove_olt_from_config(vendor)
            continue

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
    """Get menu options for each vendor from config.json"""
    # Mapeamento global de nomes de funções para funções reais
    function_map = {
        # Parks
        "provision": provision,
        "unauthorized_complete": unauthorized_complete,
        "onu_list": onu_list,
        "consult_information_complete": consult_information_complete,
        "reboot_complete": reboot_complete,
        "list_of_compatible_models": list_of_compatible_models,
        "list_onu_csv_parks": list_onu_csv_parks,
        # Nokia
        "provision_nokia": provision_nokia,
        "unauthorized_complete_nokia": unauthorized_complete_nokia,
        "onu_list_nokia": onu_list_nokia,
        "consult_information_complete_nokia": consult_information_complete_nokia,
        "reboot_complete_nokia": reboot_complete_nokia,
        "list_of_compatible_models_nokia": list_of_compatible_models_nokia,
        "grant_remote_access_wan_complete": grant_remote_access_wan_complete,
        "configure_wifi": configure_wifi,
        "list_pon_nokia": list_pon_nokia,
        "mass_migration_nokia": mass_migration_nokia,
        "list_onu_csv_nokia": list_onu_csv_nokia
    }
    menu = {}
    for vendor, data in CONFIG["vendors"].items():
        commands = {}
        for cmd in data.get("commands", []):
            func = function_map.get(cmd["function"]) if cmd["function"] else None
            commands[cmd["key"]] = (cmd["desc"], func)
        menu[vendor] = commands
    return menu

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
