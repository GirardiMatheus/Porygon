from dotenv import load_dotenv
import os
import time
from services.parks_service import *
from services.nokia_service import *
from utils.log import get_logger

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Carrega variáveis de ambiente
load_dotenv()

class OLTManager:
    def _init_(self):
        self.current_olt = None
        self.vendor_type = None

    def set_olt(self, ip, vendor):
        """Configura a OLT atual e seu fabricante"""
        self.current_olt = ip
        self.vendor_type = vendor.lower()
        logger.info(f"OLT configurada: {ip} ({vendor})")

def clear_screen():
    """Limpa a tela do console"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_menu(title, options):
    """Exibe um menu e retorna a escolha do usuário"""
    clear_screen()
    print(f"\n{title}")
    for key, value in options.items():
        description = value[0] if isinstance(value, tuple) else value
        print(f"[{key}] {description}")
    return input("\nINSIRA A OPÇÃO DESEJADA: ")

def get_olt_connection(manager, vendor):
    """Obtém a conexão com a OLT selecionada"""
    olt_options = {
        'parks': {
            1: ("LAB_Parks", os.getenv('LAB_IP_PARKS')),
            2: ("BACAXA 01", os.getenv('BACAXA_IP_01')),
            3: ("BACAXA 02", os.getenv('BACAXA_IP_02')),
            4: ("SAMBE", os.getenv('SAMBE_IP_01'))
        },
        'nokia': {
            1: ("LAB_Nokia", os.getenv('LAB_IP')),
            2: ("NOKIA_INOA", os.getenv('INOA_IP')),
            3: ("NOKIA_ITAIPUACU", os.getenv('ITAIPUACU_IP')),
            4: ("NOKIA_NITEROI", os.getenv('NITEROI_IP')),
            5: ("NOKIA_BACAXA", os.getenv('BACAXA_IP')),
            6: ("NOKIA_SAMPAIO", os.getenv('SAMPAIO_IP')),
            7: ("NOKIA_SAQUAREMA", os.getenv('SAQUAREMA_IP'))
        }
    }

    while True:
        choice = show_menu(f"Escolha a OLT {vendor.upper()} desejada:", olt_options[vendor])

        if choice.isdigit() and int(choice) in olt_options[vendor]:
            name, ip = olt_options[vendor][int(choice)]
            if ip:
                manager.set_olt(ip, vendor)
                return True
            logger.warning(f"IP não configurado para a OLT: {name}")
            print("IP não configurado para esta OLT!")
        else:
            logger.warning(f"Opção inválida no menu de OLTs: {choice}")
            print("Opção inválida!")
        time.sleep(1)
    return False

def handle_vendor_menu(manager, vendor):
    """Menu específico para cada fabricante"""
    menu_options = {
        'parks': {
            '1': ("Provisionar ONU", provision),
            '2': ("Desautorizar ONU", unauthorized_complete),
            '3': ("Listar ONU/ONT pedindo autorização", onu_list),
            '4': ("Consultar Informações da ONU/ONT", consult_information_complete),
            '5': ("Reiniciar ONU/ONT", reboot_complete),
            '6': ("Lista de modelos compatíveis", list_of_compatible_models),
            '7': ("Fechar", exit)
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
            '9': ("Migração em massa", mass_migration_nokia),
            '10': ("Fechar", exit)
        }
    }

    while True:
        choice = show_menu(f"MENU {vendor.upper()}", menu_options[vendor])
        logger.info(f"Menu {vendor.upper()} - Opção selecionada: {choice}")

        if choice == '10':
            logger.info("Sistema encerrado pelo menu")
            clear_screen()
            exit()

            
        if choice in menu_options[vendor]:
            try:
                if choice == '6':  
                    menu_options[vendor][choice][1]()
                    input("\nPressione Enter para continuar...")
                    continue

                if not manager.current_olt:
                    print("Nenhuma OLT selecionada!")
                    logger.warning("Tentativa de executar ação sem OLT definida")
                    time.sleep(1)
                    continue


                function = menu_options[vendor][choice][1]
                logger.info(f"Executando função: {function.__name__}")
                
                function(ip_olt=manager.current_olt)

                logger.info(f"Concluído: {function.__name__}")
                input("\nPressione Enter para continuar...")

            except Exception as e:
                logger.error(f"Erro na execução: {str(e)}", exc_info=True)
                print(f"Erro na operação: {str(e)}")
                time.sleep(2)
        else:
            print("Opção inválida!")
            logger.warning(f"Opção inválida no menu do fabricante: {choice}")
            time.sleep(1)

def main():
    """Função principal do sistema"""
    logger.info("Sistema iniciado")
    manager = OLTManager()

    vendor_options = {
        '1': "NOKIA",
        '2': "PARKS"
    }

    try:
        while True:
            choice = show_menu("Escolha o fabricante:", vendor_options)
            logger.info(f"Fabricante selecionado: {choice}")

            if choice in vendor_options:
                vendor = vendor_options[choice].lower()
                if get_olt_connection(manager, vendor):
                    handle_vendor_menu(manager, vendor)
            else:
                logger.warning(f"Opção inválida de fabricante: {choice}")
                print("Opção inválida!")
                time.sleep(1)

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