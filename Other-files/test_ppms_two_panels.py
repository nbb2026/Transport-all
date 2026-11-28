"""PPMS2 isolation and Zurich lifecycle without Tk or physical devices."""
import threading
import textwrap
import types
import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from test_ppms_motor_debug import app


class Var:
    def __init__(self, value=None, **kwargs): self.value = value
    def get(self): return self.value
    def set(self, value): self.value = value


class ImmediateExecutor:
    def __init__(self, **kwargs): pass
    def submit(self, fn, *args):
        result = Future()
        try: result.set_result(fn(*args))
        except BaseException as error: result.set_exception(error)
        return result
    def shutdown(self, **kwargs): pass


class TwoPanelTests(unittest.TestCase):

    def test_legacy_reference_controller_follows_demod_four(self):
        block = app._MFLI_BRIDGE_SOURCE.split('            if extref_demod == 3:', 1)[1].split('            configured_extref_demod = extref_demod', 1)[0]
        code = textwrap.dedent('            if extref_demod == 3:' + block)
        daq = Mock()
        daq.getInt.side_effect = lambda node: 1 if '/extrefs/0/' in node else 3
        env = dict(EXTREF=0, extref_demod=3, daq=daq, device='dev4414')
        exec(code, env)
        self.assertEqual(env['EXTREF'], 1)
        daq.setInt.assert_called_once_with('/dev4414/extrefs/0/enable', 0)
        env['extref_demod'] = 1
        daq.reset_mock()
        exec(code, env)
        self.assertEqual(env['EXTREF'], 0)
        daq.setInt.assert_called_once_with('/dev4414/extrefs/1/enable', 0)
        env['extref_demod'] = 3
        daq.getInt.side_effect = lambda node: 1
        with self.assertRaises(RuntimeError):
            exec(code, env)

    def make_panel(self):
        parent = app.CombinedControlApp.__new__(app.CombinedControlApp)
        parent.root = Mock()
        parent.closing = False
        parent.ui_queue = Mock()
        parent.post_ui = lambda callback: callback()
        parent.thread_log = Mock()
        controller = Mock(lock=threading.RLock(), mfli_connected=False)
        def connect(device):
            controller.mfli_connected = True
        def disconnect():
            controller.mfli_connected = False
        def build(panel):
            panel.ppms_instruments_frame = Mock()
            panel.ppms_settings_panel = Mock()
            panel.ppms_plot_frame = Mock()
        controller.connect_mfli.side_effect = connect
        controller.disconnect_mfli.side_effect = disconnect
        controller.read_stfmr_mfli.side_effect = lambda frequency, **kwargs: controller.read_mfli(frequency)
        with patch.object(app.tk, 'StringVar', Var), patch.object(app.tk, 'IntVar', Var), \
             patch.object(app.tk, 'BooleanVar', Var), patch.object(app, 'ThreadPoolExecutor', ImmediateExecutor), \
             patch.object(app, 'NonLocalACController', return_value=controller), \
             patch.object(app.CombinedControlApp, 'build_ppms_ui', build), \
             patch.object(app.PPMS2Panel, '_redraw_ppms_transport_plot'), \
             patch.object(app.tk, 'Canvas'), patch.object(app.ttk, 'Frame'), patch.object(app.ttk, 'Checkbutton'), \
             patch.object(app.ttk, 'LabelFrame'), patch.object(app.ttk, 'Label'), \
             patch.object(app.ttk, 'Entry'), patch.object(app.ttk, 'Combobox'), patch.object(app.ttk, 'Button'):
            parent._initialize_ppms_state()
            panel = app.PPMS2Panel(parent, Mock())
        panel.post_ui = lambda callback: callback()
        return parent, panel, controller

if __name__ == '__main__': unittest.main()
