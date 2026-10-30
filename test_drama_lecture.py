"""Exact reads, truncated files, short syscalls and bounded descriptor reuse."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util

@unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy required')
class LectureTest(unittest.TestCase):
    def test_indices_offsets_types_et_descripteurs(self):
        import numpy as np
        from drama_lecture import LectureDirecte
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bank'
            for dtype in ('uint32','uint16','float32','float16'):
                data=np.arange(16*8*4,dtype=dtype).reshape(16,8,4)
                p.write_bytes(b'header!'+data.tobytes())
                read=LectureDirecte()
                try:
                    for indices in ([1,2,3,7],[7,2,7],[],[15]):
                        result=read((p,dtype,7,data.shape),indices)
                        np.testing.assert_array_equal(result,data[list(indices)])
                    self.assertEqual(len(read.fichiers),1)
                    with self.assertRaises(ValueError):read((p,dtype,7,data.shape),[16])
                    with self.assertRaises(EOFError):read((p,dtype,8,data.shape),[15])
                finally:read.close()
                self.assertFalse(read.fichiers)

    def test_lectures_courtes_et_fallback(self):
        import numpy as np
        from drama_lecture import LectureDirecte
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bank';data=np.arange(64,dtype='uint32').reshape(8,8);p.write_bytes(data.tobytes())
            read=LectureDirecte();original=os.preadv
            def short(fd, buffers, offset):return original(fd,[buffers[0][:7]],offset)
            try:
                with patch('os.preadv',side_effect=short):
                    np.testing.assert_array_equal(read((p,'uint32',0,data.shape),[1,2,5]),data[[1,2,5]])
                with patch('drama_lecture.hasattr',return_value=False,create=True):
                    np.testing.assert_array_equal(read((p,'uint32',0,data.shape),[3,4]),data[[3,4]])
            finally:read.close()
