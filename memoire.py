"""Budget vocal prudent ; limites d'allocateur et surveillance du processus isolé."""
import ctypes
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
    try:limite=float(os.environ.get('STUDIO_TTS_MAX_RAM_GB','12'))
    except ValueError:raise ValueError('STUDIO_TTS_MAX_RAM_GB doit être un nombre positif.')
    if not 0<limite<=1024:raise ValueError('Budget vocal invalide.')
    plafond=int(min(limite*GIB,physique()/2))
    transmis=os.environ.get('STUDIO_TTS_EFFECTIVE_LIMIT')
    return min(plafond,int(transmis)) if transmis else plafond

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
    if moteur=='drama3-mlx':
        if pression()>=4:raise ValueError('Pression mémoire macOS critique : essai refusé.')
        if disponible()<4*GIB:raise ValueError('Moins de 4 Gio disponibles : attendez avant de lancer la synthèse.')
        if plafond<2*GIB:raise ValueError('Budget vocal inférieur à 2 Gio : augmentez STUDIO_TTS_MAX_RAM_GB.')
        return plafond
    if besoin>plafond:raise ValueError(f'{moteur} : environ {besoin/GIB:.0f} Go nécessaires, budget vocal {plafond/GIB:.0f} Go. Modèle refusé avant chargement pour préserver les applications.')
    if pression()>=2:raise ValueError('macOS signale une pression mémoire : synthèse vocale refusée pour préserver les applications.')
    if disponible()<besoin+4*GIB:raise ValueError('Mémoire disponible insuffisante : il faut garder au moins 4 Go de marge en plus du modèle vocal.')
    return plafond

def configurer_mlx(mx,moteur):
    plafond=verifier(moteur)
    mx.set_memory_limit(plafond)
    mx.set_cache_limit(min(256*1024**2,plafond//16))
    return plafond

def danger_systeme(niveau=None):
    # A warning alone may persist after a previous job; retain a real RAM reserve.
    niveau=pression() if niveau is None else niveau
    return niveau>=4 or (niveau>=2 and disponible()<4*GIB)

def surveiller(plafond, mesure=None):
    stop=threading.Event()
    def boucle():
        while not stop.wait(.5):
            try:
                rss=int(subprocess.check_output(['ps','-p',str(os.getpid()),'-o','rss='],stderr=subprocess.DEVNULL))*1024
                gpu=mesure() if mesure else 0
                if max(rss,gpu)>plafond or danger_systeme():
                    os.write(2,b'Protection memoire : synthese arretee pour preserver les applications.\n')
                    os._exit(73)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):pass
    threading.Thread(target=boucle,daemon=True).start()
    return stop


class UsageV2(ctypes.Structure):
    # Darwin sys/resource.h rusage_info_v2, UUID then 18 uint64_t fields.
    _fields_=[('uuid',ctypes.c_uint8*16)]+[(n,ctypes.c_uint64) for n in (
        'user','system','idle','interrupt','pageins','wired','resident','footprint',
        'start','exit','child_user','child_system','child_idle','child_interrupt',
        'child_pageins','child_elapsed','disk_read','disk_written')]

def empreinte(pid):
    if platform.system()=='Darwin':
        lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
        usage=UsageV2()
        if lib.proc_pid_rusage(int(pid),2,ctypes.byref(usage))!=0:raise OSError(ctypes.get_errno(),'Mesure mémoire indisponible')
        return max(usage.footprint,usage.resident)
    return int(subprocess.check_output(['ps','-p',str(pid),'-o','rss='],stderr=subprocess.DEVNULL))*1024

def attendre(process,plafond,log):
    """Parent watchdog: independent of the model interpreter/GIL. Stop the child only."""
    pic=0
    while True:
        try:
            code=process.wait(timeout=.1)
            log.write(f'Pic mémoire mesuré par le superviseur : {pic/GIB:.2f} Gio\n');log.flush()
            return code
        except subprocess.TimeoutExpired:pass
        try:
            utilise=empreinte(process.pid);pic=max(pic,utilise)
            niveau=pression()
            systeme_en_danger=danger_systeme(niveau)
            danger=utilise>plafond or systeme_en_danger
            raison='pression macOS '+str(niveau) if systeme_en_danger else 'budget dépassé'
        except (OSError,ValueError,subprocess.SubprocessError):
            if process.poll() is not None:continue
            danger=True;raison='mesure mémoire indisponible'  # Fail closed.
        if danger:
            process.kill();process.wait()
            log.write(f'Protection mémoire externe : arrêt à {pic/GIB:.2f} Gio ; plafond {plafond/GIB:.2f} Gio ; {raison}.\n');log.flush()
            return 73
