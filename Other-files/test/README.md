# Offline tests run from this folder

Four offline regression modules for `Transport_all.py`, run with
`PYTHONPATH=../..` (see the root README):

- `test_instrument_safety_logic.py`
- `test_mfli_autorange.py`
- `test_mfli_overload.py`
- `test_stfmr_realtime_recording.py`

The standalone single-instrument scripts and the `.nitrace` protocol captures
that used to be here are kept unchanged on `main`; the modular branch carries
only the program and its tests (user, 2026-11-01).
