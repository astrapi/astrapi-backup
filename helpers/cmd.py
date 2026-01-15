import subprocess
from helpers.logger import log
from config import config

def run_cmd(cmd: str, connection: str, env=None):
    if isinstance(cmd, list): 
        cmd = " ".join(cmd) 
    elif isinstance(cmd, str): 
        cmd = cmd 
    else: 
        log("ERROR", f"Ungültiger Kommando-Typ") 
        return
    
    if connection == "local": 
        return run_cmd_local(cmd, env)
    else:
        return run_cmd_remote(cmd, connection, env)

def run_cmd_local(cmd, env=None):
    final_cmd = ["bash", "-c", cmd]

    if config.debug:
        log("DEBUG", final_cmd)
        return True

    result = subprocess.run(final_cmd, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result

def run_cmd_remote(cmd, connection, env=None):
    final_cmd = ["ssh", "-o", "BatchMode=yes", connection, cmd]

    if config.debug:
        log("DEBUG", final_cmd)
        return True

    result = subprocess.run( final_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result
