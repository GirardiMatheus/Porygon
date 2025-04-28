from nokia.nokia_ssh import *
from nokia.nokia_tl1 import *
import csv
from utils.log import get_logger

# Logger principal
logger = get_logger(__name__)
logger.info("Sistema iniciado")

def onu_list_nokia(ip_olt):
    conexao = None

    try:
        logger.info(f"Conectando à OLT {ip_olt}...")
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error(f"Falha na conexão com a OLT {ip_olt}")
            return

        logger.info("Conexão SSH estabelecida com sucesso")
        logger.info("Listando ONUs não autorizadas...")
        unauthorized = list_unauthorized(conexao)
        logger.debug(unauthorized)

        if not unauthorized:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            logger.info("Nenhuma ONU ou ONT encontrada na unauthorized")
            return

    finally:
        if conexao:
            logger.info("Encerrando conexão SSH...")
            try:
                conexao.terminate()
                logger.info("Conexão encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar a conexão: {str(e)}")

def unauthorized_complete_nokia(ip_olt):
    conexao = None
    try:
        logger.info(f"Iniciando processo de desautorização para OLT {ip_olt}")
        
        serial = input("Qual o serial da ONU? ").strip()
        if not serial:
            logger.error("Serial não informado pelo usuário")
            print("❌ Serial não pode estar vazio!")
            return False
            
        logger.info(f"Serial informado: {serial}")
        serial_ssh = format_ssh_serial(serial)
        logger.debug(f"Serial formatado para SSH: {serial_ssh}")
        
        logger.info("Estabelecendo conexão SSH...")
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error("Falha na conexão SSH")
            print("❌ Falha ao conectar na OLT")
            return False
        
        logger.info("Consultando informações necessárias...")
        slot, pon, position = check_onu_position(conexao, serial_ssh)

        logger.info("Executando desautorização...")
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
    finally:
        if conexao:
            try:
                logger.info("Encerrando conexão SSH...")
                conexao.terminate()
                logger.info("Conexão encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")

def consult_information_complete_nokia(ip_olt):
    conexao = None
    try:
        logger.info(f"Iniciando consulta completa para OLT {ip_olt}")
        
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error("Falha na conexão SSH")
            print("❌ Falha ao conectar na OLT")
            return
            
        serial = input("Digite o serial: ").strip()
        if not serial:
            logger.error("Serial não informado pelo usuário")
            print("❌ Serial não pode estar vazio!")
            return
            
        logger.info(f"Serial informado: {serial}")
        serial_format = format_ssh_serial(serial)
        logger.debug(f"Serial formatado: {serial_format}")
        
        logger.info("Verificando posição da ONU...")
        slot, pon, position = check_onu_position(conexao, serial_format)
        if not all([slot, pon, position]):
            logger.error("Falha ao obter posição da ONU")
            print("❌ Não foi possível localizar a ONU")
            return
            
        logger.info(f"ONU encontrada - Slot: {slot}, PON: {pon}, Posição: {position}")
        
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
    finally:
        if conexao:
            try:
                logger.info("Encerrando conexão SSH...")
                conexao.terminate()
                logger.info("Conexão encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")

def reboot_complete_nokia(ip_olt):
    conexao_ssh = None
    conexao_tl1 = None
    try:
        logger.info(f"Iniciando reboot para OLT {ip_olt}")
        
        input("Após enviado o comando pode demorar até 3 min até que a ONU seja reiniciada.\nPressione ENTER para prosseguir.")
        
        logger.info("Estabelecendo conexão SSH...")
        conexao_ssh = login_olt_ssh(host=ip_olt)
        if not conexao_ssh:
            logger.error("Falha na conexão SSH")
            print("❌ Falha ao conectar na OLT")
            return
            
        serial = input("Digite o serial: ").strip()
        if not serial:
            logger.error("Serial não informado pelo usuário")
            print("❌ Serial não pode estar vazio!")
            return
            
        logger.info(f"Serial informado: {serial}")
        serial_ssh = format_ssh_serial(serial)
        logger.debug(f"Serial formatado: {serial_ssh}")
        
        logger.info("Verificando posição da ONU...")
        slot, pon, position = check_onu_position(conexao_ssh, serial_ssh)
        if not all([slot, pon, position]):
            logger.error("Falha ao obter posição da ONU")
            print("❌ Não foi possível localizar a ONU")
            return
            
        logger.info(f"ONU encontrada - Slot: {slot}, PON: {pon}, Posição: {position}")
        
        logger.info("Encerrando conexão SSH...")
        conexao_ssh.terminate()
        
        logger.info("Estabelecendo conexão TL1...")
        conexao_tl1 = login_olt_tl1(host=ip_olt)
        if not conexao_tl1:
            logger.error("Falha na conexão TL1")
            print("❌ Falha ao conectar via TL1")
            return
            
        logger.info("Executando reboot...")
        if not reboot_onu(conexao_tl1, slot, pon, position):
            logger.error("Falha no comando de reboot")
            print("❌ Falha ao reiniciar ONU")
        else:
            logger.info("Reboot solicitado com sucesso")
            print("✅ Comando de reboot enviado com sucesso")
            
    except Exception as e:
        logger.error(f"Erro durante reboot: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")
    finally:
        if conexao_ssh:
            try:
                conexao_ssh.terminate()
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")
        if conexao_tl1:
            try:
                conexao_tl1.terminate()
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão TL1: {str(e)}")

def list_of_compatible_models_nokia():
    bridge_models = ["TP-Link: TX-6610, XZ000-G3", "Intelbras: R1v2, 110Gb", 
                    "Fiberhome: AN5506-01-A", "PARKS: Fiberlink100, FiberLink101"]
    router_models = ["NOKIA: G-1425G-A, G-1425G-B, G-1426G-A"]

    print("\n=== MODELOS SUPORTADOS ===")
    
    print("\n🔶 BRIDGE:")
    for modelo in bridge_models:
        print(f"  → {modelo}")
    
    print("\n🔷 ROUTER:")
    for modelo in router_models:
        print(f"  → {modelo}")

    logger.info("Modelos compatíveis exibidos com sucesso")
    input("\nPressione Enter para voltar...")

def grant_remote_access_wan_complete(ip_olt):
    conexao = None
    conexao_tl1 = None
    try:
        logger.info(f"Iniciando consulta completa para OLT {ip_olt}")
        
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error("Falha na conexão SSH")
            print("❌ Falha ao conectar na OLT")
            return
            
        serial = input("Digite o serial: ").strip()
        if not serial:
            logger.error("Serial não informado pelo usuário")
            print("❌ Serial não pode estar vazio!")
            return

        while True:
            try:
                password = input(
                    "Digite a nova senha de acesso remoto:"
                    "\n(Para o modelo 1426G é necessário adicionar no mínimo "
                    "1 número, 1 caractere especial e 1 letra maiúscula.)"
                    "\nA senha deve conter exatamente 10 caracteres: "
                ).strip()

                if not password:
                    raise ValueError("Senha não pode estar vazia!")

                if len(password) != 10:
                    raise ValueError("Senha deve conter exatamente 10 caracteres!")

                break

            except Exception as e:
                logger.error(f"Erro ao validar senha: {str(e)}")
                print(f"❌ Erro: {str(e)}")

        logger.info(f"Serial informado: {serial}")
        serial_format = format_ssh_serial(serial)
        logger.debug(f"Serial formatado: {serial_format}")
        
        logger.info("Verificando posição da ONU...")
        slot, pon, position = check_onu_position(conexao, serial_format)
        if not all([slot, pon, position]):
            logger.error("Falha ao obter posição da ONU")
            print("❌ Não foi possível localizar a ONU")
            return
            
        logger.info(f"ONU encontrada - Slot: {slot}, PON: {pon}, Posição: {position}")

        # Encerrar conexão SSH e iniciar TL1
        conexao.terminate()
        logger.info("Finalizada sessão SSH")
        conexao_tl1 = login_olt_tl1(host=ip_olt)

        logger.info("Iniciada sessão TL1")
        logger.info("Ativando acesso remoto pela WAN...")
        if not grant_remote_access_wan(conexao_tl1, slot, pon, position, password):
            logger.warning("Falha ao ativar acesso remoto, tentando corrigir.")
        print("Habilitado acesso remoto na porta 8080 com sucesso. \
              \nUtilize o protocolo http:// seguido do IP adquirido na conexão WAN e, :8080\
              \nUtilize o usuário de acesso padrão AdminGPON e a nova senha configurada")
        logger.info("Sucesso ao alterar senha de acesso remoto.")
    except Exception as e:
        logger.error(f"Erro durante consulta: {str(e)}", exc_info=True)
        print(f"❌ Erro inesperado: {str(e)}")

    finally:
        if conexao:
            try:
                logger.info("Encerrando conexão SSH...")
                conexao.terminate()
                logger.info("Conexão SSH encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")
        if conexao_tl1:
            try:
                logger.info("Encerrando conexão TL1...")
                conexao_tl1.terminate()
                logger.info("Conexão TL1 encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão TL1: {str(e)}")

def configure_wifi(ip_olt):
    conexao = None
    conexao_tl1 = None
    try:
        logger.info(f"Iniciando consulta completa para OLT {ip_olt}")
        
        conexao = login_olt_ssh(host=ip_olt)
        if not conexao:
            logger.error("Falha na conexão SSH")
            print("❌ Falha ao conectar na OLT")
            return
            
        serial = input("Digite o serial: ").strip()
        if not serial:
            logger.error("Serial não informado pelo usuário")
            print("❌ Serial não pode estar vazio!")
            return

        logger.info(f"Serial informado: {serial}")
        serial_format = format_ssh_serial(serial)
        logger.debug(f"Serial formatado: {serial_format}")
        
        logger.info("Verificando posição da ONU...")
        slot, pon, position = check_onu_position(conexao, serial_format)
        if not all([slot, pon, position]):
            logger.error("Falha ao obter posição da ONU")
            print("❌ Não foi possível localizar a ONU")
            return
            
        logger.info(f"ONU encontrada - Slot: {slot}, PON: {pon}, Posição: {position}")

        # Encerrar conexão SSH e iniciar TL1
        conexao.terminate()
        logger.info("Finalizada sessão SSH")
        conexao_tl1 = login_olt_tl1(host=ip_olt)

        # Obter SSID
        while True:
            try:
                ssid = input("Digite o nome do WIFI: ").strip()
                if not ssid:
                    raise ValueError("Nome do WiFi não pode estar vazio")
                if len(ssid) < 4 or len(ssid) > 32:
                    raise ValueError("Nome do WiFi deve ter entre 4 e 32 caracteres")
                if not re.match(r'^[a-zA-Z0-9_ ]+$', ssid):
                    raise ValueError("Nome do WiFi só pode conter letras, números, espaços e underline")
                break
            except Exception as e:
                logger.error(f"Erro no SSID: {str(e)}")
                print(f"Erro: {str(e)}")

        # Obter senha WiFi
        while True:
            try:
                ssidpassword = input("\nDigite a senha do WIFI \
                \n(Para ONT Nokia 1426G é necessario adicionar a senha \
                \n1 número, 1 caracter especial e uma letra maiuscula no mínimo \
                \npara que a senha seja aplicada corretamente): ").strip()

                if len(ssidpassword) < 8:
                    raise ValueError("Senha deve ter no mínimo 8 caracteres")
                break
            except Exception as e:
                logger.error(f"Erro na senha WiFi: {str(e)}")
                print(f"Erro: {str(e)}")

        result = config_wifi(conexao_tl1, slot, pon, position, ssid, ssidpassword)
        if result:
            print("✅ WiFi configurado com sucesso")
        else:
            print("❌ Falha na configuração do WiFi")
    finally:
        if conexao:
            try:
                logger.info("Encerrando conexão SSH...")
                conexao.terminate()
                logger.info("Conexão SSH encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão SSH: {str(e)}")
        if conexao_tl1:
            try:
                logger.info("Encerrando conexão TL1...")
                conexao_tl1.terminate()
                logger.info("Conexão TL1 encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar conexão TL1: {str(e)}")

def provision_nokia(ip_olt):
    conexao = None
    conexao_tl1 = None
    try:
        # Conexão SSH
        logger.info(f"Conectando à OLT {ip_olt}")
        conexao = login_olt_ssh(host=ip_olt)
        logger.info("Conexão SSH estabelecida com sucesso")

        # Listar ONUs não autorizadas
        logger.info("Listando ONUs não autorizadas...")
        unauthorized_onu = list_unauthorized(conexao)

        if not unauthorized_onu:
            logger.warning("Nenhuma ONU ou ONT pedindo autorização")
            print("Nenhuma ONU ou ONT pedindo autorização...")
            return
        # Seleção da ONU
        while True:
            try:
                serial = input("Digite o serial da ONU que deseja provisionar: ")
                logger.info(f"Serial informado: {serial}")
                
                if not serial:
                    raise ValueError("Serial não pode estar vazio")
                
                # Buscar os dados da ONU selecionada
                find_onu = next((onu for onu in unauthorized_onu if onu[0].upper() == serial), None)
                
                if not find_onu:
                    logger.warning(f"Serial {serial} não encontrado na lista")
                    print("ONU não encontrada na lista de não provisionadas. Tente novamente.")
                    continue

                # Extrai dados da ONU encontrada
                serial, slot, pon = find_onu  
                break
            except Exception as e:
                logger.error(f"Erro na seleção da ONU: {str(e)}")
                print(f"Erro: {str(e)}")

        logger.info(f"ONU selecionada - Serial: {serial}, Slot: {slot}, PON: {pon}")
        print(f"\nDados da ONU selecionada:")
        print(f"Slot: {slot}")
        print(f"PON: {pon}")

        # Obter nome do cliente
        while True:
            try:
                name = input("Qual o nome de cadastro do MK do cliente? ")[:63].strip()
                if not name:
                    raise ValueError("Nome não pode estar vazio")
                logger.info(f"Nome do cliente: {name}")
                break
            except Exception as e:
                logger.error(f"Erro ao obter nome do cliente: {str(e)}")
                print(f"Erro: {str(e)}")

        # Verificar posições livres na PON
        try:
            position = checkfreeposition(conexao, slot, pon)
            logger.info(f"Posição livre encontrada: {position}")
        except Exception as e:
            logger.error(f"Erro ao verificar posições livres: {str(e)}")
            print(f"Erro ao verificar posições livres: {str(e)}")
            return

        # Carregar configurações do CSV
        vlan = None
        csv_path = './csv/nokia.csv'
        try:
            logger.info(f"Consultando CSV em {csv_path}...")
            with open(csv_path, mode='r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if (row['CARD'] == slot and str(row['PON']) == str(pon)):
                        vlan = row['VLAN']
                        logger.info(f"Config CSV - VLAN: {vlan}")
                        break
                else:
                    msg = f"VLAN não encontrada para o CARD {slot} e PON {pon}"
                    logger.warning(msg)
                    print(msg)
                    
                    while not vlan:
                        try:
                            vlan = input("Digite a VLAN: ").strip()
                            if not vlan.isdigit():
                                raise ValueError("VLAN deve conter apenas números")
                            logger.info(f"Valor manual - VLAN: {vlan}")
                        except Exception as e:
                            logger.error(f"Erro ao obter VLAN: {str(e)}")
                            print(f"Erro: {str(e)}")
        except FileNotFoundError:
            logger.error(f"Arquivo CSV não encontrado em {csv_path}")
            print(f"Arquivo CSV não encontrado em {csv_path}")
            
            while not vlan:
                try:
                    vlan = input("Digite a VLAN: ").strip()
                    if not vlan.isdigit():
                        raise ValueError("VLAN deve conter apenas números")
                    logger.info(f"Valor manual - VLAN: {vlan}")
                except Exception as e:
                    logger.error(f"Erro ao obter VLAN: {str(e)}")
                    print(f"Erro: {str(e)}")
        except Exception as e:
            logger.error(f"Erro ao ler CSV: {str(e)}")
            print(f"Erro ao ler CSV: {str(e)}")
            
            while not vlan:
                try:
                    vlan = input("Digite a VLAN: ").strip()
                    if not vlan.isdigit():
                        raise ValueError("VLAN deve conter apenas números")
                    logger.info(f"Valor manual - VLAN: {vlan}")
                except Exception as e:
                    logger.error(f"Erro ao obter VLAN: {str(e)}")
                    print(f"Erro: {str(e)}")

        # Verificar se é uma ONU ALCL
        if serial.startswith(('ALCL')):
            logger.info("ONT Nokia ALCL detectada")
            print("\nONT Nokia detectada - Escolha o modo de provisionamento:")
            serial_tl1 = format_tl1_serial(serial)
            print("1 - Bridge")
            print("2 - Router")
            
            while True:
                try:
                    escolha = input("Digite o número correspondente ao modo desejado: ").strip()
                    if escolha not in ('1', '2'):
                        raise ValueError("Opção inválida")
                    break
                except Exception as e:
                    logger.warning(f"Opção inválida: {escolha}")
                    print("Opção inválida. Digite 1 para Bridge ou 2 para Router")

            # Encerrar conexão SSH e iniciar TL1
            conexao.terminate()
            logger.info("Finalizada sessão SSH")
            conexao_tl1 = login_olt_tl1(host=ip_olt)
            logger.info("Iniciada sessão TL1")

            if escolha == '1':
                logger.info("Provisionamento em modo Bridge")
                desc2 = "BRIDGE"
                auth_bridge_tl1(conexao_tl1, serial_tl1, vlan, name, slot, pon, position, desc2)
                print("ONU provisionada em modo bridge")
            else:
                logger.info("Provisionamento em modo Router")
                desc2 = "ROUTER"
                
                # Obter SSID
                while True:
                    try:
                        ssid = input("Digite o nome do WIFI: ").strip()
                        if not ssid:
                            raise ValueError("Nome do WiFi não pode estar vazio")
                        if len(ssid) < 4 or len(ssid) > 32:
                            raise ValueError("Nome do WiFi deve ter entre 4 e 32 caracteres")
                        if not re.match(r'^[a-zA-Z0-9_ ]+$', ssid):
                            raise ValueError("Nome do WiFi só pode conter letras, números, espaços e underline")
                        break
                    except Exception as e:
                        logger.error(f"Erro no SSID: {str(e)}")
                        print(f"Erro: {str(e)}")

                # Obter senha WiFi
                while True:
                    try:
                        ssidpassword = input("\nDigite a senha do WIFI \
                        \n(Para ONT Nokia 1426G é necessario adicionar a senha \
                        \n1 número, 1 caracter especial e uma letra maiuscula no mínimo \
                        \npara que a senha seja aplicada corretamente): ").strip()

                        if len(ssidpassword) < 8:
                            raise ValueError("Senha deve ter no mínimo 8 caracteres")
                        break
                    except Exception as e:
                        logger.error(f"Erro na senha WiFi: {str(e)}")
                        print(f"Erro: {str(e)}")

                # Obter credenciais PPPoE
                while True:
                    try:
                        user_pppoe = input("Qual o login PPPoE do cliente: ").strip()
                        if not user_pppoe:
                            raise ValueError("Login PPPoE não pode estar vazio")
                        break
                    except Exception as e:
                        logger.error(f"Erro no login PPPoE: {str(e)}")
                        print(f"Erro: {str(e)}")

                while True:
                    try:
                        password_pppoe = input("Qual a senha do PPPoE do cliente: ").strip()
                        if not password_pppoe:
                            raise ValueError("Senha PPPoE não pode estar vazia")
                        break
                    except Exception as e:
                        logger.error(f"Erro na senha PPPoE: {str(e)}")
                        print(f"Erro: {str(e)}")

                logger.info("Iniciando provisionamento em modo Router")
                auth_router_tl1(conexao_tl1, vlan, name, desc2, user_pppoe, password_pppoe, slot, pon, position, serial_tl1)
                result = config_wifi(conexao_tl1, slot, pon, position, ssid, ssidpassword)
                if result:
                    print("✅ WiFi configurado com sucesso")
                else:
                    print("❌ Falha na configuração do WiFi")
                
                print("ONT Autorizada em modo router!")
                logger.info("ONT autorizada com sucesso!")

            # Encerrar conexão TL1
            conexao_tl1.terminate()
            logger.info("Finalizada sessão TL1")
            return
        
        else:
            # Formatando serial
            serial_ssh = format_ssh_serial(serial)
            logger.info(serial_ssh)
            # Provisionamento para ONUs não ALCL
            logger.info("Provisionando ONU de outros fabricantes")
            desc2 = "Bridge"
            logger.info(f"Dados para provisionamento - Serial: {serial_ssh}, Slot: {slot}, PON: {pon}, Posição: {position}, VLAN: {vlan}, Nome: {name}, Desc: {desc2}")

            add_to_pon(conexao, slot, pon, position, serial_ssh, name, desc2)
            time.sleep(10)
            try:
                model = onu_model(conexao, slot, pon, position)
                logger.info(f"Modelo da ONU detectado: {model}")
            except Exception as e:
                logger.error(f"Erro ao obter modelo da ONU: {str(e)}")
                print("❗ Modelo da ONU não encontrado")
                return
            
            # model_group01 não recebe o comando pvid-tagging-flag olt ao final do provisionamento
            model_group01 = {"TX-6610", "R1v2", "XZ000-G3", "Fiberlink100"}
            # model_group02 recebe o comando pvid-tagging-flag olt ao final do provisionamento
            model_group02 = {"AN5506-01-A", "PON110_V3.0", "RTL9602C", "DM985-100", "HG8310M", "110Gb", "SH901"}

            if model in model_group01:
                try:
                    auth_group01_ssh(conexao, slot, pon, position, vlan)
                    logger.info("Provisionamento concluído com sucesso!")
                    print("Provisionamento concluído com sucesso!")
                except Exception as e:
                    logger.error(f"Erro no provisionamento: {str(e)}")
                    print(f"Erro no provisionamento: {str(e)}")

            elif model in model_group02:
                try:
                    auth_group02_ssh(conexao, slot, pon, position, vlan)
                    logger.info("Provisionamento concluído com sucesso!")
                    print("Provisionamento concluído com sucesso!")
                except Exception as e:
                    logger.error(f"Erro no provisionamento: {str(e)}")
                    print(f"Erro no provisionamento: {str(e)}")

            else:
                logger.warning(f"Modelo incompativel: {model}. Excluindo ONU/ONT.")
                print("Modelo não compatível, excluindo ONU/ONT")
                countdown_timer(15)
                logger.info("Prosseguindo...")
                try:
                    unauthorized(conexao, serial_ssh, slot, pon, position)
                except Exception as e:
                    logger.error(f"Erro ao excluir ONU: {str(e)}")
    finally:
        conexao.terminate()
        logger.info("Finalizado processo")
        print("Finalizado.")



