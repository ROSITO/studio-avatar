"""Budget vocal prudent ; limites d'allocateur et surveillance du processus isolé."""
import os
import platform
import re
import subprocess
import threading

GIB=1024**3
BESOINS={'omnivoice':8*GIB,'qwen3-tts-mlx':8*GIB,'drama3-mlx':28*GIB}

def physique():
    try:
        if platform.system()=='Darwin':return int(subprocess.check_output(['sysctl','-n','hw.memsize']))
        return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    except (OSError,ValueError,subprocess.SubprocessError):return 16*GIB

def budget():
    try:limite=float(os.environ.get('STUDIO_TTS_MAX_RAM_GB','16'))
    except ValueError:raise ValueError('STUDIO_TTS_MAX_RAM_GB doit être un nombre positif.')
    if not 0<limite<=1024:raise ValueError('Budget vocal invalide.')
    return int(min(limite*GIB,physique()/2))

def pression():
    if platform.system()!='Darwin':return 0
    try:return int(subprocess.check_output(['sysctl','-n','kern.memorystatus_vm_pressure_level'],stderr=subprocess.DEVNULL))
    except (OSError,ValueError,subprocess.SubprocessError):return 0

def disponible():
    try:
        if platform.system()=='Darwin':
            texte=subprocess.check_output(['vm_stat'],text=True)
            page=int(re.search(r'page size of (\d+) bytes',texte)[1])
            return sum(int(re.search(re.escape(k)+r':\s*(\d+)',texte)[1]) for k in ['Pages free','Pages inactive','Pages speculative'])*page
        texte=open('/proc/meminfo').read()
        return int(re.search(r'MemAvailable:\s*(\d+)',texte)[1])*1024
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):return physique()/2

def verifier(moteur):
    plafond=budget();besoin=BESOINS[moteur]
    if besoin>plafond:raise ValueError(f'{moteur} : environ {besoin/GIB:.0f} Go nécessaires, budget vocal {plafond/GIB:.0f} Go. Modèle refusé avant chargement pour préserver les applications.')
    if pression()>=2:raise ValueError('macOS signale une pression mémoire : synthèse vocale refusée pour préserver les applications.')
    if disponible()<besoin+4*GIB:raise ValueError('Mémoire disponible insuffisante : il faut garder au moins 4 Go de marge en plus du modèle vocal.')
    return plafond

def configurer_mlx(mx,moteur):
    plafond=verifier(moteur)
    mx.set_memory_limit(plafond)
    mx.set_cache_limit(min(256*1024**2,plafond//16))
    return plafond

def surveiller(plafond, mesure=None):
    stop=threading.Event()
    def boucle():
        while not stop.wait(.5):
            try:
                rss=int(subprocess.check_output(['ps','-p',str(os.getpid()),'-o','rss='],stderr=subprocess.DEVNULL))*1024
                gpu=mesure() if mesure else 0
                if max(rss,gpu)>plafond or pression()>=2:
                    os.write(2,b'Protection memoire : synthese arretee pour preserver les applications.\n')
                    os._exit(73)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):pass
    threading.Thread(target=boucle,daemon=True).start()
    return stop
