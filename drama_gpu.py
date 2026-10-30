"""Metal tuning for isolated Drama workers; never change the system GPU limits."""
import os
import platform


def preparer_environnement():
    """Must run before importing MLX: its Metal backend reads the flag at startup."""
    try:
        major = int(platform.mac_ver()[0].split('.')[0])
    except ValueError:
        major = 0
    if platform.system() == 'Darwin' and major >= 15:
        os.environ.setdefault('MLX_METAL_FAST_SYNCH', '1')


def configurer(mx, plafond):
    import memoire
    try:
        requested = int(os.environ.get('STUDIO_DRAMA_WIRED_MB', '0'))
    except ValueError:
        raise ValueError('STUDIO_DRAMA_WIRED_MB doit être un entier entre 0 et 512.')
    if not 0 <= requested <= 512:
        raise ValueError('STUDIO_DRAMA_WIRED_MB doit être entre 0 et 512.')
    limit = min(requested * 1024**2, plafond // 16,
                int(mx.device_info()['max_recommended_working_set_size']))
    # Residency competes with other applications for the same unified memory.
    if limit and (memoire.pression() >= 2 or memoire.disponible() < 4 * memoire.GIB + limit):
        limit = 0
    mx.set_wired_limit(limit)
    print(f"Metal : synchronisation rapide {os.environ.get('MLX_METAL_FAST_SYNCH','0')} ; résidence bornée {limit/1024**2:.0f} Mio", flush=True)
    return limit
