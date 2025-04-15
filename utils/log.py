import logging
import os
from datetime import datetime

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  

    if not logger.handlers:
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)

        log_filename = name.replace(".", "_") + "_log.log"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        full_path = os.path.join(logs_dir, f"{timestamp}_{log_filename}")

        file_handler = logging.FileHandler(full_path)
        file_handler.setLevel(logging.DEBUG)

        # Aqui personalizamos o formato do log
        formatter = logging.Formatter(
            fmt='%(asctime)s - [%(levelname)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger