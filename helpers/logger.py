logs = []

def log(*args):
    if len(args) == 1:
        level = "INFO"
        message = args[0]
    elif len(args) == 2:
        level = args[0].upper()
        message = args[1]
    else:
        raise ValueError("log() erwartet 1 oder 2 Argumente")

    entry = f"{level}: {message}"

    # Konsolenausgabe
    print(entry)

    # Log-Datei (alles außer DEBUG)
    if level != "DEBUG":
        logs.append(entry)



def get_ntfy_logs(level: str): 
    return "\n".join( 
        line for line in logs 
        if line.startswith(level) 
    )


# from helpers.notify import notify_ntfy

# logs = []

# def log(*args):
#     if len(args) == 1:
#         level = "INFO"
#         message = args[0]
#     elif len(args) == 2:
#         level = args[0].upper()
#         message = args[1]
#     else:
#         raise ValueError("log() erwartet 1 oder 2 Argumente")

#     entry = f"{level}: {message}"

#     # -------------------------
#     # Teil A: Konsolenausgabe
#     # -------------------------
#     print(entry)

#     # -------------------------
#     # Teil B: ntfy-Ausgabe
#     # -------------------------
#     if level in ("SYSTEM", "WARNING"):
#         #send_ntfy(entry)
#         notify_ntfy(entry)

#     # -------------------------
#     # Teil C: Log-Datei (alles außer DEBUG)
#     # -------------------------
#     # if level != "DEBUG":
#     #     logs.append(entry)


# def get_logs():
#     return "\n".join(logs)


# def send_ntfy(message: str):
#     pass



# logs = []

# LOG_LEVEL = "INFO"   # DEBUG, INFO, WARNING, ERROR

# LEVEL_ORDER = {
#     "DEBUG": 10,
#     "INFO": 20,
#     "WARNING": 30,
#     "ERROR": 40,
# }

# def set_log_level(level: str):
#     global LOG_LEVEL
#     LOG_LEVEL = level.upper()

# def log(*args):
#     if len(args) == 1:
#         level = "INFO"
#         message = args[0]

#     elif len(args) == 2:
#         level = args[0].upper()
#         message = args[1]

#     else:
#         raise ValueError("log() erwartet 1 oder 2 Argumente")

#     entry = f"{level}: {message}"
#     logs.append(entry)


# def get_logs():
#     return "\n".join(logs)
