import pexpect
import os
from dotenv import load_dotenv
import time
import re
from utils.log import get_logger

logger = get_logger(__name__)
logger.info("Sistema iniciado")

# Carrega variáveis do arquivo .env
load_dotenv()
ssh_user = os.getenv('SSH_USER')
ssh_password = os.getenv('SSH_PASSWORD')
port = os.getenv('PORT')


def log_interaction(titulo, mensagem=None, level="info"):
    """Wrapper para log com níveis variados"""
    if mensagem:
        getattr(logger, level)(f"{titulo} | {mensagem}")
    else:
        getattr(logger, level)(titulo)


def login_olt_ssh(host=None):
    """Estabelece conexão SSH com a OLT"""
    try:
        log_interaction("Iniciando conexão SSH", "Obtendo variáveis de ambiente")

        if not all([ssh_user, host, ssh_password]):
            error_msg = "Variáveis de ambiente não configuradas corretamente"
            log_interaction("Erro de configuração", error_msg, "error")
            raise ValueError(error_msg)

        log_interaction("Conectando à OLT", f"Usuário: {ssh_user} | OLT: {host}")
        child = pexpect.spawn(f"ssh {ssh_user}@{host} -p {port}", encoding='utf-8', timeout=30)

        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)

        if index == 1:
            log_interaction("Primeira conexão SSH", "Aceitando certificado", "debug")
            child.sendline("yes")
            child.expect("password:")

        log_interaction("SSH", "Enviando senha", "debug")
        child.sendline(ssh_password)

        login_success = child.expect([r"typ:isadmin>#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            log_interaction("Conexão SSH", f"Autenticado com sucesso na OLT {host}")
            print(f"✅ Conectado com sucesso à OLT {host}")
        else:
            log_interaction("Erro SSH", "Não foi possível autenticar", "error")
            print("❌ Falha na autenticação")
            return None

        child.sendline("environment inhibit-alarms")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        log_interaction("Ambiente", "Alarmes desativados")
        return child

    except pexpect.EOF:
        log_interaction("Erro SSH", "Conexão fechada inesperadamente", "error")
        print("❌ Conexão encerrada antes da autenticação")
    except pexpect.exceptions.ExceptionPexpect as e:
        log_interaction("Erro de conexão SSH", str(e), "error")
        print(f"Erro de conexão: {e}")
        return None
    except Exception as e:
        log_interaction("Erro inesperado", str(e), "error")
        print(f"Erro inesperado: {e}")
        return None


def list_unauthorized(child):
    try:
        logger.info("Listando ONUs não provisionadas...")
        child.sendline('show pon unprovision-onu')
        time.sleep(3)
        child.sendline('logout')
        child.terminate()
        parse = str(child.readlines()[7:])
        parse_split = parse.split(",")

        for count, line in enumerate(parse_split):
            if "1/1/" in line:
                pos_slot = line.find('1/1/')
                dados_temp = line[pos_slot:].split(" ")
                dados = list(filter(None, dados_temp))
                if len(dados) >= 2:
                    slot = dados[0].split('/')[2]
                    pon = dados[0].split('/')[3]
                    serial = dados[1]
                    logger.info(f"Detectado - Slot: {slot}, PON: {pon}, Serial: {serial}")
                    print(f"Slot: {slot} Pon: {pon} Serial: {serial}")
        logger.info("Listagem de ONUs não provisionadas concluída")
    except Exception as e:
        logger.error(f"Erro ao listar ONUs não provisionadas: {e}")


def return_signal_temp(child):
    logger.info("Iniciando verificação de sinal e temperatura da ONU")
    try:
        serial = input("Qual o serial da ONU? ").strip()
        SNONUP = serial.upper()[:12]
        if len(SNONUP) > 4:
            SNONUP = SNONUP[:4] + ':' + SNONUP[4:]
        log_interaction("Serial formatado", SNONUP)

        logger.debug("Executando busca da ONU")
        child.sendline(f"show equipment ont status pon | match match exact:{SNONUP}")
        child.expect("#")
        output = child.before

        match = re.search(r"(\d+)\/(\d+)\/(\d+)\/(\d+)\/(\d+)", output)
        if not match:
            msg = "ONU não encontrada na OLT, verifique o serial informado"
            logger.warning(msg)
            print(msg)
            return

        slot = match.group(3)
        pon = match.group(4)
        posicao = match.group(5)
        logger.info(f"ONU detectada: Slot {slot}, PON {pon}, Posição {posicao}")

        child.sendline(f"show equipment ont optics 1/1/{slot}/{pon}/{posicao} detail")
        child.expect("#")
        sinal_temp = child.before.strip()
        logger.debug(f"Saída bruta do comando optics: {sinal_temp}")

        match = re.search(r"rx-signal-level\s*:\s*(-\d+\.\d{2}).*?ont-temperature\s*:\s*(\d{2})", sinal_temp, re.DOTALL)
        if match:
            rx_signal = match.group(1)[:5]
            temperature = match.group(2)
            print(f"Sinal: {rx_signal}dBm\nTemperatura: {temperature}ºC")
            logger.info(f"Sinal: {rx_signal} dBm | Temperatura: {temperature} ºC")
        else:
            logger.warning("ONU não retornou os dados esperados")

    except pexpect.exceptions.ExceptionPexpect as e:
        logger.error(f"Erro de conexão ou comando: {e}")
        print(f"Erro de conexão ou comando: {e}")
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        print(f"Erro inesperado: {e}")
    finally:
        if 'child' in locals():
            try:
                child.sendline("logout")
                child.terminate()
                logger.info("Sessão SSH encerrada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao encerrar sessão SSH: {e}")
