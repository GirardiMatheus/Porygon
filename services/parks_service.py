from parks.parks_ssh import *
import csv
import random


def provision(ip_olt):
    """Função de provisionamento com logs detalhados"""
    try:
        # Conexão SSH
        log_interaction(f"Conectando à OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        log_interaction("Conexão SSH estabelecida com sucesso")

        # Listar ONUs não autorizadas
        log_interaction("Listando ONUs não autorizadas...")
        blacklist = list_unauthorized(conexao)

        if not blacklist:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            return

        # Listar e exibir ONUs não autorizadas
        print("\nONUs na blacklist:")
        for serial, dados in blacklist.items():
            print(f"Serial: {serial} | Slot: {dados['slot']} | PON: {dados['pon']}")
            log_interaction(f"Serial: {serial}, PON: {dados['pon']}")

        # Consulta informações da ONU
        serial = input("\nQual o serial da ONU? ").strip().lower()
        log_interaction(f"Serial informado: {serial}")

        # Verificar se o serial existe na blacklist e obter a PON correspondente
        if serial in blacklist:
            pon = blacklist[serial]['pon']
            log_interaction(f"PON encontrada para {serial}: {pon}")
            add_onu_to_pon(conexao, serial, pon)
            time.sleep(random.uniform(10, 30))
        else:
            print(f"Erro: Serial {serial} não encontrado na blacklist")
            log_interaction(f"Serial não encontrado: {serial}")
        

        log_interaction(f"Consultando informações da ONU {serial}...")
        dados_onu = consult_information(conexao, serial)
        
        if not dados_onu or not dados_onu['model']:
            msg = "Falha ao obter informações da ONU"
            log_interaction(msg)
            print(msg)
            return
            
        model = dados_onu['model'].strip()
        log_interaction(f"Dados ONU - Modelo: {model}, PON: {pon}")

        # Determinar tipo de ONU
        bridge_models = {"TX-6610", "R1v2", "XZ000-G3", "Fiberlink100", "110", "AN5506-01-A", "FiberLink101"}
        router_models = ["FiberLink611", "121AC", "FiberLink411", "ONU HW01N", "Fiberlink501(Rev2)", "ONU GW24AC", "Fiberlink210"]
        
        if model in bridge_models:
            onu_type = "bridge"
        elif model in router_models:
            onu_type = "router"
        else:
            onu_type = None
            
        log_interaction(f"Tipo detectado: {onu_type or 'Desconhecido'}")
        print(model)

        if not onu_type:
            msg = f"Modelo {model} não reconhecido"
            log_interaction(msg)
            print(msg)
            return

        # Carregar configurações do CSV
        csv_path = './csv/parks.csv'
        try:
            log_interaction(f"Consultando CSV em {csv_path}...")
            with open(csv_path, mode='r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Converter pon para string para comparação segura
                    csv_pon = str(row['pon']) 
                    input_pon = str(pon)       
                    
                    if (row['olt_ip'] == ip_olt and 
                        csv_pon == input_pon and  
                        row['type'].lower() == onu_type.lower()):
                        
                        vlan = row['vlan']
                        profile = row['profile']
                        log_interaction(f"Config CSV - VLAN: {vlan}, Profile: {profile}")
                        break
                else:
                    msg = f"Configuração não encontrada para OLT {ip_olt} PON {pon} Tipo {onu_type}"
                    log_interaction(msg)
                    print(msg)
                    vlan = input("Digite a VLAN: ").strip()
                    profile = input("Digite o profile: ").strip()
                    log_interaction(f"Valores manuais - VLAN: {vlan}, Profile: {profile}")
            
        except FileNotFoundError:
            msg = f"Arquivo CSV não encontrado em {csv_path}"
            log_interaction(msg, "error")
            print(msg)
            vlan = input("Digite a VLAN: ").strip()
            profile = input("Digite o profile: ").strip()
                    
        except Exception as e:
            msg = f"Erro ao ler CSV: {str(e)}"
            log_interaction(msg)
            print(msg)
            vlan = input("Digite a VLAN: ").strip()
            profile = input("Digite o profile: ").strip()
            log_interaction(f"Valores manuais - VLAN: {vlan}, Profile: {profile}")

        # Dados adicionais
        nome = str(input("\nDigite o alias/nome da ONU: ")).strip() or serial
        log_interaction(f"Alias/Nome definido: {nome}")

        # Provisionamento específico
        log_interaction(f"Iniciando provisionamento como {onu_type}...")
        if onu_type == 'bridge':
            log_interaction("Executando fluxo Bridge...")
            auth_bridge(conexao, serial, pon, nome, profile, vlan)
        
        elif model in ["ONU HW01N", "Fiberlink210"]:
            log_interaction(f"Executando fluxo Default Router para {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            log_interaction(f"Credenciais PPPoE coletadas {login_pppoe}, {senha_pppoe}")
            if not vlan.isdigit():
                print("Erro: VLAN deve conter apenas números")
                return
            auth_router_default(conexao, serial, nome, vlan, pon, profile, login_pppoe, senha_pppoe)
            
        elif model == "121AC":
            log_interaction(f"Executando fluxo {model}...")
            auth_router_121AC(conexao, serial, pon, nome, profile, vlan)
            print("ALERTA: Configurar PPPoE/WiFi manualmente")
            
        elif model in ["FiberLink411", "ONU GW24AC"]:
            log_interaction(f"Executando fluxo {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            log_interaction(f"Credenciais PPPoE coletadas {login_pppoe}, {senha_pppoe}")
            auth_router_config2(conexao, serial, pon, nome, vlan, profile, login_pppoe, senha_pppoe)

        elif model == "Fiberlink501(Rev2)":
            log_interaction(f"Executando fluxo {model}...")
            login_pppoe = input("Qual login PPPoE do cliente? ")
            senha_pppoe = input("Qual a senha do PPPoE do cliente? ")
            log_interaction(f"Credenciais PPPoE coletadas {login_pppoe}, {senha_pppoe}")
            auth_router_Fiberlink501Rev2(conexao, serial, pon, nome, profile, login_pppoe, senha_pppoe)


        log_interaction(f"Provisionamento concluído - ONU {serial} na PON {pon}")
        print(f"\nProvisionamento concluído com sucesso!")

    except Exception as e:
        error_msg = f"ERRO NO PROVISIONAMENTO: {str(e)}"
        conexao.terminate()
        log_interaction(error_msg)
        print(error_msg)
        
    finally:
        if 'conexao' in locals():
            log_interaction("Encerrando conexão SSH...")
            conexao.terminate()

def onu_list(ip_olt):
    try:
        # Conexão SSH
        log_interaction(f"Conectando à OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        log_interaction("Conexão SSH estabelecida com sucesso")

        # Listar ONUs não autorizadas
        log_interaction("Listando ONUs não autorizadas...")
        blacklist = list_unauthorized(conexao)

        if not blacklist:
            print("Nenhuma ONU ou ONT pedindo autorização...")
            return

        print("\nONUs na blacklist:")
        for serial, dados in blacklist.items():
            print(f"Serial: {serial} | Slot: {dados['slot']} | PON: {dados['pon']}")
            conexao.terminate()
    
    except Exception as e:
        error_msg = f"ERRO AO LISTAR ONU's: {str(e)}"
        conexao.terminate()
        log_interaction(error_msg)

        print(error_msg)

    finally:
        if 'conexao' in locals():
            log_interaction("Encerrando conexão SSH...")
            conexao.terminate()

def unauthorized_complete(ip_olt):
    conexao = None
    try:
        # 1. Conexão SSH
        log_interaction(f"Iniciando processo para desautorizar ONU na OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        if not conexao:
            print("Falha ao conectar na OLT")
            log_interaction("Conexão SSH falhou", level="ERROR")
            return False

        # 2. Consulta ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        log_interaction(f"Serial informado: {serial}")
        
        dados_onu = consult_information(conexao, serial)
        if not dados_onu:
            print("ONU/ONT não encontrada na OLT")
            log_interaction(f"ONU {serial} não encontrada", level="WARNING")
            return False

        pon = dados_onu.get('pon')
        if not pon:
            print("Falha ao obter informação da PON")
            log_interaction("Dados da PON não encontrados", level="ERROR")
            return False

        # Formata PON (extrai apenas o número)
        pon_numero = pon.split('/')[-1] if '/' in pon else pon
        log_interaction(f"Dados obtidos - Serial: {serial}, PON: {pon_numero}")

        # 3. Reboot
        log_interaction(f"Iniciando reboot da ONU {serial}")
        if not reboot(conexao, pon_numero, serial):
            print("Falha no reboot da ONU")
            log_interaction("Reboot falhou", level="ERROR")
            return False

        print("ONU reiniciada com sucesso, aguardando 10 segundos...")
        time.sleep(10)  

        # 4. Desautorização
        log_interaction(f"Iniciando desautorização da ONU {serial}")
        if not unauthorized(conexao, pon_numero, serial):
            print("Falha na desautorização da ONU")
            log_interaction("Desautorização falhou", level="ERROR")
            return False

        print("✅ ONU desautorizada com sucesso")
        log_interaction(f"Processo completo concluído para ONU {serial}")
        return True

    except Exception as e:
        error_msg = f"Erro no processo: {str(e)}"
        print(f"⚠️ Erro: {error_msg}")
        log_interaction(error_msg, level="ERROR")
        return False

    finally:
        # 5. Encerra conexão
        if 'conexao' in locals() and conexao:
            log_interaction("Encerrando conexão SSH")
            conexao.terminate()

def consult_information_complete(ip_olt):
    conexao = None
    try:
        log_interaction(f"Iniciando consulta completa para OLT {ip_olt}")
        
        # Estabelece conexão SSH
        conexao = login_ssh(host=ip_olt)
        log_interaction("Conexão SSH estabelecida com sucesso")
        
        # Solicita serial da ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        log_interaction(f"Serial informado pelo usuário: {serial}")
        
        # Consulta informações da ONU
        log_interaction(f"Consultando informações da ONU {serial}")
        dados_onu = consult_information(conexao, serial)
        
        if not dados_onu:
            msg = "Falha ao consultar informações da ONU/ONT ou ONU não encontrada"
            print(msg)
            conexao.terminate()
            log_interaction(msg, level="WARNING")
            return
            
        # Extrai dados
        model = dados_onu.get('model', 'N/A')
        alias = dados_onu.get('alias', 'N/A')
        power_level = dados_onu.get('power_level', 'N/A')
        distance_km = dados_onu.get('distance_km', 'N/A')
        pon = dados_onu.get('pon', 'N/A')
        if pon != 'N/A':
            pon = pon.split('/')[-1]  
        status = dados_onu.get('status', 'N/A')
        
        # Prepara e exibe informações formatadas
        info_formatada = (
            f"\n=== Informações da ONU {serial} ===\n"
            f"Modelo: {model}\n"
            f"Nome/Descrição: {alias}\n"
            f"Nível do Sinal: {power_level}\n"
            f"Distância da OLT: {distance_km} KM\n"
            f"PON: {pon}\n"  
            f"Status: {status}\n"
            "======================================="
        )
        
        print(info_formatada)
        log_interaction(f"Informações exibidas para o usuário:\n{info_formatada}")
        
    except Exception as e:
        error_msg = f"Erro durante consulta: {str(e)}"
        print(f"\nErro: {error_msg}")
        conexao.terminate()
        log_interaction(error_msg, level="ERROR")
        
    finally:
        if conexao:
            log_interaction("Encerrando conexão SSH")
            conexao.terminate()

def reboot_complete(ip_olt):
    conexao = None
    try:
        # 1. Conexão SSH
        log_interaction(f"Iniciando processo para desautorizar ONU na OLT {ip_olt}")
        conexao = login_ssh(host=ip_olt)
        if not conexao:
            print("Falha ao conectar na OLT")
            log_interaction("Conexão SSH falhou", level="ERROR")
            return False

        # 2. Consulta ONU
        serial = input("Qual o serial da ONU? ").strip().lower()
        log_interaction(f"Serial informado: {serial}")
        
        dados_onu = consult_information(conexao, serial)
        if not dados_onu:
            print("ONU/ONT não encontrada na OLT")
            log_interaction(f"ONU {serial} não encontrada", level="WARNING")
            return False

        pon = dados_onu.get('pon')
        if not pon:
            print("Falha ao obter informação da PON")
            log_interaction("Dados da PON não encontrados", level="ERROR")
            return False

        # Formata PON (extrai apenas o número)
        pon_numero = pon.split('/')[-1] if '/' in pon else pon
        log_interaction(f"Dados obtidos - Serial: {serial}, PON: {pon_numero}")

        # 3. Reboot
        log_interaction(f"Iniciando reboot da ONU {serial}")
        if not reboot(conexao, pon_numero, serial):
            print("Falha no reboot da ONU")
            log_interaction("Reboot falhou", level="ERROR")
            return False
        
        print("✅ ONU desautorizada com sucesso")
        log_interaction(f"Processo completo concluído para ONU {serial}")
        return True
            
    except Exception as e:
        error_msg = f"Erro no processo: {str(e)}"
        print(f"⚠️ Erro: {error_msg}")
        log_interaction(error_msg, level="ERROR")
        return False

    finally:
        # 5. Encerra conexão
        if 'conexao' in locals() and conexao:
            log_interaction("Encerrando conexão SSH")
            conexao.terminate()

def list_of_compatible_models():
    """Exibe os modelos suportados divididos por categoria"""
    bridge_models = ["TX-6610", "R1v2", "XZ000-G3", "Fiberlink100", 
                    "110", "AN5506-01-A", "FiberLink101"]
    router_models = ["FiberLink611", "121AC", "FiberLink411", "ONU HW01N", 
                    "Fiberlink501(Rev2)", "ONU GW24AC", "Fiberlink210"]

    print("\n=== MODELOS SUPORTADOS ===")
    print("\n🔷 MODOS BRIDGE:")
    for modelo in bridge_models:
        print(f"  → {modelo}")
    
    print("\n🔶 MODOS ROTEADOR:")
    for modelo in router_models:
        print(f"  → {modelo}")
    
    input("\nPressione Enter para voltar...")