import pexpect
import os
import time
import re
from dotenv import load_dotenv
from utils.log import get_logger
from ast import List
from typing import List, Tuple

logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Carrega variáveis do arquivo .env
load_dotenv()
ssh_user = os.getenv('SSH_USER')
ssh_password = os.getenv('SSH_PASSWORD')
port = os.getenv('PORT')

def login_olt_ssh(host=None):
    """Estabelece conexão SSH com a OLT"""
    try:
        logger.info("Iniciando conexão SSH e obtendo variáveis de ambiente")

        if not all([ssh_user, host, ssh_password, port]):
            error_msg = "Variáveis de ambiente não configuradas corretamente"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Conectando à OLT | Usuário: {ssh_user} | OLT: {host}")
        child = pexpect.spawn(f"ssh {ssh_user}@{host} -p {port}", encoding='utf-8', timeout=30)

        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)

        if index == 1:
            logger.debug("Primeira conexão SSH - Aceitando certificado")
            child.sendline("yes")
            child.expect("password:")

        logger.debug("Enviando senha SSH")
        child.sendline(ssh_password)

        login_success = child.expect([r"typ:isadmin>#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            logger.info(f"Autenticado com sucesso na OLT {host}")
            print(f"✅ Conectado com sucesso à OLT {host}")
        else:
            logger.error("Falha na autenticação SSH")
            print("❌ Falha na autenticação")
            return None

        child.sendline("environment inhibit-alarms")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        logger.info("Alarmes desativados com sucesso")
        return child

    except pexpect.EOF:
        logger.error("Conexão fechada inesperadamente")
        print("❌ Conexão encerrada antes da autenticação")
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de conexão SSH: {e}")
        print(f"Erro de conexão: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        print(f"Erro inesperado: {e}")
    return None

def check_onu_position(child, serial):
    try:
        child.sendline(f"show equipment ont status pon | match match exact:{serial}")
        child.expect("#")
        output = child.before

        match = re.search(r"(\d+)\/(\d+)\/(\d+)\/(\d+)\/(\d+)", output)
        if not match:
            msg = "ONU não encontrada na OLT. Verifique o serial informado."
            logger.warning(msg)
            print(msg)
            return

        slot, pon, position = match.group(3), match.group(4), match.group(5)
        logger.info(f"ONU detectada: Slot {slot}, PON {pon}, Posição {position}")
        print("ONU detectada.")
        return slot, pon, position
    except Exception as e:
        logger.error(f"Erro ao verificar posição da ONU: {e}")
        print(f"Erro: {e}")

def list_unauthorized(child):
    """Lista as ONUs não autorizadas na OLT"""
    logger.info("Iniciando busca por ONUs não autorizadas...")
    onu_list: List[Tuple[str, str, str]] = []
    
    try:
        cmd = "show pon unprovision-onu"
        child.sendline(cmd)
        logger.info(f"Enviando comando: {cmd}")
        time.sleep(3)
        child.expect("#", timeout=10)
        output = child.before.decode('utf-8', errors='ignore') if isinstance(child.before, bytes) else child.before
        
        lines = output.splitlines()
        for line in lines:
            if "1/1/" in line:
                parts = line.strip().split()
                for idx, part in enumerate(parts):
                    if "1/1/" in part:
                        try:
                            slot = part.split('/')[2]
                            pon = part.split('/')[3]
                            serial = parts[idx + 1]
                            onu_list.append((serial.strip(), slot, pon))
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Erro ao processar linha: '{line}' -> {e}")
                            continue
        
        # Exibe a lista formatada
        if onu_list:
            print("----------------------------------------")
            print("Serial           | Slot | PON")
            print("----------------------------------------")
            for serial, slot, pon in onu_list:
                print(f"{serial:<16} | {slot:<4} | {pon}")
            print("----------------------------------------")
            print(f"Total de ONUs não autorizadas: {len(onu_list)}\n")
        else:
            print("Nenhuma ONU não autorizada encontrada.\n")
        
        logger.info(f"Busca concluída. Total de ONUs não autorizadas: {len(onu_list)}")
        return onu_list

    except pexpect.exceptions.TIMEOUT as e:
        logger.error(f"Timeout ao listar ONUs não autorizadas: {e}")
        print("❌ Timeout ao listar ONUs não autorizadas.")
        return []
    except Exception as e:
        logger.error(f"Erro inesperado ao listar ONUs não autorizadas: {e}")
        print("❌ Erro inesperado ao listar ONUs não autorizadas.")
        return []

def return_signal_temp(child, slot, pon, position):
    logger.info("Iniciando verificação de sinal e temperatura da ONU")
    try:
        child.sendline(f"show equipment ont optics 1/1/{slot}/{pon}/{position} detail")
        child.expect("#")
        sinal_temp = child.before.strip()
        logger.debug(f"Saída do comando optics: {sinal_temp}")

        match = re.search(r"rx-signal-level\s*:\s*(-\d+\.\d{2}).*?ont-temperature\s*:\s*(\d{2})", sinal_temp, re.DOTALL)
        if match:
            rx_signal = match.group(1)
            temperature = match.group(2)
            logger.info(f"Sinal: {rx_signal} dBm | Temperatura: {temperature} ºC")
            print(f"Sinal: {rx_signal}dBm\nTemperatura: {temperature}ºC")
        else:
            logger.warning("Dados de sinal/temperatura não encontrados")

    except Exception as e:
        logger.error(f"Erro ao obter sinal/temperatura: {e}")
        print(f"Erro: {e}")

def checkfreeposition(child, slot, pon):
    logger.info(f"Verificando posição livre na PON {slot}/{pon}")
    posocupadas = []
    capacidade_pon = range(1, 129)  # 1 até 128 inclusive

    try:
        child.sendline(f'show equipment ont status pon 1/1/{slot}/{pon}')
        child.expect('#', timeout=10)

        saida = child.before.decode() if isinstance(child.before, bytes) else child.before
        linhas = saida.splitlines()

        for line in linhas:
            if f'1/1/{slot}/{pon}/' in line:
                try:
                    partes = line.split()
                    if len(partes) >= 2:
                        ont_path = partes[1]  # Ex: '1/1/1/1/1'
                        pos = int(ont_path.split('/')[4])
                        posocupadas.append(pos)
                except (IndexError, ValueError):
                    continue

        posicoes_livres = sorted(set(capacidade_pon) - set(posocupadas))
        if not posicoes_livres:
            raise Exception("Nenhuma posição livre disponível")

        menorposlivre = posicoes_livres[0]
        logger.info(f"Menor posição livre encontrada: {menorposlivre}")
        return menorposlivre

    except Exception as e:
        logger.error(f"Erro ao validar posição livre: {e}")
        raise

def add_to_pon(child, slot, pon, position, serial, name, desc2):
    logger.info("Adicionando a ONT na PON para consultar modelo")
    
    try:
        # Provisionamento inicial
        cmd = (f"configure equipment ont interface 1/1/{slot}/{pon}/{position} "
               f"sernum {serial} sw-ver-pland disabled desc1 \"{name}\" "
               f"desc2 \"{desc2}\" optics-hist enable")
        child.sendline(cmd)
        logger.info(f"Enviando comando de provisionamento: {cmd}")
        child.expect(r"\$")  # Espera pelo prompt $
        logger.info(f"ONU provisionada em 1/1/{slot}/{pon}/{position}")
    except Exception as e:
        logger.error(f"Erro no provisionamento inicial da ONU: {e}")
        print("Houve um problema ao provisionar a ONU na PON")
        return False

    try:
        child.sendline("admin-state up")
        logger.info("Enviando comando: admin-state up")
        child.expect(r"\$")  # Espera pelo prompt $
    except Exception as e:
        logger.error(f"Erro ao colocar a ONU UP: {e}")
        print("Houve um problema ao subir a ONU")
        return False

    try:
        child.sendline("exit all")
        logger.info("Enviando comando: exit all")
        child.expect("#")  # Espera pelo prompt #
    except Exception as e:
        logger.error(f"Erro ao sair do modo de configuração: {e}")
        print("Houve um problema ao finalizar o provisionamento")
        return False

    logger.info("ONU está UP e pronta para uso.")
    
    try:
        logger.info("Aguardando 20 segundos para estabilidade...")
        time.sleep(20)
    except Exception as e:
        logger.warning(f"Erro durante espera de estabilidade: {e}")

    return True

def onu_model(child, slot, pon, position):
    try:
        logger.info(f"Verificando modelo da ONU em 1/1/{slot}/{pon}/{position}")
        # Envia comando para obter detalhes da ONU
        child.sendline(f"show equipment ont interface 1/1/{slot}/{pon}/{position} detail")
        child.expect("#", timeout=15)
        output = child.before.strip()
        
        # Procura pelo padrão do modelo no output
        match = re.search(r"equip-id\s*:\s*([^\n\r]+?)(?=\s{2,}|$)", output, re.MULTILINE)

        if not match:
            logger.warning("Modelo da ONU não encontrado na saída do comando")
            print("❗ Modelo da ONU não encontrado")
            return None
            
        model = match.group(1).strip()
        logger.info(f"Modelo detectado: {model}")
        print(f"✅ Modelo detectado: {model}")
        return model
        
    except pexpect.exceptions.TIMEOUT:
        logger.error("Tempo esgotado ao tentar obter modelo da ONU")
        print("❗ Tempo esgotado ao verificar modelo da ONU")
        return None
    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de comunicação: {str(e)}")
        print(f"❗ Erro de comunicação: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao obter modelo: {str(e)}")
        print(f"❗ Erro inesperado: {str(e)}")
        return None

def auth_group01_ssh(child, slot, pon, position, vlan):
    logger.info("Iniciando autorização do grupo 01 via SSH")
    
    try:
        time.sleep(3)
    except Exception as e:
        logger.warning(f"Problema ao esperar: {e}")

    comandos = [
        (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
        (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS na porta UNI"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac 4 max-committed-mac 1", "$", "Configurar limite de MACs na bridge"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN à porta bridge (untagged)"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
    ]

    for cmd, prompt, descricao in comandos:
        try:
            child.sendline(cmd)
            logger.info(f"Enviando comando: {descricao} -> {cmd}")
            child.expect(prompt, timeout=5)
            logger.info(f"Comando concluído com sucesso: {descricao}")
        except Exception as e:
            logger.error(f"Erro ao executar comando '{descricao}': {e}")
            print(f"Houve um problema durante: {descricao}")
            return False

    logger.info("Configuração do grupo 01 concluída com sucesso.")
    return True

def auth_group02_ssh(child, slot, pon, position, vlan):
    logger.info("Iniciando autorização do grupo 02 via SSH")
    
    try:
        time.sleep(3)
    except Exception as e:
        logger.warning(f"Problema ao aguardar: {e}")

    comandos = [
        (f"configure equipment ont slot 1/1/{slot}/{pon}/{position}/1 plndnumdataports 1 plndnumvoiceports 0 planned-card-type ethernet admin-state up", "$", "Configurar slot da ONT"),
        (f"configure interface port uni:1/1/{slot}/{pon}/{position}/1/1 admin-up", "#", "Habilitar porta UNI"),
        (f"configure qos interface 1/1/{slot}/{pon}/{position}/1/1 upstream-queue 0 bandwidth-profile name:HSI_1G_UP", "#", "Configurar QoS na porta UNI"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 max-unicast-mac 4 max-committed-mac 1", "$", "Configurar limite de MACs na bridge"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 vlan-id {vlan} tag untagged", "$", "Atribuir VLAN à porta bridge (untagged)"),
        ("exit all", "#", "Sair do modo de configuração"),
        (f"configure bridge port 1/1/{slot}/{pon}/{position}/1/1 pvid {vlan}", "#", "Definir PVID na porta bridge"),
        ("pvid-tagging-flag olt", "#", "Configurar pvid-tagging-flag para OLT"),
    ]

    for cmd, prompt, descricao in comandos:
        try:
            child.sendline(cmd)
            logger.info(f"Enviando comando: {descricao} -> {cmd}")
            child.expect(prompt, timeout=5)
            logger.info(f"Comando concluído com sucesso: {descricao}")
        except Exception as e:
            logger.error(f"Erro ao executar comando '{descricao}': {e}")
            print(f"Houve um problema durante: {descricao}")
            return False

    logger.info("Configuração do grupo 02 concluída com sucesso.")
    return True

def unauthorized(child, serial_ssh, slot, pon, position):
    try:
        logger.info(f"Iniciando desautorização da ONU {serial_ssh}")
        commands = [
            f"configure equipment ont interface 1/1/{slot}/{pon}/{position} admin-state down",
            f"configure equipment ont no interface 1/1/{slot}/{pon}/{position}",
            "exit all"
        ]

        for cmd in commands:
            try:
                child.sendline(cmd)
                child.expect("#", timeout=10)
                if "error" in child.before.lower():
                    logger.error(f"Erro no comando: {cmd} - Saída: {child.before}")
                    print(f"❌ Falha ao executar comando na OLT")
                    return False
            except pexpect.TIMEOUT:
                logger.error(f"Timeout no comando: {cmd}")
                print("❌ Tempo esgotado na execução do comando")
                return False

        # 4. Confirmar sucesso
        logger.info(f"ONU {serial_ssh} desautorizada com sucesso")
        return True

    except pexpect.ExceptionPexpect as e:
        logger.error(f"Erro de comunicação: {str(e)}", exc_info=True)
        print("❌ Erro de comunicação com a OLT")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}", exc_info=True)
        print("❌ Erro inesperado no processo")
        return None

def format_ssh_serial(serial: str) -> str:
    logger.info(f"Iniciando formatação do serial: {serial}")

    try:
        serial = serial.upper()[:12]
        if len(serial) > 4:
            serial = serial[:4] + ':' + serial[4:]
        logger.info(f"Serial formatado para SSH: {serial}")
        return serial
    except Exception as e:
        logger.error(f"Erro ao formatar o serial '{serial}': {e}")
        return ""
