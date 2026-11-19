# Conversion voix vers voix

Dans **Mes voix → Remplacer une voix**, importez un audio ou une vidéo, sélectionnez une voix RVC entraînée puis lancez la conversion. Le travail utilise la file commune et peut être annulé. Les vidéos conservent leur piste image sans réencodage. L’audio converti reste disponible pour les projets.

Le moteur conserve les paroles et la hauteur de la source par défaut. Le réglage avancé permet une transposition de −12 à +12 demi-tons. Ce procédé remplace aussi les autres sons présents dans la piste : privilégiez une voix isolée sans musique. La limite est de dix minutes par extrait.

## Configuration locale

Installer séparément le runtime [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) et ses dépendances dans son `.venv`. Le worker utilise `infer/cli.py` (interface actuelle) et RMVPE. Déclarer les modèles personnels dans `voix/conversion.json`, ignoré par Git :

```json
{
  "runtime": "/chemin/vers/rvc",
  "modeles": [{
    "id": "ma-voix",
    "nom": "Ma voix · RVC",
    "poids": "/disque-externe/ma-voix.pth",
    "index": "/disque-externe/ma-voix.index"
  }]
}
```

Les composants HuBERT et RMVPE doivent également être installés dans le runtime. Les poids et index restent sur leur disque, sans copie par Studio Avatar. Un disque déconnecté désactive le modèle. L’entraînement n’est pas exposé dans cette interface.

Le sous-processus est supervisé avec un plafond de 12 Gio, en complément du contrôle de disponibilité mémoire et de pression système. Les modèles personnels, corpus, chemins privés et médias ne sont pas distribués dans le dépôt.
