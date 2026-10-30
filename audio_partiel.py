"""Atomic, independently playable snapshots of decoded mono float32 audio."""
import os
from pathlib import Path
import struct


def chemin(sortie):
    sortie=Path(sortie)
    return sortie.with_name(sortie.stem+'-partiel.wav')


def sauver(sortie, pcm, sample_rate):
    if not isinstance(sample_rate,int) or not 0<sample_rate<=384000 or len(pcm)%4:
        raise ValueError('Audio partiel invalide.')
    if not pcm:return
    if len(pcm)>2**32-49:raise ValueError('Audio partiel trop volumineux pour WAV.')
    cible=chemin(sortie);tmp=cible.with_suffix('.tmp.wav')
    # IEEE float32 WAV, including the fact chunk required for non-PCM formats.
    header=(b'RIFF'+struct.pack('<I',len(pcm)+48)+b'WAVEfmt '+
            struct.pack('<IHHIIHH',16,3,1,sample_rate,sample_rate*4,4,32)+
            b'fact'+struct.pack('<II',4,len(pcm)//4)+b'data'+struct.pack('<I',len(pcm)))
    with tmp.open('wb') as stream:
        stream.write(header);stream.write(pcm);stream.flush();os.fsync(stream.fileno())
    tmp.replace(cible)
