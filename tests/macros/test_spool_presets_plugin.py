"""Check the file handling of the Orca plugin, without OrcaSlicer.
Usage: python3 tests/macros/test_spool_presets_plugin.py"""
import importlib.util
import pathlib
import sys
import tempfile
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
fake = types.ModuleType("orca")
fake.pages = types.SimpleNamespace(PagesPluginCapabilityBase=object)
fake.base = object
fake.registered, fake.capabilities = [], []
fake.plugin = lambda cls: fake.registered.append(cls) or cls
fake.register_capability = fake.capabilities.append
sys.modules["orca"] = fake
spec = importlib.util.spec_from_file_location("plugin", ROOT / "slicer/orca/plugins/q2_spool_presets.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def test_url_ignores_the_port_scheme_of_the_host_field():
    assert plugin.spools_url("10.69.2.204") == "http://10.69.2.204/q2-spools/"
    assert plugin.spools_url("https://printer.lan/") == "https://printer.lan/q2-spools/"


def test_presets_are_installed_then_stale_ones_removed():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp)
        assert plugin.sync_files(target, {"hash": "a", "files": {"#1.json": "{}", "#2.json": "{}"}})
        assert plugin.sync_files(target, {"hash": "b", "files": {"#2.json": "{}"}})
        assert [p.name for p in (target / "filament").glob("*.json")] == ["#2.json"]
        assert (target / "bundle_metadata.json").exists()


def test_a_name_from_the_host_stays_in_the_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "bundle"
        plugin.sync_files(target, {"hash": "a", "files": {"../../evil.json": "{}"}})
        assert (target / "filament" / "evil.json").exists() and not (pathlib.Path(tmp) / "evil.json").exists()


def test_same_hash_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp)
        (target / plugin.STATE_FILE).write_text('{"hash": "a"}')
        assert plugin.sync_files(target, {"hash": "a", "files": {"#1.json": "{}"}}) is False


def test_plugin_registers_its_capability():
    fake.registered[0]().register_capabilities()
    assert fake.capabilities == [plugin.Q2BoxPage]


def test_a_failure_stays_on_the_page():
    def broken():
        raise OSError("no route to host")
    fake.host = types.SimpleNamespace(preset_bundle=broken)
    shown = plugin.Q2BoxPage().refresh()
    assert shown["gates"] == [] and "no route to host" in shown["status"]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d plugin tests passed" % len(tests))
