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

    def test_unused_demodulators_disabled_without_touching_reference(self):
        controller = app.NonLocalACController.__new__(app.NonLocalACController)
        controller.lock = threading.RLock()
        controller.mfli_bridge = None
        controller.mfli_device = 'dev4414'
        controller.mfli_daq = Mock()
        controller.mfli_daq.getInt.return_value = 0
        for mode, indices in (('1', (1,2)), ('2', (1,2)), ('3', (1,2)), ('1+2', (2,)), ('1+2+3', ())):
            controller.mfli_config = {'extref_demodulator': 3}
            controller.mfli_daq.reset_mock()
            controller.disable_unused_ppms_demods(mode)
            self.assertEqual([c.args[0] for c in controller.mfli_daq.setInt.call_args_list],
                             [f'/dev4414/demods/{i}/enable' for i in indices])

    def test_compact_five_row_axes_stay_inside_canvas(self):
        panel = app.CombinedControlApp.__new__(app.CombinedControlApp)
        panel._draw_plot_grid = Mock()
        for height in (80, 95, 119, 150):
            canvas = Mock(ppms_compact_plot=True)
            canvas.winfo_width.return_value = 600
            canvas.winfo_height.return_value = height
            panel._draw_nonlocal_series(canvas, {'test': [(0., 0.), (1., 1.)]},
                                        'Magnetic field (T)', 'X voltage', 'waiting', show_legend=False)
            rect = canvas.create_rectangle.call_args.args
            self.assertEqual(rect[3], height - 44)
            for call in canvas.create_text.call_args_list:
                self.assertGreaterEqual(call.args[1], 0)
                self.assertLess(call.args[1], height)
            title = [c for c in canvas.create_text.call_args_list if c.kwargs.get('text') == 'Magnetic field (T)']
            self.assertEqual(title[0].args[1], height - 10)

    def test_dual_harmonic_config_preserves_pll(self):
        controller = app.NonLocalACController.__new__(app.NonLocalACController)
        controller.lock = threading.RLock()
        controller.mfli_config = dict(extref_demodulator=1, harmonic=1)
        controller.mfli_bridge = None
        controller.mfli_device = 'dev4414'
        nodes = {}
        controller.mfli_daq = Mock()
        controller.mfli_daq.setInt.side_effect = lambda key, value: nodes.update({key: value})
        controller.mfli_daq.getInt.side_effect = lambda key: nodes[key]
        controller.configure_second_harmonic(.1)
        self.assertEqual(nodes['/dev4414/demods/2/harmonic'], 2)
        self.assertTrue(all('/demods/2/' in key for key in nodes))
        controller.mfli_bridge = Mock()
        controller.configure_second_harmonic(.1)
        self.assertEqual(controller.mfli_bridge.request.call_args.args[0], 'configure_second_harmonic')
        controller.mfli_config['extref_demodulator'] = 0
        with self.assertRaises(RuntimeError):
            controller.configure_second_harmonic(.1)

    def test_third_harmonic_does_not_modify_reference(self):
        controller = app.NonLocalACController.__new__(app.NonLocalACController)
        controller.lock = threading.RLock()
        controller.mfli_config = dict(extref_demodulator=1, harmonic=1)
        controller.mfli_bridge = None
        controller.mfli_device = 'dev4414'
        nodes = {}
        controller.mfli_daq = Mock()
        controller.mfli_daq.setInt.side_effect = lambda key, value: nodes.update({key: value})
        controller.mfli_daq.getInt.side_effect = lambda key: nodes[key]
        controller.configure_third_harmonic(.1)
        self.assertEqual(nodes['/dev4414/demods/3/harmonic'], 3)
        self.assertTrue(all('/demods/3/' in key for key in nodes))
        controller.mfli_daq.getInt.return_value = 0
        controller.mfli_daq.getInt.side_effect = None
        with self.assertRaises(RuntimeError):
            controller.configure_third_harmonic(.1)
        controller.mfli_bridge = Mock()
        controller.configure_third_harmonic(.1)
        self.assertEqual(controller.mfli_bridge.request.call_args.args[0], 'configure_third_harmonic')

    def test_triple_demod_order_with_reference_on_four(self):
        controller = app.NonLocalACController.__new__(app.NonLocalACController)
        controller.lock = threading.RLock()
        controller.mfli_config = dict(extref_demodulator=3, harmonic=1)
        controller.mfli_bridge = None
        controller.mfli_device = 'dev4414'
        nodes = {}
        controller.mfli_daq = Mock()
        controller.mfli_daq.setInt.side_effect = lambda k, v: nodes.update({k: v})
        controller.mfli_daq.getInt.side_effect = lambda k: nodes[k]
        controller.configure_second_harmonic(.1)
        controller.configure_third_harmonic(.1)
        self.assertEqual(nodes['/dev4414/demods/1/harmonic'], 2)
        self.assertEqual(nodes['/dev4414/demods/2/harmonic'], 3)
        self.assertFalse(any('/demods/3/' in k for k in nodes))

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

    def test_four_demods_saved_independently_and_no_setting_writes(self):
        controller = app.NonLocalACController(lambda message: None)
        controller.mfli_props = {'options': 'MD'}      # four demodulators: MF-MD
        controller.mfli_device = 'dev4414'
        controller.mfli_daq = Mock()
        def sample(node):
            index = int(node.split('/')[3]) + 1
            return {'x': [index * 1e-6], 'y': [-index * 2e-6], 'frequency': [index * 317.3], 'timestamp': [100 + index]}
        controller.mfli_daq.getSample.side_effect = sample
        controller.mfli_daq.getInt.side_effect = lambda node: 1
        result = controller.read_mfli_four_demods()
        self.assertEqual(len(result), 40)
        for i in range(1, 5):
            self.assertAlmostEqual(result[f'zurich_demod{i}_x_v'], i * 1e-6)
            self.assertAlmostEqual(result[f'zurich_demod{i}_frequency_hz'], i * 317.3)
        controller.mfli_daq.setInt.assert_not_called()
        controller.mfli_daq.getInt.side_effect = lambda node: 0 if '/demods/2/enable' in node else 1
        controller.mfli_daq.getSample.reset_mock()
        disabled = controller.read_mfli_four_demods()
        self.assertEqual(disabled.keys(), result.keys())
        self.assertEqual(disabled['zurich_demod3_status'], 'disabled')
        self.assertEqual(disabled['zurich_demod3_x_v'], '')
        self.assertEqual(disabled['zurich_demod3_enabled'], 0)
        self.assertEqual(controller.mfli_daq.getSample.call_count, 3)
        self.assertEqual(disabled['zurich_demod4_x_v'], result['zurich_demod4_x_v'])
        controller.mfli_daq.getSample.side_effect = RuntimeError('communication failed')
        with self.assertRaisesRegex(RuntimeError, 'communication failed'):
            controller.read_mfli_four_demods()

    def test_legacy_bridge_skips_disabled_demod4_and_keeps_fixed_csv_columns(self):
        block = app._MFLI_BRIDGE_SOURCE.split('        elif command == "read_demods":', 1)[1].split('        elif command == "autorange":', 1)[0]
        daq, emit = Mock(), Mock()
        daq.getInt.side_effect = lambda node: 0 if '/demods/3/enable' in node else 1
        daq.getSample.return_value = dict(x=1e-6, y=2e-6, frequency=317.3, timestamp=42)
        exec(textwrap.dedent(block), dict(daq=daq, device='dev4414', emit=emit, request={},
            scalar=lambda sample, key, required=True: sample.get(key)))
        channels = emit.call_args.args[0]['demods']
        self.assertEqual(len(channels), 4)
        self.assertEqual(channels[3], {'enabled': 0})
        self.assertEqual(daq.getSample.call_count, 3)
        controller = app.NonLocalACController(lambda _: None)
        controller.mfli_bridge = Mock()
        controller.mfli_bridge.request.return_value = {'demods': channels}
        controller.mfli_props = {'options': 'MD'}      # four demodulators: MF-MD
        row = controller.read_mfli_four_demods()
        self.assertEqual(row['zurich_demod4_status'], 'disabled')
        self.assertEqual(row['zurich_demod4_frequency_hz'], '')
        self.assertEqual(row['zurich_demod1_x_v'], 1e-6)

    def test_reused_autorange_overload_low_signal_and_retry_limit(self):
        controller = app.NonLocalACController(lambda _: None)
        controller.read_mfli = Mock(return_value={'input_overload': True,
            'input_extrema_valid': True, 'input_utilization': .95})
        controller._run_mfli_autorange = Mock(return_value='RANGE')
        controller.mfli_config = {'input_range_v': .1}
        result = controller.read_stfmr_mfli(317.3, auto_range=True)
        self.assertEqual(result['auto_range'], 'RANGE')
        with self.assertRaisesRegex(RuntimeError, '3 retries'):
            controller.read_stfmr_mfli(317.3, auto_range=True, attempts=3)
        controller._run_mfli_autorange.reset_mock()
        controller.mfli_range_cooldown = 0
        controller.mfli_low_range_count = 0
        # 10 % of the range is not low any more (under 1 %; user, 2026-11-16).
        controller.read_mfli.return_value = {'input_overload': False,
            'input_extrema_valid': True, 'input_utilization': .1}
        for _ in range(6):
            controller.read_stfmr_mfli(317.3, auto_range=True)
        controller._run_mfli_autorange.assert_not_called()
        controller.read_mfli.return_value = {'input_overload': False,
            'input_extrema_valid': True, 'input_utilization': .005}
        for _ in range(2):
            controller.read_stfmr_mfli(317.3, auto_range=True)
            controller._run_mfli_autorange.assert_not_called()
        controller.read_stfmr_mfli(317.3, auto_range=True)
        controller._run_mfli_autorange.assert_called_once_with('low')

if __name__ == '__main__': unittest.main()
