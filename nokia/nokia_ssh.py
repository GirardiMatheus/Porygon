import pexpect
import os
from dotenv import load_dotenv
import logging
# from collections import defaultdict
import time


def setup_logging():
    """Configura o sistema de logging com rotação de arquivos"""
    logging.basicConfig(
        filename=f"OLT_LOG.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.info("="*50)
    logging.info("Iniciando nova sessão de conexão OLT")
    logging.info("="*50)

def log_interaction(action, details="", level="info"):
    """Função padronizada para registro de logs"""
    message = f"{action.upper()} | {details}"
    if level.lower() == "debug":
        logging.debug(message)
    elif level.lower() == "warning":
        logging.warning(message)
    elif level.lower() == "error":
        logging.error(message)
    else:
        logging.info(message)

# Carrega variáveis do arquivo .env
load_dotenv()
setup_logging()

def login_olt_ssh():
    """Estabelece conexão SSH com a OLT"""
    try:
        log_interaction("Iniciando conexão SSH", "Obtendo variáveis de ambiente")
        
        # Obtém variáveis de ambiente
        ssh_user = os.getenv('SSH_USER')
        olt_ip = os.getenv('LAB_IP')
        ssh_password = os.getenv('SSH_PASSWORD')
        port = os.getenv('PORT')
        
        # Validação das variáveis
        if not all([ssh_user, olt_ip, ssh_password]):
            error_msg = "Variáveis de ambiente não configuradas corretamente"
            log_interaction("Erro de configuração", error_msg, "error")
            raise ValueError(error_msg)
       
        log_interaction("Conectando à OLT", f"Usuário: {ssh_user} | OLT: {olt_ip}")
        # print(f"Usuário: {ssh_user}, IP: {olt_ip}, Porta: {port}")
        # Conexão SSH
        child = pexpect.spawn(f"ssh {ssh_user}@{olt_ip} -p {port}", encoding='utf-8', timeout=30)

        log_interaction("SSH iniciado", "Aguardando prompt de senha", "debug")

        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)
        
        if index == 1:
            log_interaction("SSH", "Primeira conexão - aceitando certificado", "debug")
            child.sendline("yes")
            child.expect("password:")
        
        log_interaction("SSH", "Enviando credenciais de acesso", "debug")
        child.sendline(ssh_password)
        login_success = child.expect([r"typ:isadmin>#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            log_interaction("Conexão estabelecida", f"Conectado à OLT {olt_ip}")
            print(f"✅ Conectado com sucesso à OLT {olt_ip}")

        else:
            log_interaction("Erro SSH", "Não foi possível autenticar na OLT", "error")
            print("❌ Falha na autenticação")
            return None
        child.sendline("environment inhibit-alarms")
        child.expect("#")
        child.sendline("exit")
        child.expect("#")
        log_interaction("Alarmes desativados.")
        return child
    

    except pexpect.EOF:
        log_interaction("Erro SSH", "Conexão fechada inesperadamente", "error")
        print("❌ Erro: Conexão foi fechada antes do login.")
        
    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Falha na conexão SSH: {str(e)}"
        log_interaction("Erro SSH", error_msg, "error")
        print(error_msg)
        return None
        
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        log_interaction("Erro geral", error_msg, "error")
        print(error_msg)
        return None
    
def list_unauthorized(child):
            child.sendline('show pon unprovision-onu')
            time.sleep(3)
            child.sendline('logout')
            child.terminate()
            parse = str(child.readlines()[7::])
            parse_split = parse.split(",")
            
            for count,line in enumerate(parse_split):
                if "1/1/" in line:
                    pos_slot = line.find('1/1/')
                    dados_temp = line[pos_slot:].split(" ")
                    dados = list(filter(None,dados_temp))
                    print(f"Slot: {dados[0].split('/')[2]} Pon: {dados[0].split('/')[3]} Serial: {dados[1]}")
                    continue
                continue  

def return_signal_temp(child):
    print("Identificando a ONU ou ONT na OLT...")
    try:
        serial = input("Qual o serial da ONU? ").strip()
        # Formatação do serial
        SNONUP = serial.upper()[:12]
        if len(SNONUP) > 4:  # Evita erro se serial for muito curto
            SNONUP = SNONUP[:4] + ':' + SNONUP[4:]
        log_interaction(f"Serial formatado para a OLT: {SNONUP}")
        logging.info("Buscando ONU e ONT")

        login_olt_ssh()

        # Busca ONU
        child = pexpect.spawn(f"show equipment ont status pon | match match exact:{SNONUP}")
        child.expect("#")
        output = child.before

        # Regex para capturar slot, pon e posição
        match = re.search(r"(\d+)\/(\d+)\/(\d+)\/(\d+)\/(\d+)", output)
        if not match:
            print("ONU não encontrada na OLT, verifique se o serial informado está correto e tente novamente")
            return

        print("ONU detectada.")
        slot = match.group(3)
        pon = match.group(4)
        posicao = match.group(5)
        log_interaction(f"ONU detectada: Slot {slot}, PON {pon}, Posição {posicao}")

        # Verifica sinal e temperatura
        child.sendline(f"show equipment ont optics 1/1/{slot}/{pon}/{posicao} detail")
        child.expect("#")
        sinal_temp = child.before.strip()
        log_interaction(f"Retorno coletado: {sinal_temp}")

        match = re.search(r"rx-signal-level\s*:\s*(-\d+\.\d{2}).*?ont-temperature\s*:\s*(\d{2})", sinal_temp, re.DOTALL)
        if match:
            rx_signal = match.group(1)[:5]  # Garante 2 decimais (ex: -00.00)
            temperature = match.group(2)
            print(f"Sinal: {rx_signal}dBm\nTemperatura: {temperature}ºC")
            log_interaction(f"Dados coletados: Sinal {rx_signal}, Temperatura {temperature}")
        else:
            print("ONU não retornou os dados esperados, verifique se o serial está correto e tente novamente")

    except pexpect.exceptions.ExceptionPexpect as e:
        print(f"Erro de conexão/comando: {str(e)}")
        logging.error(f"Erro na execução: {str(e)}")
    except Exception as e:
        print(f"Erro inesperado: {str(e)}")
        logging.error(f"Erro inesperado: {str(e)}")
    finally:
        if 'child' in locals():
            child.sendline("logout")
            child.terminate()
    continue 
