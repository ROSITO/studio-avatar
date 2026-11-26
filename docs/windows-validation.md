# État de validation Windows — 26 novembre 2026

**Le dépôt ne dispose pas encore d'une validation complète sur Windows réel.**
L'audit de `main` à partir de `d830830` a retrouvé des défauts que les tests précédents
ne détectaient pas. Les correctifs de cet audit ne constituent pas une certification
d'installation ou d'inférence sous Windows.

Trois revues indépendantes ont porté sur l'installation, les moteurs et les parcours
UI/médias. Les vérifications ci-dessous ont été exécutées depuis macOS, sauf indication
contraire. Un test qui simule une API Windows n'est pas une exécution de cette API.

## Matrice des contrôles

| Point | Preuve disponible | À valider sous Windows réel |
|---|---|---|
| Python 3.12/3.13 x64 | Versions/wheels vérifiés ; choix standard x64 ; refus du mélange de versions dans un venv ; désactivation de l'auto-install par le launcher `py` | Découverte dans les installations locales et lancement par CMD/PowerShell 5.1 |
| Python, FFmpeg, Visual C++ | URL accessibles, trois téléchargements complets et SHA-256 vérifiés ; registre 64 bits/version minimale revus ; réparation FFmpeg testée avec fixtures et exécutables macOS | Exécution des `.exe`, élévation UAC, registre et PATH Windows |
| Scripts PowerShell | Analyse syntaxique et tests exécutés avec PowerShell 7.7 sur macOS | Windows PowerShell 5.1, double-clic, Ctrl+C et console |
| Dépendances des quatre moteurs | Résolution Windows x64 pour Python 3.12/3.13 et disponibilité des roues, dont CUDA 12.8 ; sources LTX épinglées et SoX Python identifiées | Installation/import des DLL et packages sur Windows |
| Qwen/OmniVoice | Imports réels sous macOS ; contrat référence/transcription/sortie testé ; liens symboliques évités sous Windows | Première synthèse CPU et CUDA avec les vrais poids et une référence |
| LTX | Deux parseurs CLI officiels du SHA épinglé exercés ; défaut `mmap` Windows reproduit et adaptation testée avec le vrai chargeur, en simulant le runtime CUDA | Allocation CUDA réelle sous Windows, chargement des poids, clip, transition et vidéo parlante |
| FLUX | Import réel sous macOS ; contrats de références, graines, offload, sorties et nettoyage après arrêt testés | Inférence Windows, qualité et pic mémoire avec les vrais poids |
| Choix du GPU | Matrices de RAM/VRAM/architecture et plusieurs cartes CUDA testées ; allocation sur la carte choisie | Pilote et GPU de la machine cible ; le mode affiché dans le catalogue reste une proposition matérielle |
| Photos et médias | Import HTTP réel, JPG/PNG, noms réservés/Unicode, collisions de casse simulées, non-écrasement et FFmpeg testés | NTFS réel et chemins de l'installation cible |
| Projets, montage et reprise | Montage/aperçu FFmpeg réels ; fichiers absents, sauvegarde atomique, annulation au redémarrage et refus MuseTalk avant calcul testés | Interruption par fermeture de console ou arrêt Windows et reprise |
| Contrôle du visage | OpenCV 4.13 intégré au runtime LTX ; préflight avant calcul ; erreurs distinctes d'une image sans visage | Exécution dans le runtime Windows installé et sur les rushs réels |
| Mémoire | Contrats des structures/API Windows revus ; réserve Windows et watchdog testés par simulation, dont arrêt d'un véritable processus enfant | Mesure des API Win32 et comportement sous pression mémoire réelle |
| Secrets et données privées | Gitleaks sur le contenu et l'historique ; barrière de publication et exclusions des états temporaires | Ne remplace pas la gestion privée des tokens et médias sur chaque machine |

## Défauts corrigés par cet audit

- OmniVoice ne nécessite plus de privilège de création de liens symboliques sous Windows.
- Le chargeur LTX épinglé n'utilise plus les flags `mmap` POSIX dans son adaptation Windows.
- Les workers sélectionnent une carte CUDA visible admissible ; le plafond concerne cette carte.
- L'installation CPU explicite n'entraîne plus l'installation des moteurs CUDA.
- Python/venv, marqueurs de succès, FFmpeg et Visual C++ sont vérifiés plus strictement.
- Les modèles incomplets ne sont plus déclarés installés quand des configurations ou
  des shards nécessaires au chargeur manquent.
- Les imports ne remplacent plus une photo existante ; les références existantes gardent
  leur nom exact. Les noms masqués et réservés sont pris en charge.
- Les dépendances MuseTalk sont contrôlées avant mise en file ; les médias manquants sont
  régénérés lors de la reprise. Les exports a2v/aperçus CPU restent disponibles.
- L'état des tâches est écrit atomiquement, les annulations sont conservées et les
  fichiers temporaires privés restent exclus de Git.
- La réserve système est surveillée pendant le calcul Windows, même sans signal de
  pression macOS. Un échec OpenCV ne déclenche plus trois rendus inutiles.

## Limites de support

- EliteBook x64, 32 Go RAM et environ 4 Go VRAM : voix CPU proposées ; LTX/FLUX refusés.
- Les seuils de l'application sont des règles prudentes, pas des minima universels ni
  une garantie de performance : NVIDIA Ampere+, pilote 570+, RAM nominale 32 Go,
  VRAM nominale 8 Go pour LTX ou 12 Go pour FLUX. Les petites réservations matérielles
  sont prises en compte.
- FLUX conserve environ 14,9 Gio de poids côté CPU : la marge sous le budget visuel
  par défaut sur une machine de 32 Go n'a pas été mesurée en inférence réelle.
- Wan-Animate/MPS et l'adaptateur MuseTalk restent des intégrations Mac. RVC demande
  un runtime et des voix entraînées externes ; son inférence Windows n'est pas validée.
- Les contrôles du catalogue distinguent compatibilité matérielle et présence des poids ;
  ils ne prouvent ni l'installation du runtime ni un rendu réussi.

## Blocage de validation Windows

GitHub refuse le lancement des workflows avec : `Actions has been disabled for this user`.
Aucun résultat Windows natif n'était disponible pour le commit audité. Les workflows
incluent désormais le vrai bootstrap dans un chemin avec espaces, les imports des
runtimes et un contrôle du buffer LTX sur Windows sans matériel CUDA. Ils devront
réussir après rétablissement d'Actions ; les rendus GPU resteront un essai séparé.

## Reproduire les contrôles locaux

```sh
python -m unittest discover -p 'test_*.py'
node test_plateforme.js
node test_modeles.js
node test_import_photo.js
node test_progression.js
node test_balises.js
node test_voix_lot.js
python tools/check_publication.py
gitleaks git . --redact
gitleaks dir . --redact
```

Les tests marqués ignorés ne sont pas des validations. Sur Windows avec le runtime LTX
installé : `python -m unittest test_ltx_windows_runtime -v` teste le mapping réel avec
l'enregistrement CUDA simulé ; cela ne valide pas un calcul GPU.

Sources des contrats : [symlinks Python](https://docs.python.org/3.13/library/os.html#os.symlink),
[mmap Python](https://docs.python.org/3.13/library/mmap.html),
[chargeur LTX épinglé](https://github.com/Lightricks/LTX-2/blob/daa6b16fc7f0f1628f2c9e36a303e3312b333cc6/packages/ltx-core/src/ltx_core/loader/buffers.py),
[Visual C++](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist),
[mémoire processus Win32](https://learn.microsoft.com/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo).
