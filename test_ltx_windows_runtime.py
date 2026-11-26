"""Opt-in real Windows mmap check; requires the pinned native LTX packages."""
import gc
import importlib.util
import sys
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform=='win32' and importlib.util.find_spec('ltx_core') is not None,
                     'Requires Windows and the native LTX runtime')
class WindowsLtxRuntimeTest(unittest.TestCase):
    def test_real_upstream_staging_buffer_without_posix_flags(self):
        from ltx_core.loader import buffers
        from lancer_visuel import adapter_mmap_ltx_windows
        runtime=Mock();runtime.cudaHostRegister.return_value=0
        with patch.object(buffers,'mmap',buffers.mmap),patch.object(buffers.torch.cuda,'cudart',return_value=runtime):
            with self.assertRaises(AttributeError):buffers.host_bytes(2**21,pin=True)
            adapter_mmap_ltx_windows()
            weight=buffers.host_bytes(2**21,pin=True)
            pointer=weight.data_ptr();weight[0]=20
            self.assertEqual(weight[0].item(),20)
            runtime.cudaHostRegister.assert_called_once_with(pointer,2**21,0)
            del weight;gc.collect()
            runtime.cudaHostUnregister.assert_called_once_with(pointer)


if __name__=='__main__':unittest.main()
