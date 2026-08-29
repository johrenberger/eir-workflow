from eir_runtime.conformance import adapter_conformance_errors
from eir_runtime.registry import available_adapters, create_adapter


def test_all_registered_adapters_conform_to_the_generic_objective_contract():
    assert {name: adapter_conformance_errors(create_adapter(name)) for name in available_adapters()} == {
        "technical-research": [],
        "test-automation": [],
    }
