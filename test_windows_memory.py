"""Windows memory contracts and reserve protection without a Windows host."""
import ctypes
import io
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import memoire


class WindowsMemoryTest(unittest.TestCase):
    def test_reserve_is_enforced_without_macos_pressure_signal(self):
        for system in ('Windows','Linux'):
            with self.subTest(system=system),patch.object(memoire.platform,'system',return_value=system),patch.object(memoire,'pression',return_value=0),patch.object(memoire,'disponible',return_value=3*memoire.GIB):
                self.assertTrue(memoire.danger_systeme())
        with patch.object(memoire.platform,'system',return_value='Darwin'),patch.object(memoire,'disponible',return_value=3*memoire.GIB):
            self.assertFalse(memoire.danger_systeme(0))

    def test_global_memory_structure_and_winapi_buffer(self):
        def fill(pointer):
            status=pointer._obj
            self.assertEqual(status.length,64)
            status.total_phys=32*memoire.GIB;status.avail_phys=5*memoire.GIB
            return 1
        api=SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=Mock(side_effect=fill)))
        with patch.object(ctypes,'windll',api,create=True):
            result=memoire.memoire_windows()
        self.assertEqual(result.total_phys,32*memoire.GIB)
        self.assertEqual(result.avail_phys,5*memoire.GIB)

    def test_parent_watchdog_stops_its_child_when_windows_reserve_is_low(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'])
        try:
            with patch.object(memoire.platform,'system',return_value='Windows'),patch.object(memoire,'empreinte',return_value=1024),patch.object(memoire,'pression',return_value=0),patch.object(memoire,'disponible',return_value=3*memoire.GIB):
                log=io.StringIO();code=memoire.attendre(child,12*memoire.GIB,log)
            self.assertEqual(code,73)
            self.assertIn('réserve système',log.getvalue())
            self.assertIn('Windows',log.getvalue())
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:child.kill();child.wait()


if __name__=='__main__':unittest.main()
