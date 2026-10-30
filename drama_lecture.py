"""Bounded expert reads without mapping entire weight banks into process memory."""
import os


class LectureDirecte:
    """Keep file descriptors, never model-sized mappings or resident weight caches."""
    def __init__(self):
        self.fichiers = {}

    def close(self):
        for fd in self.fichiers.values():
            os.close(fd)
        self.fichiers.clear()

    def __del__(self):
        self.close()

    def __call__(self, description, indices):
        import numpy as np
        fichier, dtype, offset, shape = description
        indices = np.asarray(indices, dtype=np.int64)
        if indices.ndim != 1 or np.any(indices < 0) or np.any(indices >= shape[0]):
            raise ValueError('Indices experts hors banque.')
        output = np.empty((len(indices), *shape[1:]), dtype=dtype)
        if not len(indices):
            return output
        key = os.fspath(fichier)
        if key not in self.fichiers:
            self.fichiers[key] = os.open(key, os.O_RDONLY)
        fd = self.fichiers[key]
        row_bytes = output[0].nbytes
        target = memoryview(output).cast('B')
        begin = 0
        while begin < len(indices):
            end = begin + 1
            while end < len(indices) and indices[end] == indices[end - 1] + 1:
                end += 1
            view = target[begin * row_bytes:end * row_bytes]
            position = offset + int(indices[begin]) * row_bytes
            done = 0
            while done < len(view):
                if hasattr(os, 'preadv'):
                    count = os.preadv(fd, [view[done:]], position + done)
                else:
                    # Positional read: no shared mutable file cursor.
                    data = os.pread(fd, len(view) - done, position + done)
                    count = len(data)
                    view[done:done + count] = data
                if count == 0:
                    raise EOFError('Fichier de poids incomplet pendant la lecture des experts.')
                done += count
            begin = end
        return output
