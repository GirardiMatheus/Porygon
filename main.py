from dotenv import load_dotenv
import os
import time
from services.parks_service import *

# Carrega variáveis de ambiente
load_dotenv()

class OLTManager:
    def __init__(self):
        self.current_olt = None
        self.ssh_credentials = {
            'user': os.getenv('SSH_USER_PARKS'),
            'password': os.getenv('SSH_PASSWORD_PARKS')
        }
        
    def set_olt(self, ip):
        """Configura a OLT atual"""
        self.current_olt = ip
        log_interaction(f"OLT configurada: {ip}")

def clear_screen():
    """Limpa a tela do console"""
    os.system('cls' if os.name == 'nt' else 'clear')

def show_menu(title, options):
    """Exibe um menu e retorna a escolha do usuário"""
    clear_screen()
    print(f"\n{title}")
    for key, value in options.items():
        # Trata tanto valores simples quanto tuplas
        description = value[0] if isinstance(value, tuple) else value
        print(f"[{key}] {description}")
    return input("\nINSIRA A OPÇÃO DESEJADA: ")

def get_olt_connection(manager):
    """Obtém a conexão com a OLT selecionada"""
    olt_options = {
        1: ("LAB", os.getenv('LAB_IP_PARKS')),
        2: ("BACAXA 01", os.getenv('BACAXA_IP_01')),
        3: ("BACAXA 02", os.getenv('BACAXA_IP_02')),
        4: ("SAMBE", os.getenv('SAMBE_IP_01'))
    }
    
    while True:
        choice = show_menu("Escolha a OLT desejada:", olt_options)
        
        if choice.isdigit() and int(choice) in olt_options:
            _, ip = olt_options[int(choice)]
            if ip:
                manager.set_olt(ip)
                return
            print("IP não configurado para esta OLT!")
        else:
            print("Opção inválida!")
        time.sleep(1)

def handle_parks_menu(manager):
    """Menu específico para OLTs PARKS"""
    menu_options = {
        1: ("Provisionar ONU", "provision"),
        2: ("Desautorizar ONU", "unauthorized_complete"),
        3: ("Listar ONU/ONT pedindo autorização", "onu_list"),
        4: ("Consultar Informações da ONU/ONT", "consult_information_complete"),
        5: ("Reiniciar ONU/ONT", "reboot_complete"),
        6: ("Lista de modelos compatíveis", "list_of_compatible_models"),
        7: ("Fechar", "exit")
    }
    
    while True:
        choice = show_menu("MENU PARKS", menu_options)
        log_interaction(f"Menu PARKS - Opção selecionada: {choice}")
        
        if choice == '7':
            exit()
            break
            
        if choice in ('1', '2', '3', '4', '5', '6'):  
            try:
                if choice == '6':  
                    list_of_compatible_models()
                    continue
                    
                if not manager.current_olt:
                    print("Nenhuma OLT selecionada!")
                    time.sleep(1)
                    continue
                    
                function_name = menu_options[int(choice)][1]
                log_interaction(f"Executando: {function_name}")
                
                globals()[function_name](ip_olt=manager.current_olt)
                
                log_interaction(f"Concluído: {function_name}")
                input("\nPressione Enter para continuar...")
                
            except Exception as e:
                error_msg = f"Erro em {function_name}: {str(e)}"
                log_interaction(error_msg)
                print(error_msg)
                time.sleep(2)
        else:
            print("Opção inválida!")
            time.sleep(1)

def main():
    log_interaction("Sistema iniciado")
    manager = OLTManager()
    
    vendor_options = {
        1: "NOKIA", 
        2: "PARKS"
    }
    
    try:
        while True:
            choice = show_menu("Escolha o fabricante:", vendor_options)
            log_interaction(f"Fabricante selecionado: {choice}")
            
            if choice == '1':
                print("Opção NOKIA em desenvolvimento")
                time.sleep(1)
            elif choice == '2':
                get_olt_connection(manager)
                if manager.current_olt:
                    handle_parks_menu(manager)
            else:
                print("Opção inválida!")
                time.sleep(1)
                
    except KeyboardInterrupt:
        log_interaction("Sistema encerrado pelo usuário")
        print("\nEncerrando programa...")
    except Exception as e:
        log_interaction(f"ERRO GRAVE: {str(e)}")
        print(f"Erro inesperado: {str(e)}")
    finally:
        log_interaction("Sistema encerrado")

if __name__ == "__main__":
    main()