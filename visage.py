#!/usr/bin/env python3
"""Contrôle « visage face caméra » d'un morceau de vidéo, pour un lipsync propre.
Pour chaque image : détection de visage de face (Haar OpenCV) ; un visage tourné de côté n'est pas détecté.
Sortie JSON : part des images avec un visage de face, et décalage maximal du centre du visage par rapport à la 1re image
(en part de la largeur du visage).
Usage (Python avec OpenCV, ex. .venv-portrait) : visage.py video.mp4 [debut_image fin_image]"""
import sys, json, cv2

def main():
    f = sys.argv[1]; a = int(sys.argv[2]) if len(sys.argv) > 2 else 0; z = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
    det = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(f); n, vus, ref, ecart, i = 0, 0, None, 0.0, -1
    while True:
        ok, img = cap.read(); i += 1
        if not ok or i >= z: break
        if i < a or (i - a) % 2: continue   # une image sur deux suffit
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY); h = g.shape[0]
        faces = det.detectMultiScale(g[: int(h * .6)], scaleFactor=1.1, minNeighbors=6, minSize=(g.shape[1] // 8,) * 2)
        n += 1
        if len(faces):
            x, y, w, hh = max(faces, key=lambda r: r[2] * r[3]); c = (x + w / 2, y + hh / 2)
            vus += 1; ref = ref or (c, w)
            ecart = max(ecart, abs(c[0] - ref[0][0]) / ref[1], abs(c[1] - ref[0][1]) / ref[1])
    print(json.dumps(dict(face=round(vus / max(n, 1), 3), decalage=round(ecart, 3), images=n)))

if __name__ == '__main__': main()
